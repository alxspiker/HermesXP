#!/bin/bash
# Deploy a freshly built HermesXP.exe to the XP (Ruiter) over the LAN.
# The XP has no internet: the ZBook serves the file over HTTP and the XP
# downloads it with the proven VBScript route (bitsadmin does not exist on
# this XP Home). If the exe is currently running on the XP it is stopped
# first (tskill), since Windows cannot overwrite a running executable.
#
# Needs the xp_cmd.py helper (same ZBook, user alxtheprogrammer's copy or a
# copy in $HOME) and a reachable XP. Override the XP address with XP_HOST.
# Usage: ./deploy-exe.sh [exe-path]   (default: <repo>/dist/HermesXP.exe)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
EXE="${1:-$REPO_ROOT/dist/HermesXP.exe}"
XP_HOST="${XP_HOST:-192.168.1.78}"
PORT="${DEPLOY_PORT:-18766}"

log() { echo "[deploy-exe] $*"; }
warn() { echo "[deploy-exe] WARNING: $*" >&2; }

[ -f "$EXE" ] || { echo "[deploy-exe] exe not found: $EXE" >&2; exit 2; }
LOCAL_SIZE="$(stat -c%s "$EXE")"
log "deploying $EXE ($LOCAL_SIZE bytes) to $XP_HOST ..."

XP_CMD=""
for cand in "$HOME/xp_cmd.py" /home/alxtheprogrammer/xp_cmd.py; do
    if [ -f "$cand" ]; then XP_CMD="python3 $cand"; break; fi
done
[ -n "$XP_CMD" ] || { echo "[deploy-exe] xp_cmd.py not found (looked in \$HOME and /home/alxtheprogrammer)" >&2; exit 2; }

# Stop a running copy first (tskill = XP Home; ignore failure if not running).
$XP_CMD "tskill HermesXP" >/dev/null 2>&1 || true
sleep 1

LAN_IP="$(ip route get 1.1.1.1 2>/dev/null | sed -n 's/.*src \([0-9.]*\).*/\1/p')"
[ -n "$LAN_IP" ] || LAN_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
[ -n "$LAN_IP" ] || { echo "[deploy-exe] could not detect ZBook LAN IP" >&2; exit 2; }

# Temp HTTP server serving the exe's directory (killed on exit).
DIR="$(dirname "$EXE")"
python3 -m http.server "$PORT" --bind 0.0.0.0 --directory "$DIR" >/tmp/hermesxp-http.log 2>&1 &
HTTP_PID=$!
trap 'kill $HTTP_PID 2>/dev/null || true' EXIT
sleep 1

# Build the downloader on the XP (echo lines; avoid carets — cmd echo does
# not collapse ^^ to ^) and run it.
$XP_CMD "echo Set o = CreateObject(\"MSXML2.XMLHTTP\") > C:\\dl2.vbs" >/dev/null
$XP_CMD "echo o.open \"GET\", \"http://$LAN_IP:$PORT/$(basename "$EXE")\", False >> C:\\dl2.vbs" >/dev/null
$XP_CMD "echo o.send >> C:\\dl2.vbs" >/dev/null
$XP_CMD "echo Set s = CreateObject(\"ADODB.Stream\") >> C:\\dl2.vbs" >/dev/null
$XP_CMD "echo s.Type = 1 >> C:\\dl2.vbs" >/dev/null
$XP_CMD "echo s.Open >> C:\\dl2.vbs" >/dev/null
$XP_CMD "echo s.Write o.responseBody >> C:\\dl2.vbs" >/dev/null
$XP_CMD "echo s.SaveToFile \"C:\\HermesXP.exe\", 2 >> C:\\dl2.vbs" >/dev/null
$XP_CMD "echo s.Close >> C:\\dl2.vbs" >/dev/null
$XP_CMD "cscript //nologo C:\\dl2.vbs" >/dev/null

# Verify the size on the XP matches.
OUT="$($XP_CMD "dir C:\\HermesXP.exe" 2>/dev/null || true)"
if echo "$OUT" | tr -d ',' | grep -q "$LOCAL_SIZE"; then
    log "verified: C:\\HermesXP.exe on $XP_HOST is $LOCAL_SIZE bytes"
else
    warn "could not verify size on the XP (dir output: $(echo "$OUT" | tr '\n' ' ' | head -c 200))"
    exit 1
fi
log "done"
