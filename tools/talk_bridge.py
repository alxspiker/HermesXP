"""Loopback-only Windows Live Messenger RTP <-> Hermes Talk PCM bridge.

The MSN Node process owns SIP, RTP and its paired XP address. This process runs
inside the *Hermes CLI plugin host*, so Talk's existing provider/auth/tool
registrations are reused. No voice model, token extraction, or legacy ASR/TTS
code is implemented here.

Wire frames: uint32 big-endian payload length (including type), ASCII type,
payload. H=JSON token handshake, I=24kHz PCM16 from Messenger, O=24kHz PCM16
    from Talk, R=ready, D=clear queued playback, X=error; only one authenticated local call at a time.
"""
from __future__ import annotations

import argparse
import asyncio
import hmac
import json
import logging
import math
import os
import queue
import shutil
import signal
import socket
import struct
import subprocess
import threading
import time
from array import array
from dataclasses import dataclass
from typing import ClassVar

LOG = logging.getLogger("hermesxp.talk")
PORT = 18771
MAX_FRAME = 256 * 1024
MAX_INPUT_QUEUE = 128
SAMPLE_RATE = 24_000
PCM_BYTES_PER_SECOND = SAMPLE_RATE * 2
FRAME_BYTES = 960  # 20 ms of 24 kHz mono PCM16; maps to one PCMU/8000 RTP packet
MAX_PLAYBACK_BYTES = PCM_BYTES_PER_SECOND * 20
PLAYBACK_PREROLL_FRAMES = 4
# Node starts RTP playout with 800ms buffered. The XP speakers can still be
# audible after our output queue has drained, so keep the microphone echo
# gate active over that last physical playback window.
ECHO_OUTPUT_HOLD_S = 1.1
MAX_TOOL_PROMPT = 4000
MAX_TOOL_OUTPUT = 5000
MAX_TOOL_CALLS = 12
HERMES_TOOL_TIMEOUT = 180
MAX_TALK_RECONNECTS = 3


class HermesVoiceExecution:
    """HermesXP-only foreground Hermes action, not Talk's delegation agent.

    This is NOT a forged Hermes gateway capability. It uses the same local
    Hermes CLI that an authorized operator can run at the server, with no
    shell expansion, and remains subject to that CLI's configured tool
    availability, credentials, and approval policy. The MSN peer is verified
    by the paired native SIP call and the loopback token prior to creation.
    """

    def __init__(self):
        # Only this explicitly enabled, authenticated HermesXP transport
        # may advertise its foreground Hermes action as a host attachment.
        # Talk's ordinary unknown-host-tool deny policy stays unchanged.
        self.hermesxp_authenticated_voice_action = True
        self.closed = False
        self.calls = 0
        self._issued = {}
        self._lock = threading.Lock()
        self._process_lock = threading.Lock()
        self._run_lock = threading.Lock()
        self._process = None

    def tool_definitions(self):
        return (
            {
                "name": "hermes_execute",
                "description": (
                    "Execute the user's request immediately with the Hermes "
                    "agent and its real configured tools, and return the "
                    "result for speech. Do NOT explain delegation or suggest "
                    "switching agents. Use this for terminal, file, browser, "
                    "screen and other real actions. The host owns its normal "
                    "approval and tool permissions; report refusals accurately."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "request": {"type": "string", "description":
                                    "The user's concrete action or information request."}
                    },
                    "required": ["request"],
                    "additionalProperties": False,
                },
            },
        )

    def mint_tool_call_permit(self, **kwargs):
        name = kwargs.get("tool_name")
        args = kwargs.get("arguments")
        call_id = kwargs.get("call_id")
        if self.closed or name != "hermes_execute":
            raise ValueError("HermesXP voice tool not authorized")
        if not isinstance(call_id, str) or not call_id or not isinstance(args, dict):
            raise ValueError("invalid HermesXP tool call")
        with self._lock:
            if self.calls >= MAX_TOOL_CALLS:
                raise ValueError("HermesXP voice command limit reached")
            self.calls += 1
            permit = object()
            self._issued[id(permit)] = (permit, call_id, name, dict(args))
            return permit

    async def execute_tool_batch(self, permits):
        from asyncio import to_thread
        results = []
        for permit in permits:
            with self._lock:
                issued = self._issued.pop(id(permit), None)
            if issued is None or issued[0] is not permit or self.closed:
                raise ValueError("Expired or invalid HermesXP voice permit")
            _, call_id, name, args = issued
            output = await to_thread(self._run_hermes, args.get("request"))
            results.append({"call_id": call_id, "output": output[:MAX_TOOL_OUTPUT],
                            "receipt_id": f"hermesxp-{self.calls}-{call_id}"})
        return tuple(results)

    def _run_hermes(self, request):
        if not isinstance(request, str) or not request.strip():
            return "Hermes needs a concrete request."
        if len(request) > MAX_TOOL_PROMPT:
            return "That request is too long for one voice action. Please shorten it."
        executable = (
            os.environ.get("HERMES_XP_TALK_HERMES_BINARY")
            or shutil.which("hermes")
            or str(os.path.expanduser("~/.local/bin/hermes"))
        )
        if not os.path.isfile(executable) or not os.access(executable, os.X_OK):
            return "Hermes command is not installed on the server."
        context = (
            "You are Hermes acting on the operator's request made through "
            "HermesXP Windows Live Messenger on the paired Windows XP machine. "
            "Perform the action yourself using your available configured tools. "
            "Do not delegate or launch a subagent. Do not claim an action "
            "succeeded unless verified. Report results or refusals in 1-3 "
            "short sentences suitable for speech. For computer control "
            "requests about XP, target the paired Windows XP computer, not "
            "the Hermes server.\n\nOperator request: " + request.strip()
        )
        with self._run_lock:
            if self.closed:
                return "The HermesXP call ended before the command started."
            try:
                process = subprocess.Popen(
                    [executable, "-z", context], shell=False,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True, cwd=os.path.expanduser("~"),
                    start_new_session=True,
                )
            except (OSError, ValueError) as exc:
                LOG.warning("HermesXP voice command could not start (%s)", type(exc).__name__)
                return "The Hermes agent could not start this action."
            with self._process_lock:
                self._process = process
                cancelled = self.closed
            if cancelled:
                self._terminate(process)
            try:
                stdout, _stderr = process.communicate(timeout=HERMES_TOOL_TIMEOUT)
            except subprocess.TimeoutExpired:
                self._terminate(process)
                try:
                    process.communicate(timeout=2)
                except subprocess.TimeoutExpired:
                    self._kill(process)
                    process.communicate()
                return "Hermes did not finish that action before the three-minute limit."
            except OSError:
                self._terminate(process)
                return "The Hermes agent was interrupted."
            finally:
                with self._process_lock:
                    if self._process is process:
                        self._process = None
        if self.closed:
            return "The HermesXP call ended before Hermes finished."
        body = (stdout or "").strip()
        if process.returncode != 0:
            # stderr often contains credentials or sensitive host details;
            # do not feed it back into the voice model.
            LOG.warning("HermesXP voice command failed (status=%s)", process.returncode)
            return ("Hermes returned an error executing that action. " +
                    (body[-1500:] if body else "No result was available."))
        return body[-MAX_TOOL_OUTPUT:] or "Hermes finished without returning any result."

    @staticmethod
    def _terminate(process):
        try:
            if process.poll() is not None:
                return
            if hasattr(os, "killpg"):
                os.killpg(process.pid, signal.SIGTERM)
            else:
                process.terminate()
        except (ProcessLookupError, PermissionError, OSError):
            pass

    @staticmethod
    def _kill(process):
        try:
            if process.poll() is not None:
                return
            if hasattr(os, "killpg"):
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
        except (ProcessLookupError, PermissionError, OSError):
            pass

    def close(self):
        self.closed = True
        with self._lock:
            self._issued.clear()
        with self._process_lock:
            process = self._process
        if process is not None:
            self._terminate(process)


def rms(pcm: bytes) -> float:
    if not pcm or len(pcm) & 1:
        return 0.0
    data = array("h")
    data.frombytes(pcm)
    if struct.pack("=H", 1) != b"\x01\0":
        data.byteswap()
    return min(1.0, math.sqrt(sum(v * v for v in data) / len(data)) / 32768)


def frame(kind: bytes, data: bytes = b"") -> bytes:
    if len(kind) != 1 or len(data) + 1 > MAX_FRAME:
        raise ValueError("invalid Talk frame")
    return struct.pack(">I", len(data) + 1) + kind + data


def receive(sock: socket.socket) -> tuple[bytes, bytes]:
    def read_exact(length):
        parts = bytearray()
        while len(parts) < length:
            block = sock.recv(length - len(parts))
            if not block:
                raise ConnectionError("HermesXP call disconnected")
            parts.extend(block)
        return bytes(parts)

    size = struct.unpack(">I", read_exact(4))[0]
    if not 1 <= size <= MAX_FRAME:
        raise ValueError("invalid Talk frame size")
    data = read_exact(size)
    return data[:1], data[1:]


@dataclass(frozen=True)
class PlaybackProgress:
    consumed_bytes: int
    discarded_bytes: int
    pending: bool


class SocketAudio:
    """Duck-type Talk's DuplexAudio without using any physical server devices."""

    _startup_lock: ClassVar[threading.Lock] = threading.Lock()

    def __init__(self, connection: socket.socket, *, disconnected=None):
        self.connection = connection
        self.disconnected = disconnected
        self.input = queue.Queue(maxsize=MAX_INPUT_QUEUE)
        # Talk providers often synthesize multiple seconds of audio in a
        # fraction of a second. Frame it here and send at REAL playback speed
        # instead of flooding Messenger's 2s jitter buffer.
        self.output = queue.Queue(maxsize=MAX_PLAYBACK_BYTES // FRAME_BYTES + 1)
        self.lock = threading.Lock()
        self.active = threading.Event()
        self.paused = False
        self.consumed = 0
        self.discarded = 0
        self.played_bytes = 0
        self.queued_bytes = 0
        self.item_id = None
        self.output_generation = 0
        self.output_level = 0.0
        self.output_at = 0.0
        self.echo_gate = os.environ.get("TALK_ECHO_GATE", "").strip().lower() not in {
            "0", "off", "false", "no", "disabled"
        }
        # The XP sound card's microphone is physically close to its speaker.
        # Favor ignoring playback leakage while leaving room for a clearly
        # louder human interruption. Talk remains responsible for VAD itself.
        self.echo_threshold = 0.12
        self.echo_ratio = 1.8
        self.suppressed_frames = 0
        self.input_dropped_frames = 0
        self.write_lock = threading.Lock()
        self.threads = []

    def send(self, kind, payload=b""):
        with self.write_lock:
            self.connection.sendall(frame(kind, payload))

    def start(self):
        if self.active.is_set():
            # A transient Realtime session reconnect must reuse the one
            # authenticated MSN TCP/audio transport. Never start another pair
            # of reader/writer threads, or playback will race and stutter.
            self.send(b"R")
            return
        self.active.set()
        self.connection.settimeout(None)
        for target in (self._read, self._write):
            thread = threading.Thread(target=target, daemon=True)
            thread.start()
            self.threads.append(thread)
        self.send(b"R")

    def stop(self):
        self.active.clear()
        try:
            self.connection.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.connection.close()
        for thread in self.threads:
            if thread is not threading.current_thread():
                thread.join(timeout=1)


    def _read(self):
        try:
            while self.active.is_set():
                kind, data = receive(self.connection)
                if kind != b"I" or not data or len(data) % 2:
                    raise ValueError("invalid messenger audio frame")
                with self.lock:
                    paused = self.paused
                    playing = self.queued_bytes > 0 or (
                        time.monotonic() - self.output_at < ECHO_OUTPUT_HOLD_S
                    )
                    echo_level = self.output_level
                if paused:
                    continue
                if self.echo_gate and playing and rms(data) < max(
                    self.echo_threshold, echo_level * self.echo_ratio
                ):
                    # Substitute silence rather than skipping the frame.
                    # Realtime VAD needs continuous sample timing: deleting
                    # microphone frames can create spurious turn boundaries.
                    data = bytes(len(data))
                    self.suppressed_frames += 1
                try:
                    self.input.put_nowait(data)
                except queue.Full:
                    self.input_dropped_frames += 1
                    # Realtime must prefer recent microphone samples to stale
                    # speech. Never block the network thread on a full queue.
                    try:
                        self.input.get_nowait()
                    except queue.Empty:
                        pass
                    self.input.put_nowait(data)
        except (ConnectionError, OSError, ValueError):
            pass
        finally:
            self.active.clear()
            if self.disconnected is not None:
                self.disconnected()

    def _write(self):
        packet_index = 0
        started_at = None
        try:
            while self.active.is_set():
                try:
                    generation, item_id, data = self.output.get(timeout=0.1)
                except queue.Empty:
                    packet_index = 0
                    started_at = None
                    continue
                if started_at is None:
                    started_at = time.monotonic()
                deadline = started_at + max(
                    0, packet_index - PLAYBACK_PREROLL_FRAMES + 1
                ) * 0.02
                while self.active.is_set() and time.monotonic() < deadline:
                    time.sleep(min(0.005, deadline - time.monotonic()))
                # When the process stalls, don't emit old audio at an
                # unbounded catch-up rate. Re-align to the current clock.
                if time.monotonic() - deadline > 0.1:
                    started_at = time.monotonic() - max(
                        0, packet_index - PLAYBACK_PREROLL_FRAMES + 1
                    ) * 0.02
                with self.lock:
                    if generation != self.output_generation:
                        # A Talk cancellation invalidated this in-flight
                        # packet. D flushes any already transmitted packets.
                        self.queued_bytes -= len(data)
                        self.discarded += len(data)
                        packet_index = 0
                        started_at = None
                        continue
                    self.queued_bytes -= len(data)
                self.send(b"O", data)
                with self.lock:
                    if item_id != self.item_id:
                        self.item_id = item_id
                        self.played_bytes = 0
                    self.played_bytes += len(data)
                    self.consumed += len(data)
                    self.output_level = rms(data)
                    self.output_at = time.monotonic()
                packet_index += 1
        except (ConnectionError, OSError, ValueError):
            self.active.clear()
            if self.disconnected is not None:
                self.disconnected()

    def read_input_chunk(self):
        if not self.active.is_set() or self.input_paused:
            return None
        try:
            return self.input.get_nowait()
        except queue.Empty:
            return None

    def queue_playback(self, pcm, item_id=None):
        if not pcm or not self.active.is_set():
            return
        if len(pcm) % 2 or len(pcm) + 1 > MAX_FRAME:
            raise ValueError("invalid Talk playback audio")
        for offset in range(0, len(pcm), FRAME_BYTES):
            part = bytes(pcm[offset:offset + FRAME_BYTES])
            with self.lock:
                if self.queued_bytes + len(part) > MAX_PLAYBACK_BYTES:
                    # Don't trim audio mid-word: if Talk generates an
                    # impossibly long response, reject the excess audio.
                    self.discarded += len(part)
                    continue
                try:
                    self.output.put_nowait((self.output_generation, item_id, part))
                except queue.Full:
                    self.discarded += len(part)
                    continue
                self.queued_bytes += len(part)

    def drain_playback(self):
        with self.lock:
            while True:
                try:
                    _generation, _item_id, pcm = self.output.get_nowait()
                except queue.Empty:
                    break
                self.discarded += len(pcm)
                self.queued_bytes -= len(pcm)
            result = (self.item_id, self.played_ms)
            self.item_id = None
            self.played_bytes = 0
            self.output_generation += 1
            self.output_level = 0.0
        if self.active.is_set():
            # Tell MSN to discard audio already queued after interruption.
            # Sending D is ordered with any in-flight O frames by write_lock.
            try:
                self.send(b"D")
            except OSError:
                pass
        return result

    @property
    def playback_pending(self):
        with self.lock:
            return self.queued_bytes > 0

    @property
    def playback_progress(self):
        with self.lock:
            return PlaybackProgress(self.consumed, self.discarded, self.queued_bytes > 0)

    @property
    def played_ms(self):
        # Read without reacquiring lock; used in drain_playback under lock.
        return int(self.played_bytes * 1000 / PCM_BYTES_PER_SECOND)

    def reset_played_ms(self):
        with self.lock:
            self.played_bytes = 0
            self.item_id = None

    def pause_input(self):
        with self.lock:
            self.paused = True
        self._clear_input()

    def resume_input(self):
        self._clear_input()
        with self.lock:
            self.paused = False

    @property
    def input_paused(self):
        with self.lock:
            return self.paused

    def _clear_input(self):
        while True:
            try:
                self.input.get_nowait()
            except queue.Empty:
                break


class SessionAudioView:
    """Keep one authenticated MSN audio leg across provider reconnects.

    Talk can stop a provider session; only the outer run_call owns the
    underlying media socket and its reader/writer threads.
    """

    def __init__(self, audio):
        self.audio = audio

    def __getattr__(self, name):
        return getattr(self.audio, name)

    def start(self):
        self.audio.start()

    def stop(self):
        return None


async def run_call(connection: socket.socket):
    """Use Talk's registered provider and approved Hermes task execution."""
    try:
        from hermes_plugins.hermes_talk import talk_cli
    except ImportError as exc:
        raise RuntimeError("Hermes Talk is not installed/enabled in this CLI") from exc
    loop = asyncio.get_running_loop()
    current = asyncio.current_task()
    cancelled = False

    def disconnected():
        nonlocal cancelled
        if not cancelled:
            cancelled = True
            loop.call_soon_threadsafe(current.cancel)

    audio = SocketAudio(connection, disconnected=disconnected)
    target = os.environ.get("HERMES_XP_TALK_TARGET", "").strip()
    task = None
    if target:
        task = {
            "target_id": target,
            "peer_id": os.environ.get("HERMES_XP_TALK_PEER", "local"),
            "profile": os.environ.get("HERMES_XP_TALK_PROFILE", "default"),
            "tab_id": "hermesxp-msn",
        }
    elif os.environ.get("TALK_VOICE_MODE", "").strip().lower() == "live":
        raise RuntimeError("Hermes Talk Live requires HERMES_XP_TALK_TARGET")
    direct = os.environ.get("HERMES_XP_TALK_DIRECT_TOOLS", "").strip() == "1"
    if task and direct:
        raise RuntimeError(
            "Choose either HERMES_XP_TALK_TARGET or HERMES_XP_TALK_DIRECT_TOOLS"
        )
    if not task and not direct:
        raise RuntimeError(
            "HermesXP voice must use an authorized Talk task or direct Hermes tools"
        )
    session_audio = SessionAudioView(audio)
    try:
        for attempt in range(MAX_TALK_RECONNECTS + 1):
            attachment = HermesVoiceExecution() if direct else None
            refusals = []
            try:
                result = await talk_cli.run_talk_session(
                    audio=session_audio, lane="cli", keyboard_control=False,
                    on_refusal=refusals.append,
                    **({"host_execution_attachment": attachment} if attachment else {}),
                    **({"native_task": task} if task else {}),
                )
            finally:
                if attachment is not None:
                    attachment.close()
            if not audio.active.is_set() or refusals:
                return result
            if attempt == MAX_TALK_RECONNECTS:
                LOG.warning(
                    "Hermes Talk stopped %d times while the MSN call was still "
                    "connected; ending call rather than looping forever",
                    MAX_TALK_RECONNECTS + 1,
                )
                return result or 1
            LOG.warning(
                "Hermes Talk provider session stopped while Messenger is still "
                "connected (result=%s); reconnecting (%d/%d)",
                result, attempt + 1, MAX_TALK_RECONNECTS,
            )
            # Drop orphaned provider output, not the authenticated TCP leg.
            # A new provider has its own item IDs and cannot continue a
            # partially spoken old response or accept old microphone input.
            audio.drain_playback()
            audio._clear_input()
            await asyncio.sleep(min(1 + attempt, 3))
        return 1
    finally:
        audio.stop()


def handle(connection: socket.socket):
    try:
        connection.settimeout(4)
        kind, data = receive(connection)
        expected = os.environ.get("HERMES_MSN_BRIDGE_TOKEN", "")
        if not expected or len(expected) < 32 or kind != b"H" or len(data) > 2048:
            return
        try:
            provided = json.loads(data).get("token", "")
        except (ValueError, UnicodeError, AttributeError):
            return
        if not isinstance(provided, str) or not hmac.compare_digest(expected, provided):
            LOG.warning("Unauthorized local MSN Talk connection refused")
            return
        connection.settimeout(None)
        try:
            asyncio.run(run_call(connection))
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            LOG.error("Hermes Talk call failed (%s)", type(exc).__name__)
            try:
                connection.sendall(frame(b"X", type(exc).__name__.encode("ascii")))
            except OSError:
                pass
    finally:
        connection.close()


def serve(args):
    if len(os.environ.get("HERMES_MSN_BRIDGE_TOKEN", "")) < 32:
        raise SystemExit("HERMES_MSN_BRIDGE_TOKEN is required (32+ chars)")
    logging.basicConfig(level=logging.INFO)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", args.port))
        sock.listen(1)
        LOG.info("HermesXP Talk audio listening on loopback:%d", args.port)
        while True:
            conn, address = sock.accept()
            with conn:
                handle(conn)


def setup_cli(parser: argparse.ArgumentParser):
    parser.add_argument("--port", type=int, default=PORT, help="loopback PCM bridge port")


def cli_entry(args):
    serve(args)
