#!/bin/bash
# HermesXP update service — runs when the hermes-msn plugin is updated
# (systemd path watcher on the installed plugin dir), or manually.
#
# Flow: pull the public repo -> sync the plugin files -> rebuild the XP
# executable from source if the source changed -> deploy it to the XP over
# the LAN if the build changed -> restart the gateway/bridge if the plugin
# changed. The XP needs no internet at any point: the ZBook does the
# downloading and building, the XP only receives the finished exe.
#
# Idempotent and safe to run any time; nothing is rebuilt or restarted when
# nothing changed. State lives in ~/.hermes/msn-server/.xp-update-state.
# Log: ~/.hermes/logs/hermes-xp-update.log
#
# Usage: ./update-xp.sh [repo-checkout]   (default: ~/HermesXP)
set -u
REPO="${1:-$HOME/HermesXP}"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
PLUGIN_DIR="$HERMES_HOME/plugins/hermes-msn"
STATE_DIR="$HERMES_HOME/msn-server"
STATE_FILE="$STATE_DIR/.xp-update-state"
LOG="$HERMES_HOME/logs/hermes-xp-update.log"
mkdir -p "$HERMES_HOME/logs" "$STATE_DIR"
exec >>"$LOG" 2>&1
echo "=== $(date '+%F %T') update-xp start (repo $REPO) ==="

hash_dir() { (cd "$1" && find . -type f -not -path '*/__pycache__/*' -not -path '*/.git/*' -print0 | sort -z | xargs -0 sha256sum 2>/dev/null | sha256sum | awk '{print $1}'); }
state_get() { grep "^$1=" "$STATE_FILE" 2>/dev/null | cut -d= -f2-; }
state_set() { tmp="$STATE_FILE.tmp"; grep -v "^$1=" "$STATE_FILE" 2>/dev/null > "$tmp" || true; echo "$1=$2" >> "$tmp"; mv "$tmp" "$STATE_FILE"; }

# 1. Pull the public repo (no auth needed).
if [ -d "$REPO/.git" ]; then
    (cd "$REPO" && git pull --ff-only origin main 2>&1 | tail -2) || echo "[update-xp] git pull failed; continuing with the current checkout"
else
    echo "[update-xp] no checkout at $REPO; nothing to pull"
fi

# 2. Sync plugin files into the installed plugin dir.
if [ -d "$REPO/hermes-plugin/hermes-msn" ]; then
    mkdir -p "$PLUGIN_DIR"
    cp -r "$REPO/hermes-plugin/hermes-msn/"* "$PLUGIN_DIR/" 2>/dev/null || true
fi

# 3. Rebuild the exe when the client source changed.
SRC_HASH="$(hash_dir "$REPO/xp-client" 2>/dev/null || echo none)"
if [ "$SRC_HASH" != "$(state_get src_hash)" ]; then
    if bash "$REPO/local-server/build-exe.sh" "$REPO"; then
        state_set src_hash "$SRC_HASH"
    else
        echo "[update-xp] build failed (see above); leaving the old exe in place"
    fi
else
    echo "[update-xp] client source unchanged; skipping build"
fi

# 4. Deploy the exe when the build changed.
if [ -f "$REPO/dist/HermesXP.exe" ]; then
    EXE_SHA="$(sha256sum "$REPO/dist/HermesXP.exe" | awk '{print $1}')"
    if [ "$EXE_SHA" != "$(state_get exe_sha)" ]; then
        if bash "$REPO/local-server/deploy-exe.sh" "$REPO/dist/HermesXP.exe"; then
            state_set exe_sha "$EXE_SHA"
        else
            echo "[update-xp] deploy failed (see above); will retry on the next run"
        fi
    else
        echo "[update-xp] exe unchanged; skipping deploy"
    fi
fi

# 4b. Rebuild the XP install package so the zip matches the current exe.
bash "$REPO/local-server/build-xp-package.sh" "$REPO" 2>&1 | tail -2 || echo "[update-xp] package build failed (non-fatal)"

# 5. Restart the gateway + bridge when the plugin changed.
PLUGIN_HASH="$(hash_dir "$PLUGIN_DIR" 2>/dev/null || echo none)"
if [ "$PLUGIN_HASH" != "$(state_get plugin_hash)" ]; then
    state_set plugin_hash "$PLUGIN_HASH"
    systemctl --user restart hermes-gateway.service 2>&1 | tail -1 || true
    systemctl --user restart hermes-msn-bridge.service 2>&1 | tail -1 || true
    echo "[update-xp] plugin changed; restarted gateway + bridge"
else
    echo "[update-xp] plugin unchanged; no restart"
fi

echo "=== $(date '+%F %T') update-xp done ==="
