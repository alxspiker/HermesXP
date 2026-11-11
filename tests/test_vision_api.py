import unittest
from unittest.mock import patch
import io
from PIL import Image
from fastapi import HTTPException
from fastapi.testclient import TestClient
from api_server import app
from tools.hermesxp_ui import HermesXPClient, ResponseTooLargeError

class TestVisionAPI(unittest.TestCase):
    """Tests for host-side screenshot analysis and CUA validation."""

    @staticmethod
    def bmp_bytes(width=80, height=60):
        image = Image.new("RGB", (width, height), "white")
        buffer = io.BytesIO()
        image.save(buffer, format="BMP")
        return buffer.getvalue()

    def test_remote_client_bounds_server_response_bytes(self):
        with patch("tools.hermesxp_ui.http.client.HTTPConnection") as connection_class, \
             patch("tools.hermesxp_ui._MAX_RESPONSE_BYTES", 4):
            connection_class.return_value.getresponse.return_value.status = 200
            connection_class.return_value.getresponse.return_value.read.return_value = b"12345"
            client = HermesXPClient("127.0.0.1", "a" * 64)
            with self.assertRaises(ResponseTooLargeError):
                client.screenshot()
            connection_class.return_value.getresponse.return_value.read.assert_called_once_with(5)

    def test_screenshot_route_selects_paired_device_without_exposing_secret(self):
        token = "a" * 64
        devices = [
            {"name": "XP-A", "host": "192.168.2.11", "port": 18768, "token": token},
            {"name": "XP-B", "host": "192.168.2.12", "port": 18768, "token": "b" * 64},
        ]
        with patch("api_server.read_registry", return_value=devices), \
             patch("api_server.HermesXPClient") as client_class:
            client_class.return_value.screenshot.return_value = self.bmp_bytes(320, 200)
            response = TestClient(app).get("/api/screenshot?device=XP-B")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "image/bmp")
        self.assertEqual(response.headers["x-hermesxp-width"], "320")
        self.assertEqual(response.headers["x-hermesxp-height"], "200")
        self.assertNotIn("token", response.text.lower())
        client_class.assert_called_once_with("192.168.2.12", "b" * 64, port=18768, timeout=5.0)

    def test_device_list_exposes_names_but_not_pairing_tokens(self):
        devices = [
            {"name": "XP-A", "host": "192.168.2.11", "port": 18768, "token": "a" * 64},
            {"name": "XP-B", "host": "192.168.2.12", "port": 18768, "token": "b" * 64},
        ]
        with patch("api_server.read_registry", return_value=devices):
            response = TestClient(app).get("/api/devices")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"devices": [{"name": "XP-A"}, {"name": "XP-B"}]})
        self.assertNotIn("token", response.text.lower())
        self.assertNotIn("aaaa", response.text)

    def test_screenshot_route_reports_missing_or_unknown_paired_device(self):
        client = TestClient(app)
        with patch("api_server.read_registry", return_value=[]):
            self.assertEqual(client.get("/api/screenshot").status_code, 503)
        devices = [{"name": "XP-A", "host": "192.168.2.11", "port": 18768, "token": "a" * 64}]
        with patch("api_server.read_registry", return_value=devices):
            self.assertEqual(client.get("/api/screenshot?device=not-paired").status_code, 404)

    def test_screenshot_route_requires_device_when_multiple_devices_are_paired(self):
        devices = [
            {"name": "XP-A", "host": "192.168.2.11", "port": 18768, "token": "a" * 64},
            {"name": "XP-B", "host": "192.168.2.12", "port": 18768, "token": "b" * 64},
        ]
        with patch("api_server.read_registry", return_value=devices):
            response = TestClient(app).get("/api/screenshot")
        self.assertEqual(response.status_code, 400)
        self.assertIn("device", response.json()["detail"].lower())

    def test_screenshot_route_reports_offline_timeout_and_invalid_image(self):
        devices = [{"name": "XP-A", "host": "192.168.2.11", "port": 18768, "token": "a" * 64}]
        client = TestClient(app)
        with patch("api_server.read_registry", return_value=devices), \
             patch("api_server.HermesXPClient") as client_class:
            client_class.return_value.screenshot.side_effect = RuntimeError("XP unavailable")
            self.assertEqual(client.get("/api/screenshot").status_code, 503)
            client_class.return_value.screenshot.side_effect = TimeoutError()
            self.assertEqual(client.get("/api/screenshot").status_code, 504)
            client_class.return_value.screenshot.side_effect = None
            client_class.return_value.screenshot.return_value = b"bad image"
            self.assertEqual(client.get("/api/screenshot").status_code, 502)
            client_class.return_value.screenshot.return_value = b"x" * (32 * 1024 * 1024 + 1)
            self.assertEqual(client.get("/api/screenshot").status_code, 502)

    def test_analyze_endpoint_returns_real_model_detections_separately(self):
        detections = [{"type": "button", "text": "OK", "bbox": [10, 20, 30, 40],
                      "confidence": 0.93, "source": "LFM3-VL"}]
        status = {"state": "verified", "model": "LFM3-VL-2B-QAD-Q4_0.gguf",
                  "last_success": 123.0, "error": None}
        with (
            patch("api_server.fetch_paired_screenshot", return_value=(self.bmp_bytes(), 80, 60)),
            patch("api_server.infer_lfm3vl", return_value=detections) as infer,
            patch("api_server.model_status", return_value=status),
        ):
            result = TestClient(app).get("/api/analyze?device=XP-A").json()
        self.assertEqual(result["analysis_mode"], "lfm3-vl")
        self.assertEqual(result["model"], status["model"])
        self.assertEqual(result["detections"], detections)
        self.assertEqual(result["suggestions"][0]["coords"], [62, 45])
        self.assertEqual(infer.call_args.args[0].size, (80, 60))

    def test_analyze_endpoint_reports_heuristics_without_fabricated_detection(self):
        with (
            patch("api_server.fetch_paired_screenshot", return_value=(self.bmp_bytes(), 80, 60)),
            patch("api_server.infer_lfm3vl", side_effect=RuntimeError("model unavailable")),
        ):
            result = TestClient(app).get("/api/analyze").json()

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["analysis_mode"], "heuristic")
        self.assertEqual(result["screenshot_size"], "80x60")
        self.assertEqual(result["suggestions"][0]["coords"], [62, 45])
        self.assertEqual(result["detections"], [])
        self.assertEqual(result["model_error"], "RuntimeError")
        self.assertIn("heuristic", result["note"].lower())
        for suggestion in result["suggestions"]:
            self.assertNotIn("lmf_reason", suggestion)
            self.assertIn("action", suggestion)
            self.assertIn("reason", suggestion)
            self.assertTrue(0 <= suggestion["coords"][0] < 80)
            self.assertTrue(0 <= suggestion["coords"][1] < 60)

    def test_custom_vision_provider_is_not_reported_as_lfm3(self):
        with (
            patch("api_server.fetch_paired_screenshot", return_value=(self.bmp_bytes(), 80, 60)),
            patch("api_server.infer_lfm3vl", return_value=[]),
            patch("api_server.model_status", return_value={
                "state": "verified", "model": "custom-vl",
                "backend": "openai-compatible", "last_success": 123.0, "error": None,
            }),
        ):
            client = TestClient(app)
            analysis = client.get("/api/analyze").json()
            status = client.get("/api/status").json()
        self.assertEqual(analysis["analysis_mode"], "vision-model")
        self.assertEqual(analysis["model"], "custom-vl")
        self.assertEqual(status["vision"], "vision-model")
        self.assertEqual(status["model"], "custom-vl")

    def test_status_reports_model_unavailable_and_simulated_cua(self):
        result = TestClient(app).get("/api/status").json()
        self.assertEqual(result["vision"], "heuristic-only")
        self.assertEqual(result["model"], "unavailable")
        self.assertEqual(result["cua"], "simulated-only")

    def test_status_reports_live_cua_opt_in_only_with_auth_configuration(self):
        import os
        configured = {
            "HERMES_CUA_TOKEN": "s" * 32,
            "HERMES_CUA_ALLOWED_IP": "127.0.0.1",
            "HERMES_CUA_LIVE_ENABLED": "1",
        }
        dashboard = {"services": [], "diagnostics": {"systemd": "available"}}
        with patch.dict(os.environ, configured), \
             patch("api_server.dashboard_status", return_value=dashboard), \
             patch("api_server.model_status", return_value={"state": "unavailable", "model": None}):
            result = TestClient(app).get("/api/status").json()
        self.assertEqual(result["cua"], "live-opt-in")

    def test_generate_heuristic_suggestions_returns_proportional_coords_for_various_sizes(self):
        from api_server import generate_heuristic_suggestions
        for w, h in [(800, 600), (1024, 768), (640, 480)]:
            suggestions = generate_heuristic_suggestions(w, h)
            self.assertEqual(len(suggestions), 7)
            for s in suggestions:
                self.assertIn("action", s)
                self.assertIn("coords", s)
                self.assertIn("confidence", s)
                self.assertIn("reason", s)
                x, y = s["coords"]
                self.assertTrue(0 <= x < w, f"X {x} out of bounds for width {w}")
                self.assertTrue(0 <= y < h, f"Y {y} out of bounds for height {h}")
                self.assertGreater(s["confidence"], 0.7)

    def test_analyze_endpoint_returns_error_for_unreadable_image(self):
        with patch("api_server.fetch_paired_screenshot", side_effect=HTTPException(502, "invalid screenshot")):
            result = TestClient(app).get("/api/analyze").json()
        self.assertEqual(result["status"], "error")

    def test_analyze_endpoint_returns_error_when_screenshot_fetch_fails(self):
        with patch("api_server.fetch_paired_screenshot", side_effect=HTTPException(503, "offline")):
            result = TestClient(app).get("/api/analyze").json()
        self.assertEqual(result["status"], "error")
        self.assertIn("Paired XP screenshot", result["note"])

    def test_cua_requires_exact_peer_and_validates_action_payload(self):
        import os
        from fastapi.testclient import TestClient
        from api_server import app
        os.environ["HERMES_CUA_TOKEN"] = "test-secret-token-0123456789abcdef"
        os.environ["HERMES_CUA_ALLOWED_IP"] = "not-testclient"
        try:
            response = TestClient(app).post("/api/cua/execute", json={
                "action": "click", "coords": [10, 20], "token": "test-secret-token-0123456789abcdef"
            })
            self.assertEqual(response.status_code, 403)
        finally:
            os.environ.pop("HERMES_CUA_TOKEN", None)
            os.environ.pop("HERMES_CUA_ALLOWED_IP", None)

    def test_cua_requires_credentials_and_text_for_typing(self):
        import os
        from fastapi.testclient import TestClient
        from api_server import app
        client = TestClient(app)
        response = client.post("/api/cua/execute", json={
            "action": "click", "coords": [10, 20], "token": "test-secret-token-0123456789abcdef"
        })
        self.assertEqual(response.status_code, 503)
        os.environ["HERMES_CUA_TOKEN"] = "test-secret-token-0123456789abcdef"
        os.environ["HERMES_CUA_ALLOWED_IP"] = "testclient"
        try:
            response = client.post("/api/cua/execute", json={
                "action": "type_text", "coords": [10, 20], "token": "test-secret-token-0123456789abcdef"
            })
            self.assertEqual(response.status_code, 422)
        finally:
            os.environ.pop("HERMES_CUA_TOKEN", None)
            os.environ.pop("HERMES_CUA_ALLOWED_IP", None)

    def test_cua_rejects_out_of_bounds_coordinates(self):
        import os
        from fastapi.testclient import TestClient
        from api_server import app
        os.environ["HERMES_CUA_TOKEN"] = "test-secret-token-0123456789abcdef"
        os.environ["HERMES_CUA_ALLOWED_IP"] = "testclient"
        try:
            response = TestClient(app).post("/api/cua/execute", json={
                "action": "click", "coords": [-1, 20], "token": "test-secret-token-0123456789abcdef"
            })
            self.assertEqual(response.status_code, 422)
        finally:
            os.environ.pop("HERMES_CUA_TOKEN", None)
            os.environ.pop("HERMES_CUA_ALLOWED_IP", None)

    def test_cua_rejects_invalid_action(self):
        import os
        from fastapi.testclient import TestClient
        from api_server import app
        os.environ["HERMES_CUA_TOKEN"] = "test-secret-token-0123456789abcdef"
        os.environ["HERMES_CUA_ALLOWED_IP"] = "testclient"
        try:
            response = TestClient(app).post("/api/cua/execute", json={
                "action": "shell", "coords": [1, 2], "token": "test-secret-token-0123456789abcdef"
            })
            self.assertEqual(response.status_code, 422)
        finally:
            os.environ.pop("HERMES_CUA_TOKEN", None)
            os.environ.pop("HERMES_CUA_ALLOWED_IP", None)

    def test_cua_rejects_short_configured_secret(self):
        import os
        from fastapi.testclient import TestClient
        from api_server import app
        os.environ["HERMES_CUA_TOKEN"] = "x" * 31
        os.environ["HERMES_CUA_ALLOWED_IP"] = "testclient"
        try:
            response = TestClient(app).post("/api/cua/execute", json={
                "action": "click", "coords": [1, 1], "token": "x" * 32
            })
            self.assertEqual(response.status_code, 503)
        finally:
            os.environ.pop("HERMES_CUA_TOKEN", None)
            os.environ.pop("HERMES_CUA_ALLOWED_IP", None)

    def test_cua_auth_handles_utf8_secret_safely(self):
        import os
        token = "é" * 32
        with patch.dict(os.environ, {
            "HERMES_CUA_TOKEN": token,
            "HERMES_CUA_ALLOWED_IP": "testclient",
        }):
            response = TestClient(app).post("/api/cua/execute", json={
                "action": "click", "coords": [1, 1], "token": token,
            })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["executed"])

    def test_cua_accepts_authenticated_action_only_as_simulation(self):
        import os
        from fastapi.testclient import TestClient
        from api_server import app
        token = "s" * 32
        os.environ["HERMES_CUA_TOKEN"] = token
        os.environ["HERMES_CUA_ALLOWED_IP"] = "testclient"
        try:
            response = TestClient(app).post("/api/cua/execute", json={
                "action": "click", "coords": [10, 20], "token": token
            })
            self.assertEqual(response.status_code, 200)
            self.assertFalse(response.json()["executed"])
        finally:
            os.environ.pop("HERMES_CUA_TOKEN", None)
            os.environ.pop("HERMES_CUA_ALLOWED_IP", None)

    def test_cua_routes_live_click_through_authenticated_paired_fixture(self):
        import os
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer

        browser_token = "s" * 32
        device_token = "d" * 64
        received = []

        class XPFixture(BaseHTTPRequestHandler):
            def do_GET(self):
                received.append((self.command, self.path, self.headers.get("X-Hermes-Token"), b""))
                body = b"width=800 height=600 title=Fixture"
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                received.append((self.command, self.path, self.headers.get("X-Hermes-Token"), body))
                reply = b"clicked"
                self.send_response(200)
                self.send_header("Content-Length", str(len(reply)))
                self.end_headers()
                self.wfile.write(reply)

            def log_message(self, format, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), XPFixture)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        env = {
            "HERMES_CUA_TOKEN": browser_token,
            "HERMES_CUA_ALLOWED_IP": "testclient",
            "HERMES_CUA_DEVICE": "Fixture",
            "HERMES_CUA_LIVE_ENABLED": "1",
        }
        registry = [{"name": "Fixture", "host": "127.0.0.1",
                     "token": device_token, "port": server.server_port}]
        try:
            with (
                patch.dict(os.environ, env),
                patch("api_server.read_registry", return_value=registry),
            ):
                client = TestClient(app)
                simulated = client.post("/api/cua/execute", json={
                    "action": "click", "coords": [13, 27], "token": browser_token,
                })
                executed = client.post("/api/cua/execute", json={
                    "action": "click", "coords": [13, 27], "token": browser_token,
                    "confirm_live": True,
                })
        finally:
            server.shutdown()
            thread.join(timeout=2)
            server.server_close()
        self.assertEqual(simulated.status_code, 200)
        self.assertFalse(simulated.json()["executed"])
        self.assertEqual(executed.status_code, 200, executed.text)
        self.assertTrue(executed.json()["executed"])
        self.assertTrue(executed.json()["verified"])
        self.assertEqual(executed.json()["device"], "Fixture")
        self.assertNotIn(device_token, executed.text)
        self.assertEqual(received, [
            ("GET", "/ui/inspect", device_token, b""),
            ("POST", "/ui/click", device_token, b"x=13&y=27&button=left"),
        ])

    def test_cua_dispatches_mouse_actions_with_verified_acknowledgements(self):
        import os
        token = "s" * 32
        registry = [{"name": "Lab", "host": "127.0.0.1", "token": "d" * 64, "port": 18768}]
        env = {
            "HERMES_CUA_TOKEN": token,
            "HERMES_CUA_ALLOWED_IP": "testclient",
            "HERMES_CUA_DEVICE": "Lab",
            "HERMES_CUA_LIVE_ENABLED": "1",
        }
        with (
            patch.dict(os.environ, env),
            patch("api_server.read_registry", return_value=registry),
            patch("api_server.HermesXPClient") as client_class,
        ):
            xp = client_class.return_value
            xp.inspect.return_value = "width=800 height=600 title=Fixture"
            xp.double_click.return_value = "double-clicked"
            xp.drag.return_value = "dragged"
            xp.scroll.return_value = "scrolled"
            client = TestClient(app)
            replies = [
                client.post("/api/cua/execute", json={
                    "action": "double_click", "coords": [5, 6], "token": token, "confirm_live": True,
                }),
                client.post("/api/cua/execute", json={
                    "action": "drag", "coords": [1, 2], "end_coords": [10, 20],
                    "token": token, "confirm_live": True,
                }),
                client.post("/api/cua/execute", json={
                    "action": "scroll", "coords": [5, 6], "delta": -2,
                    "token": token, "confirm_live": True,
                }),
            ]
        self.assertEqual([reply.status_code for reply in replies], [200, 200, 200])
        self.assertTrue(all(reply.json()["verified"] for reply in replies))
        xp.double_click.assert_called_once_with(5, 6, 800, 600)
        xp.drag.assert_called_once_with(1, 2, 10, 20, 800, 600)
        xp.scroll.assert_called_once_with(5, 6, 800, 600, -2)

    def test_cua_live_type_text_ack_does_not_echo_sensitive_payload(self):
        import os
        token = "t" * 32
        typed_text = "sensitive-example"
        registry = [{"name": "Lab", "host": "127.0.0.1", "token": "d" * 64, "port": 18768}]
        env = {
            "HERMES_CUA_TOKEN": token,
            "HERMES_CUA_ALLOWED_IP": "testclient",
            "HERMES_CUA_DEVICE": "Lab",
            "HERMES_CUA_LIVE_ENABLED": "1",
        }
        with (
            patch.dict(os.environ, env),
            patch("api_server.read_registry", return_value=registry),
            patch("api_server.HermesXPClient") as client_class,
        ):
            xp = client_class.return_value
            xp.type_text.return_value = "typed"
            response = TestClient(app).post("/api/cua/execute", json={
                "action": "type_text", "text": typed_text, "token": token, "confirm_live": True,
            })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["verified"])
        self.assertNotIn(typed_text, response.text)

    def test_cua_rejects_non_text_host_acknowledgement(self):
        import os
        token = "n" * 32
        registry = [{"name": "Lab", "host": "127.0.0.1", "token": "d" * 64, "port": 18768}]
        env = {
            "HERMES_CUA_TOKEN": token,
            "HERMES_CUA_ALLOWED_IP": "testclient",
            "HERMES_CUA_DEVICE": "Lab",
            "HERMES_CUA_LIVE_ENABLED": "1",
        }
        with (
            patch.dict(os.environ, env),
            patch("api_server.read_registry", return_value=registry),
            patch("api_server.HermesXPClient") as client_class,
        ):
            xp = client_class.return_value
            xp.inspect.return_value = "width=800 height=600 title=Fixture"
            xp.click.return_value = None
            response = TestClient(app, raise_server_exceptions=False).post("/api/cua/execute", json={
                "action": "click", "coords": [5, 6], "token": token, "confirm_live": True,
            })
        self.assertEqual(response.status_code, 502)
        self.assertNotEqual(response.json().get("status"), "success")

    def test_cua_rate_limits_live_actions_per_auth_identity(self):
        import os
        token = "r" * 32
        registry = [{"name": "Lab", "host": "127.0.0.1", "token": "d" * 64, "port": 18768}]
        env = {
            "HERMES_CUA_TOKEN": token,
            "HERMES_CUA_ALLOWED_IP": "testclient",
            "HERMES_CUA_DEVICE": "Lab",
            "HERMES_CUA_LIVE_ENABLED": "1",
        }
        with (
            patch.dict(os.environ, env),
            patch("api_server.read_registry", return_value=registry),
            patch("api_server.HermesXPClient") as client_class,
        ):
            xp = client_class.return_value
            xp.inspect.return_value = "width=800 height=600 title=Fixture"
            xp.click.return_value = "clicked"
            client = TestClient(app)
            replies = [client.post("/api/cua/execute", json={
                "action": "click", "coords": [5, 6], "token": token, "confirm_live": True,
            }) for _ in range(11)]
        self.assertEqual([reply.status_code for reply in replies[:10]], [200] * 10)
        self.assertEqual(replies[10].status_code, 429)
        self.assertEqual(xp.click.call_count, 10)

    def test_cua_rejects_live_action_with_unexpected_host_ack(self):
        import os
        token = "s" * 32
        registry = [{"name": "Lab", "host": "127.0.0.1", "token": "d" * 64, "port": 18768}]
        env = {
            "HERMES_CUA_TOKEN": token,
            "HERMES_CUA_ALLOWED_IP": "testclient",
            "HERMES_CUA_DEVICE": "Lab",
            "HERMES_CUA_LIVE_ENABLED": "1",
        }
        with (
            patch.dict(os.environ, env),
            patch("api_server.read_registry", return_value=registry),
            patch("api_server.HermesXPClient") as client_class,
        ):
            xp = client_class.return_value
            xp.inspect.return_value = "width=800 height=600 title=Fixture"
            xp.click.return_value = "unexpected"
            response = TestClient(app).post("/api/cua/execute", json={
                "action": "click", "coords": [5, 6], "token": token, "confirm_live": True,
            })
        self.assertEqual(response.status_code, 502)
        self.assertNotEqual(response.json().get("status"), "success")

    def test_cua_rejects_declared_oversized_body(self):
        from fastapi.testclient import TestClient
        from api_server import app
        response = TestClient(app).post("/api/cua/execute", content=b" " * 4097)
        self.assertEqual(response.status_code, 413)

    def test_cua_rejects_streamed_oversized_body_without_content_length(self):
        import asyncio
        from api_server import app
        from starlette.types import Scope

        scope: Scope = {
            "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
            "method": "POST", "scheme": "http", "path": "/api/cua/execute",
            "raw_path": b"/api/cua/execute", "query_string": b"",
            "headers": [(b"content-type", b"application/json")],
            "client": ("testclient", 123), "server": ("testserver", 80),
        }
        messages = [
            {"type": "http.request", "body": b" " * 3000, "more_body": True},
            {"type": "http.request", "body": b" " * 1097, "more_body": False},
        ]
        sent = []
        async def receive():
            return messages.pop(0)
        async def send(message):
            sent.append(message)
        asyncio.run(app(scope, receive, send))
        self.assertEqual(sent[0]["status"], 413)

if __name__ == '__main__':
    unittest.main()
