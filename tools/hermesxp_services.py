"""Windows service management on a paired HermesXP computer.

No credentials on the command line: the host obtains its LAN pairing token
from the protected HermesXP device registry. Only native SCM operations
exposed by the XP client are supported; there is no remote shell command.

    python3 -m tools.hermesxp_services --device RUITER --service AudioSrv status
    python3 -m tools.hermesxp_services --device RUITER --service Spooler restart
"""

from __future__ import annotations

import argparse
import sys

from tools.hermesxp_ui import HermesXPClient
from tools.hermesxp_update import read_registry


def select_device(devices: list[dict], wanted: str | None) -> dict:
    matches = [
        device for device in devices
        if wanted is None or wanted.lower() in (
            device["name"].lower(), device["host"].lower()
        )
    ]
    if len(matches) != 1:
        raise ValueError(
            "Select one paired XP device by name or private IP"
            if wanted is not None or matches
            else "No paired XP devices found"
        )
    return matches[0]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage a Windows XP service through HermesXP")
    parser.add_argument("--device", help="Paired device name or private IPv4; optional for a single device")
    parser.add_argument("--service", required=True, help="Windows SCM service name, not display title")
    parser.add_argument("action", choices=("status", "start", "stop", "restart"))
    args = parser.parse_args(argv)
    try:
        device = select_device(read_registry(), args.device)
        result = HermesXPClient(
            device["host"], device["token"], port=device["port"], timeout=9,
        ).service(args.service, args.action)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"HermesXP service request failed: {exc}", file=sys.stderr)
        return 1
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
