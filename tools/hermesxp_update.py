"""Authenticated Windows XP binary delivery; the XP never contacts GitHub.

Windows XP companion implements GET /update/status and POST /update/exe on
port 18768, restricted to the paired Hermes host IP and a 256-bit token.
Transfer is bounded, SHA-256 verified on XP, installed by a separate process
and rolled back automatically if the restarted listener is not healthy.

The private device registry is outside all plugin/source/package directories:
~/.hermes/hermesxp-devices.json, mode 0600. Never publish it.
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import ipaddress
import json
import os
from pathlib import Path
import re
import struct
import sys
import time


MAX_EXE_BYTES = 524288
TOKEN_PATTERN = re.compile(r"[0-9a-fA-F]{64}\Z")
REGISTRY = Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))) / "hermesxp-devices.json"


class UpdateError(RuntimeError):
    """A retryable or invalid XP update."""


def validate_binary(blob: bytes) -> str:
    """Reject malformed, too-large, non-x86 or non-XP-targeted executables."""
    if not 4096 <= len(blob) <= MAX_EXE_BYTES or blob[:2] != b"MZ":
        raise UpdateError("Expected an XP executable between 4 KiB and 512 KiB")
    if len(blob) < 0x40:
        raise UpdateError("Invalid PE header")
    pe_offset = struct.unpack_from("<I", blob, 0x3C)[0]
    if pe_offset > len(blob) - 100 or blob[pe_offset : pe_offset + 4] != b"PE\0\0":
        raise UpdateError("Invalid PE signature")
    machine, sections = struct.unpack_from("<HH", blob, pe_offset + 4)
    opt_offset = pe_offset + 24
    if machine != 0x14C or sections not in range(1, 16):
        raise UpdateError("Binary is not a 32-bit x86 Windows executable")
    if struct.unpack_from("<H", blob, opt_offset)[0] != 0x10B:
        raise UpdateError("Not a PE32 image")
    major, minor = struct.unpack_from("<HH", blob, opt_offset + 48)
    if major > 5 or (major == 5 and minor > 1):
        raise UpdateError(f"PE subsystem {major}.{minor} exceeds Windows XP")
    return hashlib.sha256(blob).hexdigest()


def validate_device(device: dict) -> dict:
    ip = ipaddress.ip_address(str(device.get("host", "")))
    if ip.version != 4 or not (ip.is_private or ip.is_loopback):
        raise ValueError("Devices must have private IPv4 addresses")
    token = str(device.get("token", ""))
    if not TOKEN_PATTERN.fullmatch(token):
        raise ValueError("Device token must be 64 hex characters")
    port = device.get("port", 18768)
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("Device port is invalid")
    return {"host": str(ip), "token": token, "port": port, "name": str(device.get("name", ip))}


def read_registry(path: Path = REGISTRY) -> list[dict]:
    if not path.exists():
        return []
    if path.stat().st_mode & 0o077:
        raise UpdateError(f"Refusing insecure device registry permissions: {path} (must be 0600)")
    config = json.loads(path.read_text())
    return [validate_device(dev) for dev in config.get("devices", [])]


def save_registry(devices: list[dict], path: Path = REGISTRY) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps({"devices": [validate_device(d) for d in devices]}, indent=2) + "\n").encode()
    temp = path.with_name(path.name + f".{os.getpid()}.tmp")
    try:
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
        os.chmod(path, 0o600)
    finally:
        temp.unlink(missing_ok=True)


def request(device: dict, method: str, path: str, body: bytes = b"",
            headers: dict | None = None, timeout: float = 9) -> bytes:
    dev = validate_device(device)
    conn = http.client.HTTPConnection(dev["host"], dev["port"], timeout=timeout)
    fields = {"X-Hermes-Token": dev["token"], "Content-Length": str(len(body))}
    fields.update(headers or {})
    try:
        conn.request(method, path, body=body, headers=fields)
        response = conn.getresponse()
        content = response.read(1024)
        if response.status != 200:
            raise UpdateError(f"XP returned HTTP {response.status}: {content[:90]!r}")
        return content
    except (OSError, TimeoutError, http.client.HTTPException) as exc:
        raise UpdateError(f"XP unavailable ({type(exc).__name__})") from exc
    finally:
        conn.close()


def current_digest(device: dict, *, helper: bool = False) -> str:
    response = request(device, "GET",
                       "/update/helper-status" if helper else "/update/status")
    if not response.startswith(b"sha256=") or len(response.strip()) != 71:
        raise UpdateError("XP does not support the new authenticated update protocol")
    digest = response[7:].decode("ascii").strip()
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise UpdateError("XP returned a malformed digest")
    return digest


def deploy_helper(device: dict, blob: bytes) -> str:
    """The separate updater is idle while the GUI serves this request."""
    desired = validate_binary(blob)
    before = current_digest(device, helper=True)
    if desired == before:
        return "current"
    response = request(
        device, "POST", "/update/helper", blob,
        headers={"X-Hermes-SHA256": desired, "Content-Type": "application/octet-stream"},
        timeout=20,
    )
    if b"helper updated" not in response:
        raise UpdateError("XP rejected the rollback helper")
    if current_digest(device, helper=True) != desired:
        raise UpdateError("XP did not activate the verified rollback helper")
    return "updated"


def deploy(device: dict, blob: bytes, *, helper: bytes | None = None,
           poll_seconds: int = 35) -> str:
    if helper is not None:
        deploy_helper(device, helper)
    desired = validate_binary(blob)
    before = current_digest(device)
    if desired == before:
        return "current"
    response = request(
        device, "POST", "/update/exe", blob,
        headers={"X-Hermes-SHA256": desired, "Content-Type": "application/octet-stream"},
        timeout=20,
    )
    if b"verified" not in response:
        raise UpdateError("XP failed to acknowledge the verified update")
    deadline = time.monotonic() + poll_seconds
    last = "unavailable"
    while time.monotonic() < deadline:
        time.sleep(1)
        try:
            observed = current_digest(device)
        except UpdateError as exc:
            last = str(exc)
            continue
        if observed == desired:
            return "updated"
        if observed == before:
            last = "old image still running (or rollback completed)"
        else:
            last = "unexpected image digest"
    raise UpdateError(f"Update did not become healthy within {poll_seconds}s: {last}")


def deploy_fleet(binary: Path, *, helper_path: Path | None = None,
                 registry: Path = REGISTRY, poll_seconds: int = 35) -> dict:
    blob = binary.read_bytes()
    desired = validate_binary(blob)
    helper = helper_path.read_bytes() if helper_path is not None else None
    if helper is not None:
        validate_binary(helper)
    fleet = read_registry(registry)
    if not fleet:
        print("No paired XP devices. Add a device with the 'pair' command.")
        return {}
    results = {}
    for device in fleet:
        name = device["name"]
        try:
            result = deploy(device, blob, helper=helper, poll_seconds=poll_seconds)
        except UpdateError as exc:
            result = "pending"
            print(f"{name}: pending ({exc})")
        else:
            print(f"{name}: {result} ({desired[:12]})")
        results[name] = result
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Hermes-hosted, authenticated XP client updater")
    sub = parser.add_subparsers(dest="command", required=True)
    pairing = sub.add_parser("pair", help="Save an existing 64-hex XP pairing token securely")
    pairing.add_argument("name")
    pairing.add_argument("host")
    pairing.add_argument("--token-file", type=Path, required=True, help="A private local file containing the XP token")
    pairing.add_argument("--port", type=int, default=18768)
    status = sub.add_parser("status", help="Check all paired XP client versions")
    apply = sub.add_parser("apply", help="Update every paired XP client; offline devices stay pending")
    apply.add_argument("binary", type=Path)
    apply.add_argument("--helper", type=Path, help="Matching rollback helper executable")
    args = parser.parse_args(argv)
    try:
        if args.command == "pair":
            token = args.token_file.read_text().strip()
            new = validate_device({"name": args.name, "host": args.host, "token": token, "port": args.port})
            devices = [d for d in read_registry() if d["name"] != new["name"]]
            devices.append(new)
            save_registry(devices)
            print(f"Paired device {args.name} at {args.host}; token stored privately")
        elif args.command == "status":
            for device in read_registry():
                try:
                    digest = current_digest(device)
                    print(f"{device['name']}: {digest[:12]}")
                except UpdateError as exc:
                    print(f"{device['name']}: offline/unavailable ({exc})")
        elif args.command == "apply":
            results = deploy_fleet(args.binary, helper_path=args.helper)
            return 1 if "pending" in results.values() else 0
        return 0
    except (OSError, ValueError, UpdateError) as exc:
        print(f"XP updater: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
