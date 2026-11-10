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
  # A plugin upgrade must update its *installed* systemd units too. Merely
  # changing the source template leaves the old service rules in place.
  UNITS="$HOME/.config/systemd/user"
  mkdir -p "$UNITS"
  sed "s|__REPO_ROOT__|$REPO|g" "$REPO/local-server/hermes-xp-update.service" \
    > "$UNITS/hermes-xp-update.service.tmp"
  mv -f "$UNITS/hermes-xp-update.service.tmp" "$UNITS/hermes-xp-update.service"
  cp "$REPO/local-server/hermes-xp-update.path" "$UNITS/hermes-xp-update.path.tmp"
  mv -f "$UNITS/hermes-xp-update.path.tmp" "$UNITS/hermes-xp-update.path"
  cp "$REPO/local-server/hermes-xp-update.timer" "$UNITS/hermes-xp-update.timer.tmp"
  mv -f "$UNITS/hermes-xp-update.timer.tmp" "$UNITS/hermes-xp-update.timer"
  systemctl --user daemon-reload
  systemctl --user enable --now hermes-xp-update.path hermes-xp-update.timer
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
    cp "$REPO/msn-bridge/lan_address.js" "$HERMES_HOME/msn-bridge/lan_address.js.tmp"
    mv -f "$HERMES_HOME/msn-bridge/lan_address.js.tmp" "$HERMES_HOME/msn-bridge/lan_address.js"
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
  # Authenticated LAN address discovery is a normal HermesXP service,
  # not an RUITER-specific workaround. Runs independently of SSH and the
  # MSN bot. A network change updates the paired registry and RTP address.
  sed -e "s|__REPO_ROOT__|$REPO|g" \
    "$REPO/local-server/hermes-xp-discovery.service" \
    > "$HOME/.config/systemd/user/hermes-xp-discovery.service"
  systemctl --user daemon-reload
  systemctl --user enable --now hermes-xp-discovery.service || \
    echo "[update-xp] LAN discovery service needs attention"
  systemctl --user try-restart hermes-xp-discovery.service || true
  bash "$REPO/local-server/enable-lan-discovery-firewall.sh" ||
    echo "[update-xp] discovery ingress needs LAN firewall authorization"
  printf '%s\n' "$REVISION" > "$REV_FILE.tmp"
  mv -f "$REV_FILE.tmp" "$REV_FILE"
fi
if python3 "$REPO/tools/update_manager.py"; then
  echo "[update-xp] all reachable paired XP clients current"
else
  status=$?
  if [ "$status" -eq 75 ]; then
    echo "[update-xp] offline devices queued; timer will retry when reachable"
  else
    echo "[update-xp] host-side updater failed (exit $status); see error above"
  fi
  exit "$status"
fi
echo "=== $(date -Is) HermesXP update done ==="
