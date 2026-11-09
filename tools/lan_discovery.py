"""Authenticated LAN address discovery for paired HermesXP computers.

Port 18773/UDP, no public server, no shared credentials broadcast.
Three-way HMAC-SHA256 handshake:
  HXP1 <token_fingerprint16> <client_nonce16> <mac64>
  HXP2 <client_nonce16> <server_nonce16> <host_ipv4> <mac64>
  HXP3 <token_fingerprint16> <client_nonce16> <server_nonce16> <mac64>
Only a validated final acknowledgement from the same LAN source may
update ~/.hermes/hermesxp-devices.json. Never accept an untrusted claimed IP.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import ipaddress
import logging
import os
from pathlib import Path
import re
import secrets
import socket
import subprocess
import time
from dataclasses import dataclass

from tools.hermesxp_update import read_registry, save_registry

LOG = logging.getLogger("hermesxp.discovery")
PORT = 18773


def identity(token: str) -> str:
    return hashlib.sha256(bytes.fromhex(token)).hexdigest()[:16]


def sign(token: str, message: str) -> str:
    return hmac.new(bytes.fromhex(token), message.encode("ascii"), hashlib.sha256).hexdigest()


def private_ipv4(value: str) -> bool:
    try:
        addr = ipaddress.IPv4Address(value)
        return addr.is_private and not (addr.is_loopback or addr.is_link_local)
    except ipaddress.AddressValueError:
        return False


def own_ip_for(remote_ip: str) -> str | None:
    if not private_ipv4(remote_ip):
        return None
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect((remote_ip, 9))  # no UDP packet is sent
            ip = sock.getsockname()[0]
            return ip if private_ipv4(ip) else None
    except OSError:
        return None


@dataclass
class Pending:
    token: str
    device_id: str
    client_nonce: str
    server_nonce: str
    host_ip: str
    timestamp: float


class Discovery(asyncio.DatagramProtocol):
    def __init__(self, *, devices=read_registry, save=save_registry, resolve=own_ip_for,
                 restart=None, reconfigure=None):
        self.devices = devices
        self.save = save
        self.resolve = resolve
        self.restart = restart or restart_bridge
        self.reconfigure = reconfigure or reconcile_host_ip
        self.transport = None
        self.pending: dict[tuple[str, int], Pending] = {}
        self.current_hosts: dict[str, str] = {}
        self.last_restart = 0.0

    def connection_made(self, transport):
        self.transport = transport
        LOG.info("Authenticated XP LAN discovery listening on UDP %d", PORT)

    def datagram_received(self, data: bytes, addr):
        ip, port = addr[:2]
        if not private_ipv4(ip) or len(data) > 200:
            return
        try:
            message = data.decode("ascii")
        except UnicodeDecodeError:
            return
        fields = message.split(" ")
        if fields[0] == "HXP1" and len(fields) == 4:
            self._hello(fields, ip, port)
        elif fields[0] == "HXP3" and len(fields) == 5:
            self._ack(fields, ip, port)

    def _hello(self, fields, ip, port):
        _, device_id, client_nonce, mac = fields
        if (len(device_id) != 16 or len(client_nonce) != 16 or len(mac) != 64
                or any(x not in "0123456789abcdef" for x in device_id+client_nonce+mac)):
            return
        devices = self.devices()
        matching = [d for d in devices if identity(d["token"]) == device_id]
        if len(matching) != 1:
            return
        token = matching[0]["token"]
        if not hmac.compare_digest(sign(token, " ".join(fields[:3])), mac):
            return
        host_ip = self.resolve(ip)
        if host_ip is None:
            return
        nonce = secrets.token_hex(8)
        challenge = f"HXP2 {client_nonce} {nonce} {host_ip}"
        self.pending = {k: p for k, p in self.pending.items()
                        if time.monotonic() - p.timestamp < 8}
        self.pending[ip, port] = Pending(token, device_id, client_nonce,
                                         nonce, host_ip, time.monotonic())
        self.transport.sendto(f"{challenge} {sign(token, challenge)}".encode(), (ip, port))

    def _ack(self, fields, ip, port):
        pending = self.pending.pop((ip, port), None)
        if pending is None or time.monotonic() - pending.timestamp > 8:
            return
        _, device_id, client_nonce, server_nonce, mac = fields
        if (device_id != pending.device_id or client_nonce != pending.client_nonce
                or server_nonce != pending.server_nonce
                or not hmac.compare_digest(sign(pending.token, " ".join(fields[:4])), mac)):
            return
        devices = self.devices()
        matching = [d for d in devices if identity(d["token"]) == device_id]
        if len(matching) != 1:
            return
        previous = matching[0]["host"]
        current_host = self.current_hosts.get(device_id)
        self.current_hosts[device_id] = pending.host_ip
        host_reconfigured = self.reconfigure(pending.host_ip)
        if previous != ip:
            matching[0]["host"] = ip
            self.save(devices)
            LOG.info("Paired XP %s moved: %s -> %s (authenticated)",
                     matching[0]["name"], previous, ip)
        if current_host not in (None, pending.host_ip):
            LOG.info("Hermes host LAN address moved: %s -> %s",
                     current_host, pending.host_ip)
        # Recreate MSN's IP-bound RTP socket only when an address changes.
        # Reconnect resets a call that cannot survive that interface move.
        if previous != ip or current_host not in (None, pending.host_ip) or host_reconfigured:
            self.restart()


def reconcile_host_ip(host_ip: str, home: Path | None = None) -> bool:
    """Repair the *managed* XP MSN local DNS/redirect and TLS bind addresses.

    Only fixed key-value settings generated by HermesXP are updated. User
    credentials, CA key/certificate and other server configuration are
    untouched. Existing DNS:msn.local on the same CA avoids cert rotation.
    """
    if not private_ipv4(host_ip):
        return False
    directory = (home or Path.home()) / ".hermes" / "msn-server"
    specs = [
        (directory / "settings_local.py", [
            (r"(?m)^((?:TARGET_HOST|LOGIN_HOST|STORAGE_HOST)\s*=\s*)'[^']*'",
             lambda m: f"{m.group(1)}'{host_ip}'"),
        ]),
        (directory / "stunnel.conf", [
            (r"(?m)^(\s*accept\s*=\s*)\d+\.\d+\.\d+\.\d+:443\b",
             lambda m: f"{m.group(1)}{host_ip}:443"),
        ]),
    ]
    changed = False
    for path, transforms in specs:
        try:
            content = path.read_text()
        except OSError:
            continue
        replaced = content
        for regex, function in transforms:
            replaced = re.sub(regex, function, replaced)
        if replaced != content:
            tmp = path.with_name(path.name + ".hermesxp.new")
            try:
                tmp.write_text(replaced)
                os.chmod(tmp, path.stat().st_mode & 0o777)
                os.replace(tmp, path)
                changed = True
            finally:
                tmp.unlink(missing_ok=True)
    if changed:
        LOG.info("Managed MSN server endpoints now use authenticated LAN IP %s", host_ip)
        for unit in ("msn-server.service", "msn-tls.service"):
            try:
                subprocess.Popen(["systemctl", "--user", "try-restart", unit],
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, start_new_session=True)
            except OSError as exc:
                LOG.warning("Cannot restart %s: %s", unit, exc)
    return changed


def restart_bridge():
    try:
        subprocess.Popen(["systemctl", "--user", "restart", "hermes-msn-bridge.service"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    except OSError as exc:
        LOG.warning("Bridge restart failed: %s", exc)


async def serve():
    loop = asyncio.get_running_loop()
    transport, _protocol = await loop.create_datagram_endpoint(
        Discovery, local_addr=("0.0.0.0", PORT),
    )
    try:
        await asyncio.Event().wait()
    finally:
        transport.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(serve())
