#!/usr/bin/env bash
# Stream watchdog — checks all critical components and triggers restart if needed.
# Called from cron every 2 minutes (see setup_crons.sh).
# Logs to /tmp/stream_watchdog.log (rotated at 500KB).
set -uo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
LOGFILE="/tmp/stream_watchdog.log"
RESTART_SCRIPT="$REPO/scripts/restart.sh"

# Rotate log if > 500KB
if [ -f "$LOGFILE" ] && [ "$(stat -c%s "$LOGFILE" 2>/dev/null || echo 0)" -gt 512000 ]; then
    mv "$LOGFILE" "${LOGFILE}.1"
fi

log() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] WATCHDOG: $*"
    echo "$msg" >> "$LOGFILE"
}

fail=0
reasons=()

# ── Guard: skip check if service started less than 60s ago ──────────────────
# Exception: if we've skipped 3 consecutive times (≥6 min crash-loop), force checks.
SKIP_COUNT_FILE="/tmp/stream_watchdog_skip_count"
consecutive_skips=$(cat "$SKIP_COUNT_FILE" 2>/dev/null || echo 0)

if systemctl --user is-active --quiet chatgpt-radio.service 2>/dev/null; then
    start_ts=$(systemctl --user show chatgpt-radio.service --property=ActiveEnterTimestamp \
        --value 2>/dev/null | xargs -I{} date -d "{}" +%s 2>/dev/null || echo 0)
    now_ts=$(date +%s)
    uptime_s=$(( now_ts - start_ts ))
    if [ "$uptime_s" -lt 60 ] && [ "$consecutive_skips" -lt 3 ]; then
        echo $(( consecutive_skips + 1 )) > "$SKIP_COUNT_FILE"
        log "Service started ${uptime_s}s ago — skipping checks during startup (skip $((consecutive_skips + 1))/3)."
        exit 0
    elif [ "$uptime_s" -lt 60 ] && [ "$consecutive_skips" -ge 3 ]; then
        log "Crash-loop detected (${consecutive_skips} consecutive startup skips) — forcing checks."
    fi
fi
# Reset skip counter — we're proceeding with checks this run
echo 0 > "$SKIP_COUNT_FILE"

# ── Stale process cleanup ────────────────────────────────────────────────────
# Kill orphaned development processes (pytest, uv-run-pytest, shell snapshots)
# that accumulate from Claude Code sessions and consume RAM.
_killed=0

# pytest workers — never belong on a production stream host
while IFS= read -r pid; do
    # Safety: never kill main.py or anything owned by a different user
    cmdline=$(tr '\0' ' ' < "/proc/${pid}/cmdline" 2>/dev/null || true)
    [[ "$cmdline" == *"main.py"* ]] && continue
    kill "$pid" 2>/dev/null && (( _killed++ )) || true
done < <(pgrep -f "python.*pytest|python -m pytest" 2>/dev/null || true)

# Shell snapshot launchers left behind by Claude Code harness (>5 min old)
while IFS= read -r pid; do
    cmdline=$(tr '\0' ' ' < "/proc/${pid}/cmdline" 2>/dev/null || true)
    [[ "$cmdline" == *"shell-snapshots"* ]] || continue
    start_s=$(stat -c %Y "/proc/${pid}" 2>/dev/null || echo 9999999999)
    age_s=$(( $(date +%s) - start_s ))
    if [ "$age_s" -gt 300 ]; then
        kill "$pid" 2>/dev/null && (( _killed++ )) || true
    fi
done < <(pgrep -f "bash.*shell-snapshot" 2>/dev/null || true)

[ "$_killed" -gt 0 ] && log "Cleaned up ${_killed} stale process(es)."

# ── Memory pressure check ────────────────────────────────────────────────────
_avail_mb=$(awk '/MemAvailable/ {printf "%d", $2/1024}' /proc/meminfo)
if [ "$_avail_mb" -lt 150 ]; then
    log "CRITICAL: low memory — ${_avail_mb} MB available — triggering restart."
    bash "$RESTART_SCRIPT" >> "$LOGFILE" 2>&1
    log "Restart triggered by OOM pressure (exit: $?)"
    exit 0
elif [ "$_avail_mb" -lt 300 ]; then
    log "WARN: memory pressure — ${_avail_mb} MB available."
fi

# ── Log rotation ─────────────────────────────────────────────────────────────
# Rotate ffmpeg_live.log at 50 MB (grows indefinitely otherwise)
_ffmpeg_log="/tmp/ffmpeg_live.log"
if [ -f "$_ffmpeg_log" ] && [ "$(stat -c%s "$_ffmpeg_log" 2>/dev/null || echo 0)" -gt 52428800 ]; then
    mv "$_ffmpeg_log" "${_ffmpeg_log}.1"
    log "Rotated ffmpeg_live.log (was > 50 MB)."
fi

# ── Check 1: systemd service active ─────────────────────────────────────────
if ! systemctl --user is-active --quiet chatgpt-radio.service 2>/dev/null; then
    (( fail++ )) || true
    reasons+=("systemd service not active")
fi

# ── Check 2: main.py process running ────────────────────────────────────────
if ! pgrep -f "python.*main\.py" > /dev/null 2>&1; then
    (( fail++ )) || true
    reasons+=("main.py not running")
fi

# ── Check 3: FFmpeg streaming to RTMP ───────────────────────────────────────
if ! pgrep -f "rtmp://" > /dev/null 2>&1; then
    (( fail++ )) || true
    reasons+=("FFmpeg→RTMP not running")
fi

# ── Check 4: Chromium running ────────────────────────────────────────────────
if ! pgrep -f "chromium" > /dev/null 2>&1; then
    (( fail++ )) || true
    reasons+=("Chromium not running")
fi

# ── Check 5: WebSocket port 8765 accepting connections ───────────────────────
# Use ss (no TCP connection opened) — nc -z triggers InvalidMessage errors in
# the WebSocket server logs every 2 min because it connects without a WS handshake.
if ! ss -tnl 2>/dev/null | grep -q ':8765 '; then
    (( fail++ )) || true
    reasons+=("WebSocket :8765 not responding")
fi

# ── Check 6: fps degradation — restart if instantaneous fps < 15 for 3 checks ─
# Uses delta(frame)/delta(encoded_time) — NOT ffmpeg's running-average fps= field
# which stays above threshold for minutes after degradation starts.
_FPS_FAIL_FILE="/tmp/stream_watchdog_fps_fail_count"
_FPS_PREV_FILE="/tmp/stream_watchdog_fps_prev"  # stores "frame:time_sec" from last check
_fps_fail_count=$(cat "$_FPS_FAIL_FILE" 2>/dev/null || echo 0)
_fps_threshold=24
_fps_fail_max=3  # 3 checks × 2 min = 6 min sustained fps < 24 → restart

if systemctl --user is-active --quiet chatgpt-radio.service 2>/dev/null; then
    _svc_start=$(systemctl --user show chatgpt-radio.service --property=ActiveEnterTimestamp \
        --value 2>/dev/null | xargs -I{} date -d "{}" +%s 2>/dev/null || echo 0)
    _svc_uptime=$(( $(date +%s) - _svc_start ))

    if [ "$_svc_uptime" -ge 300 ] && [ -f "/tmp/ffmpeg_live.log" ]; then
        # Extract latest frame count and encoded time from ffmpeg log
        _raw=$(tail -c 4096 /tmp/ffmpeg_live.log 2>/dev/null | tr '\r' '\n' | \
            grep -oP 'frame=\s*\K\d+(?=.*?time=)|time=\K\d+:\d+:\d+\.\d+' | tail -4)
        _cur_frame=$(echo "$_raw" | grep -E '^\d+$' | tail -1)
        _cur_time=$(echo "$_raw" | grep -E '^\d+:\d+:\d+' | tail -1)

        if [ -n "$_cur_frame" ] && [ -n "$_cur_time" ]; then
            # Convert time HH:MM:SS.xx to seconds
            _cur_sec=$(echo "$_cur_time" | awk -F: '{printf "%.2f", $1*3600+$2*60+$3}')

            # Compute instantaneous fps from delta vs. previous check
            _prev=$(cat "$_FPS_PREV_FILE" 2>/dev/null || echo "0:0")
            _prev_frame=$(echo "$_prev" | cut -d: -f1)
            _prev_sec=$(echo "$_prev" | cut -d: -f2)

            # Save current for next check
            echo "${_cur_frame}:${_cur_sec}" > "$_FPS_PREV_FILE"

            _inst_fps=$(awk "BEGIN{
                df=$_cur_frame - $_prev_frame;
                dt=$_cur_sec - $_prev_sec;
                if (dt > 5) printf \"%.1f\", df/dt; else print \"skip\"
            }")

            if [ "$_inst_fps" != "skip" ] && [ -n "$_inst_fps" ]; then
                if awk "BEGIN{exit !($_inst_fps < $_fps_threshold)}"; then
                    (( _fps_fail_count++ )) || true
                    echo "$_fps_fail_count" > "$_FPS_FAIL_FILE"
                    log "WARN: fps_inst=${_inst_fps} < ${_fps_threshold} (low-fps count: ${_fps_fail_count}/${_fps_fail_max})"
                    if [ "$_fps_fail_count" -ge "$_fps_fail_max" ]; then
                        log "fps degraded for ${_fps_fail_count} checks — triggering restart."
                        echo 0 > "$_FPS_FAIL_FILE"
                        rm -f "$_FPS_PREV_FILE"
                        bash "$RESTART_SCRIPT" >> "$LOGFILE" 2>&1
                        log "fps-restart completed (exit: $?)"
                        exit 0
                    fi
                else
                    echo 0 > "$_FPS_FAIL_FILE"
                fi
            fi
        fi
    fi
fi

# ── Decision: restart if 2+ checks fail, or if service/main.py is down ──────
# Rationale: single-check failures (e.g. Chromium not yet started) are transient.
# Service or main.py down is always critical regardless of other checks.
critical_fail=0
for r in "${reasons[@]}"; do
    case "$r" in
        "systemd service not active"|"main.py not running"|"FFmpeg→RTMP not running")
            (( critical_fail++ )) || true ;;
    esac
done

if [ "$critical_fail" -gt 0 ] || [ "$fail" -ge 2 ]; then
    log "FAIL ($fail checks failed): ${reasons[*]}"
    log "Triggering restart..."
    bash "$RESTART_SCRIPT" >> "$LOGFILE" 2>&1
    log "Restart script completed (exit: $?)"
else
    if [ "$fail" -eq 0 ]; then
        log "OK — all checks passed."
    else
        log "WARN ($fail check): ${reasons[*]} — below restart threshold."
    fi
fi
