#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
UID_NUM="$(id -u)"

# Watchdog every 2 minutes (needs XDG_RUNTIME_DIR + DBUS for systemctl --user from cron)
WATCHDOG="*/2 * * * * XDG_RUNTIME_DIR=/run/user/${UID_NUM} DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/${UID_NUM}/bus ${REPO}/scripts/check_stream.sh"
# Rotation daily at 3:00 AM
ROTATE="0 3 * * * ${REPO}/scripts/rotate_clips.sh"

# Idempotent: remove old entries, add new ones
( crontab -l 2>/dev/null | grep -v -E "check_stream|rotate_clips" || true; echo "$WATCHDOG"; echo "$ROTATE" ) | crontab -

echo "Crons installed:"
crontab -l | grep -E "check_stream|rotate_clips"
