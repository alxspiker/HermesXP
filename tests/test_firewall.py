import importlib.util
import pathlib
import unittest
from subprocess import CompletedProcess
from unittest.mock import patch

PATH = pathlib.Path(__file__).resolve().parents[1] / 'local-server' / 'setup-firewall.py'


def load():
    spec = importlib.util.spec_from_file_location('firewall', PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FirewallTests(unittest.TestCase):
    def test_sudo_noninteractive_executes_only_absolute_ufw(self):
        m = load()
        commands = []
        def run(cmd, **kwargs):
            commands.append(cmd)
            self.assertNotIn('shell', kwargs)
            if cmd[-1] == 'status':
                output = 'Status: active\n'
                if len(commands) > 1:
                    output += ''.join(f'{p}/tcp ALLOW IN 192.168.1.4\n' for p in (443, 1863, 1864))
                return CompletedProcess(cmd, 0, output, '')
            return CompletedProcess(cmd, 0, '', '')
        with patch.object(m.os, 'geteuid', return_value=1000), patch.object(m, 'trusted_executable', return_value=True, create=True), patch.object(m.subprocess, 'run', side_effect=run):
            self.assertEqual(m.configure('192.168.1.4'), 0)
        self.assertEqual(commands, [['/usr/bin/sudo', '-n', '/usr/sbin/ufw', 'status']] + [['/usr/bin/sudo', '-n', '/usr/sbin/ufw', 'allow', 'in', 'proto', 'tcp', 'from', '192.168.1.4', 'to', 'any', 'port', str(p)] for p in (443, 1863, 1864)] + [['/usr/bin/sudo', '-n', '/usr/sbin/ufw', 'status']])

    def test_invalid_inputs_never_execute(self):
        m = load()
        with patch.object(m.subprocess, 'run') as run:
            for ip in ('192.168.1.0/24', '0.0.0.0', '127.0.0.1', '224.0.0.1', '1.2.3.255', '1.2.3.4;id', 'bad'):
                self.assertEqual(m.configure(ip), 1)
            run.assert_not_called()

    def test_interactive_sudo_retry_only_when_terminal(self):
        m = load()
        responses = [CompletedProcess([], 1, '', 'password needed'), CompletedProcess([], 0, 'Status: inactive\n', None)]
        with patch.object(m.os, 'geteuid', return_value=1000), patch.object(m, 'trusted_executable', return_value=True), patch.object(m.sys.stdin, 'isatty', return_value=True), patch.object(m.sys.stderr, 'isatty', return_value=True), patch.object(m.subprocess, 'run', side_effect=responses) as run:
            self.assertEqual(m.configure('192.168.1.4'), 0)
            self.assertEqual(run.call_args_list[1].args[0], ['/usr/bin/sudo', '/usr/sbin/ufw', 'status'])
            self.assertIsNone(run.call_args_list[1].kwargs['stderr'])

    def test_failed_sudo_noninteractive_stops(self):
        m = load()
        with patch.object(m.os, 'geteuid', return_value=1000), patch.object(m, 'trusted_executable', return_value=True), patch.object(m.sys.stdin, 'isatty', return_value=False), patch.object(m.subprocess, 'run', return_value=CompletedProcess([], 1, '', 'denied')) as run:
            self.assertEqual(m.configure('192.168.1.4'), 1)
            self.assertEqual(run.call_count, 1)

    def test_inactive_or_unrecognized_status_never_adds_rules(self):
        m = load()
        with patch.object(m.os, 'geteuid', return_value=0), patch.object(m, 'trusted_executable', return_value=True):
            for output, expected in [('Status: inactive\n', 0), ('unexpected\n', 1)]:
                with patch.object(m.subprocess, 'run', return_value=CompletedProcess([], 0, output, '')) as run:
                    self.assertEqual(m.configure('192.168.1.4'), expected)
                    self.assertEqual(run.call_count, 1)

    def test_failure_and_missing_verification_fail_closed(self):
        m = load()
        with patch.object(m.os, 'geteuid', return_value=0), patch.object(m, 'trusted_executable', return_value=True):
            responses = [CompletedProcess([], 0, 'Status: active\n', ''), CompletedProcess([], 1, '', 'denied')]
            with patch.object(m.subprocess, 'run', side_effect=responses) as run:
                self.assertEqual(m.configure('192.168.1.4'), 1)
                self.assertEqual(run.call_count, 2)
            with patch.object(m.subprocess, 'run', return_value=CompletedProcess([], 0, 'Status: active\n443/tcp ALLOW IN Anywhere\n', '')):
                self.assertEqual(m.configure('192.168.1.4'), 1)

    def test_untrusted_executable_never_runs(self):
        m = load()
        with patch.object(m, 'trusted_executable', return_value=False), patch.object(m.subprocess, 'run') as run:
            self.assertEqual(m.configure('192.168.1.4'), 1)
            run.assert_not_called()

    def test_decline_and_cli_argument_cannot_bypass_confirmation(self):
        m = load()
        with patch.object(m, 'configure') as configure:
            with patch.object(m.sys, 'argv', ['helper', '192.168.1.4']):
                self.assertEqual(m.main(), 2)
            with patch.object(m.sys, 'argv', ['helper']), patch.object(m.sys.stdin, 'isatty', return_value=True), patch('builtins.input', return_value='n'):
                self.assertEqual(m.main(), 0)
            configure.assert_not_called()

    def test_trust_checks_reject_writable_or_symlink_components(self):
        m = load()
        from types import SimpleNamespace
        import stat
        def metadata(mode, uid=0):
            return SimpleNamespace(st_mode=mode, st_uid=uid)
        good = {'/usr/sbin/ufw': metadata(stat.S_IFREG | 0o755), '/usr/sbin': metadata(stat.S_IFDIR | 0o755), '/usr': metadata(stat.S_IFDIR | 0o755), '/': metadata(stat.S_IFDIR | 0o755)}
        with patch.object(m.os, 'lstat', side_effect=lambda path: good[path]):
            self.assertTrue(m.trusted_executable('/usr/sbin/ufw'))
            good['/usr/sbin'] = metadata(stat.S_IFDIR | 0o777)
            self.assertFalse(m.trusted_executable('/usr/sbin/ufw'))
            good['/usr/sbin'] = metadata(stat.S_IFLNK | 0o777)
            self.assertFalse(m.trusted_executable('/usr/sbin/ufw'))
            good['/usr/sbin'] = metadata(stat.S_IFDIR | 0o755, 1000)
            self.assertFalse(m.trusted_executable('/usr/sbin/ufw'))
