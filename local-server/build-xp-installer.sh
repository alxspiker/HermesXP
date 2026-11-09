#!/usr/bin/env bash
# Create an XP-native Setup.exe from the package staging folder.
# The companion, network config, local CA and MSN switcher are bundled.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="${1:-$(cd "$SCRIPT_DIR/.." && pwd)}"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
STAGE="$HERMES_HOME/msn-server/xp-package/files"
OUT="$HERMES_HOME/msn-server/xp-package/HermesXP-Setup.exe"

command -v makensis >/dev/null 2>&1 || {
  echo "[xp-installer] NSIS compiler missing (install the free nsis package)" >&2
  exit 3
}
for name in HermesXP.exe HermesXP-Updater.exe hermesxp.ini ca.pem escargot.dll \
            msnmsgr.exe-escargot.ini wlcomm.exe-escargot.ini README.txt; do
  test -s "$STAGE/$name" || {
    echo "[xp-installer] Required package file missing: $name" >&2
    exit 2
  }
done

# The app install directory is set by NSIS; this output is a standard
# Windows setup executable rather than a manually extracted ZIP.
makensis -V2 -DINPUT_DIR="$STAGE" -DOUTPUT_FILE="$OUT" \
  "$REPO_ROOT/xp-client/HermesXP-Setup.nsi"
test -s "$OUT"
echo "[xp-installer] ready: $OUT ($(stat -c %s "$OUT") bytes)"
