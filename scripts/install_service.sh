#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
SERVICE_DIR="$HOME/.config/systemd/user"
mkdir -p "$SERVICE_DIR"

cat > "$SERVICE_DIR/chatgpt-radio.service" << UNIT
[Unit]
Description=ChatGPT Radio Stream
After=network-online.target

[Service]
Type=simple
WorkingDirectory=$REPO
# Kill orphan processes from any previous run before starting
ExecStartPre=-/bin/bash -c 'pkill -9 -f "rtmp://" || true; pkill -9 -f "chromium" || true; pkill -9 -x Xvfb || true; fuser -k 8765/tcp 2>/dev/null || true; fuser -k 8080/tcp 2>/dev/null || true; sleep 1'
ExecStart=/home/stream/.local/bin/uv run python main.py
Restart=always
RestartSec=10
# Kill entire cgroup (includes FFmpeg children) on service stop
KillMode=control-group
KillSignal=SIGTERM
TimeoutStopSec=15
StandardOutput=journal
StandardError=journal
Environment=HOME=/home/stream

[Install]
WantedBy=default.target
UNIT

systemctl --user daemon-reload
systemctl --user enable chatgpt-radio.service
echo "Service installed and enabled. Run: systemctl --user start chatgpt-radio"
