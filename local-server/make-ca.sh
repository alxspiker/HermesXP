#!/bin/bash
# Generate a local CA + server cert for the HermesXP MSN TLS terminator.
# The CA cert (ca.pem) must be installed into the XP Trusted Root store
# (double-click it on the XP, or certmgr). The server cert covers the ZBook
# LAN IP (IP SAN) so WLM can validate https://192.168.1.81/login.
# Usage: ./make-ca.sh <certs-dir> <lan-ip>   (idempotent: skips if present)
set -euo pipefail
CERTS_DIR="${1:?certs dir}"
LAN_IP="${2:?lan ip}"
mkdir -p "$CERTS_DIR"
cd "$CERTS_DIR"

if [ -f server.pem ]; then
    echo "server.pem already exists, leaving it alone"
    exit 0
fi

# Local CA (10 years)
openssl genrsa -out ca-key.pem 2048 2>/dev/null
openssl req -x509 -new -nodes -key ca-key.pem -sha256 -days 3650 \
    -subj "/CN=HermesXP Local MSN CA" -out ca.pem 2>/dev/null

# Server cert: IP SAN = ZBook LAN IP, DNS SAN = msn.local
openssl genrsa -out server-key.pem 2048 2>/dev/null
openssl req -new -key server-key.pem -subj "/CN=$LAN_IP" -out server.csr 2>/dev/null
printf "subjectAltName=IP:%s,DNS:msn.local\n" "$LAN_IP" > server.ext
openssl x509 -req -in server.csr -CA ca.pem -CAkey ca-key.pem -CAcreateserial \
    -sha256 -days 730 -extfile server.ext -out server.pem 2>/dev/null
chmod 600 ca-key.pem server-key.pem
rm -f server.csr server.ext
echo "CA + server cert written to $CERTS_DIR (ca.pem is the one to install on the XP)"
