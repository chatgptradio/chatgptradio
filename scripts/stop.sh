#!/usr/bin/env bash
set -euo pipefail

if systemctl --user is-active --quiet chatgpt-radio.service 2>/dev/null; then
    systemctl --user stop chatgpt-radio
    echo "chatgpt-radio stopped."
else
    echo "chatgpt-radio is not running."
fi
