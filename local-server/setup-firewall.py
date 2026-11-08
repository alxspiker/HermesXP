#!/usr/bin/env python3
"""Optionally allow one XP host to reach the HermesXP TCP listeners via UFW."""
import ipaddress
import os
import re
import stat
import subprocess
import sys

PORTS = (443, 1863, 1864)


def valid_ip(value):
    try:
        address = ipaddress.IPv4Address(value)
        return not (address.is_unspecified or address.is_multicast or address.is_loopback or address.is_reserved or str(address).endswith('.255'))
    except ipaddress.AddressValueError:
        return False


UFW = '/usr/sbin/ufw'
SUDO = '/usr/bin/sudo'


def trusted_executable(path):
    """Reject symlinks or paths writable by non-root, including parent dirs."""
    try:
        current = path
        first = True
        while True:
            info = os.lstat(current)
            if info.st_uid != 0 or info.st_mode & 0o022:
                return False
            if first:
                if not stat.S_ISREG(info.st_mode) or not info.st_mode & 0o111:
                    return False
            elif not stat.S_ISDIR(info.st_mode):
                return False
            if current == '/':
                return True
            current = os.path.dirname(current)
            first = False
    except OSError:
        return False


def configure(ip):
    if not valid_ip(ip):
        print('A single valid XP IPv4 address is required; CIDRs are not allowed.', file=sys.stderr)
        return 1
    if not trusted_executable(UFW) or (os.geteuid() != 0 and not trusted_executable(SUDO)):
        print('Trusted UFW or sudo executable unavailable; firewall unchanged.', file=sys.stderr)
        return 1
    prefix = [] if os.geteuid() == 0 else [SUDO, '-n']
    # Do not pass caller-controlled Python or dynamic-loader environment to UFW.
    env = {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL': 'C'}
    def run(*args, interactive=False):
        # In interactive mode inherit stderr so the sudo password prompt is visible.
        try:
            return subprocess.run([*prefix, UFW, *args], text=True, stdout=subprocess.PIPE,
                                  stderr=None if interactive else subprocess.PIPE, env=env)
        except OSError as exc:
            return subprocess.CompletedProcess([], 1, '', str(exc))

    status = run('status')
    if status.returncode and prefix and sys.stdin.isatty() and sys.stderr.isatty():
        print('Non-interactive sudo failed; requesting interactive authorization.', file=sys.stderr)
        prefix = [SUDO]
        status = run('status', interactive=True)
    if status.returncode:
        print('Unable to read UFW status: ' + (status.stderr or '').strip(), file=sys.stderr)
        return 1
    if re.search(r'^Status: inactive\s*$', status.stdout, re.MULTILINE):
        print('UFW is inactive; it was not enabled and no rules were added.')
        return 0
    if not re.search(r'^Status: active\s*$', status.stdout, re.MULTILINE):
        print('Unrecognized UFW status; firewall unchanged.', file=sys.stderr)
        return 1
    for port in PORTS:
        result = run('allow', 'in', 'proto', 'tcp', 'from', ip, 'to', 'any', 'port', str(port), interactive=prefix == [SUDO])
        if result.returncode:
            print(f'UFW rule for {port}/tcp failed; earlier rules may remain: {(result.stderr or "").strip()}', file=sys.stderr)
            return 1
    status = run('status', interactive=prefix == [SUDO])
    if status.returncode or not re.search(r'^Status: active\s*$', status.stdout, re.MULTILINE):
        print('Could not verify active UFW rules; inspect UFW manually.', file=sys.stderr)
        return 1
    for port in PORTS:
        pattern = rf'^\s*{port}/tcp\s+ALLOW IN\s+{re.escape(ip)}(?:/32)?\s*$'
        if not re.search(pattern, status.stdout, re.MULTILINE):
            print(f'Could not verify the {port}/tcp rule for {ip}; inspect UFW manually.', file=sys.stderr)
            return 1
    print(f'Verified UFW inbound TCP rules for {ip}: 443, 1863, 1864.')
    return 0


def main():
    if len(sys.argv) != 1:
        print(f'Usage: {sys.argv[0]}', file=sys.stderr)
        return 2
    if not sys.stdin.isatty():
        print('No interactive terminal; firewall unchanged.')
        return 0
    if input('Configure UFW for one XP device? [y/N] ').strip().lower() not in ('y', 'yes'):
        print('Firewall unchanged.')
        return 0
    ip = input('XP device IPv4 address (not the server IP): ').strip()
    if not valid_ip(ip):
        print('A single valid XP IPv4 address is required; CIDRs are not allowed.', file=sys.stderr)
        return 1
    print(f'Will allow inbound TCP 443, 1863 and 1864 from {ip} only.')
    if input('Apply these UFW rules? [y/N] ').strip().lower() not in ('y', 'yes'):
        print('Firewall unchanged.')
        return 0
    return configure(ip)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (EOFError, KeyboardInterrupt):
        print('\nCancelled.', file=sys.stderr)
        sys.exit(1)
