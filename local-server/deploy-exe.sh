#!/bin/bash
# Deploy a freshly built HermesXP.exe to a configured XP machine over the LAN.
# The XP may have no internet: the Hermes host serves the file over HTTP and the XP
# downloads it with the proven VBScript route (bitsadmin does not exist on
# this XP Home). C:\HermesXP.exe is a temporary transfer staging path, NOT
# a second installation; remove it once the canonical package copy verifies.
# If the exe is running on XP it is stopped first (tskill), since Windows
# cannot overwrite a running executable.
#
# Needs an explicitly configured xp_cmd.py helper and reachable XP host.
# Set XP_HOST and XP_CMD_PATH; no target IP or local account is assumed.
# Usage: ./deploy-exe.sh [exe-path]   (default: <repo>/dist/HermesXP.exe)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
EXE="${1:-$REPO_ROOT/dist/HermesXP.exe}"
XP_HOST="${XP_HOST:-${HERMESXP_HOST:-}}"
[ -n "$XP_HOST" ] || { echo "[deploy-exe] set XP_HOST to the intended paired XP IPv4 address" >&2; exit 2; }
if ! python3 "$REPO_ROOT/tools/validate_lan_ip.py" "$XP_HOST"; then
    echo "[deploy-exe] XP_HOST must be an RFC1918 private LAN IPv4 address" >&2
    exit 2
fi
export HERMESXP_HOST="$XP_HOST"
PORT="${DEPLOY_PORT:-18766}"

log() { echo "[deploy-exe] $*"; }
warn() { echo "[deploy-exe] WARNING: $*" >&2; }

[ -f "$EXE" ] || { echo "[deploy-exe] exe not found: $EXE" >&2; exit 2; }
LOCAL_SIZE="$(stat -c%s "$EXE")"
log "deploying $EXE ($LOCAL_SIZE bytes) to $XP_HOST ..."

XP_CMD_PATH="${XP_CMD_PATH:-$HOME/xp_cmd.py}"
[ -f "$XP_CMD_PATH" ] || { echo "[deploy-exe] xp_cmd.py not found at $XP_CMD_PATH (set XP_CMD_PATH)" >&2; exit 2; }
# Use an array to support user-selected helper paths containing spaces.
XP_CMD=(python3 "$XP_CMD_PATH")

# Use the registered installation location if setup has been run. New users
# default to Program Files, while older installs use C:\HermesXP. Never
# create an extra C:\HermesXP copy alongside a registered Program Files app.
REGISTERED="$("${XP_CMD[@]}" 'reg query "HKLM\Software\HermesXP" /v InstallDir' 2>/dev/null || true)"
INSTALL_DIR="$(printf '%s\n' "$REGISTERED" | sed -n -E 's/^[[:space:]]*InstallDir[[:space:]]+REG_SZ[[:space:]]+([A-Za-z]:\\.*)$/\1/p' | head -1 | tr -d '\r')"
if [ -z "$INSTALL_DIR" ]; then
    INSTALL_DIR='C:\HermesXP'
fi
case "$INSTALL_DIR" in
    *'&'*|*'|'*|*'<'*|*'>'*|*'"'*|*'%'*|*'^'*|*'!'*)
        echo "[deploy-exe] unsafe install directory returned by XP registry; refusing deployment" >&2
        exit 2;;
esac
log "installation target: $INSTALL_DIR"

# Stop a running copy first (tskill = XP Home; ignore failure if not running).
"${XP_CMD[@]}" "tskill HermesXP" >/dev/null 2>&1 || true
sleep 1

LAN_IP="${LAN_IP:-}"
[ -n "$LAN_IP" ] || LAN_IP="$(ip route get "$XP_HOST" 2>/dev/null | sed -n 's/.*src \([0-9.]*\).*/\1/p')"
[ -n "$LAN_IP" ] || LAN_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
[ -n "$LAN_IP" ] || { echo "[deploy-exe] could not detect host LAN IP; set LAN_IP" >&2; exit 2; }
if ! python3 "$REPO_ROOT/tools/validate_lan_ip.py" "$LAN_IP"; then
    echo "[deploy-exe] LAN_IP must be an RFC1918 private LAN IPv4 address" >&2
    exit 2
fi

# Temp HTTP server serving the exe's directory (killed on exit).
DIR="$(dirname "$EXE")"
python3 -m http.server "$PORT" --bind "$LAN_IP" --directory "$DIR" >/tmp/hermesxp-http.log 2>&1 &
HTTP_PID=$!
trap 'kill $HTTP_PID 2>/dev/null || true' EXIT
sleep 1

# Build the downloader on the XP (echo lines; avoid carets — cmd echo does
# not collapse ^^ to ^) and run it.
"${XP_CMD[@]}" "echo Set o = CreateObject(\"MSXML2.XMLHTTP\") > C:\\dl2.vbs" >/dev/null
"${XP_CMD[@]}" "echo o.open \"GET\", \"http://$LAN_IP:$PORT/$(basename "$EXE")\", False >> C:\\dl2.vbs" >/dev/null
"${XP_CMD[@]}" "echo o.send >> C:\\dl2.vbs" >/dev/null
"${XP_CMD[@]}" "echo Set s = CreateObject(\"ADODB.Stream\") >> C:\\dl2.vbs" >/dev/null
"${XP_CMD[@]}" "echo s.Type = 1 >> C:\\dl2.vbs" >/dev/null
"${XP_CMD[@]}" "echo s.Open >> C:\\dl2.vbs" >/dev/null
"${XP_CMD[@]}" "echo s.Write o.responseBody >> C:\\dl2.vbs" >/dev/null
"${XP_CMD[@]}" "echo s.SaveToFile \"C:\\HermesXP.exe\", 2 >> C:\\dl2.vbs" >/dev/null
"${XP_CMD[@]}" "echo s.Close >> C:\\dl2.vbs" >/dev/null
"${XP_CMD[@]}" "cscript //nologo C:\\dl2.vbs" >/dev/null

# Verify the size on the XP matches.
OUT="$("${XP_CMD[@]}" "dir C:\\HermesXP.exe" 2>/dev/null || true)"
if echo "$OUT" | tr -d ',' | grep -q "$LOCAL_SIZE"; then
    log "verified: C:\\HermesXP.exe on $XP_HOST is $LOCAL_SIZE bytes"
else
    warn "could not verify size on the XP (dir output: $(echo "$OUT" | tr '\n' ' ' | head -c 200))"
    exit 1
fi
# The registered installation (or older legacy folder) is the ONLY permanent
# executable location. Its adjacent .ini, DLL and CA files stay untouched.
"${XP_CMD[@]}" "copy /Y C:\\HermesXP.exe \"$INSTALL_DIR\\HermesXP.exe\"" >/dev/null
OUT2="$("${XP_CMD[@]}" "dir \"$INSTALL_DIR\\HermesXP.exe\"" 2>/dev/null || true)"
if echo "$OUT2" | tr -d ',' | grep -q "$LOCAL_SIZE"; then
    log "verified: $INSTALL_DIR\\HermesXP.exe on $XP_HOST is $LOCAL_SIZE bytes"
else
    warn "could not verify package-folder copy on the XP (dir output: $(echo "$OUT2" | tr '\n' ' ' | head -c 200))"
    exit 1
fi
# The top-level executable was only a download staging file. Leaving it
# behind created two versions, so users could launch an obsolete copy.
# Cleanup happens ONLY after the canonical installation has been verified.
"${XP_CMD[@]}" "del /F /Q C:\\HermesXP.exe" >/dev/null 2>&1 || warn "could not remove temporary C:\\HermesXP.exe"
"${XP_CMD[@]}" "del /F /Q C:\\dl2.vbs" >/dev/null 2>&1 || warn "could not remove temporary C:\\dl2.vbs"
log "done"
