"""Fetch a versioned *generic* HermesXP release on the modern Hermes host.

Release assets must carry a RELEASE.json with the exact source Git commit and
SHA-256 digests. The XP never downloads from GitHub and release assets contain
no machine-specific tokens, local CA certificates, or account credentials.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.request


REPOSITORY = "alxspiker/HermesXP"
ASSETS = ("HermesXP.exe", "HermesXP-Updater.exe", "HermesXP-Service.exe")
MAX_DOWNLOAD = 2 * 1024 * 1024


def release_repository() -> str:
    """Choose the explicitly approved release source for forks of HermesXP."""
    repository = os.environ.get("HERMESXP_RELEASE_REPOSITORY", REPOSITORY).strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}", repository):
        raise ValueError("HERMESXP_RELEASE_REPOSITORY must be a GitHub owner/repo")
    owner, name = repository.split("/")
    if owner in (".", "..") or name in (".", ".."):
        raise ValueError("HERMESXP_RELEASE_REPOSITORY must not contain path traversal segments")
    return repository


def _get(url: str) -> bytes:
    if not url.startswith("https://"):
        raise ValueError("Updates must be fetched over HTTPS")
    request = urllib.request.Request(url, headers={"User-Agent": "HermesXP-host-updater"})
    with urllib.request.urlopen(request, timeout=12) as response:
        if response.url.split("/")[2] not in ("github.com", "api.github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com"):
            raise ValueError("Unexpected release download hostname")
        data = response.read(MAX_DOWNLOAD + 1)
    if len(data) > MAX_DOWNLOAD:
        raise ValueError("Release asset exceeds size limit")
    return data


def load_release(version: str, commit: str) -> dict[str, bytes] | None:
    """Return verified files if and ONLY if the tag matches the installed plugin revision."""
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        raise ValueError("Invalid plugin version")
    if not re.fullmatch(r"[0-9a-fA-F]{40}", commit):
        raise ValueError("Missing plugin source revision")
    url = f"https://api.github.com/repos/{release_repository()}/releases/tags/v{version}"
    try:
        data = json.loads(_get(url))
    except (urllib.error.HTTPError, OSError, TimeoutError, ValueError):
        return None
    urls = {a["name"]: a["browser_download_url"] for a in data.get("assets", [])}
    if not all(name in urls for name in (*ASSETS, "RELEASE.json")):
        return None
    manifest = json.loads(_get(urls["RELEASE.json"]))
    if manifest.get("commit", "").lower() != commit.lower() or manifest.get("version") != version:
        return None
    files = {}
    for name in ASSETS:
        expected = manifest.get("sha256", {}).get(name, "")
        if not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise ValueError(f"Release digest missing for {name}")
        binary = _get(urls[name])
        if hashlib.sha256(binary).hexdigest() != expected:
            raise ValueError(f"Release checksum mismatch: {name}")
        files[name] = binary
    return files


def write_release_manifest(folder: Path, version: str, commit: str) -> Path:
    manifest = {
        "version": version,
        "commit": commit,
        "sha256": {
            name: hashlib.sha256((folder / name).read_bytes()).hexdigest()
            for name in ASSETS
        },
    }
    output = folder / "RELEASE.json"
    output.write_text(json.dumps(manifest, indent=2) + "\n")
    return output
