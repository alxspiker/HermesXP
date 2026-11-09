"""Authenticated LAN updates, strict PE validation and retry behavior."""
from __future__ import annotations

import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import socket
import tempfile
import threading
import unittest
from unittest.mock import patch

from tools import hermesxp_update as client


ROOT = Path(__file__).resolve().parents[1]
TOKEN = "a" * 64


class XPUpdateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = (ROOT / "dist/HermesXP.exe").read_bytes()

    def test_pe_xp_and_size_checked(self):
        self.assertEqual(client.validate_binary(self.image), hashlib.sha256(self.image).hexdigest())
        for invalid in (b"MZ", b"hello" * 10000, b"MZ" + b"0" * 600000):
            with self.assertRaises(client.UpdateError):
                client.validate_binary(invalid)

    def test_device_registry_permissions_and_secret_handling(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "devices.json"
            device = {"name": "XP", "host": "192.168.1.84", "token": TOKEN}
            client.save_registry([device], p)
            self.assertEqual(p.stat().st_mode & 0o777, 0o600)
            self.assertEqual(client.read_registry(p)[0]["token"], TOKEN)
            p.chmod(0o644)
            with self.assertRaises(client.UpdateError):
                client.read_registry(p)
            for invalid in ("8.8.8.8", "fe80::1", "not-an-ip"):
                with self.assertRaises(ValueError):
                    client.validate_device({**device, "host": invalid})

    def test_authenticated_hash_upload_and_health_poll(self):
        current = "f" * 64
        desired = hashlib.sha256(self.image).hexdigest()
        requests = []

        class FakeXP(BaseHTTPRequestHandler):
            def do_GET(self):
                requests.append(("GET", self.path, self.headers.get("X-Hermes-Token")))
                if self.headers.get("X-Hermes-Token") != TOKEN:
                    self.send_error(401)
                    return
                data = b"sha256=" + (desired if any(x[0] == "POST" for x in requests) else current).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                requests.append(("POST", self.path, self.headers.get("X-Hermes-Token"), body))
                if (self.headers.get("X-Hermes-Token") != TOKEN
                        or self.headers.get("X-Hermes-SHA256") != desired
                        or body != XPUpdateTests.image):
                    self.send_error(401)
                    return
                data = b"verified; restarting"
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, fmt, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), FakeXP)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            device = {"name": "test", "host": "127.0.0.1", "port": server.server_port, "token": TOKEN}
            with patch.object(client.time, "sleep", lambda _: None):
                result = client.deploy(device, self.image, poll_seconds=5)
            self.assertEqual(result, "updated")
            self.assertEqual([r[0] for r in requests], ["GET", "POST", "GET"])
            self.assertEqual(requests[1][3], self.image)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(2)

    def test_offline_devices_stay_pending(self):
        with tempfile.TemporaryDirectory() as td:
            registry = Path(td) / "devices.json"
            device = {"name": "offline", "host": "127.0.0.1", "port": 1, "token": TOKEN}
            client.save_registry([device], registry)
            result = client.deploy_fleet(ROOT / "dist/HermesXP.exe", registry=registry)
            self.assertEqual(result, {"offline": "pending"})

    def test_xp_candidate_preflight_before_live_binary_swap(self):
        receiver = (ROOT / "xp-client/update_receiver.h").read_text()
        gui = (ROOT / "xp-client/hermesxp.c").read_text()
        rollback = (ROOT / "xp-client/hermesxp-updater.c").read_text()
        self.assertIn('update_preflight(pending)', receiver)
        self.assertLess(receiver.index('update_preflight(pending)'),
                        receiver.index('send_http_text(sock,"200 OK","verified; restarting")'))
        self.assertIn('/update-selftest', gui)
        self.assertIn('ExitProcess(0)', gui)
        self.assertIn('preflight(pending)', rollback)
        self.assertLess(rollback.index('preflight(pending)'),
                        rollback.index('MoveFileExA(live,backup'))
        self.assertIn('HermesXP.failed.exe', rollback)
        self.assertIn('MoveFileExA(backup,live', rollback)


if __name__ == "__main__":
    unittest.main()
