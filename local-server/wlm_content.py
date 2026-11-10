"""Host-side WLM display picture, custom emoticon, and background store.

The XP client is not contacted. Operators pass image paths explicitly;
nothing here invents a portrait.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote

UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
KINDS = {"emoticon": 2, "dp": 3, "background": 5}
CAPS = {"emoticon": 64 * 1024, "dp": 256 * 1024, "background": 512 * 1024}
MAX_EMOTICONS = 32
_PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDAT\x08\xd7c\xf8\xcf\xc0"
    b"\x00\x00\x00\x03\x00\x01\x00\x05\xfe\xd4\xef\x00\x00\x00\x00IEND\xaeB`\x82"
)


def sha1d(data: bytes) -> str:
    return base64.b64encode(hashlib.sha1(data).digest()).decode("ascii")


def sha1_hex(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def sha1c(*, creator: str, size: int, object_type: int, location: str, friendly: str, sha1d: str) -> str:
    blob = (
        f"Creator{creator}Size{size}Type{object_type}"
        f"Location{location}Friendly{friendly}SHA1D{sha1d}"
    )
    return base64.b64encode(hashlib.sha1(blob.encode("utf-8")).digest()).decode("ascii")


def friendly_name(text: str) -> str:
    raw = ("\x00" if not text else text).encode("utf-16le")
    return base64.b64encode(raw).decode("ascii")


def _xml(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def msn_object(*, creator: str, data: bytes, object_type: int, location: str, friendly: str) -> str:
    digest = sha1d(data)
    checksum = sha1c(
        creator=creator,
        size=len(data),
        object_type=object_type,
        location=location,
        friendly=friendly,
        sha1d=digest,
    )
    return (
        f'<msnobj Creator="{_xml(creator)}" Size="{len(data)}" Type="{object_type}" '
        f'Location="{_xml(location)}" Friendly="{_xml(friendly)}" '
        f'SHA1D="{digest}" SHA1C="{checksum}"/>'
    )


def quote_msnobj(msnobj: str) -> str:
    return quote(msnobj, safe="")


def image_kind(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8"):
        return "jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    return None


def _check_uuid(uuid: str) -> str:
    if not isinstance(uuid, str) or not UUID_RE.fullmatch(uuid):
        raise ValueError("uuid must be a canonical hex UUID")
    return uuid


def resolve_usertile(storage_path: Path, uuid: str, small: bool) -> Path | None:
    if not isinstance(uuid, str) or not UUID_RE.fullmatch(uuid):
        return None
    storage_path = Path(storage_path)
    if not storage_path.is_dir():
        return None
    if small:
        thumb = storage_path / f"{uuid}_thumb.png"
        return thumb if thumb.is_file() else None
    matches = sorted(
        p for p in storage_path.glob(f"{uuid}.*")
        if p.is_file() and not p.name.startswith(f"{uuid}_thumb")
    )
    return matches[0] if matches else None


def profile_image_stats(storage_path: Path, uuid: str) -> tuple[str | None, int, int]:
    full = resolve_usertile(storage_path, uuid, small=False)
    thumb = resolve_usertile(storage_path, uuid, small=True)
    if full is None:
        return None, 0, thumb.stat().st_size if thumb else 0
    mime = full.suffix[1:] if full.suffix else None
    return mime, full.stat().st_size, thumb.stat().st_size if thumb else 0


def _thumb_png(data: bytes) -> bytes:
    try:
        from io import BytesIO
        from PIL import Image
        image = Image.open(BytesIO(data))
        image = image.convert("RGB").resize((21, 21))
        out = BytesIO()
        image.save(out, format="PNG")
        return out.getvalue()
    except Exception:
        return _PNG_1X1 if _PNG_1X1.startswith(b"\x89PNG") else data[:0] or _fallback_png()


def _fallback_png() -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
    )


class ContentStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    def store(self, uuid: str, kind: str, data: bytes, *, creator: str, location: str,
              friendly: str = "", shortcut: str | None = None) -> dict:
        uuid = _check_uuid(uuid)
        if kind not in KINDS:
            raise ValueError("unknown content kind")
        if not isinstance(data, (bytes, bytearray)):
            raise ValueError("content must be bytes")
        data = bytes(data)
        if len(data) > CAPS[kind]:
            raise ValueError(f"{kind} exceeds {CAPS[kind]} bytes")
        ext = image_kind(data)
        if ext is None:
            raise ValueError("only PNG, JPEG, and GIF are hosted")
        if not creator or "@" not in creator or any(c in creator for c in "\"<>&\r\n\t "):
            raise ValueError("creator must be a plain email")
        if not location or any(c in location for c in "\"<>&\r\n\t "):
            raise ValueError("location must be a single token")
        object_type = KINDS[kind]
        friendly_attr = friendly_name(friendly)
        obj = msn_object(
            creator=creator, data=data, object_type=object_type,
            location=location, friendly=friendly_attr,
        )
        digest = sha1d(data)
        hexid = sha1_hex(data)
        record = {
            "kind": kind,
            "object_type": object_type,
            "sha1d": digest,
            "sha1hex": hexid,
            "msnobj": obj,
            "location": location,
            "shortcut": shortcut,
            "ext": ext,
        }
        wlm_dir = self.root / "storage" / "wlm" / uuid
        wlm_dir.mkdir(parents=True, exist_ok=True)
        if kind == "dp":
            (wlm_dir / f"dp.{ext}").write_bytes(data)
            (wlm_dir / "dp_thumb.png").write_bytes(_thumb_png(data))
            tile_dir = self.root / "storage" / "dp" / uuid[0] / uuid[:2]
            tile_dir.mkdir(parents=True, exist_ok=True)
            for old in tile_dir.glob(f"{uuid}.*"):
                if old.is_file() and not old.name.startswith(f"{uuid}_thumb"):
                    old.unlink()
            (tile_dir / f"{uuid}.{ext}").write_bytes(data)
            (tile_dir / f"{uuid}_thumb.png").write_bytes(_thumb_png(data))
        else:
            kind_dir = wlm_dir / kind
            kind_dir.mkdir(parents=True, exist_ok=True)
            (kind_dir / f"{hexid}.{ext}").write_bytes(data)
        if kind == "background":
            (wlm_dir / "scene.xml").write_text(obj, encoding="utf-8")
        self._put_manifest(uuid, kind, record)
        return record

    def _manifest_path(self, uuid: str) -> Path:
        return self.root / "storage" / "wlm" / uuid / "manifest.json"

    def _put_manifest(self, uuid: str, kind: str, record: dict) -> None:
        path = self._manifest_path(uuid)
        manifest = {"dp": [], "emoticons": [], "background": []}
        if path.is_file():
            manifest.update(json.loads(path.read_text(encoding="utf-8")))
        key = {"dp": "dp", "emoticon": "emoticons", "background": "background"}[kind]
        rows = [row for row in manifest.get(key, []) if row.get("sha1hex") != record["sha1hex"]
                and row.get("shortcut") != record.get("shortcut")]
        rows.append(record)
        manifest[key] = rows
        path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def matching_emoticons(text: str, catalog: list) -> list:
    hits = []
    for item in catalog:
        shortcut = item.get("shortcut") or ""
        if not shortcut:
            continue
        start = 0
        while True:
            index = text.find(shortcut, start)
            if index < 0:
                break
            before = text[index - 1] if index else ""
            after = text[index + len(shortcut):index + len(shortcut) + 1]
            if not _token_char(before) and not _token_char(after):
                hits.append(item)
                break
            start = index + 1
    return hits


def _token_char(ch: str) -> bool:
    return bool(ch) and (ch.isalnum() or ch == "_")


def sync_configured(store: ContentStore, *, uuid: str, creator: str, environ) -> dict:
    dp = (environ.get("HERMES_MSN_DP") or "").strip()
    background = (environ.get("HERMES_MSN_BACKGROUND") or "").strip()
    emoticon_dir = (environ.get("HERMES_MSN_EMOTICONS_DIR") or "").strip()
    if not dp and not background and not emoticon_dir:
        return {"status": "skipped"}
    result = {"status": "synced", "rejected": []}
    if dp:
        saved = store.store(
            uuid, "dp", Path(dp).read_bytes(), creator=creator, location="tile.tmp"
        )
        result["msnobj"] = saved["msnobj"]
        result["msnobj_quoted"] = quote_msnobj(saved["msnobj"])
    if background:
        saved = store.store(
            uuid, "background", Path(background).read_bytes(),
            creator=creator, location="scene.tmp",
        )
        result["scene"] = saved["msnobj"]
    if emoticon_dir:
        names = sorted(p.name for p in Path(emoticon_dir).iterdir() if p.is_file())
        stored = 0
        for name in names:
            if stored >= MAX_EMOTICONS:
                result["rejected"].append(name)
                continue
            path = Path(emoticon_dir) / name
            stem = Path(name).stem
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,24}", stem):
                result["rejected"].append(name)
                continue
            data = path.read_bytes()
            if image_kind(data) is None or len(data) > CAPS["emoticon"]:
                result["rejected"].append(name)
                continue
            shortcut = f"({stem})"
            store.store(
                uuid, "emoticon", data, creator=creator,
                location=shortcut, friendly=shortcut, shortcut=shortcut,
            )
            stored += 1
    catalog = store.root / "storage" / "wlm" / uuid / "manifest.json"
    if catalog.is_file():
        result["catalog_path"] = str(catalog)
    return result


def serve(root: str | Path, path: str) -> tuple[int, str, bytes]:
    if not path.startswith("/") or "\\" in path or "\x00" in path:
        return 404, "text/plain", b""
    parts = [part for part in path.split("?")[0].split("/") if part]
    if any(part in (".", "..") for part in parts):
        return 404, "text/plain", b""
    root = Path(root)
    try:
        if len(parts) == 4 and parts[0] == "storage" and parts[1] == "usertile":
            uuid, which = parts[2], parts[3]
            if which not in ("static", "small") or not UUID_RE.fullmatch(uuid):
                return 404, "text/plain", b""
            folder = root / "storage" / "dp" / uuid[0] / uuid[:2]
            found = resolve_usertile(folder, uuid, small=(which == "small"))
            if found is None:
                return 404, "text/plain", b""
            return 200, _ctype(found.suffix), found.read_bytes()
        if len(parts) == 4 and parts[0] == "storage" and parts[1] in ("emoticon", "background"):
            kind, uuid, hexid = parts[1], parts[2], parts[3]
            if not UUID_RE.fullmatch(uuid) or not SHA_RE.fullmatch(hexid):
                return 404, "text/plain", b""
            folder = root / "storage" / "wlm" / uuid / kind
            if not folder.is_dir():
                return 404, "text/plain", b""
            matches = sorted(
                p for p in folder.glob(f"{hexid}.*")
                if p.is_file() and p.name.startswith(hexid + ".")
            )
            if not matches:
                return 404, "text/plain", b""
            return 200, _ctype(matches[0].suffix), matches[0].read_bytes()
    except OSError:
        return 404, "text/plain", b""
    return 404, "text/plain", b""


def _ctype(suffix: str) -> str:
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
    }.get(suffix.lower(), "application/octet-stream")


def serve_forever(root: str | Path, host: str = "127.0.0.1", port: int = 0):
    if host != "127.0.0.1":
        raise ValueError("content host binds loopback only")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            status, ctype, body = serve(root, self.path)
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            return

    server = ThreadingHTTPServer((host, port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
