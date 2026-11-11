import copy
import hashlib
import subprocess
import tempfile
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from tools.lan_discovery import (Discovery, host_leaf_matches_ip, identity,
                                 reconcile_host_ip, reissue_host_leaf_if_needed, sign)


TOKEN = "d" * 64


class TestAuthenticatedLanDiscovery(unittest.TestCase):
    def setUp(self):
        self.device = {"name": "XP-Example", "host": "192.168.5.22",
                       "token": TOKEN, "port": 18768}
        self.saved = [self.device]
        self.save = Mock(side_effect=self._save)
        self.restart = Mock()
        self.reconfigure = Mock(return_value=False)
        self.notify_update = Mock()
        self.discovery = Discovery(devices=lambda: copy.deepcopy(self.saved),
                                   save=self.save,
                                   resolve=lambda ip: "192.168.5.8",
                                   restart=self.restart, reconfigure=self.reconfigure,
                                   notify_update=self.notify_update)
        self.transport = Mock()
        self.discovery.connection_made(self.transport)

    def _save(self, new):
        self.saved = copy.deepcopy(new)

    def handshake(self, ip="192.168.5.92", host_ip="192.168.5.8"):
        device_id = identity(TOKEN)
        nonce = "1122334455667788"
        request = f"HXP1 {device_id} {nonce}"
        self.discovery.datagram_received(f"{request} {sign(TOKEN, request)}".encode(),
                                         (ip, 30001))
        sent, destination = self.transport.sendto.call_args.args
        self.assertEqual(destination, (ip, 30001))
        fields = sent.decode().split(" ")
        self.assertEqual(fields[:2], ["HXP2", nonce])
        self.assertEqual(fields[3], host_ip)
        self.assertEqual(fields[4], sign(TOKEN, " ".join(fields[:4])))
        ack = f"HXP3 {device_id} {nonce} {fields[2]}"
        self.discovery.datagram_received(f"{ack} {sign(TOKEN, ack)}".encode(),
                                         (ip, 30001))
        return ack

    def test_authenticated_xp_address_change_updates_registry(self):
        self.handshake()
        self.assertEqual(self.saved[0]["host"], "192.168.5.92")
        self.save.assert_called_once()
        self.restart.assert_called_once()
        self.notify_update.assert_called_once()
        self.assertEqual(self.saved[0]["token"], TOKEN)

    def test_same_address_never_restarts_bridge(self):
        self.handshake("192.168.5.22")
        self.save.assert_not_called()
        self.restart.assert_not_called()
        self.notify_update.assert_called_once()

    def test_repeated_authenticated_heartbeats_are_throttled(self):
        self.handshake()
        self.notify_update.assert_called_once()
        self.handshake()
        self.notify_update.assert_called_once()
        with patch("tools.lan_discovery.time.monotonic", return_value=10**10):
            self.handshake()
        self.notify_update.assert_called()
        self.assertEqual(self.notify_update.call_count, 2)

    def test_invalid_mac_cannot_move_device(self):
        request = f"HXP1 {identity(TOKEN)} 1122334455667788"
        self.discovery.datagram_received(f"{request} {'0'*64}".encode(),
                                         ("192.168.5.200", 30001))
        self.transport.sendto.assert_not_called()
        self.save.assert_not_called()
        self.restart.assert_not_called()

    def test_ack_requires_same_source_and_valid_mac(self):
        device_id, nonce = identity(TOKEN), "1122334455667788"
        request = f"HXP1 {device_id} {nonce}"
        self.discovery.datagram_received(f"{request} {sign(TOKEN, request)}".encode(),
                                         ("192.168.5.92", 30001))
        challenge = self.transport.sendto.call_args.args[0].decode().split()
        ack = f"HXP3 {device_id} {nonce} {challenge[2]}"
        self.discovery.datagram_received(f"{ack} {sign(TOKEN, ack)}".encode(),
                                         ("192.168.5.93", 30001))
        self.save.assert_not_called()
        self.discovery.datagram_received(f"{ack} {'0'*64}".encode(),
                                         ("192.168.5.92", 30001))
        self.save.assert_not_called()

    def test_repeated_valid_hello_is_not_replayable_without_new_ack(self):
        self.handshake()
        self.save.reset_mock()
        self.restart.reset_mock()
        self.handshake()
        self.save.assert_not_called()
        self.restart.assert_not_called()

    def test_public_sources_and_malformed_frames_rejected(self):
        for source in ("8.8.8.8", "127.0.0.1", "169.254.5.3"):
            self.discovery.datagram_received(b"HXP1 bad", (source, 30001))
        self.discovery.datagram_received(b"HXP1 \0 noise", ("192.168.5.22", 30001))
        self.discovery.datagram_received(b"x" * 500, ("192.168.5.22", 30001))
        self.transport.sendto.assert_not_called()

    def test_managed_host_address_rewrites_only_managed_config(self):
        with tempfile.TemporaryDirectory() as root:
            home = Path(root)
            server = home / ".hermes" / "msn-server"
            server.mkdir(parents=True)
            local = server / "settings_local.py"
            local.write_text(
                "TARGET_HOST = '192.168.1.81'\n"
                "LOGIN_HOST = '192.168.1.81'\n"
                "STORAGE_HOST = '192.168.1.81'\n"
                "EXTRA_USER_SETTING='preserve-this'\n"
            )
            tls = server / "stunnel.conf"
            tls.write_text("[msn]\naccept = 192.168.1.81:443\nconnect=127.0.0.1:8081\n")
            with patch("tools.lan_discovery.subprocess.Popen") as restarted:
                self.assertTrue(reconcile_host_ip("192.168.2.44", home=home))
                self.assertFalse(reconcile_host_ip("192.168.2.44", home=home))
                self.assertEqual(restarted.call_count, 2)
            content = local.read_text()
            self.assertIn("EXTRA_USER_SETTING='preserve-this'", content)
            self.assertIn("TARGET_HOST = '192.168.2.44'", content)
            self.assertIn("LOGIN_HOST = '192.168.2.44'", content)
            self.assertIn("STORAGE_HOST = '192.168.2.44'", content)
            self.assertIn("accept = 192.168.2.44:443", tls.read_text())

    def test_host_ip_change_after_handshake_reconfigures_and_restarts(self):
        self.handshake("192.168.5.22")
        self.discovery.resolve = lambda ip: "192.168.5.9"
        self.reconfigure.return_value = True
        self.handshake("192.168.5.22", host_ip="192.168.5.9")
        self.save.assert_not_called()
        self.restart.assert_called_once()

    def test_host_ip_migration_updates_package_host_binding(self):
        with tempfile.TemporaryDirectory() as root:
            home = Path(root)
            server = home / ".hermes/msn-server"
            server.mkdir(parents=True)
            (server / "settings_local.py").write_text("TARGET_HOST = '192.168.1.81'\n")
            unit = home / ".config/systemd/user/hermes-xp-package.service"
            unit.parent.mkdir(parents=True)
            unit.write_text("ExecStart=/usr/bin/python3 -m http.server 18767 --bind 192.168.1.81\n")
            with (
                patch("tools.lan_discovery.subprocess.Popen") as restarted,
                patch("tools.lan_discovery.subprocess.run") as run,
            ):
                self.assertTrue(reconcile_host_ip("192.168.5.19", home=home))
            self.assertIn("--bind 192.168.5.19", unit.read_text())
            run.assert_called_once()
            self.assertEqual(run.call_args.args[0], ["systemctl", "--user", "daemon-reload"])
            restarted.assert_any_call(
                ["systemctl", "--user", "try-restart", "hermes-xp-package.service"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
            )

    def test_tls_leaf_ip_san_rotates_under_same_ca_without_changing_private_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            certs = Path(tmp)
            ca = certs / "ca.pem"
            ca_key = certs / "ca-key.pem"
            server_key = certs / "server-key.pem"
            server = certs / "server.pem"
            csr = certs / "old.csr"
            ext = certs / "old.ext"
            def run(*args):
                subprocess.run(["openssl", *map(str, args)],
                               check=True, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=18)
            run("req", "-x509", "-newkey", "rsa:2048", "-nodes",
                "-keyout", ca_key, "-out", ca, "-days", "5",
                "-subj", "/CN=HermesXP Test CA")
            run("genrsa", "-out", server_key, "2048")
            run("req", "-new", "-key", server_key,
                "-subj", "/CN=192.168.1.81", "-out", csr)
            ext.write_text("subjectAltName=IP:192.168.1.81,DNS:msn.local\n")
            run("x509", "-req", "-in", csr, "-CA", ca, "-CAkey", ca_key,
                "-CAcreateserial", "-extfile", ext, "-out", server)
            before_ca = hashlib.sha256(ca.read_bytes()).hexdigest()
            before_server_key = hashlib.sha256(server_key.read_bytes()).hexdigest()
            self.assertTrue(reissue_host_leaf_if_needed(certs, "192.168.6.12"))
            self.assertFalse(reissue_host_leaf_if_needed(certs, "192.168.6.12"))
            self.assertTrue(host_leaf_matches_ip(server, "192.168.6.12"))
            self.assertFalse(host_leaf_matches_ip(server, "192.168.6.1"))
            san = subprocess.run(["openssl", "x509", "-in", str(server),
                                  "-noout", "-ext", "subjectAltName"],
                                 capture_output=True, text=True, check=True).stdout
            self.assertIn("IP Address:192.168.6.12", san)
            self.assertIn("DNS:msn.local", san)
            self.assertEqual(hashlib.sha256(ca.read_bytes()).hexdigest(), before_ca)
            self.assertEqual(hashlib.sha256(server_key.read_bytes()).hexdigest(), before_server_key)

    def test_cert_renewal_failure_does_not_migrate_host_endpoints(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            root = home / ".hermes" / "msn-server"
            certs = root / "certs"
            certs.mkdir(parents=True)
            (certs / "server.pem").write_text("invalid certificate")
            settings = root / "settings_local.py"
            settings.write_text("TARGET_HOST = '192.168.1.81'\n")
            tls = root / "stunnel.conf"
            tls.write_text("[msn]\naccept = 192.168.1.81:443\n")
            # Patch only service restarts. OpenSSL's subprocess.run itself
            # needs Popen, so a blanket mock would corrupt certificate tests.
            real_popen = subprocess.Popen
            def forbid_restart(args, *other, **kwargs):
                if args and args[0] == "systemctl":
                    raise AssertionError("must not restart services with invalid TLS")
                return real_popen(args, *other, **kwargs)
            with patch("tools.lan_discovery.subprocess.Popen", side_effect=forbid_restart):
                self.assertFalse(reconcile_host_ip("192.168.4.55", home=home))
            self.assertIn("192.168.1.81", settings.read_text())
            self.assertIn("192.168.1.81", tls.read_text())


if __name__ == "__main__":
    unittest.main()
