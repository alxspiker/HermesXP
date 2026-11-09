#!/usr/bin/env bash
# Build and publish generic HermesXP release assets on the modern Hermes host.
# No GitHub Actions billing, XP internet access, or private client settings.
# Default is a GitHub DRAFT, pending live Windows XP rollback verification.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
MODE="${1:---draft}"
case "$MODE" in
  --draft|--dry-run|--publish) ;;
  *) echo "Usage: $0 [--dry-run|--draft|--publish]" >&2; exit 2 ;;
esac
for cmd in git gh python3 clang lld-link llvm-objdump; do
  command -v "$cmd" >/dev/null || { echo "Missing host command: $cmd" >&2; exit 2; }
done
case "$(git remote get-url origin)" in
  https://github.com/alxspiker/HermesXP|https://github.com/alxspiker/HermesXP.git|git@github.com:alxspiker/HermesXP.git) ;;
  *) echo "Unexpected Git origin; refusing release" >&2; exit 2 ;;
esac
test -z "$(git status --porcelain)" || { echo "Commit changes before release" >&2; exit 2; }
git fetch origin main --quiet
COMMIT="$(git rev-parse HEAD)"
test "$COMMIT" = "$(git rev-parse origin/main)" || { echo "Not at origin/main HEAD" >&2; exit 2; }
VERSION="$(python3 - <<'PY'
import re
from pathlib import Path
m=re.search(r'(?m)^version:\s*([0-9]+\.[0-9]+\.[0-9]+)\s*$', Path('plugin.yaml').read_text())
if not m:raise SystemExit('Missing semantic plugin version')
print(m.group(1))
PY
)"
TAG="v$VERSION"
echo "[xp-release] validating $TAG at ${COMMIT:0:12}"
bash local-server/build-exe.sh "$ROOT"
python3 -m unittest discover -s tests -p 'test_*.py' -q
test -z "$(git status --porcelain)" || {
  echo "Build changed tracked files; review and commit the new binaries first." >&2
  exit 2
}
python3 - "$VERSION" "$COMMIT" <<'PY'
import sys
from pathlib import Path
from tools.hermesxp_update import validate_binary
from tools.release_assets import write_release_manifest
root=Path('dist')
for name in ('HermesXP.exe','HermesXP-Updater.exe'):
    validate_binary((root/name).read_bytes())
print('Release manifest:',write_release_manifest(root,sys.argv[1],sys.argv[2]))
PY
if [ "$MODE" = "--dry-run" ]; then
  echo "[xp-release] build/manifest validated; no GitHub changes."
  exit 0
fi
if ! git rev-parse --verify "refs/tags/$TAG" >/dev/null 2>&1; then
  git tag -a "$TAG" -m "HermesXP $VERSION — host-managed XP update"
fi
test "$(git rev-parse "$TAG^{}")" = "$COMMIT" || {
  echo "Tag already points at another commit" >&2; exit 2;
}
git push origin "refs/tags/$TAG"
if ! gh release view "$TAG" -R alxspiker/HermesXP >/dev/null 2>&1; then
  gh release create "$TAG" \
    dist/HermesXP.exe dist/HermesXP-Updater.exe \
    dist/SHA256SUMS dist/RELEASE.json \
    --verify-tag --draft --title "HermesXP $TAG" \
    --notes "Generic Windows XP SP3 x86 binaries, no host credentials or machine-specific certificates. Use the authenticated LAN updater on Hermes."
  echo "[xp-release] uploaded DRAFT release; not public yet."
fi
if [ "$MODE" = "--publish" ]; then
  gh release edit "$TAG" -R alxspiker/HermesXP --draft=false
  echo "[xp-release] published $TAG"
fi
