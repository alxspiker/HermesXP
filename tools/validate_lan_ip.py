"""Validate explicitly configured HermesXP host/device addresses.

Only RFC1918 LANs are accepted, matching the supported XP discovery boundary.
This validation is intentionally independent of a particular home network.
"""
from __future__ import annotations

import ipaddress
import sys

_NETWORKS = tuple(ipaddress.IPv4Network(block) for block in (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
))


def valid_lan_ip(value: str) -> bool:
    try:
        address = ipaddress.IPv4Address(value)
    except (ipaddress.AddressValueError, ValueError):
        return False
    return any(address in block for block in _NETWORKS)


if __name__ == "__main__":
    if len(sys.argv) != 2 or not valid_lan_ip(sys.argv[1]):
        print("expected an RFC1918 LAN IPv4 address", file=sys.stderr)
        raise SystemExit(2)
