"""Direct Hermes tools: no dashboard process, no network calls in fixtures."""
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from PIL import Image

from tools import xp_agent_tools as xp


PAIR = {
    "name": "Lab XP", "host": "192.168.100.37", "port": 18768,
    "token": "a" * 64,
}


def bmp_image(width=80, height=60):
    image = Image.new("RGB", (width, height), "white")
    buffer = io.BytesIO()
    image.save(buffer, format="BMP")
    return buffer.getvalue()


class XPAgentToolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.patch_home = patch.object(xp, "_home", return_value=self.home)
        self.patch_registry = patch.object(xp, "read_registry", return_value=[dict(PAIR)])
        self.patch_home.start()
        self.patch_registry.start()
        self.addCleanup(self.patch_home.stop)
        self.addCleanup(self.patch_registry.stop)
        with xp._ACTION_LOCK:
            xp._RECENT_ACTIONS.clear()

    def test_status_is_read_only_by_default_and_never_leaks_pairing_token(self):
        with (
            patch.object(xp, "_client") as client,
            patch.object(xp, "_systemd_status", return_value={"state": "active"}),
        ):
            result = xp.xp_status({})
        client.assert_not_called()
        self.assertEqual(result["devices"], [{"name": "Lab XP", "state": "paired; not probed"}])
        self.assertEqual(len(result["services"]), 7)
        self.assertNotIn(PAIR["token"], json.dumps(result))
        self.assertNotIn(PAIR["host"], json.dumps(result))

    def test_host_ports_probe_loopback_only(self):
        from types import SimpleNamespace
        reply = SimpleNamespace(stdout="ActiveState=active\nSubState=running\n", returncode=0)
        with (
            patch.object(xp.subprocess, "run", return_value=reply) as command,
            patch.object(xp.socket, "create_connection") as connect,
        ):
            xp._systemd_status("hermes-msn-bridge.service")
            connect.assert_called_once_with(("127.0.0.1", 18769), timeout=0.25)
            command.assert_called_once()
            self.assertNotIn("shell", command.call_args.kwargs)
            with self.assertRaises(ValueError):
                xp._systemd_status("arbitrary.service")

    def test_removed_browser_dashboard_cannot_be_started_from_checkout(self):
        root = Path(__file__).resolve().parents[1]
        self.assertFalse((root / "local-server/dashboard.html").exists())
        self.assertFalse((root / "local-server/api_server.py").exists())
        self.assertNotIn("fastapi", (root / "requirements-test.txt").read_text().lower())

    def test_explicit_probe_reads_authenticated_network_status(self):
        with patch.object(xp, "_client") as client:
            client.return_value.network_status.return_value = (
                "paired_host_ip=192.168.100.1 discovery_state=6 verified=3 win32_error=0")
            result = xp.xp_status({"probe": True})
        self.assertEqual(result["devices"][0]["state"], "reachable")
        client.assert_called_once_with(dict(PAIR), timeout=2.0)
        self.assertNotIn(PAIR["token"], json.dumps(result))

    def test_probe_distinguishes_unavailable_from_verified(self):
        with patch.object(xp, "_client", side_effect=TimeoutError("test")):
            result = xp.xp_status({"probe": True})
        self.assertEqual(result["devices"][0]["state"], "offline or unavailable")

    def test_update_snapshot_handles_version_and_package_without_secrets(self):
        root = self.home / "msn-server"
        root.mkdir()
        (root / ".xp-active-plugin-revision").write_text("a" * 40)
        cache = root / "update-artifacts"
        cache.mkdir()
        (cache / "build-state.json").write_text(json.dumps({
            "revision": "b" * 40, "version": "1.2.3", "access_token": "secret",
        }))
        package = root / "xp-package/HermesXP-Setup.exe"
        package.parent.mkdir()
        package.write_bytes(b"setup")
        status = xp._update_status()
        self.assertEqual(status["installed_revision"], "a" * 40)
        self.assertEqual(status["artifact_revision"], "b" * 40)
        self.assertEqual(status["artifact_version"], "1.2.3")
        self.assertTrue(status["package_ready"])
        self.assertNotIn("secret", str(status))

    def test_device_requires_exact_unique_pairing_name(self):
        self.assertEqual(xp._select_device(), PAIR)
        with patch.object(xp, "read_registry", return_value=[PAIR, {**PAIR, "name": "XP B"}]):
            with self.assertRaisesRegex(ValueError, "Specify"):
                xp._select_device()
            with self.assertRaisesRegex(ValueError, "not found"):
                xp._select_device("unknown")
            self.assertEqual(xp._select_device("XP B")["name"], "XP B")

    def test_screenshot_returns_dimensions_and_private_atomic_file(self):
        with patch.object(xp, "_client") as client:
            client.return_value.screenshot.return_value = bmp_image()
            result = xp.xp_screen({"save": True})
        path = Path(result["screenshot_path"])
        self.assertEqual(path.read_bytes(), bmp_image())
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
        self.assertEqual((result["width"], result["height"]), (80, 60))
        self.assertNotIn(PAIR["token"], json.dumps(result))
        with patch.object(xp, "_client") as client:
            client.return_value.screenshot.return_value = bmp_image(100, 50)
            second = xp.xp_screen({"save": True})
        self.assertEqual(second["screenshot_path"], result["screenshot_path"])
        self.assertEqual(Path(second["screenshot_path"]).read_bytes(), bmp_image(100, 50))

    def test_screen_without_save_does_not_persist_image(self):
        with patch.object(xp, "_client") as client:
            client.return_value.screenshot.return_value = bmp_image()
            result = xp.xp_screen({"save": False})
        self.assertNotIn("screenshot_path", result)
        self.assertFalse((self.home / "hermesxp-screenshots").exists())

    def test_screenshot_rejects_malformed_or_oversized_bmp(self):
        for invalid in (b"BMP?", b"" , b"BM" + b"\0" * 52):
            with self.subTest(content=invalid), self.assertRaises(ValueError):
                xp._bmp_dimensions(invalid)
        self.assertEqual(xp._bmp_dimensions(bmp_image()), (80, 60))

    def test_screenshot_directory_symlink_is_refused(self):
        directory = self.home / "hermesxp-screenshots"
        directory.symlink_to(self.home)
        with self.assertRaises(RuntimeError):
            xp._save_private_screenshot(bmp_image(), PAIR["name"])

    def test_optional_vision_analyzes_without_web_endpoint(self):
        with (
            patch.object(xp, "_client") as client,
            patch("tools.xp_vision.infer_screenshot", return_value={
                "status": "verified", "model": "selected", "detections": [],
            }) as infer,
        ):
            client.return_value.screenshot.return_value = bmp_image()
            result = xp.xp_screen({"save": False, "analyze": True})
        self.assertEqual(result["vision"]["model"], "selected")
        self.assertEqual(infer.call_args.args[0].size, (80, 60))
        self.assertFalse((self.home / "hermesxp-screenshots").exists())

    def test_optional_vision_failure_never_fabricates_detections(self):
        with (
            patch.object(xp, "_client") as client,
            patch("tools.xp_vision.infer_screenshot", side_effect=RuntimeError("offline")),
        ):
            client.return_value.screenshot.return_value = bmp_image()
            result = xp.xp_screen({"save": False, "analyze": True})
        self.assertEqual(result["vision"]["status"], "unavailable")
        self.assertEqual(result["vision"]["detections"], [])

    def test_desktop_input_requires_host_opt_in_and_confirmation(self):
        with patch.object(xp, "_client") as client, patch.dict(os.environ, {}, clear=True):
            self.assertFalse(json.loads(xp.invoke("xp_control", {
                "action": "click", "coords": [10, 20], "confirm_live": True,
            }))["success"])
            client.assert_not_called()
        with patch.object(xp, "_client") as client, patch.dict(
            os.environ, {"HERMES_CUA_LIVE_ENABLED": "1"}, clear=True,
        ):
            self.assertFalse(json.loads(xp.invoke("xp_control", {
                "action": "click", "coords": [10, 20],
            }))["success"])
            client.assert_not_called()

    def test_live_click_validated_and_acknowledged(self):
        with (
            patch.object(xp, "_client") as client,
            patch.dict(os.environ, {"HERMES_CUA_LIVE_ENABLED": "1"}),
        ):
            client.return_value.inspect.return_value = "width=1024 height=600 title=XP"
            client.return_value.click.return_value = "clicked"
            result = xp.xp_control({
                "action": "right_click", "coords": [10, 20], "confirm_live": True,
            })
        self.assertTrue(result["acknowledged"])
        client.return_value.click.assert_called_once_with(10, 20, 1024, 600, "right")
        self.assertNotIn(PAIR["token"], json.dumps(result))

    def test_bad_mouse_coordinates_fail_without_performing_action(self):
        with (
            patch.object(xp, "_client") as client,
            patch.dict(os.environ, {"HERMES_CUA_LIVE_ENABLED": "1"}),
        ):
            client.return_value.inspect.return_value = "width=100 height=60"
            for coords in ([100, 0], [False, 0], [0, -1], "0,0"):
                with self.subTest(coords=coords):
                    with self.assertRaises(ValueError):
                        xp.xp_control({"action": "click", "coords": coords,
                                       "confirm_live": True})
            client.return_value.click.assert_not_called()

    def test_key_input_is_allowlisted_and_no_shell_command_endpoint(self):
        with (
            patch.object(xp, "_client") as client,
            patch.dict(os.environ, {"HERMES_CUA_LIVE_ENABLED": "1"}),
        ):
            with self.assertRaises(ValueError):
                xp.xp_control({"action": "key_press", "text": "Win+R",
                               "confirm_live": True})
            client.return_value.key.assert_not_called()
            self.assertFalse(json.loads(xp.invoke("xp_control", {
                "action": "shell", "text": "rm -rf /", "confirm_live": True,
            }))["success"])

    def test_malformed_ack_is_not_reported_as_success(self):
        with (
            patch.object(xp, "_client") as client,
            patch.dict(os.environ, {"HERMES_CUA_LIVE_ENABLED": "1"}),
        ):
            client.return_value.key.return_value = "not acknowledged"
            result = xp.invoke("xp_control", {
                "action": "key_press", "text": "Enter", "confirm_live": True,
            })
        self.assertFalse(json.loads(result)["success"])

    def test_rate_limit_enforces_ten_live_operations_in_five_seconds(self):
        with patch.dict(os.environ, {"HERMES_CUA_LIVE_ENABLED": "1"}):
            for _ in range(10):
                xp._allow_live({"confirm_live": True})
            with self.assertRaisesRegex(RuntimeError, "rate limit"):
                xp._allow_live({"confirm_live": True})

    def test_service_status_read_only_and_write_requires_host_opt_in(self):
        with (
            patch.object(xp, "_client") as client,
            patch.dict(os.environ, {}, clear=True),
        ):
            client.return_value.service.return_value = "service=Spooler state=running"
            read = xp.xp_service({"name": "Spooler"})
            self.assertEqual(read["action"], "status")
            client.return_value.service.assert_called_once_with("Spooler", "status")
            client.reset_mock()
            self.assertFalse(json.loads(xp.invoke("xp_service", {
                "name": "Spooler", "action": "stop", "confirm_live": True,
            }))["success"])
            client.assert_not_called()

    def test_service_name_is_not_shell_code(self):
        with patch.object(xp, "_client") as client:
            self.assertFalse(json.loads(xp.invoke("xp_service", {
                "name": "Spooler;echo leak", "action": "status",
            }))["success"])
            client.assert_not_called()

    def test_error_boundary_does_not_disclose_pairing_token(self):
        with patch.object(xp, "_client", side_effect=RuntimeError(PAIR["token"])):
            response = xp.invoke("xp_screen", {"save": False})
        self.assertFalse(json.loads(response)["success"])
        self.assertNotIn(PAIR["token"], response)


if __name__ == "__main__":
    unittest.main()
