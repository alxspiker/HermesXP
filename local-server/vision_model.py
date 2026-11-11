"""Bounded, user-selectable host-side vision inference for HermesXP screenshots."""
from __future__ import annotations

import base64
import io
import ipaddress
import json
import math
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time
from urllib.parse import urlsplit
from urllib.request import (
    HTTPRedirectHandler, Request, build_opener,
)

from PIL import Image

MODEL_NAME = "LFM3-VL-2B-QAD-Q4_0.gguf"
PROMPT = (
    "Identify only visible user-interface controls (windows, buttons, text fields, "
    "menus, checkboxes, and other interactive controls). Return only a JSON array. "
    "Each object must have type, text (empty string if unreadable), bbox "
    "[left,top,right,bottom] in a 0-1024 square coordinate system, and confidence "
    "from 0 to 1. Example: [{\"type\":\"button\",\"text\":\"OK\","
    "\"bbox\":[100,100,300,200],\"confidence\":0.9}]. "
    "Do not invent controls that are not visible."
)
MODEL_ROOT = Path(os.environ.get(
    "HERMESXP_VISION_ROOT",
    os.environ.get("HERMESXP_LFM3_ROOT", str(Path.home() / "local-multimodal")),
)).expanduser()
_BIN = MODEL_ROOT / "bin/llama-b12167"
_MODELS = MODEL_ROOT / "models"
_FFMPEG = Path(os.environ.get(
    "HERMESXP_VISION_FFMPEG_DIR",
    str(Path.home() / ".hermes/tools/ffmpeg-9.0.1-linux-x64/bin"),
)).expanduser()
_MAX_OUTPUT = 65536
_MAX_IMAGE_PIXELS = 3840 * 2160
_STATE = {"state": "not-verified", "last_success": None, "error": None}


def _backend() -> str:
    backend = os.environ.get("HERMESXP_VISION_BACKEND", "llama-cli").strip().lower()
    if backend not in ("llama-cli", "openai-compatible", "disabled"):
        raise ValueError("HERMESXP_VISION_BACKEND must be llama-cli, openai-compatible or disabled")
    return backend


def _model_name() -> str:
    if _backend() == "openai-compatible":
        return os.environ.get("HERMESXP_VISION_API_MODEL", "").strip()
    return os.environ.get("HERMESXP_VISION_MODEL", MODEL_NAME).strip()


def model_status() -> dict:
    """Describe observed inference state; file presence alone is never readiness."""
    backend = _backend()
    state = "disabled" if backend == "disabled" else _STATE["state"]
    return {
        "state": state,
        "model": _model_name() if state == "verified" else None,
        "backend": backend,
        "last_success": _STATE["last_success"],
        "error": _STATE["error"],
    }


def _extract_answer(raw: str, prompt: str = PROMPT) -> str:
    marker = "\n> " + prompt + "\n"
    if marker not in raw:
        raise ValueError("could not locate model response in CLI output")
    result = raw.split(marker, 1)[1].split("\n[ Prompt:", 1)[0].strip()
    if "[Start thinking]" in result:
        if "[End thinking]" not in result:
            raise ValueError("model exhausted its output budget before a final answer")
        result = result.split("[End thinking]", 1)[1].strip()
    if not result:
        raise ValueError("model returned no final answer")
    return result


def _decode_array(raw: str) -> list:
    decoder = json.JSONDecoder()
    for index, char in enumerate(raw):
        if char != "[":
            continue
        try:
            value, _end = decoder.raw_decode(raw[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, list):
            return value
    raise ValueError("vision output did not contain a JSON detection array")


def parse_model_detections(raw: str, *, width: int, height: int,
                           source: str = "LFM3-VL") -> list[dict]:
    """Validate model output and map its 0–1024 square coordinates to pixels."""
    if type(width) is not int or type(height) is not int or not 1 <= width <= 3840 or not 1 <= height <= 2160:
        raise ValueError("invalid screenshot dimensions")
    values = _decode_array(raw)
    if len(values) > 100:
        raise ValueError("model returned too many detections")
    detections = []
    for value in values:
        if not isinstance(value, dict):
            raise ValueError("each detection must be an object")
        kind = value.get("type")
        text = value.get("text", "")
        bbox = value.get("bbox")
        confidence = value.get("confidence")
        if not isinstance(kind, str) or not 1 <= len(kind) <= 40:
            raise ValueError("detection type is invalid")
        if not isinstance(text, str) or len(text) > 160:
            raise ValueError("detection text is invalid")
        if (not isinstance(bbox, list) or len(bbox) != 4 or
                any(type(point) not in (int, float) or not math.isfinite(point) for point in bbox)):
            raise ValueError("detection bbox must contain four finite numbers")
        left, top, right, bottom = bbox
        if not (0 <= left < right <= 1024 and 0 <= top < bottom <= 1024):
            raise ValueError("detection bbox is outside the normalized image")
        if (isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or
                not math.isfinite(confidence) or not 0 <= confidence <= 1):
            raise ValueError("detection confidence must be between 0 and 1")
        pixels = [round(left * width / 1024), round(top * height / 1024),
                  round(right * width / 1024), round(bottom * height / 1024)]
        detections.append({"type": kind, "text": text, "bbox": pixels,
                           "confidence": float(confidence), "source": source[:80]})
    return detections


def _configured_path(env_name: str, fallback: Path, *, root: Path = _MODELS) -> Path:
    raw = os.environ.get(env_name, "").strip()
    if not raw:
        return fallback
    path = Path(raw).expanduser()
    return path if path.is_absolute() else root / path


def _positive_int(name: str, default: int, maximum: int) -> int:
    raw = os.environ.get(name, str(default))
    try:
        number = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if not 1 <= number <= maximum:
        raise ValueError(f"{name} must be between 1 and {maximum}")
    return number


def _run_cli(image_path: Path, prompt: str = PROMPT, *, timeout: int = 180) -> str:
    binary = _configured_path("HERMESXP_VISION_LLAMA_CLI", _BIN / "llama-cli", root=MODEL_ROOT)
    model = _configured_path("HERMESXP_VISION_MODEL_PATH", _MODELS / _model_name())
    projector = _configured_path("HERMESXP_VISION_PROJECTOR_PATH", _MODELS / "mmproj-LFM3-VL-2B-F16.gguf")
    if not all(path.is_file() for path in (binary, model, projector)):
        raise RuntimeError("configured vision runtime, model or projector is missing")
    threads = _positive_int("HERMESXP_VISION_THREADS", 4, 32)
    cmd = [
        str(binary), "-m", str(model), "--mmproj", str(projector), "-t", str(threads), "-c", "4096",
        "-n", "512", "-ngl", "0", "--no-mmproj-offload", "--offline", "--single-turn",
        "--no-warmup", "--no-display-prompt", "--top-p", "1.0", "--min-p", "0.0",
        "--reasoning", "off", "--no-reasoning-preserve", "--image", str(image_path), "-p", prompt,
    ]
    prlimit = shutil.which("prlimit")
    if prlimit:
        cmd = [prlimit, "--as=7516192768", "--fsize=67108864", "--nofile=256", "--", *cmd]
    env = {
        "PATH": (str(_FFMPEG) + ":" if _FFMPEG.is_dir() else "") + "/usr/bin:/bin",
        "LD_LIBRARY_PATH": os.environ.get("HERMESXP_VISION_LIBRARY_PATH",
            str(MODEL_ROOT / "deps/usr/lib/x86_64-linux-gnu") + ":" + str(_BIN)),
        "HOME": str(Path.home()), "OMP_NUM_THREADS": str(threads),
    }
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        process = subprocess.Popen(cmd, stdout=stdout, stderr=stderr, env=env,
                                   stdin=subprocess.DEVNULL, start_new_session=True)
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            raise TimeoutError("vision inference timed out") from exc
        stdout.seek(0)
        output = stdout.read(_MAX_OUTPUT + 1)
        stderr.seek(0)
        error = stderr.read(4096).decode("utf-8", "replace")
    if process.returncode != 0:
        raise RuntimeError("vision inference failed (exit %s): %s" % (process.returncode, error[-1200:]))
    if len(output) > _MAX_OUTPUT:
        raise RuntimeError("vision output exceeded 64 KiB")
    return _extract_answer(output.decode("utf-8", "replace"), prompt)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def _run_openai_compatible(image: Image.Image, prompt: str = PROMPT) -> str:
    """Opt-in provider; credentials and image are sent only to the specified URL."""
    url = os.environ.get("HERMESXP_VISION_API_URL", "").strip()
    model = _model_name()
    parsed = urlsplit(url)
    if not model or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ValueError("configure HERMESXP_VISION_API_URL and HERMESXP_VISION_API_MODEL")
    if parsed.scheme not in ("http", "https"):
        raise ValueError("vision API URL must use HTTPS or local HTTP")
    if parsed.scheme == "http":
        try:
            host = ipaddress.ip_address(parsed.hostname)
            local = host.is_private or host.is_loopback
        except ValueError:
            local = parsed.hostname.lower() == "localhost"
        if not local:
            raise ValueError("plain HTTP vision API must use an explicit private or loopback address")
    if not parsed.path.endswith("/chat/completions"):
        raise ValueError("vision API URL must point to a chat/completions endpoint")
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    body = json.dumps({
        "model": model, "max_tokens": 512, "temperature": 0,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {
                "url": "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii"),
            }},
        ]}],
    }).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    key = os.environ.get("HERMESXP_VISION_API_KEY", "")
    if key:
        headers["Authorization"] = "Bearer " + key
    request = Request(url, body, headers=headers, method="POST")
    with build_opener(_NoRedirect).open(request, timeout=180) as response:
        data = response.read(_MAX_OUTPUT + 1)
    if len(data) > _MAX_OUTPUT:
        raise RuntimeError("vision API response exceeded 64 KiB")
    payload = json.loads(data)
    answer = payload["choices"][0]["message"]["content"]
    if not isinstance(answer, str):
        raise ValueError("vision API did not return text content")
    return answer


def infer_lfm3vl(image: Image.Image) -> list[dict]:
    """Compatibility entry point for configured vision inference."""
    try:
        if image.width * image.height > _MAX_IMAGE_PIXELS:
            raise ValueError("screenshot resolution exceeds 4K")
        backend = _backend()
        if backend == "disabled":
            raise RuntimeError("vision inference is disabled")
        if backend == "openai-compatible":
            raw = _run_openai_compatible(image.convert("RGB"))
        else:
            with tempfile.TemporaryDirectory(prefix="hermesxp-vision-") as directory:
                image_path = Path(directory) / "screenshot.png"
                image.convert("RGB").save(image_path, format="PNG")
                raw = _run_cli(image_path)
        source = "LFM3-VL" if backend == "llama-cli" and _model_name() == MODEL_NAME else _model_name()
        result = parse_model_detections(raw, width=image.width, height=image.height, source=source)
        _STATE.update(state="verified", last_success=time.time(), error=None)
        return result
    except Exception as exc:
        _STATE.update(state="unavailable", error=type(exc).__name__)
        raise
