"""Host-side WLM display-picture, emoticon, and background sync.

These tests do not touch the XP machine or the live msn-server process.
"""
import base64
import hashlib
import importlib.util
import json
import os
import pathlib
import shutil
import struct
import subprocess
import tempfile
import unittest
import zlib
from urllib.request import urlopen

ROOT = pathlib.Path(__file__).resolve().parents[1]
LIB = ROOT / "local-server" / "wlm_content.py"
PATCHER = ROOT / "local-server" / "patch-server.py"
HOSTING = ROOT / "local-server" / "wlm_hosting.py"
PRESENCE = ROOT / "msn-bridge" / "wlm_presence.js"
MSN_HOME = pathlib.Path(os.environ.get("HERMES_HOME", str(pathlib.Path.home() / ".hermes")))
UPSTREAM = MSN_HOME / "msn-server/front/msn/http/other.py"
UPSTREAM_NS = MSN_HOME / "msn-server/front/msn/msnp_ns.py"

DOCUMENTED_SHA1C = "U32o6bosZzluJq82eAtMpx5dIEI="
UUID_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
UUID_B = "aaaabbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _png(width=1, height=1, rgb=(255, 0, 0)):
    def chunk(tag, data):
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    raw = b"".join(b"\x00" + bytes(rgb) * width for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


class WlmContentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.wlm = _load("wlm_content", LIB)

    def test_sha1c_matches_documented_vector(self):
        digest = self.wlm.sha1c(
            creator="buddy1@hotmail.com",
            size=24539,
            object_type=3,
            location="TFR2C.tmp",
            friendly="AAA=",
            sha1d="trC8SlFx2sWQxZMIBAWSEnXc8oQ=",
        )
        self.assertEqual(digest, DOCUMENTED_SHA1C)

    def test_empty_friendly_is_aaa_and_named_shortcut_is_utf16le(self):
        self.assertEqual(self.wlm.friendly_name(""), "AAA=")
        self.assertEqual(
            self.wlm.friendly_name("(h)"),
            base64.b64encode("(h)".encode("utf-16le")).decode("ascii"),
        )

    def test_msn_object_uses_documented_field_order_and_checksum(self):
        data = b"not-a-real-image-but-bytes"
        obj = self.wlm.msn_object(
            creator="bot@hermes.local",
            data=data,
            object_type=3,
            location="tile.tmp",
            friendly="AAA=",
        )
        sha1d = base64.b64encode(hashlib.sha1(data).digest()).decode("ascii")
        self.assertIn('Creator="bot@hermes.local"', obj)
        self.assertIn('Type="3"', obj)
        self.assertIn(f'SHA1D="{sha1d}"', obj)
        self.assertIn(
            f'SHA1C="{self.wlm.sha1c(creator="bot@hermes.local", size=len(data), object_type=3, location="tile.tmp", friendly="AAA=", sha1d=sha1d)}"',
            obj,
        )
        self.assertTrue(obj.startswith("<msnobj "))
        self.assertTrue(obj.endswith("/>"))
        quoted = self.wlm.quote_msnobj(obj)
        self.assertNotIn(" ", quoted)
        self.assertNotIn("<", quoted)

    def test_store_writes_per_uuid_and_escargot_tile_not_shared_prefix_only(self):
        png = _png()
        with tempfile.TemporaryDirectory() as tmp:
            store = self.wlm.ContentStore(tmp)
            saved = store.store(
                UUID_A, "dp", png, creator="bot@hermes.local", location="tile.tmp"
            )
            tile = pathlib.Path(tmp) / "storage" / "dp" / "a" / "aa" / f"{UUID_A}.png"
            thumb = pathlib.Path(tmp) / "storage" / "dp" / "a" / "aa" / f"{UUID_A}_thumb.png"
            self.assertTrue(tile.is_file())
            self.assertTrue(thumb.is_file())
            self.assertTrue(thumb.read_bytes().startswith(b"\x89PNG"))
            self.assertEqual(saved["object_type"], 3)
            self.assertEqual(saved["sha1d"], self.wlm.sha1d(png))
            again = store.store(
                UUID_A, "dp", png, creator="bot@hermes.local", location="tile.tmp"
            )
            manifest = json.loads(
                (pathlib.Path(tmp) / "storage" / "wlm" / UUID_A / "manifest.json").read_text()
            )
            self.assertEqual(len(manifest["dp"]), 1)
            self.assertEqual(again["msnobj"], saved["msnobj"])

    def test_resolve_usertile_ignores_neighbor_that_sorts_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = pathlib.Path(tmp)
            folder.mkdir(exist_ok=True)
            neighbor = folder / "00000000-0000-0000-0000-000000000000.png"
            neighbor.write_bytes(b"\x89PNG\r\n\x1a\nneighbor")
            own = folder / f"{UUID_A}.jpeg"
            own.write_bytes(b"\xff\xd8own-jpeg")
            thumb = folder / f"{UUID_A}_thumb.png"
            thumb.write_bytes(_png())
            resolved = self.wlm.resolve_usertile(folder, UUID_A, small=False)
            self.assertEqual(resolved, own)
            self.assertEqual(self.wlm.resolve_usertile(folder, UUID_A, small=True), thumb)
            mime, full_size, thumb_size = self.wlm.profile_image_stats(folder, UUID_A)
            self.assertEqual(mime, "jpeg")
            self.assertEqual(full_size, own.stat().st_size)
            self.assertEqual(thumb_size, thumb.stat().st_size)

    def test_profile_stats_missing_thumb_is_zero_not_an_exception(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = pathlib.Path(tmp)
            (folder / f"{UUID_A}.png").write_bytes(_png())
            mime, full_size, thumb_size = self.wlm.profile_image_stats(folder, UUID_A)
            self.assertEqual(mime, "png")
            self.assertGreater(full_size, 0)
            self.assertEqual(thumb_size, 0)

    def test_serve_hosts_exact_object_and_rejects_traversal(self):
        png = _png()
        with tempfile.TemporaryDirectory() as tmp:
            store = self.wlm.ContentStore(tmp)
            saved = store.store(
                UUID_A, "emoticon", png,
                creator="bot@hermes.local", location="(hermes)", friendly="(hermes)",
                shortcut="(hermes)",
            )
            secret = pathlib.Path(tmp) / "secret.txt"
            secret.write_text("nope")
            status, ctype, body = self.wlm.serve(
                tmp, f"/storage/emoticon/{UUID_A}/{saved['sha1hex']}"
            )
            self.assertEqual(status, 200)
            self.assertEqual(ctype, "image/png")
            self.assertEqual(body, png)
            for bad in (
                f"/storage/emoticon/{UUID_A}/../../secret.txt",
                "/storage/emoticon/not-a-uuid/" + "a" * 40,
                "/storage/emoticon/" + UUID_A + "/../" + "a" * 40,
                "/storage/usertile/" + UUID_A + "/static/../../secret.txt",
                "/etc/passwd",
            ):
                code, _, payload = self.wlm.serve(tmp, bad)
                self.assertEqual(code, 404, bad)
                self.assertNotIn(b"nope", payload)

    def test_sync_skips_when_unconfigured_and_does_not_invent_an_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = self.wlm.ContentStore(tmp)
            result = self.wlm.sync_configured(
                store, uuid=UUID_A, creator="bot@hermes.local", environ={}
            )
            self.assertEqual(result["status"], "skipped")
            self.assertFalse((pathlib.Path(tmp) / "storage").exists())

    def test_sync_configured_paths_publishes_presence_and_catalog(self):
        png = _png()
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            dp = root / "face.png"
            bg = root / "scene.png"
            emo = root / "emos"
            emo.mkdir()
            dp.write_bytes(png)
            bg.write_bytes(_png(rgb=(0, 255, 0)))
            (emo / "hermes.png").write_bytes(_png(rgb=(0, 0, 255)))
            (emo / "not-an-image.txt").write_bytes(b"nope")
            store = self.wlm.ContentStore(root / "server")
            result = self.wlm.sync_configured(
                store,
                uuid=UUID_A,
                creator="bot@hermes.local",
                environ={
                    "HERMES_MSN_DP": str(dp),
                    "HERMES_MSN_BACKGROUND": str(bg),
                    "HERMES_MSN_EMOTICONS_DIR": str(emo),
                },
            )
            self.assertEqual(result["status"], "synced")
            self.assertNotIn(" ", result["msnobj_quoted"])
            self.assertIn("<msnobj ", result["scene"])
            self.assertIn('Type="5"', result["scene"])
            catalog = json.loads(pathlib.Path(result["catalog_path"]).read_text())
            self.assertEqual(catalog["emoticons"][0]["shortcut"], "(hermes)")
            self.assertEqual(catalog["emoticons"][0]["object_type"], 2)
            self.assertEqual(result["rejected"], ["not-an-image.txt"])
            hits = self.wlm.matching_emoticons("hi (hermes) and (h)", catalog["emoticons"])
            self.assertEqual([item["shortcut"] for item in hits], ["(hermes)"])
            nested = self.wlm.matching_emoticons(
                "see (hermes) now",
                [{"shortcut": "(hermes)"}, {"shortcut": "(h)"}],
            )
            self.assertEqual([item["shortcut"] for item in nested], ["(hermes)"])

    def test_oversized_and_non_image_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = self.wlm.ContentStore(tmp)
            with self.assertRaises(ValueError):
                store.store(UUID_A, "emoticon", b"\x89PNG\r\n\x1a\n" + b"x" * (64 * 1024),
                            creator="bot@hermes.local", location="(x)")
            with self.assertRaises(ValueError):
                store.store(UUID_A, "dp", b"MZ-not-an-image", creator="bot@hermes.local",
                            location="tile.tmp")
            with self.assertRaises(ValueError):
                store.store("../etc", "dp", _png(), creator="bot@hermes.local",
                            location="tile.tmp")

    def test_threaded_host_serves_usertile(self):
        png = _png()
        with tempfile.TemporaryDirectory() as tmp:
            store = self.wlm.ContentStore(tmp)
            store.store(UUID_A, "dp", png, creator="bot@hermes.local", location="tile.tmp")
            server = self.wlm.serve_forever(tmp, "127.0.0.1", 0)
            try:
                port = server.server_address[1]
                with urlopen(f"http://127.0.0.1:{port}/storage/usertile/{UUID_A}/static") as resp:
                    body = resp.read()
                    self.assertEqual(resp.status, 200)
                    self.assertEqual(body, png)
            finally:
                server.shutdown()
                server.server_close()


class PatchRestorationTests(unittest.TestCase):
    def test_patch_replaces_shared_directory_lookup_and_persists_scene(self):
        self.assertTrue(UPSTREAM.is_file(), "upstream msn-server fixture missing")
        upstream = UPSTREAM.read_text()
        self.assertIn("ext = files[0].suffix", upstream)
        ns = UPSTREAM_NS.read_text()
        with tempfile.TemporaryDirectory() as tmp:
            server = pathlib.Path(tmp)
            (server / "core").mkdir()
            (server / "front" / "msn" / "http").mkdir(parents=True)
            (server / "core" / "stats.py").write_text(
                "\t\thll = HyperLogLog(12)\n"
                "\t\thll.set_registers(bytearray(json['users_active']))\n"
                "\t\tstats['users_active'] = hll\n"
            )
            (server / "front" / "msn" / "http" / "other.py").write_text(upstream)
            (server / "front" / "msn" / "msnp_ns.py").write_text(ns)
            subprocess.run(
                ["/usr/bin/python3.13", str(PATCHER), str(server)],
                check=True,
                capture_output=True,
                text=True,
            )
            patched = (server / "front" / "msn" / "http" / "other.py").read_text()
            self.assertNotIn("files[0].suffix", patched)
            self.assertIn("/storage/emoticon/", patched)
            self.assertIn("/storage/background/", patched)
            hosting = server / "front" / "msn" / "wlm_hosting.py"
            self.assertTrue(hosting.is_file())
            self.assertEqual(hosting.read_text(), HOSTING.read_text())
            ns_patched = (server / "front" / "msn" / "msnp_ns.py").read_text()
            self.assertIn("save_scene", ns_patched)
            self.assertIn("load_scene", ns_patched)
            # The patched pure lookup must agree with the library on the neighbor bug.
            wlm = _load("wlm_content_patchcmp", LIB)
            folder = server / "tiles"
            folder.mkdir()
            (folder / "00000000-0000-0000-0000-000000000000.png").write_bytes(b"\x89PNG\r\n\x1a\nneighbor")
            (folder / f"{UUID_B}.jpeg").write_bytes(b"\xff\xd8jpeg")
            (folder / f"{UUID_B}_thumb.png").write_bytes(_png())
            ns_globals = {}
            exec(
                "from pathlib import Path\nimport re\n" + _extract(patched, "def _resolve_usertile_file"),
                ns_globals,
            )
            found = ns_globals["_resolve_usertile_file"](folder, UUID_B, False)
            self.assertEqual(found, wlm.resolve_usertile(folder, UUID_B, small=False))
            hosting_mod = _load("wlm_hosting_applied", hosting)
            hosting_mod.save_scene(UUID_A, "<msnobj/>")
            self.assertEqual(hosting_mod.load_scene(UUID_A), "<msnobj/>")
            with self.assertRaises(ValueError):
                hosting_mod.save_scene("../etc", "x")

    def test_patch_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            server = pathlib.Path(tmp)
            (server / "core").mkdir()
            (server / "front" / "msn" / "http").mkdir(parents=True)
            (server / "core" / "stats.py").write_text(
                "\t\thll = HyperLogLog(12)\n"
                "\t\t# HLL >= 3.0 removed set_registers; start the counter fresh.\n"
                "\t\tif hasattr(hll, 'set_registers'):\n"
                "\t\t\thll.set_registers(bytearray(json['users_active']))\n"
                "\t\tstats['users_active'] = hll\n"
            )
            (server / "front" / "msn" / "http" / "other.py").write_text(UPSTREAM.read_text())
            (server / "front" / "msn" / "msnp_ns.py").write_text(UPSTREAM_NS.read_text())
            for _ in range(2):
                subprocess.run(
                    ["/usr/bin/python3.13", str(PATCHER), str(server)],
                    check=True, capture_output=True, text=True,
                )
            text = (server / "front" / "msn" / "http" / "other.py").read_text()
            self.assertEqual(text.count("def _resolve_usertile_file"), 1)


class BridgePresenceTests(unittest.TestCase):
    def test_node_presence_helper_encodes_chg_uux_and_emoticon(self):
        script = r"""
const p = require(process.argv[1]);
const chg = p.chgLine('5', 'NLN', '0', process.env.OBJ);
if (chg.includes('<') || chg.includes(' ')) {
  if (!chg.startsWith('CHG 5 NLN 0 ')) throw new Error('chg shape ' + chg);
}
if (!chg.endsWith('\r\n')) throw new Error('chg ending');
if (chg.split(' ').length !== 5) throw new Error('chg fields ' + chg);
let threw = false;
try { p.chgLine('1', 'NLN', '0', '<msnobj />'); } catch (e) { threw = true; }
if (!threw) throw new Error('unencoded msnobj accepted');
const uux = p.uuxCommand('9', '{GUID}', '<msnobj Creator="a&b"/>');
if (!uux.startsWith('UUX 9 ')) throw new Error(uux);
if (uux.includes('<msnobj Creator="a&b"/>')) throw new Error('scene not escaped');
if (!uux.includes('&lt;msnobj Creator=&quot;a&amp;b&quot;/&gt;')) throw new Error(uux);
const body = p.emoticonAnnouncement('(hermes)', '<msnobj Type="2"/>');
if (body !== '(hermes)\t<msnobj Type="2"/>') throw new Error(body);
const hits = p.matchingShortcuts('see (hermes) now', [{shortcut:'(hermes)'},{shortcut:'(h)'}]);
if (hits.length !== 1 || hits[0].shortcut !== '(hermes)') throw new Error(JSON.stringify(hits));
console.log('ok');
"""
        env = os.environ.copy()
        env["OBJ"] = "abc%3c%3e"
        # Isolate from the broken PYTHONPATH; node does not need it.
        proc = subprocess.run(
            ["node", "-e", script, str(PRESENCE)],
            check=False, capture_output=True, text=True, env=env,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        self.assertIn("ok", proc.stdout)
        main = (ROOT / "msn-bridge" / "msnclient" / "main.js").read_text()
        self.assertIn("wlm_presence", main)
        self.assertIn("MSN_BOT_MSNOBJ", main)
        self.assertIn("MSN_BOT_SCENE", main)
        self.assertNotIn("CHG 5 NLN ' + MSN_NATIVE_CAPS + ':0' + endTag", main)

    def test_ensure_bot_user_calls_sync_without_default_image(self):
        text = (ROOT / "local-server" / "ensure-bot-user.py").read_text()
        self.assertIn("sync_configured", text)
        self.assertIn("HERMES_MSN_DP", text)
        self.assertNotIn("default.png", text)
        self.assertNotIn("generate_avatar", text)


def _extract(source, signature):
    start = source.index(signature)
    nxt = source.find("\ndef ", start + 1)
    nxt_async = source.find("\nasync def ", start + 1)
    ends = [n for n in (nxt, nxt_async) if n != -1]
    end = min(ends) if ends else len(source)
    return source[start:end]


if __name__ == "__main__":
    unittest.main()
