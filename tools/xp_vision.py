"""Lazy bridge between optional screenshot inference and Hermes tools.

Local model runtimes and optional remote providers are configured by the
Hermes host. Basic XP tools and Messenger do not import vision libraries.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path


def infer_screenshot(image) -> dict:
    path = Path(__file__).resolve().parents[1] / "local-server/vision_model.py"
    spec = importlib.util.spec_from_file_location("hermesxp_vision_model", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("HermesXP vision model helper is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    detections = module.infer_lfm3vl(image)
    status = module.model_status()
    return {"status": "verified", "backend": status["backend"],
            "model": status["model"], "detections": detections,
            "note": "Model detections, not guaranteed coordinates; verify before acting"}
