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

            def log_message(self, format, *args):
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

    def test_interrupted_update_stream_is_not_reported_as_success(self):
        original = hashlib.sha256(b"previous XP image").hexdigest()
        state = {"digest": original, "partial": False}
        requests = []

        class InterruptedXP(BaseHTTPRequestHandler):
            def do_GET(self):
                requests.append("GET")
                body = b"sha256=" + state["digest"].encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                requests.append("POST")
                self.rfile.read(128)
                state["partial"] = True
                self.close_connection = True
                self.connection.close()

            def log_message(self, format, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), InterruptedXP)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            device = {"name": "interrupted", "host": "127.0.0.1",
                      "port": server.server_port, "token": TOKEN}
            with self.assertRaises(client.UpdateError):
                client.deploy(device, self.image, poll_seconds=1)
            self.assertEqual(requests, ["GET", "POST"])
            self.assertTrue(state["partial"])
            self.assertEqual(state["digest"], original)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(2)

    def test_unhealthy_candidate_that_rolls_back_is_not_reported_as_updated(self):
        original = hashlib.sha256(b"previous XP image").hexdigest()
        desired = hashlib.sha256(self.image).hexdigest()
        state = {"digest": original, "staged": None, "rollback": False}

        class RollbackXP(BaseHTTPRequestHandler):
            def do_GET(self):
                body = b"sha256=" + state["digest"].encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                if (body != XPUpdateTests.image or
                        self.headers.get("X-Hermes-SHA256") != desired):
                    self.send_error(400)
                    return
                state["staged"] = desired
                state["rollback"] = True
                response = b"verified; restarting"
                self.send_response(200)
                self.send_header("Content-Length", str(len(response)))
                self.end_headers()
                self.wfile.write(response)

            def log_message(self, format, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), RollbackXP)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            device = {"name": "rollback", "host": "127.0.0.1",
                      "port": server.server_port, "token": TOKEN}
            with patch.object(client.time, "sleep", lambda _: None):
                with self.assertRaisesRegex(client.UpdateError, "did not become healthy"):
                    client.deploy(device, self.image, poll_seconds=0.02)
            self.assertTrue(state["rollback"])
            self.assertEqual(state["staged"], desired)
            self.assertEqual(state["digest"], original)
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

    def test_helper_readiness_handshake_precedes_client_shutdown(self):
        gui = (ROOT / "xp-client/update_receiver.h").read_text()
        helper = (ROOT / "xp-client/hermesxp-updater.c").read_text()
        self.assertIn("HXP_UPDATER_READY_EVENT", gui)
        self.assertIn("HXP_UPDATER_GO_EVENT", gui)
        self.assertIn("OpenEventA", helper)
        self.assertIn("SetEvent(ready_event)", helper)
        self.assertIn("WaitForSingleObject(go_event,8000)", helper)
        self.assertLess(gui.index("update_start_helper(dir,&go_signal)"),
                        gui.index("PostMessageA(g_main_window,WM_CLOSE"))
        self.assertLess(gui.index("SetEvent(go_signal)"),
                        gui.index("PostMessageA(g_main_window,WM_CLOSE"))
        self.assertIn("HermesXP-update.log", helper)
        self.assertIn('trace("previous-image-restored",0)', helper)

    def test_new_process_must_signal_its_own_listener(self):
        gui = (ROOT / "xp-client/hermesxp.c").read_text()
        helper = (ROOT / "xp-client/hermesxp-updater.c").read_text()
        self.assertIn(r'"Local\\HermesXP.Updated.GuiReady"', gui)
        self.assertIn(r'"Local\\HermesXP.Updated.GuiReady"', helper)
        self.assertIn('g_update_activation', gui)
        self.assertIn('OpenEventA(0x0002u,0,', gui)
        self.assertIn('SetEvent(ready)', gui)
        self.assertIn('WaitForSingleObject(gui_event,500)', helper)
        self.assertIn('WaitForSingleObject(child.process,0)', helper)
        self.assertIn(' /update-activation', helper)
        self.assertLess(gui.index('if(listen(srv,5)!=0)'),
                        gui.index('SetEvent(ready);CloseHandle(ready);'))
        self.assertIn('OpenMutexA(SYNCHRONIZE,0,HXP_SINGLE_INSTANCE_MUTEX)',helper)
        self.assertLess(helper.index('trace("old-gui-exited",0)'),
                        helper.index('MoveFileExA(live,backup'))

    def test_helper_handshake_prevents_stranding_old_gui(self):
        receiver = (ROOT / "xp-client/update_receiver.h").read_text()
        helper = (ROOT / "xp-client/hermesxp-updater.c").read_text()
        self.assertIn('CreateEventA(NULL,1,0,HXP_UPDATER_READY_EVENT)', receiver)
        self.assertIn('CreateEventA(NULL,1,0,HXP_UPDATER_GO_EVENT)', receiver)
        self.assertIn('WaitForSingleObject(ready,6000)', receiver)
        self.assertIn('WaitForSingleObject(proc.process,0)', receiver)
        self.assertIn('SetEvent(go_signal)', receiver)
        self.assertLess(receiver.index('SetEvent(go_signal)'),
                        receiver.index('PostMessageA(g_main_window,WM_CLOSE'))
        self.assertIn('OpenEventA(EVENT_MODIFY_STATE|SYNCHRONIZE', helper)
        self.assertIn('SetEvent(ready_event)', helper)
        self.assertIn('WaitForSingleObject(go_event,8000)', helper)
        self.assertLess(helper.index('WaitForSingleObject(go_event,8000)'),
                        helper.index('MoveFileExA(live,backup'))
        self.assertIn('previous-image-restored', helper)
        self.assertIn('previous-process-restarted', helper)

    def test_xp_health_probe_is_bounded_and_checks_actual_child(self):
        helper = (ROOT / "xp-client/hermesxp-updater.c").read_text()
        self.assertIn('ioctlsocket(sock,HXP_FIONBIO,&nonblocking)', helper)
        self.assertIn('deadline.tv_usec=200000', helper)
        self.assertIn('select(0,NULL,&writable,NULL,&deadline)', helper)
        self.assertIn('getsockopt(sock,HXP_SOL_SOCKET,HXP_SO_ERROR', helper)
        self.assertIn('WaitForSingleObject(gui_event,500)', helper)
        self.assertIn('WaitForSingleObject(child.process,0)!=WAIT_OBJECT_0 && ready()', helper)
        self.assertIn('trace("new-process-failed-health",0)', helper)

    def test_xp_gui_enforces_one_interactive_listener(self):
        gui = (ROOT / "xp-client/hermesxp.c").read_text()
        self.assertIn('CreateMutexA(NULL,0,"Local\\\\HermesXP.Companion.SingleInstance")', gui)
        self.assertIn('if(!cl || !str_find(cl,"/update-selftest"))', gui)
        self.assertIn('GetLastError()==183', gui)
        self.assertLess(gui.index('CreateMutexA(NULL,0,'),
                        gui.index('CreateThread(NULL,0,screenshot_server'))


if __name__ == "__main__":
    unittest.main()
