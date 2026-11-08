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
#      (bridge service). The owner password is printed ONCE — give it to the
#      person who will type it into WLM on the XP; it is never written to a file.
#      No personal details are hardcoded: the owner defaults to
#      user@hermes.local, the LAN IP is auto-detected (override with LAN_IP).
#   6. Installs + starts systemd user services for the server and the bridge.
#   7. Generates a local CA + server cert and installs the stunnel TLS
#      terminator on :443 (XP HTTPS sign-in). Needs stunnel + the
#      ip_unprivileged_port_start sysctl (see SYSTEM REQUIREMENTS below).
#   8. Writes the pre-filled Switcher INI files (with this host's LAN IP)
#      to ~/.hermes/msn-server/switcher/ for deployment to the XP.
#
# SYSTEM REQUIREMENTS (one-time, run as alxtheprogrammer with sudo):
#   sudo apt-get install -y stunnel4
#   echo 'net.ipv4.ip_unprivileged_port_start=0' | sudo tee /etc/sysctl.d/99-hermesxp.conf
#   sudo sysctl -p /etc/sysctl.d/99-hermesxp.conf
#   Configure the firewall separately; the optional helper only opens 443,
#   1863 and 1864 for a single explicit XP address.
# Without those, the installer still finishes the server + bridge, but prints
# a clear warning and skips the :443 TLS listener.
#
# Idempotent: safe to re-run. Existing clone, venv, settings, databases,
# accounts and passwords are left alone; only missing pieces are created.
# Usage: ./install.sh   (from this directory, as user `hermes`)
set -euo pipefail

PIN_COMMIT="9cddb9c"
SERVER_REPO="https://gitlab.com/valtron/msn-server"
# LAN IP: override with LAN_IP env; otherwise auto-detect the primary IPv4
# (the address WLM on the XP will connect to). No address is hardcoded.
if [ -z "${LAN_IP:-}" ]; then
    LAN_IP="$(ip route get 1.1.1.1 2>/dev/null | sed -n 's/.*src \([0-9.]*\).*/\1/p')"
    [ -z "$LAN_IP" ] && LAN_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
fi
if [ -z "$LAN_IP" ]; then echo "could not detect LAN IP; set LAN_IP env and re-run"; exit 1; fi
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
log "LAN IP: $LAN_IP"

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

# --- 5b. Switcher INI files (filled with this host's LAN IP) ---
mkdir -p "$SERVER_DIR/switcher"
for exe in msnmsgr wlcomm; do
    sed "s/__LAN_IP__/$LAN_IP/g" "$SCRIPT_DIR/$exe.exe-escargot.ini.template" > "$SERVER_DIR/switcher/$exe.exe-escargot.ini"
done
log "switcher INIs written to $SERVER_DIR/switcher/"

# --- 6. systemd user services ---
mkdir -p "$HOME/.config/systemd/user"
NODE_BIN="$(command -v node || ls -d "$HERMES_HOME"/tools/node-*/bin/node 2>/dev/null | sort -V | tail -1)"
if [ -z "$NODE_BIN" ]; then warn "no node binary found; bridge service will fail to start until node is available"; NODE_BIN="/usr/bin/node"; fi
log "using node: $NODE_BIN"

sed -e "s|__HOME__|$HOME|g" "$SCRIPT_DIR/msn-server.service" > "$HOME/.config/systemd/user/msn-server.service"
sed -e "s|__HOME__|$HOME|g" -e "s|__NODE_BIN__|$NODE_BIN|g" -e "s|__SCRIPT_DIR__|$SCRIPT_DIR|g" "$SCRIPT_DIR/hermes-msn-bridge.service" > "$HOME/.config/systemd/user/hermes-msn-bridge.service"

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
    sed -e "s|__HOME__|$HOME|g" -e "s|__LAN_IP__|$LAN_IP|g" "$SCRIPT_DIR/stunnel.conf" > "$SERVER_DIR/stunnel.conf"
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

# --- Optional UFW setup (never changes a firewall without confirmation) ---
if [ -t 0 ]; then
    python3 "$SCRIPT_DIR/setup-firewall.py" || warn "UFW setup incomplete; check firewall manually"
else
    log "Non-interactive install: firewall unchanged; run python3 $SCRIPT_DIR/setup-firewall.py to configure UFW"
fi

# --- 8. XP install package (zip) + its LAN download host ---
# The package (exe + connection config + CA + Switcher DLL + INIs + README)
# is built from the live server state, so it never contains stale addresses.
sed -e "s|__HOME__|$HOME|g" "$SCRIPT_DIR/hermes-xp-package.service" > "$HOME/.config/systemd/user/hermes-xp-package.service"
systemctl --user daemon-reload
# Stop any old host before rebuilding: it may serve a legacy archive with secrets.
# Refuse to proceed if it cannot be stopped.
systemctl --user disable --now hermes-xp-package.service || { warn "could not disable and stop the package host service"; exit 1; }
if bash "$SCRIPT_DIR/build-xp-package.sh" "$SCRIPT_DIR/.."; then
    systemctl --user enable --now hermes-xp-package.service || warn "could not start the package host service"
else
    warn "XP package build failed; package host remains stopped (re-run install.sh to retry)"
fi

log "done. Check: systemctl --user status msn-server.service hermes-msn-bridge.service msn-tls.service"
log "Next: restart the Hermes gateway so the hermes_msn platform connects, then test WLM sign-in on the XP."
