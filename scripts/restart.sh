#!/usr/bin/env bash
# Clean restart of all stream components.
# Eliminates zombie FFmpeg, Chromium, Xvfb before starting fresh.
set -uo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
LOGFILE="/tmp/stream_restart.log"

log() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $*"
    echo "$msg"
    echo "$msg" >> "$LOGFILE"
}

# ── 1. Stop systemd service gracefully ──────────────────────────────────────
log "=== RESTART START ==="
if systemctl --user is-active --quiet chatgpt-radio.service 2>/dev/null; then
    log "Stopping systemd service..."
    systemctl --user stop chatgpt-radio.service 2>/dev/null || true
    # Give it up to 8s to stop cleanly
    for i in $(seq 1 8); do
        systemctl --user is-active --quiet chatgpt-radio.service 2>/dev/null || break
        sleep 1
    done
fi

# ── 2. Kill FFmpeg → RTMP (zombie killer, highest priority) ─────────────────
log "Killing FFmpeg RTMP processes..."
pids=$(pgrep -f "rtmp://" 2>/dev/null) && kill -9 $pids 2>/dev/null || true

# ── 3. Kill Chromium ─────────────────────────────────────────────────────────
log "Killing Chromium..."
pids=$(pgrep -f "chromium" 2>/dev/null) && kill -9 $pids 2>/dev/null || true

# ── 4. Kill Xvfb ─────────────────────────────────────────────────────────────
log "Killing Xvfb..."
pids=$(pgrep -x "Xvfb" 2>/dev/null) && kill -9 $pids 2>/dev/null || true

# ── 5. Kill any remaining main.py instances ───────────────────────────────────
log "Killing stale main.py instances..."
pids=$(pgrep -f "python.*main\.py" 2>/dev/null) && kill -9 $pids 2>/dev/null || true

# ── 6. Free ports ─────────────────────────────────────────────────────────────
log "Freeing ports 8765 + 8080..."
fuser -k 8765/tcp 2>/dev/null || true
fuser -k 8080/tcp 2>/dev/null || true

# ── 7. Wait for clean state ───────────────────────────────────────────────────
sleep 3

# Final sweep: anything still alive?
remaining=$(pgrep -f "python.*main\.py|rtmp://|chromium-browser" 2>/dev/null | wc -l)
if [ "$remaining" -gt 0 ]; then
    log "WARNING: $remaining processes still alive, force-killing..."
    pgrep -f "python.*main\.py|rtmp://|chromium-browser" 2>/dev/null | xargs kill -9 2>/dev/null || true
    sleep 2
fi

log "All processes stopped cleanly."

# ── 8. Start via systemd ─────────────────────────────────────────────────────
if ! systemctl --user is-enabled chatgpt-radio.service &>/dev/null; then
    log "ERROR: systemd service not installed. Run scripts/install_service.sh first."
    exit 1
fi

log "Starting chatgpt-radio service..."
systemctl --user start chatgpt-radio.service

# ── 9. Wait for startup and report status ────────────────────────────────────
log "Waiting 20s for startup..."
sleep 20

echo ""
if systemctl --user is-active --quiet chatgpt-radio.service; then
    log "✓ chatgpt-radio service: ACTIVE"
else
    log "✗ chatgpt-radio service: FAILED"
    log "  → journalctl --user -u chatgpt-radio.service -n 50 --no-pager"
    exit 1
fi

pgrep -f "python.*main\.py" > /dev/null && log "✓ main.py: running" \
    || log "✗ main.py: not found"
pgrep -f "rtmp://" > /dev/null && log "✓ FFmpeg→RTMP: running" \
    || log "⚠ FFmpeg→RTMP: not yet started (DSP may still be buffering)"
pgrep -f "chromium" > /dev/null && log "✓ Chromium: running" \
    || log "⚠ Chromium: not yet started"
nc -z localhost 8765 2>/dev/null && log "✓ WebSocket :8765: open" \
    || log "⚠ WebSocket :8765: not yet ready"

log "=== RESTART COMPLETE ==="
