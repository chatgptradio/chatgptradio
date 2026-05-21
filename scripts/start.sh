#!/usr/bin/env bash
set -euo pipefail

if ! systemctl --user is-enabled chatgpt-radio.service &>/dev/null; then
    echo "systemd service not installed. Run scripts/install_service.sh first." >&2
    exit 1
fi
systemctl --user start chatgpt-radio
echo "chatgpt-radio started."
