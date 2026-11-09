#!/usr/bin/env bash
# Narrow discovery ingress to RFC1918 source ranges. The HMAC handshake
# authorizes paired devices; this port never accepts remote command text.
# Intentionally permits LAN subnet changes without editing firewall rules.
set -euo pipefail
if ! command -v ufw >/dev/null; then
  echo "[discovery] UFW unavailable; ensure UDP 18773 permits local LAN sources" >&2
  exit 0
fi
if ! sudo -n ufw status 2>/dev/null | grep -q '^Status: active'; then
  echo "[discovery] UFW inactive or no noninteractive admin authorization; left unchanged"
  exit 0
fi
for network in 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16; do
  sudo -n ufw allow in from "$network" to any port 18773 proto udp \
    comment "HermesXP authenticated LAN discovery" || exit 1
done
