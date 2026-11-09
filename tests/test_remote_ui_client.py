import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from tools.hermesxp_ui import (HermesXPClient, validate_click, validate_key,
                              validate_text, validate_token, validate_service_command)


class RemoteUiClientValidationTests(unittest.TestCase):
    def test_client_sends_token_and_exact_control_body(self):
        received = {}

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                received["path"] = self.path
                received["token"] = self.headers.get("X-Hermes-Token")
                received["body"] = self.rfile.read(int(self.headers["Content-Length"]))
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"clicked")

            def log_message(self, *_args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            token = "0123456789abcdef" * 4
            client = HermesXPClient("127.0.0.1", token, port=server.server_port)
            result = client.click(5, 9, 100, 100)
            self.assertEqual(result, "clicked")
            self.assertEqual(received, {"path": "/ui/click", "token": token, "body": b"x=5&y=9&button=left"})
        finally:
            server.shutdown()
            thread.join(timeout=2)
            server.server_close()

    def test_token_must_be_64_hex_chars(self):
        self.assertTrue(validate_token("0123456789abcdef" * 4))
        self.assertFalse(validate_token("short"))
        self.assertFalse(validate_token("g" * 64))

    def test_click_is_bounded_by_screen(self):
        self.assertEqual(validate_click(0, 0, 1024, 768, "left"), (0, 0, "left"))
        self.assertEqual(validate_click(1023, 767, 1024, 768, "right"), (1023, 767, "right"))
        with self.assertRaises(ValueError):
            validate_click(1024, 0, 1024, 768, "left")
        with self.assertRaises(ValueError):
            validate_click(-1, 0, 1024, 768, "left")

    def test_text_and_keys_are_allowlisted(self):
        self.assertEqual(validate_text("Hello XP!"), b"Hello XP!")
        with self.assertRaises(ValueError):
            validate_text("line\nfeed")
        with self.assertRaises(ValueError):
            validate_text("x" * 129)
        self.assertEqual(validate_key("Enter"), b"Enter")
        with self.assertRaises(ValueError):
            validate_key("Win")

    def test_general_service_management_request_is_typed_and_authenticated(self):
        received = {}

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                received["path"] = self.path
                received["token"] = self.headers.get("X-Hermes-Token")
                received["body"] = self.rfile.read(int(self.headers["Content-Length"]))
                reply = b"service=AudioSrv state=running win32_error=0"
                self.send_response(200)
                self.send_header("Content-Length", str(len(reply)))
                self.end_headers()
                self.wfile.write(reply)

            def log_message(self, *_args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            token = "0123456789abcdef" * 4
            client = HermesXPClient("127.0.0.1", token, port=server.server_port)
            self.assertIn("state=running", client.service("AudioSrv", "status"))
            self.assertEqual(received, {
                "path": "/system/service", "token": token,
                "body": b"action=status&name=AudioSrv",
            })
        finally:
            server.shutdown()
            thread.join(timeout=2)
            server.server_close()

    def test_general_service_validation_rejects_command_injection(self):
        self.assertEqual(validate_service_command("Spooler", "restart"),
                         b"action=restart&name=Spooler")
        self.assertEqual(validate_service_command("MSSQL$SQLEXPRESS", "status"),
                         b"action=status&name=MSSQL$SQLEXPRESS")
        for name in ("", " Spooler", "Spooler ", "Spooler&action=stop",
                     "foo/bar", 'cmd" /c exit', "a" * 81, "a\nb"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate_service_command(name, "status")
        for action in ("", "delete", "install", "config", "start&name=foo"):
            with self.subTest(action=action), self.assertRaises(ValueError):
                validate_service_command("Spooler", action)


if __name__ == "__main__":
    unittest.main()
