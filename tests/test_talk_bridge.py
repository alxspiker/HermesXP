"""HermesXP Talk transport tests; no provider calls or credentials required."""
import asyncio
import os
import socket
import sys
import threading
import time
import types
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import talk_bridge as bridge


class TalkBridgeTests(unittest.TestCase):
    def test_frame_rejects_oversized_audio(self):
        self.assertEqual(bridge.frame(b"I", b"xy"), b"\0\0\0\3Ixy")
        with self.assertRaises(ValueError):
            bridge.frame(b"I", b"x" * bridge.MAX_FRAME)

    def test_audio_round_trip_without_sound_card(self):
        a, b = socket.socketpair()
        try:
            audio = bridge.SocketAudio(a)
            audio.start()
            self.assertEqual(bridge.receive(b), (b"R", b""))
            b.sendall(bridge.frame(b"I", b"\x10\0" * 480))
            incoming = None
            for _ in range(50):
                incoming = audio.read_input_chunk()
                if incoming:
                    break
                time.sleep(.01)
            self.assertEqual(incoming, b"\x10\0" * 480)
            audio.queue_playback(b"\x20\0" * 480, "msg-a")
            self.assertEqual(bridge.receive(b), (b"O", b"\x20\0" * 480))
            self.assertEqual(audio.playback_progress.consumed_bytes, 960)
            audio.pause_input()
            self.assertTrue(audio.input_paused)
            audio.resume_input()
            self.assertFalse(audio.input_paused)
            audio.stop()
        finally:
            b.close()

    def test_provider_audio_is_delivered_at_real_playback_speed(self):
        a, b = socket.socketpair()
        b.settimeout(2.0)
        try:
            audio = bridge.SocketAudio(a)
            audio.start()
            self.assertEqual(bridge.receive(b), (b"R", b""))
            # A provider may send 600 ms of speech in one fast model delta.
            # HermesXP must NOT flood the RTP queue with all 30 packets at
            # once (the previous bug repeatedly dropped whole syllables).
            speech = b"\x80\x10" * (480 * 30)
            started = time.monotonic()
            audio.queue_playback(speech, "response-1")
            arrivals = []
            received = bytearray()
            for _ in range(30):
                kind, data = bridge.receive(b)
                self.assertEqual(kind, b"O")
                arrivals.append(time.monotonic() - started)
                received.extend(data)
            self.assertEqual(received, speech)
            self.assertLess(arrivals[3] - arrivals[0], 0.08)
            self.assertGreater(arrivals[-1] - arrivals[0], 0.42)
            self.assertLess(arrivals[-1] - arrivals[0], 0.75)
            self.assertEqual(audio.discarded, 0)
            self.assertFalse(audio.playback_pending)
            audio.stop()
        finally:
            b.close()

    def test_echo_gate_suppresses_speaker_and_keeps_clear_barge_in(self):
        a, b = socket.socketpair()
        b.settimeout(2.0)
        try:
            with patch.dict(os.environ, {"TALK_ECHO_GATE": "on"}):
                audio = bridge.SocketAudio(a)
            audio.start()
            bridge.receive(b)  # ready
            audio.queue_playback(b"\0\x18" * (480 * 12))
            self.assertEqual(bridge.receive(b)[0], b"O")
            self.assertGreater(audio.output_level, .1)
            b.sendall(bridge.frame(b"I", b"\0\x04" * 480))
            time.sleep(.025)
            self.assertIsNone(audio.read_input_chunk())  # speaker leakage
            speech = b"\0\x70" * 480
            b.sendall(bridge.frame(b"I", speech))
            actual = None
            for _ in range(30):
                actual = audio.read_input_chunk()
                if actual:
                    break
                time.sleep(.01)
            self.assertEqual(actual, speech)  # louder deliberate interruption
            audio.drain_playback()
            # A cancellation is sent to the RTP bridge to flush any
            # packets already forwarded but not yet heard by Messenger.
            seen_clear = False
            for _ in range(16):
                kind, _ = bridge.receive(b)
                if kind == b"D":
                    seen_clear = True
                    break
            self.assertTrue(seen_clear)
            audio.stop()
        finally:
            b.close()

    def test_fail_closed_handshake(self):
        a, b = socket.socketpair()
        with patch.dict(os.environ, {"HERMES_MSN_BRIDGE_TOKEN": "a" * 40}):
            thread = threading.Thread(target=bridge.handle, args=(a,))
            thread.start()
            b.sendall(bridge.frame(b"H", b'{"token":"wrong"}'))
            thread.join(2)
            self.assertFalse(thread.is_alive())
            self.assertEqual(b.recv(1), b"")
        b.close()

    def test_run_call_forwards_to_actual_talk_session_contract(self):
        a, b = socket.socketpair()
        captured = {}

        async def fake_talk(**kwargs):
            captured.update(kwargs)
            kwargs["audio"].start()
            self.assertEqual(bridge.receive(b), (b"R", b""))
            return 0

        fake = types.ModuleType("hermes_plugins.hermes_talk")
        fake.talk_cli = types.SimpleNamespace(run_talk_session=fake_talk)
        package = types.ModuleType("hermes_plugins")
        package.__path__ = []
        try:
            with patch.dict(sys.modules, {
                "hermes_plugins": package, "hermes_plugins.hermes_talk": fake,
            }), patch.dict(os.environ, {"TALK_VOICE_MODE": "native"}, clear=False):
                os.environ.pop("HERMES_XP_TALK_TARGET", None)
                self.assertEqual(asyncio.run(bridge.run_call(a)), 0)
            self.assertEqual(captured["lane"], "cli")
            self.assertEqual(captured["keyboard_control"], False)
            self.assertNotIn("native_task", captured)
        finally:
            a.close()
            b.close()

    def test_live_requires_task_target(self):
        a, b = socket.socketpair()
        fake = types.ModuleType("hermes_plugins.hermes_talk")
        fake.talk_cli = types.SimpleNamespace(run_talk_session=lambda **kwargs: None)
        package = types.ModuleType("hermes_plugins")
        package.__path__ = []
        try:
            with patch.dict(sys.modules, {
                "hermes_plugins": package, "hermes_plugins.hermes_talk": fake,
            }), patch.dict(os.environ, {"TALK_VOICE_MODE": "live"}, clear=False):
                os.environ.pop("HERMES_XP_TALK_TARGET", None)
                with self.assertRaisesRegex(RuntimeError, "HERMES_XP_TALK_TARGET"):
                    asyncio.run(bridge.run_call(a))
        finally:
            a.close()
            b.close()


if __name__ == "__main__":
    unittest.main()
