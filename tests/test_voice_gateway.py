"""HermesXP companion voice transport tests; no network AI calls."""
import http.client
import importlib.util
import io
import os
from pathlib import Path
import sys
from threading import Thread
import time
import unittest
from unittest.mock import patch
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import voice_gateway as v  # noqa: E402


class TestAudio(unittest.TestCase):
    def test_wav_round_trip(self):
        raw = (b"\x08\x00\xf8\xff" * 1000)
        self.assertEqual(v.pcm16_from_wav(v.as_wave(raw)), raw)

    def test_24khz_converts_to_16khz(self):
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(24000)
            w.writeframes(b"\x00\x00" * 2400)
        self.assertEqual(len(v.pcm16_from_wav(buf.getvalue())), 3200)

    def test_reject_stereo_and_oversize(self):
        b = io.BytesIO()
        with wave.open(b, "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(b"\x00\x00" * 12)
        with self.assertRaises(ValueError):
            v.pcm16_from_wav(b.getvalue())

    def test_winmm_build_includes_32bit_legacy_dll(self):
        source = (ROOT / "xp-client" / "voice_turn.h").read_text()
        self.assertIn("waveInOpen", source)
        self.assertIn("waveOutOpen", source)
        self.assertIn("g_remote_token", source)
        self.assertIn("g_remote_allowed_ip", source)
        self.assertIn("VOICE_PORT 18770", source)
        self.assertIn("NOT native Windows Live Messenger", source)
        binary = (ROOT / "dist" / "HermesXP.exe").read_bytes()
        self.assertIn(b"winmm.dll", binary)


class TestVoiceServer(unittest.TestCase):
    def setUp(self):
        self.token = "a" * 64
        self.device = {"host": "127.0.0.1", "token": self.token, "port": 18768}
        self.state = v.VoiceState(registry=lambda: [self.device])
        self.server = v.ThreadingHTTPServer(
            ("127.0.0.1", 0), v.make_handler(self.state)
        )
        self.server.daemon_threads = True
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)

    def request(self, method, path, body=b"", token=None, content_type="application/octet-stream"):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        conn.request(method, path, body=body, headers={
            "X-Hermes-Token": self.token if token is None else token,
            "Content-Type": content_type,
        })
        response = conn.getresponse()
        status, data = response.status, response.read()
        conn.close()
        return status, data

    def test_auth_and_input_limits(self):
        self.assertEqual(self.request("POST", "/voice/turn", b"\0" * 3200, token="wrong")[0], 403)
        self.assertEqual(self.request("POST", "/voice/turn", b"\0" * 100)[0], 413)
        self.assertEqual(self.request("POST", "/voice/turn", b"\0" * (v.MAX_INPUT+2))[0], 413)
        self.assertEqual(self.request("GET", "/voice/turn/a" * 8)[0], 404)

    def test_full_turn_and_history(self):
        audio = b"\0\0" * 1600
        with (patch.object(v, "transcribe", return_value="Hello Hermes") as asr,
              patch.object(v, "ask_hermes", return_value="Hello XP") as agent,
              patch.object(v, "synthesize", return_value=audio) as tts):
            code, turn = self.request("POST", "/voice/turn", audio)
            self.assertEqual(code, 202)
            self.assertEqual(len(turn), 24)
            for _ in range(150):
                code, result = self.request("GET", "/voice/turn/" + turn.decode())
                if code != 202:
                    break
                time.sleep(.01)
            self.assertEqual((code, result), (200, audio))
            asr.assert_called_once_with(audio)
            self.assertEqual(agent.call_args[0][0][-1]["content"], "Hello Hermes")
            tts.assert_called_once_with("Hello XP")
            self.assertEqual(self.state.histories[self.state.identity(self.device)][-1]["content"], "Hello XP")
            # Non-authorized polling never reveals a turn's PCM or state.
            self.assertEqual(self.request("GET", "/voice/turn/" + turn.decode(), token="b"*64)[0], 403)

    def test_busy_turn_does_not_queue_unbounded_agent_work(self):
        device = self.device
        gate = self.state.capacity
        self.assertTrue(gate.acquire(blocking=False))
        try:
            code, _ = self.request("POST", "/voice/turn", b"\0" * 3200)
            self.assertEqual(code, 429)
        finally:
            gate.release()

    def test_native_greeting_only_on_authenticated_loopback_worker(self):
        with (patch.dict(os.environ, {"HERMES_MSN_BRIDGE_TOKEN": self.token}),
              patch.object(v, "synthesize", return_value=b"\0\0" * 1600) as tts):
            server = v.ThreadingHTTPServer(("127.0.0.1", 0),
                                           v.make_handler(self.state, native=True))
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                def fetch(token):
                    connection = http.client.HTTPConnection(
                        "127.0.0.1", server.server_port, timeout=3)
                    connection.request("GET", "/voice/greeting",
                                       headers={"X-Hermes-Token": token})
                    reply = connection.getresponse()
                    status, payload = reply.status, reply.read()
                    connection.close()
                    return status, payload
                self.assertEqual(fetch("wrong")[0], 403)
                self.assertEqual(fetch(self.token), (200, b"\0\0" * 1600))
                tts.assert_called_once()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(3)


if __name__ == "__main__":
    unittest.main()
