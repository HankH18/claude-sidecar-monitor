#!/usr/bin/env bash
#
# tailscale-serve.sh — bind the csm collector's HTTPS surface to your tailnet.
#
# Idempotent: safe to re-run. If `tailscale serve` is already exposing
# port 8765 on :443, this script reports that and exits 0 without changes.
#
# Usage:
#   ./scripts/tailscale-serve.sh
#
# Prerequisites:
#   - Tailscale installed and signed in (`tailscale status` works)
#   - csm collector running on 127.0.0.1:8765
#
set -euo pipefail

readonly LOCAL_PORT=8765
readonly TS_INSTALL_URL="https://tailscale.com/download"

# --- 1. Tailscale on PATH? -----------------------------------------------------
if ! command -v tailscale >/dev/null 2>&1; then
    echo "error: \`tailscale\` not found on PATH." >&2
    echo "       Install Tailscale first: ${TS_INSTALL_URL}" >&2
    exit 1
fi

# --- 2. Already configured? ---------------------------------------------------
# `tailscale serve status` prints something like:
#   https://my-mac.tailnet-name.ts.net (Tailnet only)
#   |-- / proxy http://127.0.0.1:8765
# We grep for our local upstream to detect prior configuration.
if tailscale serve status 2>/dev/null | grep -qE "127\.0\.0\.1:${LOCAL_PORT}\b"; then
    echo "tailscale serve is already routing :443 -> 127.0.0.1:${LOCAL_PORT}. Nothing to do."
    echo
    tailscale serve status || true
    exit 0
fi

# --- 3. Bind it ---------------------------------------------------------------
echo "Binding tailscale serve --bg --https=443 ${LOCAL_PORT} ..."
tailscale serve --bg --https=443 "${LOCAL_PORT}"

echo
echo "Done. Current serve config:"
tailscale serve status || true

# --- 4. Resolve and print the tailnet hostname --------------------------------
echo
hostname=""
if command -v jq >/dev/null 2>&1; then
    hostname="$(tailscale status --json 2>/dev/null | jq -r '.Self.DNSName' | sed 's/\.$//' || true)"
elif command -v python3 >/dev/null 2>&1; then
    hostname="$(tailscale status --json 2>/dev/null \
        | python3 -c 'import sys, json; d=json.load(sys.stdin); print(d.get("Self",{}).get("DNSName","").rstrip("."))' \
        2>/dev/null || true)"
fi

if [[ -n "${hostname}" ]]; then
    echo "Your dashboard is now reachable at:"
    echo "  https://${hostname}/"
    echo
    echo "On your iPhone (signed into the same tailnet), open that URL in Safari"
    echo "and tap Share -> Add to Home Screen."
else
    echo "Tailscale serve is configured. Find your Mac's tailnet hostname with:"
    echo "  tailscale status"
    echo "Then visit: https://<your-mac-name>.<tailnet>.ts.net/"
fi
