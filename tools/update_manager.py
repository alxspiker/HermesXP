"""Hermes-hosted HermesXP update coordinator.

Executed by systemd after a Hermes plugin update, and periodically to retry
XP laptops that were offline. The plugin Git revision is selected by Hermes'
own reviewed plugin updater; this coordinator never git-pulls or bypasses
Hermes' plugin security scanner.

Default asset policy: accept a GitHub release only when its signed-transport
manifest matches this exact plugin commit and all SHA-256 hashes; otherwise
cross-compile the source on the MODERN Hermes host into a private cache.
No toolchain, external connection, or GitHub account is required on XP.
"""

from __future__ import annotations

import fcntl
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.hermesxp_update import deploy_fleet, validate_binary  # noqa: E402
from tools.release_assets import ASSETS, load_release  # noqa: E402


# A powered-off XP machine is a queued deployment, not a broken Hermes host.
# systemd's SuccessExitStatus=75 keeps the retry timer healthy while a real
# updater/build failure (status 1) still marks the unit failed.
EX_TEMPFAIL = 75


def run(command: list[str], *, cwd: Path | None = None, timeout: int = 120) -> str:
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(
            f"{Path(command[0]).name} returned {result.returncode}: "
            f"{result.stderr[-600:] or result.stdout[-600:]}"
        )
    return result.stdout


def source_digest(root: Path) -> str:
    files = [
        *sorted((root / "xp-client").glob("*.c")),
        *sorted((root / "xp-client").glob("*.h")),
        *sorted((root / "xp-client").glob("*.def")),
        root / "xp-client/build.sh",
        root / "xp-client/fix_import_names.py",
        root / "local-server/build-exe.sh",
    ]
    h = hashlib.sha256()
    for file in files:
        h.update(str(file.relative_to(root)).encode() + b"\0")
        h.update(hashlib.sha256(file.read_bytes()).digest())
    return h.hexdigest()


def plugin_version(root: Path) -> str:
    content = (root / "plugin.yaml").read_text()
    match = re.search(r"(?m)^version:\s*([0-9]+\.[0-9]+\.[0-9]+)\s*$", content)
    if not match:
        raise RuntimeError("No version in plugin.yaml")
    return match.group(1)


def current_revision(root: Path) -> str | None:
    try:
        sha = run(["git", "rev-parse", "HEAD"], cwd=root, timeout=5).strip()
    except (OSError, subprocess.TimeoutExpired, RuntimeError):
        return None
    return sha if re.fullmatch(r"[0-9a-f]{40}", sha) else None


def cached_images(root: Path, cache: Path) -> dict[str, bytes]:
    state_path = cache / "build-state.json"
    revision = current_revision(root)
    digest = source_digest(root)
    version = plugin_version(root)
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text())
            if (state.get("revision"), state.get("source"), state.get("version")) == (
                revision, digest, version
            ):
                data = {name: (cache / name).read_bytes() for name in ASSETS}
                if all(hashlib.sha256(data[n]).hexdigest() == state["sha256"][n] for n in ASSETS):
                    validate_binary(data["HermesXP.exe"])
                    validate_binary(data["HermesXP-Updater.exe"])
                    print("Verified cached update artifacts", flush=True)
                    return data
        except (OSError, ValueError, KeyError, RuntimeError):
            pass

    release = None
    if revision and os.environ.get("HERMESXP_ASSET_SOURCE", "auto") != "build":
        try:
            release = load_release(version, revision)
        except (ValueError, OSError) as exc:
            print(f"Release verification failed: {type(exc).__name__}; building from source", flush=True)
    if release is not None:
        data = release
        print(f"Using GitHub release v{version} for plugin revision {revision[:12]}", flush=True)
    else:
        if os.environ.get("HERMESXP_ASSET_SOURCE") == "release":
            raise RuntimeError("No release matches the installed plugin revision")
        if not all(shutil.which(tool) for tool in ("clang", "lld-link", "llvm-objdump")):
            raise RuntimeError("No matching release; install clang, lld and llvm on the Hermes host")
        with tempfile.TemporaryDirectory(prefix="hermesxp-build-") as td:
            checkout = Path(td) / "source"
            shutil.copytree(
                root, checkout,
                ignore=shutil.ignore_patterns(".git", "__pycache__", "*.obj", "*.lib", ".pytest_cache"),
            )
            run(["bash", str(checkout / "local-server/build-exe.sh"), str(checkout)],
                cwd=checkout, timeout=90)
            data = {name: (checkout / "dist" / name).read_bytes() for name in ASSETS}
        print("Compiled HermesXP on Hermes host (not on Windows XP)", flush=True)
    for name in ASSETS:
        validate_binary(data[name])
    cache.mkdir(parents=True, exist_ok=True)
    for name, content in data.items():
        staged = cache / (name + ".new")
        staged.write_bytes(content)
        os.replace(staged, cache / name)
    state = {
        "revision": revision, "source": digest, "version": version,
        "sha256": {name: hashlib.sha256(data[name]).hexdigest() for name in ASSETS},
    }
    temp = cache / "build-state.json.new"
    temp.write_text(json.dumps(state, indent=2) + "\n")
    os.replace(temp, state_path)
    return data


def run_update(root: Path, home: Path, *, deploy: bool = True) -> dict:
    if not (root / "xp-client/build.sh").is_file() or not (root / "plugin.yaml").is_file():
        raise RuntimeError(f"Not a full HermesXP plugin checkout: {root}")
    cache = home / "msn-server/update-artifacts"
    cache.mkdir(parents=True, exist_ok=True)
    with (cache / ".lock").open("w") as file:
        fcntl.flock(file, fcntl.LOCK_EX)
        data = cached_images(root, cache)
        # This only writes host-specific install packages, not source files.
        env = dict(os.environ, HERMES_HOME=str(home),
                   HERMESXP_PREBUILT_EXE=str(cache / "HermesXP.exe"),
                   HERMESXP_PREBUILT_UPDATER=str(cache / "HermesXP-Updater.exe"))
        package = home / "msn-server/xp-package/HermesXP-Setup.exe"
        if not package.is_file() or (cache / "build-state.json").stat().st_mtime > package.stat().st_mtime:
            result = subprocess.run(
                ["bash", str(root / "local-server/build-xp-package.sh"), str(root)],
                env=env, text=True, capture_output=True, timeout=90,
            )
            if result.returncode:
                print(f"Package rebuild deferred: {result.stderr[-180:] or result.stdout[-180:]}", flush=True)
            else:
                print("Updated LAN installer", flush=True)
        results = deploy_fleet(cache / "HermesXP.exe",
                               helper_path=cache / "HermesXP-Updater.exe") if deploy else {}
        return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Hermes-hosted XP update manager")
    parser.add_argument("--no-deploy", action="store_true",
                        help="Build/download and package, but do not contact XP laptops")
    args = parser.parse_args()
    root = ROOT
    home = Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes")))
    try:
        outcomes = run_update(root, home, deploy=not args.no_deploy)
    except Exception as exc:
        print(f"HermesXP update failed; existing XP software preserved: {type(exc).__name__}: {exc}",
              file=sys.stderr, flush=True)
        return 1
    return EX_TEMPFAIL if "pending" in outcomes.values() else 0


if __name__ == "__main__":
    raise SystemExit(main())
