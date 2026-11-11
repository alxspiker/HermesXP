#!/bin/bash
# Build the XP executable (HermesXP.exe) from the GitHub source, on a modern host.
# The XP has no internet and no toolchain, so the build happens here from the
# public repo checkout; deploy-exe.sh then pushes the result to the XP over
# the LAN. Called by the update service after a plugin/repo update, or
# manually after changing xp-client/.
#
# Requires the LLVM toolchain (one-time, with package manager privileges):
#   sudo apt-get install -y clang lld llvm
# If the tools are missing, this script prints that command and exits 3
# (the update service logs it and leaves the old exe in place).
#
# Usage: ./build-exe.sh [repo-root]   (default: the repo this script lives in)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="${1:-$(cd "$SCRIPT_DIR/.." && pwd)}"
CLIENT_DIR="$REPO_ROOT/xp-client"
DIST_DIR="$REPO_ROOT/dist"

for tool in clang lld-link llvm-objdump python3; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        echo "[build-exe] missing tool: $tool" >&2
        echo "[build-exe] install the toolchain once: sudo apt-get install -y clang lld llvm" >&2
        exit 3
    fi
done

log() { echo "[build-exe] $*"; }
log "building from $CLIENT_DIR ..."
(cd "$CLIENT_DIR" && ./build.sh >/tmp/hermesxp-build.log 2>&1) || { cat /tmp/hermesxp-build.log >&2; exit 1; }

mkdir -p "$DIST_DIR"
cp "$CLIENT_DIR/HermesXP.exe" "$DIST_DIR/HermesXP.exe"
cp "$CLIENT_DIR/HermesXP-Updater.exe" "$DIST_DIR/HermesXP-Updater.exe"
(cd "$DIST_DIR" && sha256sum HermesXP.exe HermesXP-Updater.exe > SHA256SUMS)
SIZE="$(stat -c%s "$DIST_DIR/HermesXP.exe")"
SHA="$(sha256sum "$DIST_DIR/HermesXP.exe" | awk '{print $1}')"
log "built dist/HermesXP.exe ($SIZE bytes, sha256 $SHA)"
