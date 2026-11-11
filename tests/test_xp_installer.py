"""The XP installer should register an app without erasing local pairing data."""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "xp-client/HermesXP-Setup.nsi"
BUILDER = ROOT / "local-server/build-xp-installer.sh"
FILES = (
    "HermesXP.exe",
    "HermesXP-Updater.exe",
    "HermesXP-Service.exe",
    "hermesxp.ini",
    "README.txt",
    "ca.pem",
    "escargot.dll",
    "msnmsgr.exe-escargot.ini",
    "wlcomm.exe-escargot.ini",
)


class XPInstallerTests(unittest.TestCase):
    def test_installer_has_windows_registration_and_uninstall(self):
        source = SCRIPT.read_text()
        self.assertIn('RequestExecutionLevel admin', source)
        self.assertIn('InstallDir "$PROGRAMFILES\\HermesXP"', source)
        self.assertIn('IfFileExists "C:\\HermesXP\\HermesXP.exe"', source)
        self.assertIn('IfFileExists "$INSTDIR\\hermesxp.ini" config_ready', source)
        self.assertIn('WriteUninstaller "$INSTDIR\\Uninstall.exe"', source)
        self.assertIn('Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\HermesXP', source)
        self.assertIn('CreateShortCut "$SMPROGRAMS\\HermesXP\\HermesXP.lnk"', source)
        self.assertIn('CreateShortCut "$DESKTOP\\HermesXP.lnk"', source)
        self.assertIn('Section "Uninstall"', source)
        self.assertNotIn('Delete "$INSTDIR\\hermesxp.ini"', source)
        self.assertNotIn('RMDir /r "$INSTDIR"', source)
        self.assertIn('File "${INPUT_DIR}/HermesXP-Service.exe"', source)
        self.assertIn('HermesXP-Service.exe" /install', source)
        self.assertIn('HermesXP-Service.exe" /remove', source)
        self.assertIn('Software\\Microsoft\\Windows\\CurrentVersion\\Run', source)
        self.assertIn('DeleteRegValue HKLM', source)
        self.assertIn('WriteRegStr HKLM', source)
        self.assertIn('Section "Configure installed Windows Live Messenger" SEC_MSN', source)
        self.assertIn('ExecWait \'"$INSTDIR\\HermesXP.exe" /setup-msn\'', source)
        self.assertIn('Section -LaunchCompanion', source)
        self.assertLess(source.index('SEC_MSN\n'),source.index('Section -LaunchCompanion'))
        self.assertIn('IfSilent msn_component_error_done', source)

    def test_legacy_msn_password_does_not_abort_installer(self):
        source = (ROOT / 'xp-client/hermesxp.c').read_text()
        self.assertIn('if(g_owner[0] && g_ownerPw[0] && !pwBad)', source)
        self.assertNotIn('return 3;', source)
        self.assertIn('Existing sign-in credentials remain untouched.', source)

    @unittest.skipUnless(shutil.which("makensis"), "NSIS not available")
    def test_builds_xp_native_gui_setup_from_package_stage(self):
        with tempfile.TemporaryDirectory(prefix="hermesxp-setup-") as td:
            home = pathlib.Path(td)
            stage = home / "msn-server/xp-package/files"
            stage.mkdir(parents=True)
            for name in FILES:
                (stage / name).write_bytes(b"test payload " + name.encode())
            env = dict(os.environ, HERMES_HOME=str(home))
            result = subprocess.run(
                ["/bin/bash", str(BUILDER), str(ROOT)],
                env=env, capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            setup = home / "msn-server/xp-package/HermesXP-Setup.exe"
            self.assertGreater(setup.stat().st_size, 30_000)
            self.assertEqual(setup.read_bytes()[:2], b"MZ")


if __name__ == "__main__":
    unittest.main()
