#!/bin/bash
# Build a CA bundle for Python's OpenSSL: system roots plus any TLS-inspection
# roots trusted in the macOS keychain (e.g. Cloudflare Gateway CA, Zscaler).
# Needed because Python does not read the keychain; curl does.
set -e
cd "$(dirname "$0")"
mkdir -p certs

BASE="/usr/local/etc/ca-certificates/cert.pem"
[ -f "$BASE" ] || BASE="/etc/ssl/cert.pem"
cp "$BASE" certs/ca-bundle.pem

ADDED=0
for name in "Gateway CA" "Zscaler" "Netskope"; do
  if security find-certificate -a -c "$name" -p >> certs/ca-bundle.pem 2>/dev/null; then
    ADDED=$((ADDED + 1))
  fi
done

echo "wrote certs/ca-bundle.pem (base: $BASE, extra roots matched: $ADDED)"
