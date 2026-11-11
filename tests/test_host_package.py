import os
import pathlib
import subprocess
import tempfile
import unittest
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]

class PackageSecurityTests(unittest.TestCase):
    def test_failed_build_removes_preexisting_public_artifacts(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR')) as td:
            home = pathlib.Path(td) / 'home'
            package = home / 'msn-server/xp-package'
            stage = package / 'files'
            stage.mkdir(parents=True)
            (home / '.env').write_text('UNRELATED=value\n')
            (package / 'HermesXP.zip').write_bytes(b'legacy secret')
            (stage / 'hermesxp.ini').write_text('legacy secret')
            fakebin = pathlib.Path(td) / 'bin'
            fakebin.mkdir()
            bash = fakebin / 'bash'
            bash.write_text('#!/bin/sh\nexit 1\n')
            bash.chmod(0o755)
            env = dict(os.environ, HERMES_HOME=str(home), LAN_IP='192.168.42.3', PATH=str(fakebin)+os.pathsep+os.environ['PATH'])
            result = subprocess.run(['/bin/bash', str(ROOT/'local-server/build-xp-package.sh'), td], env=env, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((package / 'HermesXP.zip').exists())
            self.assertFalse(stage.exists())

    def test_installer_keeps_host_disabled_when_build_fails(self):
        script = (ROOT / 'local-server/install.sh').read_text()
        start = script.index('# Stop any old host before rebuilding:')
        end = script.index('\nlog "done.', start)
        section = script[start:end]
        with tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR')) as td:
            root = pathlib.Path(td)
            (root / 'build-xp-package.sh').write_text('exit 1\n')
            trace = root / 'trace'
            wrapper = 'systemctl() { printf "%s\\n" "$*" >> "$TRACE"; }\nwarn() { :; }\nlog() { :; }\n' + section
            result = subprocess.run(['/bin/bash', '-c', wrapper], env=dict(os.environ, SCRIPT_DIR=td, TRACE=str(trace)), capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(trace.read_text().splitlines(), ['--user disable --now hermes-xp-package.service', '--user enable --now hermes-xp-update.path hermes-xp-update.timer'])

    def test_package_excludes_passwords_and_stale_staging_files(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR')) as td:
            root = pathlib.Path(td)
            home = root / 'home'
            stage = home / 'msn-server/xp-package/files'
            stage.mkdir(parents=True)
            (stage / 'old-secret.txt').write_text('stale-private-password')
            (home / '.env').write_text('HERMES_MSN_OWNER_EMAIL=user@example.test\nHERMES_MSN_OWNER_PASSWORD=private-password\n')
            dll = home / 'msn-server/switcher-dl/escargot.dll'
            dll.parent.mkdir(parents=True)
            dll.write_bytes(b'dll')
            repo = root / 'repo'
            (repo / 'dist').mkdir(parents=True)
            (repo / 'dist/HermesXP.exe').write_bytes(b'exe')
            (repo / 'dist/HermesXP-Updater.exe').write_bytes(b'updater')
            (repo / 'dist/HermesXP-Service.exe').write_bytes(b'service')
            fakebin = root / 'bin'
            fakebin.mkdir()
            # Skip cross compiler without touching the working checkout.
            bash = fakebin / 'bash'
            bash.write_text('#!/bin/sh\ncase "$1" in */build-exe.sh) exit 0;; esac\nexec /bin/bash "$@"\n')
            bash.chmod(0o755)
            env = dict(os.environ, HERMES_HOME=str(home), LAN_IP='192.168.42.3', PATH=str(fakebin)+os.pathsep+os.environ['PATH'])
            subprocess.run(['/bin/bash', str(ROOT/'local-server/build-xp-package.sh'), str(repo)], env=env, check=True, capture_output=True)
            with zipfile.ZipFile(home/'msn-server/xp-package/HermesXP.zip') as archive:
                self.assertNotIn('old-secret.txt', archive.namelist())
                for name in archive.namelist():
                    data = archive.read(name)
                    self.assertNotIn(b'private-password', data, name)
                    self.assertNotIn(b'OwnerPassword=', data, name)
