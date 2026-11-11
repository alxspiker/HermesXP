import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
import api_server
from api_server import app


class DashboardAPITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.client = TestClient(app)

    def _write_update_state(self):
        update = self.home / "msn-server" / "update-artifacts"
        update.mkdir(parents=True)
        (update / "build-state.json").write_text(json.dumps({
            "revision": "a" * 40,
            "source": "b" * 64,
            "version": "0.8.0",
            "sha256": {"HermesXP.exe": "c" * 64, "HermesXP-Updater.exe": "d" * 64},
        }))
        marker = self.home / "msn-server" / ".xp-active-plugin-revision"
        marker.write_text("a" * 40 + "\n")
        package = self.home / "msn-server" / "xp-package" / "HermesXP-Setup.exe"
        package.parent.mkdir(parents=True)
        package.write_bytes(b"setup")

    def test_dashboard_bind_defaults_to_loopback_and_rejects_wildcard_or_public(self):
        import os
        from api_server import dashboard_bind_host
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(dashboard_bind_host(), "127.0.0.1")
        for address in ("0.0.0.0", "::", "8.8.8.8"):
            with patch.dict(os.environ, {"HERMES_DASHBOARD_BIND_HOST": address}, clear=True):
                with self.assertRaises(RuntimeError):
                    dashboard_bind_host()
        with patch.dict(os.environ, {"HERMES_DASHBOARD_BIND_HOST": "192.168.1.20"}, clear=True):
            self.assertEqual(dashboard_bind_host(), "192.168.1.20")

    def test_systemd_query_uses_fixed_user_scope_argv_without_shell(self):
        from types import SimpleNamespace
        with patch("api_server.subprocess.run", return_value=SimpleNamespace(
                stdout="LoadState=loaded\nActiveState=active\nSubState=running\n", returncode=0)) as run:
            result = __import__("api_server").query_systemd_unit("msn-server.service")
        self.assertEqual(result["active_state"], "active")
        args, kwargs = run.call_args
        self.assertEqual(args[0], ["systemctl", "--user", "show", "msn-server.service",
                                  "--property=LoadState,ActiveState,SubState", "--no-pager"])
        self.assertNotIn("shell", kwargs)
        self.assertEqual(kwargs["timeout"], 1.5)

    def test_legacy_status_schema_remains_available_and_service_summary_is_live(self):
        services = [{"id": spec["id"], "state": "active",
                     "ports": [{"reachable": True} for _ in spec["ports"]]}
                    for spec in api_server.SERVICE_SPECS]
        live = {"services": services, "diagnostics": {"systemd": "available"}}
        with patch("api_server.dashboard_status", return_value=live):
            response = self.client.get("/api/status")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(set(data), {"services", "dashboard", "vision", "model", "cua", "xp_endpoint"})
        self.assertEqual(data["services"], "active")
        self.assertIsInstance(data["services"], str)
        services[2]["state"] = "inactive"
        with patch("api_server.dashboard_status", return_value=live):
            degraded = self.client.get("/api/status")
        self.assertEqual(degraded.json()["services"], "degraded")

    def test_status_handler_reports_observed_services_devices_updates_and_diagnostics(self):
        self._write_update_state()
        states = {
            "msn-server.service": {"load_state": "loaded", "active_state": "active", "sub_state": "running"},
            "msn-tls.service": {"load_state": "loaded", "active_state": "inactive", "sub_state": "dead"},
        }
        def service(unit):
            return states.get(unit, {"load_state": "not-found", "active_state": "inactive", "sub_state": "dead"})
        devices = [{"name": "XP-A", "host": "192.168.2.11", "port": 18768, "token": "z" * 64}]
        with patch("api_server.dashboard_home", return_value=self.home), \
             patch("api_server.query_systemd_unit", side_effect=service), \
             patch("api_server.probe_local_port", side_effect=lambda _host, port, **_kw: port in {1863, 1864, 8081}), \
             patch("api_server.read_registry", return_value=devices):
            response = self.client.get("/api/dashboard/status")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        msn = next(item for item in data["services"] if item["id"] == "msn-server")
        tls = next(item for item in data["services"] if item["id"] == "msn-tls")
        self.assertEqual(msn["state"], "active")
        self.assertTrue(msn["ports"][0]["reachable"])
        self.assertEqual(tls["state"], "inactive")
        self.assertEqual(data["devices"], [{"name": "XP-A", "state": "paired; not probed"}])
        self.assertEqual(data["update"]["plugin_revision"], "a" * 40)
        self.assertEqual(data["update"]["artifact_version"], "0.8.0")
        self.assertTrue(data["update"]["package_ready"])
        self.assertEqual(data["diagnostics"]["systemd"], "available")
        self.assertNotIn("z" * 64, response.text)

    def test_status_handler_reports_systemd_and_registry_errors_truthfully(self):
        with patch("api_server.query_systemd_unit", side_effect=OSError("system bus unavailable")), \
             patch("api_server.probe_local_port", return_value=False), \
             patch("api_server.read_registry", side_effect=OSError("registry unavailable")), \
             patch("api_server.dashboard_home", return_value=self.home):
            response = self.client.get("/api/dashboard/status")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["diagnostics"]["systemd"], "unavailable")
        self.assertEqual(data["diagnostics"]["registry"], "unavailable")
        self.assertTrue(all(item["state"] == "unknown" for item in data["services"]))
        self.assertEqual(data["devices"], [])

    def test_device_probe_requires_explicit_confirmation_and_never_returns_tokens(self):
        device = {"name": "XP-A", "host": "192.168.2.11", "port": 18768, "token": "p" * 64}
        with patch("api_server.read_registry", return_value=[device]), patch("api_server.HermesXPClient") as client_class:
            denied = self.client.get("/api/dashboard/devices")
            client_class.assert_not_called()
            self.assertEqual(denied.status_code, 400)
            denied_without_header = self.client.get("/api/dashboard/devices?confirm=1")
            client_class.assert_not_called()
            self.assertEqual(denied_without_header.status_code, 400)
            client_class.return_value.network_status.return_value = "discovery_state=6 verified=3 win32_error=0"
            response = self.client.get("/api/dashboard/devices?confirm=1", headers={"X-Hermes-Dashboard-Confirm": "user-approved-read-only-probe"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["devices"][0]["state"], "online")
        self.assertNotIn("p" * 64, response.text)
        client_class.assert_called_once_with("192.168.2.11", "p" * 64, port=18768, timeout=2.0)

    def test_device_probe_surfaces_timeout_and_offline_per_device(self):
        devices = [
            {"name": "XP-A", "host": "192.168.2.11", "port": 18768, "token": "a" * 64},
            {"name": "XP-B", "host": "192.168.2.12", "port": 18768, "token": "b" * 64},
        ]
        with patch("api_server.read_registry", return_value=devices), patch("api_server.HermesXPClient") as client_class:
            client_class.return_value.network_status.side_effect = [TimeoutError(), RuntimeError("offline")]
            response = self.client.get("/api/dashboard/devices?confirm=1", headers={"X-Hermes-Dashboard-Confirm": "user-approved-read-only-probe"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([device["state"] for device in response.json()["devices"]], ["timeout", "offline"])

    def test_root_serves_dashboard_from_module_directory(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("HermesXP Management Dashboard", response.text)

    def test_dashboard_is_responsive_and_contains_no_fabricated_status_or_direct_xp_url(self):
        html = (Path(__file__).resolve().parents[1] / "local-server" / "dashboard.html").read_text()
        self.assertIn("name=\"viewport\"", html)
        self.assertIn("@media", html)
        self.assertIn("/api/dashboard/status", html)
        self.assertIn("/api/dashboard/devices", html)
        self.assertIn("X-Hermes-Dashboard-Confirm", html)
        self.assertIn("/api/screenshot", html)
        self.assertIn("/api/analyze", html)
        for fabricated in ("MainBot connected", "XP Discovery: ENABLED", "API not yet implemented", "192.168.1.78:18768"):
            self.assertNotIn(fabricated, html)


if __name__ == "__main__":
    unittest.main()
