#!/usr/bin/env bash
# Triggered by the Hermes plugin watcher or retry timer.
# Hermes owns the Git revision and security scan; never pull an unrelated HEAD.
# Rebuild/download only on the modern Hermes host. Update every paired XP
# device via authenticated local HTTP with SHA-256 + XP rollback helper.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "${1:-$SCRIPT_DIR/..}" && pwd)"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
mkdir -p "$HERMES_HOME/logs" "$HERMES_HOME/msn-server"
LOG="$HERMES_HOME/logs/hermes-xp-update.log"
exec >>"$LOG" 2>&1
echo "=== $(date -Is) HermesXP update: source $REPO ==="
if ! [ -f "$REPO/plugin.yaml" ] || ! [ -f "$REPO/tools/update_manager.py" ]; then
  echo "[update-xp] full plugin checkout required; refusing legacy subdirectory update"
  exit 1
fi
# Keep host service versions aligned with updated Hermes plugin code, even
# while an offline XP client is pending a later binary update.
REVISION="$(git -C "$REPO" rev-parse HEAD 2>/dev/null || echo unmanaged)"
REV_FILE="$HERMES_HOME/msn-server/.xp-active-plugin-revision"
CURRENT="$(cat "$REV_FILE" 2>/dev/null || true)"
if [ "$REVISION" != "$CURRENT" ]; then
  echo "[update-xp] plugin changed ($CURRENT -> $REVISION)"
  # The live Node bridge runs from ~/.hermes/msn-bridge, not the plugin
  # checkout. Sync the bridge entrypoint BEFORE restarting its service.
  # Never copy tokens, local account settings or node_modules from GitHub.
  BRIDGE_LIVE="$HERMES_HOME/msn-bridge/bridge.js"
  if [ -d "$HERMES_HOME/msn-bridge" ] && [ -f "$REPO/msn-bridge/bridge.js" ]; then
    cp "$REPO/msn-bridge/bridge.js" "$BRIDGE_LIVE.tmp"
    chmod 644 "$BRIDGE_LIVE.tmp"
    mv -f "$BRIDGE_LIVE.tmp" "$BRIDGE_LIVE"
    # Native signaling requires both the UUN frame decoder and SIP/RTP
    # implementation. Update all atomically BEFORE the Node bridge restarts.
    cp "$REPO/msn-bridge/native_call.js" "$HERMES_HOME/msn-bridge/native_call.js.tmp"
    mv -f "$HERMES_HOME/msn-bridge/native_call.js.tmp" "$HERMES_HOME/msn-bridge/native_call.js"
    cp "$REPO/msn-bridge/msnclient/frame.js" "$HERMES_HOME/msn-bridge/msnclient/frame.js.tmp"
    mv -f "$HERMES_HOME/msn-bridge/msnclient/frame.js.tmp" "$HERMES_HOME/msn-bridge/msnclient/frame.js"
    cp "$REPO/msn-bridge/msnclient/sso.js" "$HERMES_HOME/msn-bridge/msnclient/sso.js.tmp"
    mv -f "$HERMES_HOME/msn-bridge/msnclient/sso.js.tmp" "$HERMES_HOME/msn-bridge/msnclient/sso.js"
    cp "$REPO/msn-bridge/msnclient/main.js" "$HERMES_HOME/msn-bridge/msnclient/main.js.tmp"
    mv -f "$HERMES_HOME/msn-bridge/msnclient/main.js.tmp" "$HERMES_HOME/msn-bridge/msnclient/main.js"
    echo "[update-xp] updated local MSN bridge code"
  else
    echo "[update-xp] ERROR: local bridge install missing; run local-server/install.sh"
    exit 1
  fi
  systemctl --user try-restart hermes-gateway.service || true
  systemctl --user try-restart hermes-msn-bridge.service || true
  # HermesXP voice no longer serves LAN HTTP or reimplements speech
  # inference. Only an authenticated loopback PCM connection to Talk exists.
  sed -e "s|__HOME__|$HOME|g" \
      -e "s|__HERMES_BIN__|$HOME/.local/bin/hermes|g" \
      "$REPO/local-server/hermes-xp-voice.service" \
      > "$HOME/.config/systemd/user/hermes-xp-voice.service"
  systemctl --user daemon-reload
  systemctl --user enable --now hermes-xp-voice.service || echo "[update-xp] Talk bridge needs attention"
  systemctl --user try-restart hermes-xp-voice.service || true
  printf '%s\n' "$REVISION" > "$REV_FILE.tmp"
  mv -f "$REV_FILE.tmp" "$REV_FILE"
fi
if python3 "$REPO/tools/update_manager.py"; then
  echo "[update-xp] all reachable paired XP clients current"
else
  echo "[update-xp] failed/offline devices stay pending; timer will retry"
  exit 1
fi
echo "=== $(date -Is) HermesXP update done ==="
