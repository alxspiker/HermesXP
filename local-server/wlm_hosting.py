"""Persist a WLM scene so the next sign-in can restore it.

Copied into the pinned msn-server tree by patch-server.py. Paths are relative
to the server working directory. A bad UUID is rejected before any join.
"""
import re
from pathlib import Path

_UUID = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def _check(uuid: str) -> str:
    if not isinstance(uuid, str) or not _UUID.fullmatch(uuid):
        raise ValueError("bad uuid")
    return uuid


def scene_path(uuid: str) -> Path:
    return Path("storage/wlm") / _check(uuid) / "scene.xml"


def save_scene(uuid: str, scene: str) -> None:
    path = scene_path(uuid)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(scene or "", encoding="utf-8")


def load_scene(uuid: str):
    path = scene_path(uuid)
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    return text or None
