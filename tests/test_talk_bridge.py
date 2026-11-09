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
from unittest.mock import MagicMock, patch
import subprocess

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
            self.assertEqual(audio.read_input_chunk(), b"\0" * 960)
            self.assertGreaterEqual(audio.suppressed_frames, 1)
            # Silencing, not dropping, maintains a continuous 20ms audio
            # clock for the provider's speech activity detector.
            speech = b"\0\x70" * 480
            b.sendall(bridge.frame(b"I", speech))
            actual = None
            for _ in range(30):
                actual = audio.read_input_chunk()
                if actual:
                    break
                time.sleep(.01)
            self.assertEqual(actual, speech)  # louder deliberate interruption
            # XP may still be playing the last frame 600ms AFTER our
            # server-side output queue drains. Preserve the VAD clock while
            # rejecting that delayed acoustic echo.
            with audio.lock:
                audio.output_at = time.monotonic() - .6
                audio.output_level = .2
            audio.drain_playback()
            b.sendall(bridge.frame(b"I", b"\0\x04" * 480))
            tail = None
            for _ in range(30):
                tail = audio.read_input_chunk()
                if tail is not None:
                    break
                time.sleep(.01)
            self.assertEqual(tail, b"\0" * 960)
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
            kwargs["on_refusal"]("test-session-complete")
            return 0

        fake = types.ModuleType("hermes_plugins.hermes_talk")
        fake.talk_cli = types.SimpleNamespace(run_talk_session=fake_talk)
        package = types.ModuleType("hermes_plugins")
        package.__path__ = []
        try:
            with patch.dict(sys.modules, {
                "hermes_plugins": package, "hermes_plugins.hermes_talk": fake,
            }), patch.dict(os.environ, {
                "TALK_VOICE_MODE": "native",
                "HERMES_XP_TALK_DIRECT_TOOLS": "1",
            }, clear=False):
                os.environ.pop("HERMES_XP_TALK_TARGET", None)
                self.assertEqual(asyncio.run(bridge.run_call(a)), 0)
            self.assertEqual(captured["lane"], "cli")
            self.assertEqual(captured["keyboard_control"], False)
            self.assertNotIn("native_task", captured)
            self.assertIn("host_execution_attachment", captured)
            self.assertEqual(
                {tool["name"] for tool in captured["host_execution_attachment"].tool_definitions()},
                {"hermes_execute"},
            )
        finally:
            a.close()
            b.close()

    def test_provider_reconnect_keeps_single_audio_thread_pair_and_same_socket(self):
        a, b = socket.socketpair()
        b.settimeout(3)
        calls = []

        async def fake_talk(**kwargs):
            media = kwargs["audio"]
            media.start()
            msg = bridge.receive(b)
            if calls:
                self.assertEqual(msg, (b"D", b""))
                msg = bridge.receive(b)
            self.assertEqual(msg, (b"R", b""))
            self.assertTrue(media.active.is_set())
            self.assertEqual(len(media.audio.threads), 2)
            calls.append(media)
            # This only ends the provider's session, never WLM's call.
            media.stop()
            if len(calls) == 2:
                kwargs["on_refusal"]("test-finished")
            return 0 if len(calls) == 2 else 1

        fake = types.ModuleType("hermes_plugins.hermes_talk")
        fake.talk_cli = types.SimpleNamespace(run_talk_session=fake_talk)
        package = types.ModuleType("hermes_plugins")
        package.__path__ = []
        try:
            with patch.dict(sys.modules, {
                "hermes_plugins": package, "hermes_plugins.hermes_talk": fake,
            }), patch.dict(os.environ, {
                "TALK_VOICE_MODE": "native", "HERMES_XP_TALK_DIRECT_TOOLS": "1",
            }, clear=False):
                os.environ.pop("HERMES_XP_TALK_TARGET", None)
                self.assertEqual(asyncio.run(bridge.run_call(a)), 0)
            self.assertEqual(len(calls), 2)
            self.assertIs(calls[0].audio, calls[1].audio)
            self.assertEqual(len(calls[0].audio.threads), 2)
            self.assertFalse(calls[0].audio.active.is_set())
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

    def test_voice_tool_invokes_hermes_directly_no_shell_or_delegation(self):
        tool = bridge.HermesVoiceExecution()
        definitions = tool.tool_definitions()
        self.assertEqual(len(definitions), 1)
        self.assertNotIn("delegate_task", {item["name"] for item in definitions})
        permit = tool.mint_tool_call_permit(
            tool_name="hermes_execute", call_id="voice-1",
            arguments={"request": "List the active shell tools"},
        )
        process = MagicMock()
        process.communicate.return_value = ("The tools are available.", "")
        process.returncode = 0
        with patch.object(bridge.shutil, "which", return_value="/bin/true"), patch.object(
            bridge.subprocess, "Popen", return_value=process,
        ) as spawn:
            result = asyncio.run(tool.execute_tool_batch((permit,)))
        self.assertEqual(result[0]["call_id"], "voice-1")
        self.assertEqual(result[0]["output"], "The tools are available.")
        args, kwargs = spawn.call_args
        self.assertEqual(args[0][0], "/bin/true")
        self.assertEqual(args[0][1], "-z")
        self.assertIn("List the active shell tools", args[0][2])
        self.assertEqual(kwargs["shell"], False)
        self.assertTrue(kwargs["start_new_session"])
        process.communicate.assert_called_once_with(timeout=bridge.HERMES_TOOL_TIMEOUT)
        with self.assertRaisesRegex(ValueError, "invalid"):
            asyncio.run(tool.execute_tool_batch((permit,)))
        tool.close()
        with self.assertRaisesRegex(ValueError, "not authorized"):
            tool.mint_tool_call_permit(tool_name="hermes_execute", call_id="voice-2",
                                       arguments={"request": "test"})

    def test_voice_tool_rejects_bad_commands_and_excessive_calls(self):
        tool = bridge.HermesVoiceExecution()
        with patch.object(bridge.shutil, "which", return_value="/bin/true"):
            with patch.object(bridge.subprocess, "Popen") as spawn:
                self.assertIn("too long", tool._run_hermes("x" * (bridge.MAX_TOOL_PROMPT + 1)))
                self.assertIn("concrete request", tool._run_hermes(""))
                spawn.assert_not_called()
        with self.assertRaisesRegex(ValueError, "not authorized"):
            tool.mint_tool_call_permit(tool_name="delegate_task", call_id="call-1",
                                       arguments={"task": "fake"})
        for i in range(bridge.MAX_TOOL_CALLS):
            tool.mint_tool_call_permit(tool_name="hermes_execute", call_id=f"id-{i}",
                                       arguments={"request": "test"})
        with self.assertRaisesRegex(ValueError, "limit"):
            tool.mint_tool_call_permit(tool_name="hermes_execute", call_id="one-more",
                                       arguments={"request": "test"})

    def test_no_direct_tools_or_task_refuses_limited_legacy_session(self):
        a, b = socket.socketpair()
        fake = types.ModuleType("hermes_plugins.hermes_talk")
        fake.talk_cli = types.SimpleNamespace(
            run_talk_session=lambda **kwargs: self.fail("Limited session started"))
        package = types.ModuleType("hermes_plugins")
        package.__path__ = []
        try:
            with patch.dict(sys.modules, {
                "hermes_plugins": package, "hermes_plugins.hermes_talk": fake,
            }), patch.dict(os.environ, {
                "TALK_VOICE_MODE": "native", "HERMES_XP_TALK_DIRECT_TOOLS": "0",
            }, clear=False):
                os.environ.pop("HERMES_XP_TALK_TARGET", None)
                with self.assertRaisesRegex(RuntimeError, "authorized Talk task or direct"):
                    asyncio.run(bridge.run_call(a))
        finally:
            a.close()
            b.close()


if __name__ == "__main__":
    unittest.main()
