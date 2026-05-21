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
ExecStartPre=-/bin/bash -c 'pkill -x Xvfb || true; pkill -f chromium-browser || true; sleep 1'
ExecStart=/home/stream/.local/bin/uv run python main.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
Environment=HOME=/home/stream

[Install]
WantedBy=default.target
UNIT

systemctl --user daemon-reload
systemctl --user enable chatgpt-radio.service
echo "Service installed and enabled. Run: systemctl --user start chatgpt-radio"
