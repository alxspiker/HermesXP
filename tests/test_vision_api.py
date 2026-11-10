import unittest
from unittest.mock import patch, MagicMock
import requests
import io
from PIL import Image
from fastapi.testclient import TestClient
from api_server import app

class TestVisionAPI(unittest.TestCase):
    """Tests for host-side screenshot analysis and CUA validation."""

    @staticmethod
    def bmp_bytes(width=80, height=60):
        image = Image.new("RGB", (width, height), "white")
        buffer = io.BytesIO()
        image.save(buffer, format="BMP")
        return buffer.getvalue()

    def test_analyze_endpoint_returns_scaled_heuristic_suggestions(self):
        response = MagicMock()
        response.content = self.bmp_bytes()
        response.raise_for_status.return_value = None
        with patch("api_server.requests.get", return_value=response):
            result = TestClient(app).get("/api/analyze").json()

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["analysis_mode"], "heuristic")
        self.assertEqual(result["screenshot_size"], "80x60")
        self.assertEqual(result["suggestions"][0]["coords"], [62, 45])
        self.assertEqual(result["detected"], [])
        for suggestion in result["suggestions"]:
            self.assertEqual(set(suggestion) & {"action", "coords", "confidence", "reason"},
                             {"action", "coords", "confidence", "reason"})
            self.assertTrue(0 <= suggestion["coords"][0] < 80)
            self.assertTrue(0 <= suggestion["coords"][1] < 60)

    def test_analyze_endpoint_returns_error_for_unreadable_image(self):
        response = MagicMock()
        response.content = b"not a bitmap"
        response.raise_for_status.return_value = None
        with patch("api_server.requests.get", return_value=response):
            result = TestClient(app).get("/api/analyze").json()
        self.assertEqual(result["status"], "error")

    def test_analyze_endpoint_returns_error_when_screenshot_fetch_fails(self):
        with patch("api_server.requests.get", side_effect=requests.exceptions.ConnectionError("offline")):
            result = TestClient(app).get("/api/analyze").json()
        self.assertEqual(result["status"], "error")
        self.assertIn("Screenshot endpoint unavailable", result["note"])

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
                "action": "click", "token": "x" * 32
            })
            self.assertEqual(response.status_code, 503)
        finally:
            os.environ.pop("HERMES_CUA_TOKEN", None)
            os.environ.pop("HERMES_CUA_ALLOWED_IP", None)

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
