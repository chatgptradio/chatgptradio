#!/usr/bin/env bash
# Installe et active le service systemd pour le bot Telegram de ChatGPT Radio.
set -euo pipefail

SERVICE_DIR="$HOME/.config/systemd/user"
SERVICE_FILE="$SERVICE_DIR/chatgpt-radio-tg.service"
REPO="$(cd "$(dirname "$0")/.." && pwd)"

mkdir -p "$SERVICE_DIR"

cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=ChatGPT Radio — Telegram Bot
After=network.target

[Service]
WorkingDirectory=$REPO
ExecStart=/home/stream/.local/bin/uv run python $REPO/telegram_bot.py
Restart=always
RestartSec=5
EnvironmentFile=$REPO/.env

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable chatgpt-radio-tg.service

echo "Service installé et activé."
echo "Démarrer avec : systemctl --user start chatgpt-radio-tg.service"
echo "Statut : systemctl --user status chatgpt-radio-tg.service"
