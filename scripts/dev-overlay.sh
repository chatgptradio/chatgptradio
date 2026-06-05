#!/usr/bin/env bash
# Dev overlay server — port 8081
#
# Live stream stays on :8080. This runs a second HTTP server on :8081 serving
# the same overlays/ directory so you can edit and preview without touching the live.
#
# Setup (VS Code):
#   1. Run this script on the VPS
#   2. In VS Code Remote: forward port 8081 + 8765 to localhost
#   3. Open http://localhost:8081/visualizer.html in your local browser
#      → real GlobalState data via ws://localhost:8765 (forwarded too)
#
# Usage:
#   bash scripts/dev-overlay.sh [port]        # default: 8081

set -euo pipefail

PORT="${1:-${DEV_OVERLAY_PORT:-8081}}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
OVERLAYS="$REPO/overlays"

echo ""
echo "  ┌─────────────────────────────────────────────────────┐"
echo "  │  ChatGPT Radio — Dev Overlay Server                 │"
echo "  ├─────────────────────────────────────────────────────┤"
echo "  │  HTTP  : http://localhost:$PORT                       │"
echo "  │  WS    : ws://localhost:8765  (live stream data)     │"
echo "  │  Dir   : $OVERLAYS"
echo "  ├─────────────────────────────────────────────────────┤"
echo "  │  VS Code: forward ports 8081 + 8765 to localhost     │"
echo "  │  Then open: http://localhost:$PORT/visualizer.html    │"
echo "  └─────────────────────────────────────────────────────┘"
echo ""
echo "  Live stream (:8080) is NOT affected."
echo "  Ctrl+C to stop."
echo ""

fuser -k "${PORT}/tcp" 2>/dev/null || true

python3 -m http.server "$PORT" --directory "$OVERLAYS" --bind 127.0.0.1
