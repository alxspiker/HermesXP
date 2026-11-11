from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, Response
from PIL import Image
import io
import os
from datetime import datetime
from pathlib import Path
import sys

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from tools.hermesxp_ui import HermesXPClient, ResponseTooLargeError
from tools.hermesxp_update import read_registry, UpdateError

app = FastAPI(title="HermesXP Vision Dashboard Server")

# Mount static files (dashboard.html)
app.mount("/static", StaticFiles(directory="."), name="static")

@app.get("/", response_class=HTMLResponse)
async def root():
    with open("dashboard.html", "r") as f:
        return f.read()

@app.get("/api/status")
async def status():
    return {"services": "active", "dashboard": "v0.7", "vision": "heuristic-only", "model": "unavailable", "cua": "simulated-only", "xp_endpoint": "paired-device-authenticated"}


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
    """Analyze a screenshot obtained through the selected paired XP device."""
    try:
        _content, width, height = fetch_paired_screenshot(device)
        suggestions = generate_heuristic_suggestions(width, height)
        analysis = {
            "status": "success",
            "analysis_mode": "heuristic",
            "timestamp": datetime.now().isoformat(),
            "screenshot_size": f"{width}x{height}",
            "suggestions": suggestions,
            "note": "Heuristic coordinate estimates only; visual model integration is unavailable. Suggestions are not detected UI elements."
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


from pydantic import BaseModel, Field, model_validator
from typing import Literal, Optional
class CUACommand(BaseModel):
    action: Literal["click_ok", "close_window", "click", "right_click", "double_click", "type_text", "key_press", "scroll", "drag"]
    coords: Optional[tuple[int, int]] = None
    text: Optional[str] = Field(default=None, max_length=256)
    token: str = Field(min_length=32, max_length=512)

    @model_validator(mode="after")
    def validate_coordinates(self):
        if self.coords is not None and any(value < 0 or value > 8192 for value in self.coords):
            raise ValueError("coordinates must be between 0 and 8192")
        return self

@app.post("/api/cua/execute")
async def execute_cua_command(cmd: CUACommand, request: Request):
    """Authenticate against host-configured secret and exact allowed peer; log only, never execute."""
    expected_token = os.environ.get("HERMES_CUA_TOKEN")
    allowed_ip = os.environ.get("HERMES_CUA_ALLOWED_IP")
    if not expected_token or len(expected_token) < 32 or not allowed_ip:
        raise HTTPException(status_code=503, detail="CUA is not configured")
    if request.client is None or request.client.host != allowed_ip:
        raise HTTPException(status_code=403, detail="Source IP not allowed")
    if not __import__("hmac").compare_digest(cmd.token, expected_token):
        raise HTTPException(status_code=401, detail="Invalid token")
    if cmd.action in {"type_text", "key_press"} and not cmd.text:
        raise HTTPException(status_code=422, detail="This action requires text")
    if cmd.action not in {"type_text", "key_press"} and cmd.text is not None:
        raise HTTPException(status_code=422, detail="Text is not allowed for this action")
    if cmd.action in {"drag", "scroll"} and cmd.coords is None:
        raise HTTPException(status_code=422, detail=f"{cmd.action} requires coordinates")
    print(f"{datetime.now().isoformat()} - CUA {cmd.action} at {cmd.coords} - AUTHORIZED; simulated only")
    return {"status": "accepted", "action": cmd.action, "coords": cmd.coords,
            "text": cmd.text, "executed": False,
            "note": "Authenticated request validated and logged. Live XP execution is disabled."}

app.add_middleware(CUARequestLimitMiddleware)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8082)
