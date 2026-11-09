"""Authenticated, LAN-only speech turns for the Windows XP companion.

This is a *companion voice transport*, not a WLM SIP/P2P voice-call
implementation. WLM 2009's native Call action cannot yet reach this endpoint.
The XP executable records PCM16/16kHz using WinMM, submits one spoken turn,
polls for completion, and plays PCM16/16kHz returned by this service.

Server-side audio and agent work reuse the same local LFM3-Audio REST endpoints
and Hermes api_server route as the existing hermes-talk Discord cascade.
No AI inference or paid provider runs on Windows XP.
"""
from __future__ import annotations

import argparse
from array import array
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import ipaddress
import json
import logging
import os
import secrets
import sys
from threading import Lock, Semaphore, Thread
import time
from urllib.request import Request, urlopen
import wave

try:
    from .hermesxp_update import read_registry
except ImportError:
    from hermesxp_update import read_registry

log = logging.getLogger("hermesxp.voice")
RATE = 16000
MAX_INPUT = RATE * 2 * 10  # ten seconds, PCM16 mono
MAX_OUTPUT = RATE * 2 * 45
TURN_TTL = 600
SYSTEM_PROMPT = ("You are Hermes speaking to the owner over the HermesXP "
                 "voice companion on Windows XP. Respond naturally and briefly.")
AGENT_URL = "http://127.0.0.1:8642/v1/chat/completions"
ASR_URL = "http://127.0.0.1:8899/v1/audio/transcriptions"
TTS_URL = "http://127.0.0.1:8899/tts"


def as_wave(pcm: bytes) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(RATE)
        wav.writeframes(pcm)
    return out.getvalue()


def pcm16_from_wav(raw: bytes) -> bytes:
    with wave.open(io.BytesIO(raw), "rb") as wav:
        channels, width, rate = wav.getnchannels(), wav.getsampwidth(), wav.getframerate()
        if channels != 1 or width != 2 or not 8000 <= rate <= 48000:
            raise ValueError("Unsupported TTS WAV format")
        if wav.getnframes() > 48000 * 45:
            raise ValueError("TTS audio exceeds limit")
        pcm = wav.readframes(wav.getnframes())
    if len(pcm) % 2:
        raise ValueError("Malformed PCM16")
    if rate == RATE:
        return pcm[:MAX_OUTPUT]
    samples = array("h")
    samples.frombytes(pcm)
    if sys.byteorder != "little":
        samples.byteswap()
    out = array("h")
    size = min(int(len(samples) * RATE / rate), MAX_OUTPUT // 2)
    for i in range(size):
        position = i * rate / RATE
        left = min(int(position), len(samples) - 1)
        right = min(left + 1, len(samples) - 1)
        fraction = position - left
        out.append(round(samples[left] * (1 - fraction) + samples[right] * fraction))
    if sys.byteorder != "little":
        out.byteswap()
    return out.tobytes()


def transcribe(pcm: bytes) -> str:
    boundary = "hermesxp" + secrets.token_hex(12)
    body = (("--" + boundary + "\r\nContent-Disposition: form-data; "
             "name=\"model\"\r\n\r\nwhisper-1\r\n--" + boundary +
             "\r\nContent-Disposition: form-data; name=\"file\"; "
             "filename=\"speech.wav\"\r\nContent-Type: audio/wav\r\n\r\n")
            .encode("ascii") + as_wave(pcm) + ("\r\n--" + boundary + "--\r\n").encode("ascii"))
    req = Request(ASR_URL, body, {"Content-Type": "multipart/form-data; boundary=" + boundary})
    with urlopen(req, timeout=75) as response:
        return str(json.loads(response.read(16_384)).get("text") or "").strip()


def ask_hermes(history: list[dict]) -> str:
    key = (os.environ.get("TALK_API_SERVER_KEY")
           or os.environ.get("API_SERVER_KEY") or "").strip()
    headers = {"Authorization": "Bearer " + key} if key else {}
    headers["Content-Type"] = "application/json"
    payload = json.dumps({"model": "lfm3-hermes", "messages": history, "stream": False}).encode()
    with urlopen(Request(AGENT_URL, payload, headers), timeout=230) as response:
        choices = json.loads(response.read(200_000))["choices"]
    content = choices[0]["message"]["content"]
    if not isinstance(content, str) or not content.strip():
        raise ValueError("Hermes returned an empty voice reply")
    return content.strip()[:1000]


def synthesize(text: str) -> bytes:
    payload = json.dumps({"input": text, "voice": "male", "language": "en"}).encode()
    req = Request(TTS_URL, payload, {"Content-Type": "application/json"})
    with urlopen(req, timeout=150) as response:
        raw = response.read(10_000_001)
    if len(raw) > 10_000_000:
        raise ValueError("TTS response exceeds limit")
    return pcm16_from_wav(raw)


class VoiceState:
    def __init__(self, registry=None):
        self.registry = registry or read_registry
        self.lock = Lock()
        self.capacity = Semaphore(1)
        self.turns: dict[str, dict] = {}
        self.histories: dict[str, list[dict]] = {}
        self.active: set[str] = set()

    def device_for(self, address: str, token: str):
        if len(token) != 64:
            return None
        for device in self.registry():
            if device["host"] == address and hmac.compare_digest(device["token"], token):
                return device
        return None

    @staticmethod
    def identity(device: dict) -> str:
        # A reused IP must not inherit a previous paired device's voice
        # history or job results. Keep pairing tokens out of dictionary keys.
        return hashlib.sha256(device["token"].encode("ascii")).hexdigest()

    def begin(self, device: dict, pcm: bytes) -> str | None:
        identity = self.identity(device)
        with self.lock:
            if identity in self.active or not self.capacity.acquire(blocking=False):
                return None
            self.active.add(identity)
            now = time.monotonic()
            self.turns = {key: value for key, value in self.turns.items()
                          if now - value["created"] < TURN_TTL}
            turn_id = secrets.token_hex(12)
            self.turns[turn_id] = {
                "owner": identity, "state": "pending", "created": now,
            }
        Thread(target=self._work, args=(identity, turn_id, pcm), daemon=True).start()
        return turn_id

    def _work(self, owner: str, turn_id: str, pcm: bytes):
        try:
            transcript = transcribe(pcm)
            if not transcript:
                raise ValueError("No speech detected")
            with self.lock:
                past = list(self.histories.get(owner, []))
            messages = [{"role": "system", "content": SYSTEM_PROMPT}] + past + [
                {"role": "user", "content": transcript}]
            reply = ask_hermes(messages)
            audio = synthesize(reply)
            if not audio or len(audio) > MAX_OUTPUT:
                raise ValueError("Invalid speech response")
            with self.lock:
                self.histories[owner] = (
                    past + [{"role": "user", "content": transcript},
                            {"role": "assistant", "content": reply}]
                )[-16:]
                self.turns[turn_id].update(state="done", audio=audio)
        except Exception:
            log.exception("Voice turn failed (%s)", turn_id)
            with self.lock:
                self.turns[turn_id]["state"] = "failed"
        finally:
            with self.lock:
                self.active.discard(owner)
            self.capacity.release()

    def result(self, owner: str, turn_id: str):
        with self.lock:
            item = self.turns.get(turn_id)
            if (item is None or item["owner"] != owner
                    or time.monotonic() - item["created"] >= TURN_TTL):
                return "missing", b""
            return item["state"], item.get("audio", b"")


def make_handler(state: VoiceState):
    class Handler(BaseHTTPRequestHandler):
        server_version = "HermesXP-Voice"
        sys_version = ""

        def log_message(self, fmt, *args):
            log.info("%s - %s", self.address_string(), fmt % args)

        def _reply(self, status: int, body: bytes = b"", content_type="text/plain"):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if body:
                self.wfile.write(body)

        def _device(self):
            try:
                return state.device_for(self.client_address[0],
                                        self.headers.get("X-Hermes-Token", ""))
            except (OSError, ValueError):
                return None

        def do_POST(self):
            device = self._device()
            if not device:
                self._reply(403, b"unauthorized")
                return
            if self.path != "/voice/turn":
                self._reply(404)
                return
            raw_length = self.headers.get("Content-Length", "")
            if (not raw_length.isdecimal() or self.headers.get("Transfer-Encoding")
                    or self.headers.get("Content-Type") != "application/octet-stream"):
                self._reply(400, b"invalid request")
                return
            length = int(raw_length)
            if not 3200 <= length <= MAX_INPUT or length % 2:
                self._reply(413, b"invalid PCM length")
                return
            self.connection.settimeout(15)
            pcm = self.rfile.read(length)
            if len(pcm) != length:
                self._reply(400, b"incomplete recording")
                return
            turn_id = state.begin(device, pcm)
            if not turn_id:
                self._reply(429, b"voice agent busy")
                return
            self._reply(202, turn_id.encode("ascii"))

        def do_GET(self):
            device = self._device()
            if not device:
                self._reply(403, b"unauthorized")
                return
            prefix = "/voice/turn/"
            if not self.path.startswith(prefix):
                self._reply(404)
                return
            turn_id = self.path[len(prefix):]
            if len(turn_id) != 24 or any(c not in "0123456789abcdef" for c in turn_id):
                self._reply(404)
                return
            status, audio = state.result(state.identity(device), turn_id)
            if status == "pending":
                self._reply(202, b"pending")
            elif status == "done":
                self._reply(200, audio, "application/octet-stream")
            elif status == "failed":
                self._reply(502, b"speech processing failed")
            else:
                self._reply(404)

    return Handler


def main():
    parser = argparse.ArgumentParser(description="HermesXP authenticated LAN voice turns")
    parser.add_argument("--bind", default=os.environ.get("HERMES_XP_VOICE_BIND", ""))
    parser.add_argument("--port", type=int, default=18770)
    args = parser.parse_args()
    if not args.bind:
        parser.error("set --bind to the Hermes host's private LAN IPv4 address")
    address = ipaddress.ip_address(args.bind)
    if address.version != 4 or not address.is_private or address.is_loopback:
        parser.error("voice service must bind a private, non-loopback IPv4 address")
    logging.basicConfig(level=logging.INFO)
    server = ThreadingHTTPServer((str(address), args.port), make_handler(VoiceState()))
    log.info("XP voice gateway bound on %s:%s (paired IP and token only)", *server.server_address)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()


if __name__ == "__main__":
    main()
