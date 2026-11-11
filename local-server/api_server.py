from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, Response
from PIL import Image
import hashlib
import hmac
import io
import os
import threading
import time
from collections import deque
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import ipaddress
import json
import re
import socket
import subprocess
import sys

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from tools.hermesxp_ui import (
    HermesXPClient, ResponseTooLargeError, validate_click, validate_drag,
    validate_key, validate_scroll, validate_text,
)
from tools.hermesxp_update import read_registry, UpdateError
from vision_model import infer_lfm3vl, model_status

app = FastAPI(title="HermesXP Vision Dashboard Server")

# Serve bundled UI assets independently of the process working directory.
app.mount("/static", StaticFiles(directory=str(Path(__file__).resolve().parent)), name="static")


@app.get("/", response_class=HTMLResponse)
async def root():
    dashboard = Path(__file__).resolve().with_name("dashboard.html")
    return HTMLResponse(dashboard.read_text(encoding="utf-8"))


@app.get("/api/status")
async def status():
    # Preserve the legacy shape while deriving the service summary from live
    # host observations; detailed fields are available at /api/dashboard/status.
    live = dashboard_status()
    core = ["msn-server", "msn-tls", "msn-bridge", "talk-voice", "xp-discovery"]
    service_map = {item["id"]: item for item in live["services"]}
    if live["diagnostics"]["systemd"] == "unavailable":
        service_summary = "unknown"
    elif all(service_map.get(name, {}).get("state") == "active" and
             all(port["reachable"] for port in service_map.get(name, {}).get("ports", []))
             for name in core):
        service_summary = "active"
    else:
        service_summary = "degraded"
    vision = model_status()
    cua_configured = (
        32 <= len(os.environ.get("HERMES_CUA_TOKEN", "")) <= 512
        and bool(os.environ.get("HERMES_CUA_ALLOWED_IP"))
        and os.environ.get("HERMES_CUA_LIVE_ENABLED") == "1"
    )
    return {
        "services": service_summary,
        "dashboard": "v0.7",
        "vision": (
            "lfm3-vl" if vision["state"] == "verified"
            and vision.get("backend", "llama-cli") == "llama-cli"
            and str(vision.get("model", "")).startswith("LFM3-VL")
            else "vision-model" if vision["state"] == "verified"
            else "heuristic-only"
        ),
        "model": vision["model"] or "unavailable",
        "cua": "live-opt-in" if cua_configured else "simulated-only",
        "xp_endpoint": "paired-device-authenticated",
    }


SERVICE_SPECS = (
    {"id": "msn-server", "unit": "msn-server.service", "ports": (1863, 8081)},
    {"id": "msn-tls", "unit": "msn-tls.service", "ports": (443,)},
    {"id": "msn-bridge", "unit": "hermes-msn-bridge.service", "ports": ()},
    {"id": "talk-voice", "unit": "hermes-xp-voice.service", "ports": ()},
    {"id": "xp-discovery", "unit": "hermes-xp-discovery.service", "ports": ()},
    {"id": "xp-update", "unit": "hermes-xp-update.timer", "ports": ()},
    {"id": "xp-package-server", "unit": "hermes-xp-package.service", "ports": (18767,)},
)


def dashboard_home() -> Path:
    return Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))).expanduser()


def dashboard_bind_host() -> str:
    """Default to loopback; only explicit private/loopback addresses are allowed."""
    configured = os.environ.get("HERMES_DASHBOARD_BIND_HOST", "127.0.0.1")
    try:
        address = ipaddress.ip_address(configured)
    except ValueError as exc:
        raise RuntimeError("HERMES_DASHBOARD_BIND_HOST must be a private or loopback IP address") from exc
    if address.is_unspecified or address.is_multicast or not (address.is_loopback or address.is_private):
        raise RuntimeError("Dashboard binding must be loopback or a private LAN IP; wildcard/public addresses are refused")
    return str(address)


def query_systemd_unit(unit: str) -> dict:
    """Read an allowlisted unit state using fixed argv and no shell."""
    result = subprocess.run(
        ["systemctl", "--user", "show", unit,
         "--property=LoadState,ActiveState,SubState", "--no-pager"],
        capture_output=True, text=True, timeout=1.5, check=False,
    )
    values = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    return {
        "load_state": values.get("LoadState", "unknown"),
        "active_state": values.get("ActiveState", "unknown"),
        "sub_state": values.get("SubState", "unknown"),
        "query_error": result.returncode != 0,
    }


def probe_local_port(host: str, port: int, *, timeout: float = 0.25) -> bool:
    """Probe a fixed loopback service port; never accepts a remote host here."""
    if host != "127.0.0.1" or not (1 <= port <= 65535):
        return False
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _update_snapshot(home: Path) -> dict:
    root = home / "msn-server"
    active_revision = None
    revision_file = root / ".xp-active-plugin-revision"
    try:
        if revision_file.is_file() and not revision_file.is_symlink() and revision_file.stat().st_size <= 128:
            value = revision_file.read_text(encoding="ascii").strip()
            if re.fullmatch(r"[0-9a-f]{40}|unmanaged", value):
                active_revision = value
    except (OSError, UnicodeError):
        pass

    artifact_version = artifact_revision = None
    artifact_hashes = {}
    state_file = root / "update-artifacts" / "build-state.json"
    try:
        if state_file.is_file() and not state_file.is_symlink() and state_file.stat().st_size <= 65536:
            state = json.loads(state_file.read_text(encoding="utf-8"))
            if isinstance(state, dict):
                version = state.get("version")
                revision = state.get("revision")
                hashes = state.get("sha256")
                if isinstance(version, str) and re.fullmatch(r"[0-9]+(?:\.[0-9A-Za-z-]+){1,3}", version):
                    artifact_version = version[:40]
                if isinstance(revision, str) and re.fullmatch(r"[0-9a-f]{40}", revision):
                    artifact_revision = revision
                if isinstance(hashes, dict):
                    for name in ("HermesXP.exe", "HermesXP-Updater.exe"):
                        digest = hashes.get(name)
                        if isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest):
                            artifact_hashes[name] = digest
    except (OSError, ValueError, UnicodeError):
        pass

    package = root / "xp-package" / "HermesXP-Setup.exe"
    try:
        package_ready = package.is_file() and not package.is_symlink() and package.stat().st_size > 0
        package_size = package.stat().st_size if package_ready else None
    except OSError:
        package_ready, package_size = False, None
    complete = bool(artifact_version and artifact_revision and len(artifact_hashes) == 2)
    return {
        "status": "artifacts-ready" if complete and package_ready else "incomplete-or-unknown",
        "plugin_revision": active_revision,
        "artifact_version": artifact_version,
        "artifact_revision": artifact_revision,
        "artifact_sha256": artifact_hashes,
        "package_ready": package_ready,
        "package_size_bytes": package_size,
        "deployment_claim": "not inferred from build artifacts",
    }


def _service_snapshot() -> tuple[list[dict], bool]:
    output = []
    errors = 0
    # Query units concurrently so a stopped user systemd bus is bounded by one
    # subprocess timeout, rather than the timeout multiplied by unit count.
    with ThreadPoolExecutor(max_workers=len(SERVICE_SPECS), thread_name_prefix="dashboard-status") as pool:
        futures = [pool.submit(query_systemd_unit, spec["unit"]) for spec in SERVICE_SPECS]
        for spec, future in zip(SERVICE_SPECS, futures):
            try:
                raw = future.result()
                if raw.get("query_error"):
                    errors += 1
                state = raw.get("active_state", "unknown")
                state = state if state in {"active", "inactive", "failed", "activating", "deactivating"} else "unknown"
                ports = [{"port": port, "reachable": probe_local_port("127.0.0.1", port)}
                         for port in spec["ports"]]
                output.append({"id": spec["id"], "unit": spec["unit"], "state": state,
                               "load_state": raw.get("load_state", "unknown"),
                               "sub_state": raw.get("sub_state", "unknown"), "ports": ports})
            except Exception:
                errors += 1
                output.append({"id": spec["id"], "unit": spec["unit"], "state": "unknown",
                               "load_state": "unknown", "sub_state": "unknown", "ports": []})
    return output, errors == 0


@app.get("/api/dashboard/status")
def dashboard_status():
    services, systemd_available = _service_snapshot()
    registry_available = True
    try:
        registry = read_registry()
        devices = [{"name": str(device["name"])[:80], "state": "paired; not probed"}
                   for device in registry[:32]]
    except (OSError, ValueError, KeyError, TypeError, UpdateError):
        devices = []
        registry_available = False
    home = dashboard_home()
    active_count = sum(item["state"] == "active" for item in services)
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "services": services,
        "devices": devices,
        "devices_truncated": len(devices) == 32,
        "update": _update_snapshot(home),
        "diagnostics": {
            "api": "healthy", "systemd": "available" if systemd_available else "unavailable",
            "registry": "available" if registry_available else "unavailable",
            "active_services": active_count, "service_count": len(services),
        },
    }


def _probe_device(device: dict) -> dict:
    name = str(device.get("name", "paired device"))[:80]
    result: dict[str, str | bool] = {"name": name, "state": "offline"}
    try:
        response = HermesXPClient(device["host"], device["token"],
                                  port=device["port"], timeout=2.0).network_status()
        fields = dict(re.findall(r"\b(discovery_state|verified|win32_error)=([0-9]+)\b", response))
        if len(fields) != 3:
            result["state"] = "unknown response"
        elif fields["win32_error"] != "0" or fields["discovery_state"] != "6" or fields["verified"] != "3":
            result["state"] = "degraded"
            result["verified"] = fields["verified"] == "3"
        else:
            result["state"] = "online"
            result["verified"] = True
    except (TimeoutError, socket.timeout, subprocess.TimeoutExpired):
        result["state"] = "timeout"
    except Exception:
        result["state"] = "offline"
    return result


@app.get("/api/dashboard/devices")
def dashboard_devices(request: Request, confirm: bool = False):
    if not confirm or request.headers.get("X-Hermes-Dashboard-Confirm") != "user-approved-read-only-probe":
        raise HTTPException(status_code=400, detail="Explicit confirmation is required to probe paired XP devices")
    try:
        registry = read_registry()
    except (OSError, ValueError, UpdateError) as exc:
        raise HTTPException(status_code=503, detail="Paired-device registry is unavailable") from exc
    devices = [_probe_device(item) for item in registry[:8]]
    return {"timestamp": datetime.now(timezone.utc).isoformat(), "devices": devices,
            "devices_truncated": len(registry) > 8}


def resolve_paired_device(devices: list[dict], name: str | None) -> dict:
    if not devices:
        raise HTTPException(status_code=503, detail="No paired XP devices are configured")
    if name is None:
        if len(devices) != 1:
            raise HTTPException(status_code=400, detail="Select a paired device by name")
        return devices[0]
    matches = [device for device in devices if device["name"] == name]
    if not matches:
        raise HTTPException(status_code=404, detail="Paired XP device not found")
    if len(matches) != 1:
        raise HTTPException(status_code=409, detail="Paired XP device name is ambiguous")
    return matches[0]


def fetch_paired_screenshot(name: str | None = None) -> tuple[bytes, int, int]:
    """Fetch and validate a BMP through the private paired-device registry."""
    try:
        device = resolve_paired_device(read_registry(), name)
    except HTTPException:
        raise
    except (OSError, ValueError, UpdateError) as exc:
        raise HTTPException(status_code=503, detail="Paired-device registry is unavailable") from exc

    try:
        content = HermesXPClient(
            device["host"], device["token"], port=device["port"], timeout=5.0
        ).screenshot()
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="Paired XP screenshot request timed out") from exc
    except ResponseTooLargeError as exc:
        raise HTTPException(status_code=502, detail="XP returned an oversized screenshot") from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Paired XP device is offline or unavailable") from exc

    if not content or len(content) > 32 * 1024 * 1024:
        raise HTTPException(status_code=502, detail="XP returned an invalid or oversized screenshot")
    try:
        with Image.open(io.BytesIO(content)) as image:
            if image.format != "BMP":
                raise ValueError("not a BMP")
            width, height = image.size
            if not (1 <= width <= 8192 and 1 <= height <= 8192 and width * height <= 40_000_000):
                raise ValueError("invalid image dimensions")
            image.verify()
    except Exception as exc:
        raise HTTPException(status_code=502, detail="XP returned an invalid screenshot") from exc
    return content, width, height


@app.get("/api/devices")
def paired_devices():
    try:
        devices = read_registry()
    except (OSError, ValueError, UpdateError) as exc:
        raise HTTPException(status_code=503, detail="Paired-device registry is unavailable") from exc
    return {"devices": [{"name": device["name"]} for device in devices]}


@app.get("/api/screenshot")
def screenshot(device: str | None = None):
    content, width, height = fetch_paired_screenshot(device)
    return Response(content=content, media_type="image/bmp", headers={
        "X-HermesXP-Width": str(width), "X-HermesXP-Height": str(height),
        "Cache-Control": "no-store",
    })


def generate_heuristic_suggestions(width: int, height: int) -> list:
    """Pure function for heuristic CUA suggestions. Testable independently.
    Proportional coords only; no real vision model (advances #9 safely)."""
    return [
        {
            "action": "click_ok",
            "coords": (int(width * 0.775), int(height * 0.75)),
            "confidence": 0.92,
            "reason": f"Heuristic coordinate estimate; not visually detected"
        },
        {
            "action": "close_window",
            "coords": (int(width * 0.975), int(height * 0.08)),
            "confidence": 0.85,
            "reason": "Title bar close button estimate"
        },
        {
            "action": "type_text",
            "coords": (int(width * 0.2), int(height * 0.45)),
            "text": "user@example.com",
            "confidence": 0.78,
            "reason": "Heuristic text-entry location estimate; no text field detection performed"
        },
        {
            "action": "right_click",
            "coords": (int(width * 0.5), int(height * 0.6)),
            "confidence": 0.88,
            "reason": "Heuristic midpoint estimate; no target detection performed"
        },
        {
            "action": "double_click",
            "coords": (int(width * 0.5), int(height * 0.5)),
            "confidence": 0.75,
            "reason": "Heuristic center estimate; no double-click target detection performed"
        },
        {
            "action": "scroll",
            "coords": (int(width * 0.5), int(height * 0.5)),
            "confidence": 0.82,
            "reason": "Heuristic center estimate; scrollable area not detected"
        },
        {
            "action": "drag",
            "coords": (int(width * 0.3), int(height * 0.4)),
            "confidence": 0.79,
            "reason": "Heuristic window-area estimate; no draggable element detection performed"
        }
    ]


@app.get("/api/analyze")
def analyze_screenshot(device: str | None = None):
    """Analyze a paired-device screenshot with configured vision and separate heuristics."""
    try:
        content, width, height = fetch_paired_screenshot(device)
        suggestions = generate_heuristic_suggestions(width, height)
        try:
            image = Image.open(io.BytesIO(content)).convert("RGB")
            detections = infer_lfm3vl(image)
            vision = model_status()
            analysis_mode = ("lfm3-vl" if vision.get("backend", "llama-cli") == "llama-cli"
                             and str(vision.get("model", "")).startswith("LFM3-VL")
                             else "vision-model")
            model = vision["model"]
            model_error = None
            note = "Controls and bounds are model detections; suggestions are separate heuristic estimates. Verify detections before acting."
        except Exception as exc:
            detections = []
            analysis_mode = "heuristic"
            model = None
            model_error = type(exc).__name__
            note = "Configured vision inference unavailable; only heuristic coordinate estimates are available. No controls were reported as detected."
        analysis = {
            "status": "success",
            "analysis_mode": analysis_mode,
            "model": model,
            "model_error": model_error,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "screenshot_size": f"{width}x{height}",
            "detections": detections,
            "suggestions": suggestions,
            "note": note,
        }
        return JSONResponse(analysis)
    except HTTPException as exc:
        return JSONResponse({"status": "error", "message": exc.detail,
                             "note": "Paired XP screenshot is unavailable"}, status_code=exc.status_code)
    except Exception:
        return JSONResponse({"status": "error", "message": "Screenshot analysis failed",
                             "note": "Paired XP screenshot could not be analyzed"}, status_code=502)


class CUARequestLimitMiddleware:
    """Bound CUA request buffering before FastAPI parses JSON."""
    LIMIT = 4096

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if (scope.get("type") != "http" or scope.get("method") != "POST" or
                scope.get("path") != "/api/cua/execute"):
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        raw_length = headers.get(b"content-length")
        if raw_length is not None:
            try:
                if int(raw_length) > self.LIMIT:
                    await self._too_large(scope, send)
                    return
            except ValueError:
                await self._too_large(scope, send)
                return

        body = bytearray()
        more_body = True
        while more_body:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            if message["type"] != "http.request":
                continue
            body.extend(message.get("body", b""))
            if len(body) > self.LIMIT:
                await self._too_large(scope, send)
                return
            more_body = message.get("more_body", False)

        delivered = False
        async def replay_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return {"type": "http.disconnect"}

        await self.app(scope, replay_receive, send)

    async def _too_large(self, scope, send):
        body = b'{"detail":"CUA request body exceeds 4096 bytes"}'
        await send({"type": "http.response.start", "status": 413,
                    "headers": [(b"content-type", b"application/json"),
                                (b"content-length", str(len(body)).encode("ascii"))]})
        await send({"type": "http.response.body", "body": body})


from pydantic import BaseModel, Field, StrictBool, StrictInt, model_validator
from typing import Literal, Optional

_CUA_MOUSE_ACTIONS = frozenset({
    "click_ok", "close_window", "click", "right_click", "double_click", "scroll", "drag",
})


class CUACommand(BaseModel):
    action: Literal["click_ok", "close_window", "click", "right_click", "double_click", "type_text", "key_press", "scroll", "drag"]
    coords: Optional[tuple[StrictInt, StrictInt]] = None
    end_coords: Optional[tuple[StrictInt, StrictInt]] = None
    delta: Optional[StrictInt] = None
    text: Optional[str] = Field(default=None, max_length=128)
    token: str = Field(min_length=32, max_length=512)
    confirm_live: StrictBool = False
    device: Optional[str] = Field(default=None, max_length=80)

    @model_validator(mode="after")
    def validate_command_shape(self):
        if self.coords is not None and any(value < 0 or value > 8192 for value in self.coords):
            raise ValueError("coordinates must be between 0 and 8192")
        if self.end_coords is not None and any(value < 0 or value > 8192 for value in self.end_coords):
            raise ValueError("end coordinates must be between 0 and 8192")
        if self.action in _CUA_MOUSE_ACTIONS and self.coords is None:
            raise ValueError(f"{self.action} requires coordinates")
        if self.action == "drag" and self.end_coords is None:
            raise ValueError("drag requires end_coords")
        if self.action != "drag" and self.end_coords is not None:
            raise ValueError("end_coords is only allowed for drag")
        if self.action == "scroll":
            if self.delta is None or self.delta == 0 or not -5 <= self.delta <= 5:
                raise ValueError("scroll delta must be between -5 and -1 or 1 and 5")
        elif self.delta is not None:
            raise ValueError("delta is only allowed for scroll")
        if self.action in {"type_text", "key_press"}:
            if not self.text:
                raise ValueError(f"{self.action} requires text")
        elif self.text is not None:
            raise ValueError("text is not allowed for this action")
        return self


def _screen_dimensions(response: str) -> tuple[int, int]:
    fields = dict(re.findall(r"\b(width|height)=([0-9]{1,5})\b", response))
    if set(fields) != {"width", "height"}:
        raise HTTPException(status_code=502, detail="Paired XP did not report screen dimensions")
    width, height = int(fields["width"]), int(fields["height"])
    if not 1 <= width <= 8192 or not 1 <= height <= 8192:
        raise HTTPException(status_code=502, detail="Paired XP reported invalid screen dimensions")
    return width, height


def _cua_rate_limited(peer: str, token: str) -> bool:
    """Allow at most ten authenticated CUA requests per identity in five seconds."""
    key = (peer, hashlib.sha256(token.encode("utf-8")).hexdigest())
    now = time.monotonic()
    with _CUA_RATE_LOCK:
        for old_key, timestamps in list(_CUA_ACTION_TIMES.items()):
            while timestamps and now - timestamps[0] >= _CUA_RATE_WINDOW:
                timestamps.popleft()
            if not timestamps:
                del _CUA_ACTION_TIMES[old_key]
        timestamps = _CUA_ACTION_TIMES.setdefault(key, deque())
        if len(timestamps) >= _CUA_RATE_LIMIT:
            return True
        timestamps.append(now)
        if len(_CUA_ACTION_TIMES) > 128:
            _CUA_ACTION_TIMES.pop(next(iter(_CUA_ACTION_TIMES)))
        return False


_CUA_RATE_LIMIT = 10
_CUA_RATE_WINDOW = 5.0
_CUA_RATE_LOCK = threading.Lock()
_CUA_ACTION_TIMES: dict[tuple[str, str], deque[float]] = {}


@app.post("/api/cua/execute")
async def execute_cua_command(cmd: CUACommand, request: Request):
    """Authenticate a bounded UI action; live execution is opt-in and paired-device only."""
    expected_token = os.environ.get("HERMES_CUA_TOKEN")
    allowed_ip = os.environ.get("HERMES_CUA_ALLOWED_IP")
    if expected_token is None or not 32 <= len(expected_token) <= 512 or not allowed_ip:
        raise HTTPException(status_code=503, detail="CUA is not configured")
    if request.client is None or request.client.host != allowed_ip:
        raise HTTPException(status_code=403, detail="Source IP not allowed")
    if not hmac.compare_digest(cmd.token.encode("utf-8"), expected_token.encode("utf-8")):
        raise HTTPException(status_code=401, detail="Invalid token")

    if os.environ.get("HERMES_CUA_LIVE_ENABLED") != "1" or not cmd.confirm_live:
        print(f"{datetime.now().isoformat()} - CUA {cmd.action} at {cmd.coords} - AUTHORIZED; simulated only")
        return {
            "status": "accepted", "action": cmd.action, "coords": cmd.coords,
            "text": cmd.text, "executed": False, "verified": False, "device": None,
            "note": "Authenticated request validated. Live XP execution requires server opt-in and confirm_live=true.",
        }

    if _cua_rate_limited(request.client.host, cmd.token):
        raise HTTPException(status_code=429, detail="CUA action rate limit exceeded", headers={"Retry-After": "5"})

    try:
        device_name = cmd.device or os.environ.get("HERMES_CUA_DEVICE")
        device = resolve_paired_device(read_registry(), device_name)
    except HTTPException:
        raise
    except (OSError, ValueError, KeyError, TypeError, UpdateError) as exc:
        raise HTTPException(status_code=503, detail="Paired-device registry is unavailable") from exc

    try:
        client = HermesXPClient(device["host"], device["token"], port=device["port"], timeout=5.0)
        expected_ack: str
        if cmd.action in _CUA_MOUSE_ACTIONS:
            width, height = _screen_dimensions(client.inspect())
            assert cmd.coords is not None
            x, y = cmd.coords
            if cmd.action in {"click_ok", "close_window", "click"}:
                validate_click(x, y, width, height, "left")
                acknowledgement = client.click(x, y, width, height, "left")
                expected_ack = "clicked"
            elif cmd.action == "right_click":
                validate_click(x, y, width, height, "right")
                acknowledgement = client.click(x, y, width, height, "right")
                expected_ack = "clicked"
            elif cmd.action == "double_click":
                validate_click(x, y, width, height, "left")
                acknowledgement = client.double_click(x, y, width, height)
                expected_ack = "double-clicked"
            elif cmd.action == "drag":
                assert cmd.end_coords is not None
                x2, y2 = cmd.end_coords
                validate_drag(x, y, x2, y2, width, height)
                acknowledgement = client.drag(x, y, x2, y2, width, height)
                expected_ack = "dragged"
            else:
                assert cmd.delta is not None
                validate_scroll(x, y, width, height, cmd.delta)
                acknowledgement = client.scroll(x, y, width, height, cmd.delta)
                expected_ack = "scrolled"
        elif cmd.action == "type_text":
            assert cmd.text is not None
            validate_text(cmd.text)
            acknowledgement = client.type_text(cmd.text)
            expected_ack = "typed"
        else:
            assert cmd.text is not None
            validate_key(cmd.text)
            acknowledgement = client.key(cmd.text)
            expected_ack = "key sent"
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="CUA action parameters are invalid for the paired device") from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Paired XP action could not be verified") from exc

    if not isinstance(acknowledgement, str) or acknowledgement.strip() != expected_ack:
        raise HTTPException(status_code=502, detail="Paired XP did not acknowledge the requested action")
    print(f"{datetime.now().isoformat()} - CUA {cmd.action} at {cmd.coords} - verified by paired device {device['name']}")
    return {
        "status": "success", "action": cmd.action, "coords": cmd.coords,
        "end_coords": cmd.end_coords, "delta": cmd.delta,
        "executed": True, "verified": True, "device": str(device["name"])[:80],
        "note": "The paired XP host acknowledged the requested UI action.",
    }

app.add_middleware(CUARequestLimitMiddleware)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=dashboard_bind_host(), port=8082)
