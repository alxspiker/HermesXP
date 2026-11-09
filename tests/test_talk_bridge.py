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
