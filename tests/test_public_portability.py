"""Public-install safeguards; no test reaches the XP device or starts services."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.validate_lan_ip import valid_lan_ip


ROOT = Path(__file__).resolve().parents[1]


class PortabilityTests(unittest.TestCase):
    def test_private_lan_networks_are_not_machine_specific(self):
        for address in ("10.9.8.7", "172.20.1.5", "192.168.88.1"):
            with self.subTest(address=address):
                self.assertTrue(valid_lan_ip(address))
        for address in ("", "127.0.0.1", "0.0.0.0", "8.8.8.8",
                        "100.101.22.3", "169.254.12.8",
                        "224.0.0.1", "192.168.1.3;touch /tmp/unsafe",
                        "localhost", "192.168.1.0/24", "::1"):
            with self.subTest(address=address):
                self.assertFalse(valid_lan_ip(address))

    def test_bad_ip_refuses_install_and_package_builder_clears_stale_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            package = home / "msn-server/xp-package/HermesXP.zip"
            package.parent.mkdir(parents=True)
            package.write_bytes(b"existing verified package")
            env = dict(os.environ, HERMES_HOME=str(home), LAN_IP="0.0.0.0")
            for script in ("install.sh", "build-xp-package.sh"):
                with self.subTest(script=script):
                    result = subprocess.run(
                        ["bash", str(ROOT / "local-server" / script)],
                        env=env, capture_output=True, text=True, timeout=5,
                    )
                    self.assertEqual(result.returncode, 2, result.stderr)
                    if script == "install.sh":
                        self.assertEqual(package.read_bytes(), b"existing verified package")
                    else:
                        self.assertFalse(package.exists())

    def test_bad_cert_ip_does_not_create_certificate_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "certs"
            result = subprocess.run(
                ["bash", str(ROOT / "local-server/make-ca.sh"), str(destination), "8.8.8.8"],
                capture_output=True, text=True, timeout=5,
            )
            self.assertEqual(result.returncode, 2)
            self.assertFalse(destination.exists())

    def test_manual_deploy_has_no_default_xp_machine(self):
        env = os.environ.copy()
        env.pop("XP_HOST", None)
        env.pop("HERMESXP_HOST", None)
        result = subprocess.run(
            ["bash", str(ROOT / "local-server/deploy-exe.sh")],
            env=env, capture_output=True, text=True, timeout=5,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("set XP_HOST", result.stderr)

    def test_public_switcher_files_are_templates_not_a_developer_address(self):
        for name in ("msnmsgr", "wlcomm"):
            template = ROOT / "local-server" / f"{name}.exe-escargot.ini.template"
            self.assertIn("__LAN_IP__", template.read_text())
            self.assertFalse((ROOT / "local-server" / f"{name}.exe-escargot.ini").exists())


if __name__ == "__main__":
    unittest.main()
