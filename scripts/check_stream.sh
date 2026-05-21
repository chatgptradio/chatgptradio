#!/usr/bin/env bash
# Watchdog: restart chatgpt-radio service if not active.
if ! systemctl --user is-active --quiet chatgpt-radio.service 2>/dev/null; then
    logger -t chatgpt-radio-watchdog "Service not active -- restarting"
    systemctl --user restart chatgpt-radio.service
fi
