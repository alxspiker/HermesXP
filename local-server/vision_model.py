"""Bounded host-side LFM3-VL inference for HermesXP screenshots."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time

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
MODEL_ROOT = Path(os.environ.get("HERMESXP_LFM3_ROOT", "/home/hermes/local-multimodal"))
_BIN = MODEL_ROOT / "bin/llama-b12167"
_MODELS = MODEL_ROOT / "models"
_FFMPEG = Path("/home/hermes/.hermes/tools/ffmpeg-9.0.1-linux-x64/bin")
_MAX_OUTPUT = 65536
_MAX_IMAGE_PIXELS = 3840 * 2160
_STATE = {"state": "not-verified", "last_success": None, "error": None}


def model_status() -> dict:
    """Describe observed inference state; file presence alone is never readiness."""
    return {
        "state": _STATE["state"],
        "model": MODEL_NAME if _STATE["state"] == "verified" else None,
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
    raise ValueError("LFM3-VL output did not contain a JSON detection array")


def parse_model_detections(raw: str, *, width: int, height: int) -> list[dict]:
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
                           "confidence": float(confidence), "source": "LFM3-VL"})
    return detections


def _run_cli(image_path: Path, prompt: str = PROMPT, *, timeout: int = 180) -> str:
    binary = _BIN / "llama-cli"
    model = _MODELS / MODEL_NAME
    projector = _MODELS / "mmproj-LFM3-VL-2B-F16.gguf"
    if not all(path.is_file() for path in (binary, model, projector)):
        raise RuntimeError("LFM3-VL runtime or model files are missing")
    cmd = [
        "/usr/bin/prlimit", "--as=7516192768", "--fsize=67108864", "--nofile=256", "--",
        str(binary), "-m", str(model), "--mmproj", str(projector), "-t", "4", "-c", "4096",
        "-n", "512", "-ngl", "0", "--no-mmproj-offload", "--offline", "--single-turn",
        "--no-warmup", "--no-display-prompt", "--top-p", "1.0", "--min-p", "0.0",
        "--reasoning", "off", "--no-reasoning-preserve", "--image", str(image_path), "-p", prompt,
    ]
    env = {
        "PATH": str(_FFMPEG) + ":/usr/bin:/bin",
        "LD_LIBRARY_PATH": str(MODEL_ROOT / "deps/usr/lib/x86_64-linux-gnu") + ":" + str(_BIN),
        "HOME": "/home/hermes", "OMP_NUM_THREADS": "4",
    }
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        process = subprocess.Popen(cmd, stdout=stdout, stderr=stderr, env=env,
                                   stdin=subprocess.DEVNULL, start_new_session=True)
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            raise TimeoutError("LFM3-VL inference timed out") from exc
        stdout.seek(0)
        output = stdout.read(_MAX_OUTPUT + 1)
        stderr.seek(0)
        error = stderr.read(4096).decode("utf-8", "replace")
    if process.returncode != 0:
        raise RuntimeError("LFM3-VL inference failed (exit %s): %s" % (process.returncode, error[-1200:]))
    if len(output) > _MAX_OUTPUT:
        raise RuntimeError("LFM3-VL output exceeded 64 KiB")
    return _extract_answer(output.decode("utf-8", "replace"), prompt)


def infer_lfm3vl(image: Image.Image) -> list[dict]:
    """Run actual local model inference; on error, record failure and re-raise."""
    try:
        if image.width * image.height > _MAX_IMAGE_PIXELS:
            raise ValueError("screenshot resolution exceeds 4K")
        with tempfile.TemporaryDirectory(prefix="hermesxp-vision-") as directory:
            image_path = Path(directory) / "screenshot.png"
            image.convert("RGB").save(image_path, format="PNG")
            result = parse_model_detections(_run_cli(image_path), width=image.width, height=image.height)
        _STATE.update(state="verified", last_success=time.time(), error=None)
        return result
    except Exception as exc:
        _STATE.update(state="unavailable", error=type(exc).__name__)
        raise
