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
import socket
import struct
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
        self.echo_threshold = 0.08
        self.echo_ratio = 1.4
        self.write_lock = threading.Lock()
        self.threads = []

    def send(self, kind, payload=b""):
        with self.write_lock:
            self.connection.sendall(frame(kind, payload))

    def start(self):
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
                        time.monotonic() - self.output_at < 0.35
                    )
                    echo_level = self.output_level
                if paused:
                    continue
                if self.echo_gate and playing and rms(data) < max(
                    self.echo_threshold, echo_level * self.echo_ratio
                ):
                    continue
                try:
                    self.input.put_nowait(data)
                except queue.Full:
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
    try:
        return await talk_cli.run_talk_session(
            audio=audio, lane="cli", keyboard_control=False,
            **({"native_task": task} if task else {}),
        )
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
