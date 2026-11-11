"""Hermes-facing XP operations. No web server, dashboard, or browser API.

All XP requests use the existing private paired-device registry and the
authenticated, bounded HermesXP client. No caller supplies an IP or token.
Remote input/service mutations are disabled unless the Hermes host explicitly
opts in with HERMES_CUA_LIVE_ENABLED=1 and the tool call confirms live action.
"""
from __future__ import annotations

from collections import deque
import hashlib
import io
import json
import os
from pathlib import Path
import re
import socket
import struct
import subprocess
import tempfile
import threading
import time

from .hermesxp_ui import (
    HermesXPClient, validate_click, validate_drag, validate_key,
    validate_scroll, validate_text, validate_service_command,
)
from .hermesxp_update import read_registry


_UNITS = (
    "msn-server.service", "msn-tls.service", "hermes-msn-bridge.service",
    "hermes-xp-voice.service", "hermes-xp-discovery.service",
    "hermes-xp-update.timer", "hermes-xp-package.service",
)
_LOCAL_PORTS = {
    "msn-server.service": (1863, 8081),
    "msn-tls.service": (443,),
    "hermes-msn-bridge.service": (18769,),
}
_ACTIONS = frozenset(("click", "right_click", "double_click", "drag",
                       "scroll", "type_text", "key_press"))
_RECENT_ACTIONS: deque[float] = deque()
_ACTION_LOCK = threading.Lock()


def _home() -> Path:
    return Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))).expanduser()


def _paired_devices() -> list[dict]:
    devices = read_registry()
    if not isinstance(devices, list):
        raise ValueError("Paired device registry is invalid")
    return devices


def _select_device(name: str | None = None) -> dict:
    devices = _paired_devices()
    if not devices:
        raise ValueError("No paired XP devices; complete pairing first")
    if name is None:
        if len(devices) != 1:
            raise ValueError("Specify the paired XP device by name")
        return devices[0]
    if not isinstance(name, str) or not 1 <= len(name) <= 80:
        raise ValueError("Invalid paired XP device name")
    matches = [item for item in devices if item.get("name") == name]
    if len(matches) != 1:
        raise ValueError("Paired XP device not found or name is ambiguous")
    return matches[0]


def _client(device: dict, timeout: float = 5.0) -> HermesXPClient:
    return HermesXPClient(device["host"], device["token"],
                          port=device["port"], timeout=timeout)


def _systemd_status(unit: str) -> dict:
    if unit not in _UNITS:
        raise ValueError("Systemd unit not allowlisted")
    try:
        proc = subprocess.run(
            ["systemctl", "--user", "show", unit,
             "--property=ActiveState,SubState", "--no-pager"],
            capture_output=True, text=True, timeout=2, check=False,
        )
        if proc.returncode:
            return {"state": "unknown"}
        values = dict(line.split("=", 1) for line in proc.stdout.splitlines()
                      if "=" in line)
        result = {"state": values.get("ActiveState", "unknown"),
                  "sub_state": values.get("SubState", "unknown")}
        if unit in _LOCAL_PORTS:
            ports = []
            for port in _LOCAL_PORTS[unit]:
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.25):
                        reachable = True
                except OSError:
                    reachable = False
                ports.append({"port": port, "loopback_reachable": reachable})
            result["ports"] = ports
        return result
    except (OSError, subprocess.TimeoutExpired):
        return {"state": "unknown"}


def _update_status() -> dict:
    root = _home() / "msn-server"
    outcome: dict = {"installed_revision": None, "artifact_revision": None,
                     "artifact_version": None, "package_ready": False}
    marker = root / ".xp-active-plugin-revision"
    try:
        if marker.is_file() and not marker.is_symlink() and marker.stat().st_size <= 128:
            value = marker.read_text(encoding="ascii").strip()
            if re.fullmatch(r"[0-9a-f]{40}", value):
                outcome["installed_revision"] = value
    except (OSError, UnicodeError):
        pass
    state = root / "update-artifacts/build-state.json"
    try:
        if state.is_file() and not state.is_symlink() and state.stat().st_size <= 65536:
            data = json.loads(state.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                revision, version = data.get("revision"), data.get("version")
                if isinstance(revision, str) and re.fullmatch(r"[0-9a-f]{40}", revision):
                    outcome["artifact_revision"] = revision
                if isinstance(version, str) and re.fullmatch(r"\d+\.\d+\.\d+", version):
                    outcome["artifact_version"] = version
    except (OSError, UnicodeError, ValueError, TypeError):
        pass
    package = root / "xp-package/HermesXP-Setup.exe"
    try:
        outcome["package_ready"] = (
            package.is_file() and not package.is_symlink() and package.stat().st_size > 0)
    except OSError:
        pass
    return outcome


def xp_status(args: dict) -> dict:
    """Read local host health; contact paired XP devices only if probe=true."""
    probe = args.get("probe", False)
    if type(probe) is not bool:
        raise ValueError("probe must be a boolean")
    registry = _paired_devices()
    devices = []
    for item in registry[:16]:
        state = "paired; not probed"
        if probe:
            try:
                # Read-only. Network verification and discovery state are
                # distinct from successful authentication to the XP listener.
                response = _client(item, timeout=2.0).network_status()
                state = "reachable" if response.startswith("paired_host_ip=") else "unknown response"
            except (OSError, ValueError, RuntimeError, socket.timeout):
                state = "offline or unavailable"
        devices.append({"name": str(item["name"])[:80], "state": state})
    return {
        "services": {unit: _systemd_status(unit) for unit in _UNITS},
        "devices": devices,
        "devices_truncated": len(registry) > 16,
        "update": _update_status(),
    }


def _bmp_dimensions(content: bytes) -> tuple[int, int]:
    if (not isinstance(content, bytes) or len(content) < 54 or
            len(content) > 32 * 1024 * 1024 or content[:2] != b"BM"):
        raise ValueError("XP screenshot is not a valid bounded BMP")
    offset = struct.unpack_from("<I", content, 10)[0]
    header = struct.unpack_from("<I", content, 14)[0]
    width, height = struct.unpack_from("<ii", content, 18)
    if (header < 40 or offset < 54 or offset >= len(content) or
            not 1 <= width <= 3840 or not 1 <= abs(height) <= 2160 or
            width * abs(height) > 3840 * 2160):
        raise ValueError("XP screenshot has invalid BMP dimensions or header")
    return width, abs(height)


def _save_private_screenshot(content: bytes, name: str) -> str:
    root = _home() / "hermesxp-screenshots"
    if root.is_symlink():
        raise RuntimeError("Screenshot directory cannot be a symlink")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if root.is_symlink() or not root.is_dir():
        raise RuntimeError("Screenshot directory is not a directory")
    root.chmod(0o700)
    target = root / (hashlib.sha256(name.encode("utf-8")).hexdigest()[:20] + ".bmp")
    handle, temp_path = tempfile.mkstemp(prefix=".screenshot-", suffix=".tmp", dir=root)
    try:
        with os.fdopen(handle, "wb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, target)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
    return str(target)


def xp_screen(args: dict) -> dict:
    """Capture only on tool invocation; optionally analyze and/or save locally."""
    save, analyze = args.get("save", True), args.get("analyze", False)
    if type(save) is not bool or type(analyze) is not bool:
        raise ValueError("save and analyze must be booleans")
    device = _select_device(args.get("device"))
    content = _client(device).screenshot()
    width, height = _bmp_dimensions(content)
    result: dict = {
        "device": device["name"], "width": width, "height": height,
        "sha256": hashlib.sha256(content).hexdigest(),
    }
    if save:
        result["screenshot_path"] = _save_private_screenshot(content, device["name"])
        result["privacy"] = "Private host file; overwritten on next capture for this device"
    if analyze:
        # Optional on-demand vision: no HTTP server, no forced model/provider.
        # Import lazily so MSN + basic XP tools never require Pillow.
        try:
            from PIL import Image
            from .xp_vision import infer_screenshot
            with Image.open(io.BytesIO(content)) as image:
                image.load()
                result["vision"] = infer_screenshot(image.convert("RGB"))
        except Exception as exc:
            result["vision"] = {"status": "unavailable", "reason": type(exc).__name__,
                                "detections": []}
    return result


def _allow_live(args: dict) -> None:
    if os.environ.get("HERMES_CUA_LIVE_ENABLED") != "1":
        raise PermissionError("XP write actions are disabled; set HERMES_CUA_LIVE_ENABLED=1 on the Hermes host")
    if args.get("confirm_live") is not True:
        raise PermissionError("Explicit confirm_live=true is required for an XP write action")
    now = time.monotonic()
    with _ACTION_LOCK:
        while _RECENT_ACTIONS and now - _RECENT_ACTIONS[0] >= 5.0:
            _RECENT_ACTIONS.popleft()
        if len(_RECENT_ACTIONS) >= 10:
            raise RuntimeError("XP write-action rate limit exceeded (10 per 5 seconds)")
        _RECENT_ACTIONS.append(now)


def _screen_dimensions(response: str) -> tuple[int, int]:
    values = dict(re.findall(r"\b(width|height)=([0-9]{1,5})\b", response))
    if set(values) != {"width", "height"}:
        raise ValueError("XP did not report screen dimensions")
    width, height = int(values["width"]), int(values["height"])
    if not 1 <= width <= 8192 or not 1 <= height <= 8192:
        raise ValueError("XP reported invalid screen dimensions")
    return width, height


def xp_control(args: dict) -> dict:
    """Bounded, acknowledged desktop input, never arbitrary shell execution."""
    action = args.get("action")
    if action not in _ACTIONS:
        raise ValueError("Unsupported XP control action")
    _allow_live(args)
    device = _select_device(args.get("device"))
    client = _client(device)
    if action in ("type_text", "key_press"):
        text = args.get("text")
        if action == "type_text":
            validate_text(text)
            acknowledgement, expected = client.type_text(text), "typed"
        else:
            validate_key(text)
            acknowledgement, expected = client.key(text), "key sent"
    else:
        width, height = _screen_dimensions(client.inspect())
        coords = args.get("coords")
        if (not isinstance(coords, list) or len(coords) != 2 or
                any(type(v) is not int for v in coords)):
            raise ValueError("coords must contain exactly two integer pixels")
        x, y = coords
        validate_click(x, y, width, height)
        if action in ("click", "right_click"):
            button = "right" if action == "right_click" else "left"
            acknowledgement, expected = client.click(x, y, width, height, button), "clicked"
        elif action == "double_click":
            acknowledgement, expected = client.double_click(x, y, width, height), "double-clicked"
        elif action == "drag":
            end = args.get("end_coords")
            if not isinstance(end, list) or len(end) != 2 or any(type(v) is not int for v in end):
                raise ValueError("end_coords must contain exactly two integer pixels")
            validate_drag(x, y, end[0], end[1], width, height)
            acknowledgement, expected = client.drag(x, y, end[0], end[1], width, height), "dragged"
        else:
            delta = args.get("delta")
            validate_scroll(x, y, width, height, delta)
            acknowledgement, expected = client.scroll(x, y, width, height, delta), "scrolled"
    if acknowledgement.strip() != expected:
        raise RuntimeError("XP did not acknowledge the requested action")
    return {"success": True, "device": device["name"],
            "action": action, "acknowledged": True}


def xp_service(args: dict) -> dict:
    """Named Windows SCM operation, with host opt-in for mutations."""
    name, action = args.get("name"), args.get("action", "status")
    validate_service_command(name, action)
    if action != "status":
        _allow_live(args)
    device = _select_device(args.get("device"))
    response = _client(device).service(name, action)
    return {"device": device["name"], "service": name, "action": action,
            "result": response[:512]}


def invoke(operation: str, args: dict | None) -> str:
    """Hermes register_tool handler boundary: bounded JSON, sanitized errors."""
    operations = {
        "xp_status": xp_status, "xp_screen": xp_screen,
        "xp_control": xp_control, "xp_service": xp_service,
    }
    try:
        if not isinstance(args, dict) or operation not in operations:
            raise ValueError("Unsupported XP tool invocation")
        return json.dumps({"success": True, **operations[operation](args)}, ensure_ascii=False)
    except (OSError, ValueError, RuntimeError, PermissionError, KeyError, TypeError,
            subprocess.SubprocessError, socket.timeout) as exc:
        return json.dumps({"success": False, "error": type(exc).__name__,
                           "message": str(exc)[:200] if isinstance(exc, (ValueError, PermissionError))
                           else "XP action unavailable or failed"})
