"""Plugin source provenance, build cache and release trust invariants."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import release_assets
from tools import update_manager

ROOT = Path(__file__).resolve().parents[1]


class UpdateManagerTests(unittest.TestCase):
    def test_root_manifest_and_legacy_subdirectory_match(self):
        self.assertEqual((ROOT / "plugin.yaml").read_bytes(),
                         (ROOT / "hermes-plugin/hermes-msn/plugin.yaml").read_bytes())
        self.assertEqual((ROOT / "adapter.py").read_bytes(),
                         (ROOT / "hermes-plugin/hermes-msn/adapter.py").read_bytes())
        self.assertEqual((ROOT / "__init__.py").read_bytes(),
                         (ROOT / "hermes-plugin/hermes-msn/__init__.py").read_bytes())
        self.assertEqual(update_manager.plugin_version(ROOT), "0.6.2")
        self.assertEqual(len(update_manager.source_digest(ROOT)), 64)

    def test_release_manifest_contains_commit_and_digests(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            for asset in release_assets.ASSETS:
                (folder / asset).write_bytes((ROOT / "dist" / asset).read_bytes())
            commit = "a" * 40
            manifest = release_assets.write_release_manifest(folder, "0.3.2", commit)
            data = json.loads(manifest.read_text())
            self.assertEqual(data["version"], "0.3.2")
            self.assertEqual(data["commit"], commit)
            self.assertEqual(set(data["sha256"]), set(release_assets.ASSETS))

    def test_reject_mismatched_revision_without_trusting_release(self):
        commit = "b" * 40
        assets = [
            {"name": "RELEASE.json", "browser_download_url": "https://github.com/release/manifest"},
            *[
                {"name": name, "browser_download_url": f"https://github.com/release/{name}"}
                for name in release_assets.ASSETS
            ],
        ]

        def get(url):
            if url.endswith("/manifest"):
                return json.dumps({"commit": "c" * 40, "version": "0.3.2"}).encode()
            if url.endswith("v0.3.2"):
                return json.dumps({"assets": assets}).encode()
            raise AssertionError("Mismatched release should never download executables")

        with patch.object(release_assets, "_get", side_effect=get):
            self.assertIsNone(release_assets.load_release("0.3.2", commit))

    def test_source_build_is_independent_of_git_checkout(self):
        with tempfile.TemporaryDirectory() as td:
            cache = Path(td) / "cache"
            with patch.object(release_assets, "load_release", return_value=None):
                # Explicitly avoid network probes; it must be a local compiler job.
                with patch.dict("os.environ", {"HERMESXP_ASSET_SOURCE": "build"}):
                    data = update_manager.cached_images(ROOT, cache)
                    self.assertEqual(set(data), set(release_assets.ASSETS))
                    self.assertTrue((cache / "build-state.json").exists())
                    self.assertEqual(update_manager.cached_images(ROOT, cache), data)


if __name__ == "__main__":
    unittest.main()
