"""Apply HermesXP deployment patches to the cloned msn-server tree.

The server code is downloaded at install time (not vendored), so fixes for
its drift against modern dependencies live here and are applied by
install.sh right after the pinned checkout. Each patch is small, guarded
(only applied when the exact upstream text is present), and documented
below. Re-running is safe: already-patched text is left alone.

Patches:
  1. HLL 3.0 stats restore (core/stats.py::_stats_from_json).
  2. WLM hosting restoration (front/msn/http/other.py): display-picture
     lookup uses the user's own file, not the first file in a shared
     directory, and custom emoticon/background bytes are served by SHA-1.
  3. Scene persistence call sites (front/msn/msnp_ns.py), backed by
     front/msn/wlm_hosting.py copied from this directory.

Usage: python patch-server.py <server-dir>
"""
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

PATCHES = [
    (
        "core/stats.py",
        "\t\thll = HyperLogLog(12)\n\t\thll.set_registers(bytearray(json['users_active']))\n\t\tstats['users_active'] = hll\n",
        "\t\thll = HyperLogLog(12)\n\t\t# HLL >= 3.0 removed set_registers; start the counter fresh.\n\t\tif hasattr(hll, 'set_registers'):\n\t\t\thll.set_registers(bytearray(json['users_active']))\n\t\tstats['users_active'] = hll\n",
    ),
    (
        "front/msn/http/other.py",
        "\tapp.router.add_get('/storage/usertile/{uuid}/small', lambda req: handle_usertile(req, small = True))\n\tapp.router.add_post('/ppsecure/sha1auth.srf', handle_sha1auth)\n",
        "\tapp.router.add_get('/storage/usertile/{uuid}/small', lambda req: handle_usertile(req, small = True))\n\tapp.router.add_get('/storage/emoticon/{uuid}/{sha1hex}', handle_hosted_object)\n\tapp.router.add_get('/storage/background/{uuid}/{sha1hex}', handle_hosted_object)\n\tapp.router.add_post('/ppsecure/sha1auth.srf', handle_sha1auth)\n",
    ),
    (
        "front/msn/http/other.py",
        "\t\tif files:\n\t\t\text = files[0].suffix\n\t\t\tmime = ext[1:]\n\t\t\t\n\t\t\timage_path = storage_path / '{}{}'.format(user.uuid, ext)\n\t\t\timage_size = image_path.stat().st_size\n\t\t\timage_thumb_path = storage_path / '{}_thumb{}'.format(user.uuid, ext)\n\t\t\timage_thumb_size = image_thumb_path.stat().st_size\n\t\t\n",
        "\t\tmime, image_size, image_thumb_size = _profile_image_stats(storage_path, user.uuid)\n\t\t\n",
    ),
    (
        "front/msn/http/other.py",
        "def _get_storage_path(uuid: str) -> Path:\n\treturn Path('storage/dp') / uuid[0:1] / uuid[0:2]\n",
        "def _get_storage_path(uuid: str) -> Path:\n\treturn Path('storage/dp') / uuid[0:1] / uuid[0:2]\n\ndef _resolve_usertile_file(storage_path, uuid, small):\n\timport re as _re\n\tfrom pathlib import Path as _Path\n\tif not isinstance(uuid, str) or not _re.fullmatch(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}', uuid):\n\t\treturn None\n\tstorage_path = _Path(storage_path)\n\tif not storage_path.is_dir():\n\t\treturn None\n\tif small:\n\t\tthumb = storage_path / (uuid + '_thumb.png')\n\t\treturn thumb if thumb.is_file() else None\n\tmatches = sorted(p for p in storage_path.glob(uuid + '.*') if p.is_file() and not p.name.startswith(uuid + '_thumb'))\n\treturn matches[0] if matches else None\n\ndef _profile_image_stats(storage_path, uuid):\n\tfull = _resolve_usertile_file(storage_path, uuid, False)\n\tthumb = _resolve_usertile_file(storage_path, uuid, True)\n\tif full is None:\n\t\treturn None, 0, (thumb.stat().st_size if thumb else 0)\n\tmime = full.suffix[1:] if full.suffix else None\n\treturn mime, full.stat().st_size, (thumb.stat().st_size if thumb else 0)\n",
    ),
    (
        "front/msn/http/other.py",
        "async def handle_usertile(req: web.Request, small: bool = False) -> web.Response:\n\tuuid = req.match_info['uuid']\n\tstorage_path = _get_storage_path(uuid)\n\tif not (storage_path.is_dir() and storage_path.exists()):\n\t\traise web.HTTPNotFound()\n\t\n\tfiles = list(storage_path.iterdir())\n\t\n\tif not files:\n\t\traise web.HTTPNotFound()\n\t\n\text = files[0].suffix\n\timage_path = storage_path / '{}{}{}'.format(uuid, '_thumb' if small else '', ext)\n\treturn web.HTTPOk(content_type = 'image/{}'.format(ext[1:]), body = image_path.read_bytes())\n",
        "async def handle_usertile(req: web.Request, small: bool = False) -> web.Response:\n\tuuid = req.match_info['uuid']\n\tstorage_path = _get_storage_path(uuid)\n\timage_path = _resolve_usertile_file(storage_path, uuid, small)\n\tif image_path is None:\n\t\traise web.HTTPNotFound()\n\text = image_path.suffix\n\treturn web.HTTPOk(content_type = 'image/{}'.format(ext[1:] or 'png'), body = image_path.read_bytes())\n\nasync def handle_hosted_object(req: web.Request) -> web.Response:\n\tkind = 'emoticon' if '/storage/emoticon/' in req.path else 'background'\n\tuuid = req.match_info['uuid']\n\tsha = req.match_info['sha1hex']\n\tif not re.fullmatch(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}', uuid):\n\t\traise web.HTTPNotFound()\n\tif not re.fullmatch(r'[0-9a-fA-F]{40}', sha):\n\t\traise web.HTTPNotFound()\n\tfolder = Path('storage/wlm') / uuid / kind\n\tmatches = sorted(p for p in folder.glob(sha + '.*') if p.is_file()) if folder.is_dir() else []\n\tif not matches:\n\t\traise web.HTTPNotFound()\n\text = matches[0].suffix.lower()\n\tctype = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.gif': 'image/gif'}.get(ext, 'application/octet-stream')\n\treturn web.HTTPOk(content_type = ctype, body = matches[0].read_bytes())\n",
    ),
    (
        "front/msn/msnp_ns.py",
        "\t\tbs.front_data['msn'] = True\n",
        "\t\tbs.front_data['msn'] = True\n\t\ttry:\n\t\t\tfrom .wlm_hosting import load_scene\n\t\t\t_restored_scene = load_scene(bs.user.uuid)\n\t\t\tif _restored_scene:\n\t\t\t\tbs.front_data['msn_msnobj_scene'] = _restored_scene\n\t\texcept Exception:\n\t\t\tpass\n",
    ),
    (
        "front/msn/msnp_ns.py",
        "\t\tscene = elm.find('Scene')\n\t\tif scene is not None:\n\t\t\tbs.front_data['msn_msnobj_scene'] = scene.text\n",
        "\t\tscene = elm.find('Scene')\n\t\tif scene is not None:\n\t\t\tbs.front_data['msn_msnobj_scene'] = scene.text\n\t\t\ttry:\n\t\t\t\tfrom .wlm_hosting import save_scene\n\t\t\t\tif scene.text:\n\t\t\t\t\tsave_scene(user.uuid, scene.text)\n\t\t\texcept Exception:\n\t\t\t\tpass\n",
    ),
]


def apply_patches(server_dir: Path) -> None:
    for relpath, old, new in PATCHES:
        path = server_dir / relpath
        text = path.read_text()
        if new in text:
            print(f"{relpath}: already patched")
            continue
        if old not in text:
            print(f"{relpath}: upstream text not found, NOT patched", file=sys.stderr)
            sys.exit(1)
        path.write_text(text.replace(old, new, 1))
        print(f"{relpath}: patched")
    dest = server_dir / "front" / "msn" / "wlm_hosting.py"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(HERE / "wlm_hosting.py", dest)
    print(f"{dest.name}: installed")


def main():
    apply_patches(Path(sys.argv[1]))


if __name__ == "__main__":
    main()
