#!/bin/bash
# HermesXP local MSN server — one-time installer (ZBook, run as user `hermes`).
#
# What it does:
#   1. Downloads Escargot's open server code (valtron/msn-server, CC BY-NC 4.0)
#      at install time, pinned to the tested commit. The code is NOT vendored
#      in this repo (license); it lives in ~/.hermes/msn-server.
#   2. Creates a Python venv and installs its dependencies.
#   3. Writes settings_local.py pointing every redirect at the ZBook LAN IP.
#   4. Creates the SQLite databases (direct create_all — upstream
#      script/dbcreate.py fails on modern SQLAlchemy).
#   5. Creates the two local accounts (owner + bot) and writes their
#      credentials into ~/.hermes/.env (gateway) and ~/.hermes/msn-bridge.env
#      (bridge service). The owner password is printed ONCE — give it to Alx
#      to type into WLM on the XP; it is never written to a file.
#   6. Installs + starts systemd user services for the server and the bridge.
#   7. Generates a local CA + server cert and installs the stunnel TLS
#      terminator on :443 (XP HTTPS sign-in). Needs stunnel + the
#      ip_unprivileged_port_start sysctl (see SYSTEM REQUIREMENTS below).
#
# SYSTEM REQUIREMENTS (one-time, run as alxtheprogrammer with sudo):
#   sudo apt-get install -y stunnel4
#   echo 'net.ipv4.ip_unprivileged_port_start=0' | sudo tee /etc/sysctl.d/99-hermesxp.conf
#   sudo sysctl -p /etc/sysctl.d/99-hermesxp.conf
# Without those, the installer still finishes the server + bridge, but prints
# a clear warning and skips the :443 TLS listener.
#
# Idempotent: safe to re-run. Existing clone, venv, settings, databases,
# accounts and passwords are left alone; only missing pieces are created.
# Usage: ./install.sh   (from this directory, as user `hermes`)
set -euo pipefail

PIN_COMMIT="9cddb9c"
SERVER_REPO="https://gitlab.com/valtron/msn-server"
LAN_IP="192.168.1.81"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
SERVER_DIR="$HERMES_HOME/msn-server"
VENV="$SERVER_DIR/.venv"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BRIDGE_SRC="$(cd "$SCRIPT_DIR/../msn-bridge" && pwd)"
BRIDGE_DIR="$HERMES_HOME/msn-bridge"
ENV_FILE="$HERMES_HOME/.env"
BRIDGE_ENV="$HERMES_HOME/msn-bridge.env"

log() { echo "[install] $*"; }
warn() { echo "[install] WARNING: $*" >&2; }

command -v python3 >/dev/null || { echo "python3 not found"; exit 1; }
command -v git >/dev/null || { echo "git not found"; exit 1; }

# --- 1. Server code (download at install time, pinned) ---
if [ -d "$SERVER_DIR/.git" ]; then
    log "msn-server already cloned at $SERVER_DIR"
    (cd "$SERVER_DIR" && git rev-parse HEAD | grep -q "^$PIN_COMMIT" && log "pinned commit $PIN_COMMIT confirmed" || warn "clone is at a different commit than pinned $PIN_COMMIT — leaving as-is")
else
    log "cloning msn-server (pinned $PIN_COMMIT)..."
    git clone "$SERVER_REPO" "$SERVER_DIR"
    (cd "$SERVER_DIR" && git checkout "$PIN_COMMIT")
fi

# --- 1b. Deployment patches for the pinned server tree ---
log "applying HermesXP deployment patches..."
python3 "$SCRIPT_DIR/patch-server.py" "$SERVER_DIR"
if [ ! -x "$VENV/bin/python" ]; then
    log "creating venv..."
    python3 -m venv "$VENV"
fi
log "installing server dependencies (this takes a while)..."
"$VENV/bin/pip" install -q -r "$SERVER_DIR/requirements.txt"
"$VENV/bin/pip" install -q python-dateutil

# --- 3. settings ---
if [ ! -f "$SERVER_DIR/settings_local.py" ]; then
    log "writing settings_local.py..."
    sed "s/__LAN_IP__/$LAN_IP/g" "$SCRIPT_DIR/settings_local.py.template" > "$SERVER_DIR/settings_local.py"
else
    log "settings_local.py already exists, leaving it alone"
fi

# --- 4. databases (direct create_all; upstream dbcreate.py migration breaks) ---
log "creating databases..."
(cd "$SERVER_DIR" && "$VENV/bin/python" "$SCRIPT_DIR/create-dbs.py")

# --- 5. accounts + credentials ---
log "creating accounts (owner + bot)..."
(cd "$SERVER_DIR" && "$VENV/bin/python" "$SCRIPT_DIR/create-accounts.py")

# --- 6. systemd user services ---
mkdir -p "$HOME/.config/systemd/user"
NODE_BIN="$(command -v node || ls -d "$HERMES_HOME"/tools/node-*/bin/node 2>/dev/null | sort -V | tail -1)"
if [ -z "$NODE_BIN" ]; then warn "no node binary found; bridge service will fail to start until node is available"; NODE_BIN="/usr/bin/node"; fi
log "using node: $NODE_BIN"

sed -e "s|__HOME__|$HOME|g" "$SCRIPT_DIR/msn-server.service" > "$HOME/.config/systemd/user/msn-server.service"
sed -e "s|__HOME__|$HOME|g" -e "s|__NODE_BIN__|$NODE_BIN|g" "$SCRIPT_DIR/hermes-msn-bridge.service" > "$HOME/.config/systemd/user/hermes-msn-bridge.service"

# bridge files (patched msnclient + bridge.js) live under ~/.hermes/msn-bridge
mkdir -p "$BRIDGE_DIR"
cp -r "$BRIDGE_SRC/bridge.js" "$BRIDGE_SRC/package.json" "$BRIDGE_SRC/msnclient" "$BRIDGE_DIR/"
NPM_BIN="$(command -v npm || echo "$(dirname "$NODE_BIN")/npm")"
log "installing bridge dependencies with $NPM_BIN..."
# The Hermes-bundled npm invokes `node` from PATH, so put the node dir first.
(cd "$BRIDGE_DIR/msnclient" && PATH="$(dirname "$NODE_BIN"):$PATH" "$NPM_BIN" install --no-audit --no-fund 2>&1 | tail -3)

systemctl --user daemon-reload
systemctl --user enable --now msn-server.service
log "msn-server service started"

# --- 7. TLS terminator (stunnel on :443 for XP HTTPS sign-in) ---
if ! command -v stunnel >/dev/null; then
    warn "stunnel not installed — :443 TLS listener skipped."
    warn "Run as alxtheprogrammer: sudo apt-get install -y stunnel4"
    warn "Then re-run this installer to finish TLS."
else
    if [ ! -f "$SERVER_DIR/certs/server.pem" ]; then
        log "generating local CA + server cert..."
        bash "$SCRIPT_DIR/make-ca.sh" "$SERVER_DIR/certs" "$LAN_IP"
    else
        log "server cert already exists, leaving it alone"
    fi
    sed -e "s|__HOME__|$HOME|g" "$SCRIPT_DIR/stunnel.conf" > "$SERVER_DIR/stunnel.conf"
    sed -e "s|__HOME__|$HOME|g" "$SCRIPT_DIR/msn-tls.service" > "$HOME/.config/systemd/user/msn-tls.service"
    systemctl --user daemon-reload
    if [ "$(cat /proc/sys/net/ipv4/ip_unprivileged_port_start 2>/dev/null || echo 1024)" != "0" ]; then
        warn "ip_unprivileged_port_start is not 0 — user services cannot bind :443."
        warn "Run as alxtheprogrammer: echo 'net.ipv4.ip_unprivileged_port_start=0' | sudo tee /etc/sysctl.d/99-hermesxp.conf && sudo sysctl -p /etc/sysctl.d/99-hermesxp.conf"
        warn "Then: systemctl --user enable --now msn-tls.service"
    else
        systemctl --user enable --now msn-tls.service
        log "msn-tls service started on :443"
    fi
fi

systemctl --user enable --now hermes-msn-bridge.service
log "hermes-msn-bridge service started"
log "done. Check: systemctl --user status msn-server.service hermes-msn-bridge.service msn-tls.service"
log "Next: restart the Hermes gateway so the hermes_msn platform connects, then test WLM sign-in on the XP."
