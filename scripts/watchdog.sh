#!/usr/bin/env bash
# Stream watchdog — vérifie les composants critiques et redémarre uniquement sur crash.
# Alertes non-crash → Telegram (pas de restart automatique).
# Appelé par cron toutes les 2 minutes.
# Logs : /tmp/stream_watchdog.log (rotation à 500KB).
set -uo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
LOGFILE="/tmp/stream_watchdog.log"
RESTART_SCRIPT="$REPO/scripts/restart.sh"

# Charger les tokens Telegram depuis .env
_TG_TOKEN=""
_TG_CHAT=""
if [ -f "$REPO/.env" ]; then
    _TG_TOKEN=$(grep -E '^TELEGRAM_BOT_TOKEN=' "$REPO/.env" | cut -d= -f2- | tr -d '"'"'" 2>/dev/null || true)
    _TG_CHAT=$(grep -E '^TELEGRAM_CHAT_ID=' "$REPO/.env" | cut -d= -f2- | tr -d '"'"'" 2>/dev/null || true)
fi

# Rotation log watchdog à 500KB
if [ -f "$LOGFILE" ] && [ "$(stat -c%s "$LOGFILE" 2>/dev/null || echo 0)" -gt 512000 ]; then
    mv "$LOGFILE" "${LOGFILE}.1"
fi

log() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] WATCHDOG: $*"
    echo "$msg" >> "$LOGFILE"
}

# Envoyer une alerte Telegram (non-bloquant, échec silencieux)
telegram_alert() {
    local msg="$1"
    [ -z "$_TG_TOKEN" ] || [ -z "$_TG_CHAT" ] && return 0
    curl -s --max-time 8 -X POST \
        "https://api.telegram.org/bot${_TG_TOKEN}/sendMessage" \
        -d "chat_id=${_TG_CHAT}" \
        -d "text=${msg}" > /dev/null 2>&1 || true
}

fail=0
reasons=()

# ── Guard: skip si service démarré il y a moins de 60s ──────────────────────
SKIP_COUNT_FILE="/tmp/stream_watchdog_skip_count"
consecutive_skips=$(cat "$SKIP_COUNT_FILE" 2>/dev/null || echo 0)

if systemctl --user is-active --quiet chatgpt-radio.service 2>/dev/null; then
    start_ts=$(systemctl --user show chatgpt-radio.service --property=ActiveEnterTimestamp \
        --value 2>/dev/null | xargs -I{} date -d "{}" +%s 2>/dev/null || echo 0)
    now_ts=$(date +%s)
    uptime_s=$(( now_ts - start_ts ))
    if [ "$uptime_s" -lt 60 ] && [ "$consecutive_skips" -lt 3 ]; then
        echo $(( consecutive_skips + 1 )) > "$SKIP_COUNT_FILE"
        log "Service démarré il y a ${uptime_s}s — skip startup (${consecutive_skips+1}/3)."
        exit 0
    elif [ "$uptime_s" -lt 60 ] && [ "$consecutive_skips" -ge 3 ]; then
        log "Crash-loop détecté (${consecutive_skips} skips consécutifs) — vérifications forcées."
    fi
fi
echo 0 > "$SKIP_COUNT_FILE"

# ── Nettoyage processus orphelins ────────────────────────────────────────────
_killed=0

while IFS= read -r pid; do
    cmdline=$(tr '\0' ' ' < "/proc/${pid}/cmdline" 2>/dev/null || true)
    [[ "$cmdline" == *"main.py"* ]] && continue
    kill "$pid" 2>/dev/null && (( _killed++ )) || true
done < <(pgrep -f "python.*pytest|python -m pytest" 2>/dev/null || true)

while IFS= read -r pid; do
    cmdline=$(tr '\0' ' ' < "/proc/${pid}/cmdline" 2>/dev/null || true)
    [[ "$cmdline" == *"shell-snapshots"* ]] || continue
    start_s=$(stat -c %Y "/proc/${pid}" 2>/dev/null || echo 9999999999)
    age_s=$(( $(date +%s) - start_s ))
    if [ "$age_s" -gt 300 ]; then
        kill "$pid" 2>/dev/null && (( _killed++ )) || true
    fi
done < <(pgrep -f "bash.*shell-snapshot" 2>/dev/null || true)

[ "$_killed" -gt 0 ] && log "Nettoyage : ${_killed} processus orphelin(s) tués."

# ── Pression mémoire — alerte uniquement (pas de restart) ───────────────────
_avail_mb=$(awk '/MemAvailable/ {printf "%d", $2/1024}' /proc/meminfo)
if [ "$_avail_mb" -lt 200 ]; then
    log "WARN: mémoire critique — ${_avail_mb} MB dispo."
    telegram_alert "⚠️ ChatGPT Radio — RAM critique : ${_avail_mb} MB disponible. Action manuelle requise."
elif [ "$_avail_mb" -lt 400 ]; then
    log "WARN: pression mémoire — ${_avail_mb} MB dispo."
fi

# ── Pression disque — alerte si < 2GB libres ────────────────────────────────
_disk_avail_kb=$(df / | awk 'NR==2 {print $4}')
_disk_avail_gb=$(awk "BEGIN{printf \"%.1f\", $_disk_avail_kb/1048576}")
if awk "BEGIN{exit !($_disk_avail_kb < 2097152)}"; then
    log "WARN: espace disque bas — ${_disk_avail_gb} GB disponible."
    telegram_alert "⚠️ ChatGPT Radio — Disque bas : ${_disk_avail_gb} GB disponible."
fi

# ── Rotation des logs /tmp ───────────────────────────────────────────────────
# ffmpeg_live.log → 50 MB
_ffmpeg_log="/tmp/ffmpeg_live.log"
if [ -f "$_ffmpeg_log" ] && [ "$(stat -c%s "$_ffmpeg_log" 2>/dev/null || echo 0)" -gt 52428800 ]; then
    mv "$_ffmpeg_log" "${_ffmpeg_log}.1"
    log "Rotation ffmpeg_live.log (> 50 MB)."
fi

# chromium_console.log → 5 MB
_chrom_log="/tmp/chromium_console.log"
if [ -f "$_chrom_log" ] && [ "$(stat -c%s "$_chrom_log" 2>/dev/null || echo 0)" -gt 5242880 ]; then
    mv "$_chrom_log" "${_chrom_log}.1"
    log "Rotation chromium_console.log (> 5 MB)."
fi

# stream_restart.log → 2 MB
_restart_log="/tmp/stream_restart.log"
if [ -f "$_restart_log" ] && [ "$(stat -c%s "$_restart_log" 2>/dev/null || echo 0)" -gt 2097152 ]; then
    mv "$_restart_log" "${_restart_log}.1"
    log "Rotation stream_restart.log (> 2 MB)."
fi

# diag_monitor.log → 5 MB
_diag_log="/tmp/diag_monitor.log"
if [ -f "$_diag_log" ] && [ "$(stat -c%s "$_diag_log" 2>/dev/null || echo 0)" -gt 5242880 ]; then
    mv "$_diag_log" "${_diag_log}.1"
    log "Rotation diag_monitor.log (> 5 MB)."
fi

# ── Check fps — alerte uniquement (pas de restart) ──────────────────────────
_FPS_FAIL_FILE="/tmp/stream_watchdog_fps_fail_count"
_FPS_PREV_FILE="/tmp/stream_watchdog_fps_prev"
_fps_fail_count=$(cat "$_FPS_FAIL_FILE" 2>/dev/null || echo 0)
_fps_alert_threshold=20  # alerte si fps < 20 pendant 3 checks (6 min)
_fps_alert_max=3

if systemctl --user is-active --quiet chatgpt-radio.service 2>/dev/null; then
    _svc_start=$(systemctl --user show chatgpt-radio.service --property=ActiveEnterTimestamp \
        --value 2>/dev/null | xargs -I{} date -d "{}" +%s 2>/dev/null || echo 0)
    _svc_uptime=$(( $(date +%s) - _svc_start ))

    if [ "$_svc_uptime" -ge 300 ] && [ -f "/tmp/ffmpeg_live.log" ]; then
        _raw=$(tail -c 4096 /tmp/ffmpeg_live.log 2>/dev/null | tr '\r' '\n' | \
            grep -oP 'frame=\s*\K\d+(?=.*?time=)|time=\K\d+:\d+:\d+\.\d+' | tail -4)
        _cur_frame=$(echo "$_raw" | grep -E '^\d+$' | tail -1)
        _cur_time=$(echo "$_raw" | grep -E '^\d+:\d+:\d+' | tail -1)

        if [ -n "$_cur_frame" ] && [ -n "$_cur_time" ]; then
            _cur_sec=$(echo "$_cur_time" | awk -F: '{printf "%.2f", $1*3600+$2*60+$3}')
            _prev=$(cat "$_FPS_PREV_FILE" 2>/dev/null || echo "0:0")
            _prev_frame=$(echo "$_prev" | cut -d: -f1)
            _prev_sec=$(echo "$_prev" | cut -d: -f2)
            echo "${_cur_frame}:${_cur_sec}" > "$_FPS_PREV_FILE"

            _inst_fps=$(awk "BEGIN{
                df=$_cur_frame - $_prev_frame;
                dt=$_cur_sec - $_prev_sec;
                if (dt > 5) printf \"%.1f\", df/dt; else print \"skip\"
            }")

            if [ "$_inst_fps" != "skip" ] && [ -n "$_inst_fps" ]; then
                if awk "BEGIN{exit !($_inst_fps < $_fps_alert_threshold)}"; then
                    (( _fps_fail_count++ )) || true
                    echo "$_fps_fail_count" > "$_FPS_FAIL_FILE"
                    log "WARN: fps_inst=${_inst_fps} < ${_fps_alert_threshold} (${_fps_fail_count}/${_fps_alert_max})"
                    if [ "$_fps_fail_count" -ge "$_fps_alert_max" ]; then
                        log "FPS bas depuis ${_fps_fail_count} checks — alerte Telegram envoyée."
                        telegram_alert "⚠️ ChatGPT Radio — FPS bas : ${_inst_fps} fps depuis 6 min. Vérifier le stream."
                        echo 0 > "$_FPS_FAIL_FILE"
                    fi
                else
                    echo 0 > "$_FPS_FAIL_FILE"
                fi
            fi
        fi
    fi
fi

# ── Checks crash — restart si service/ffmpeg/main.py est mort ───────────────
if ! systemctl --user is-active --quiet chatgpt-radio.service 2>/dev/null; then
    (( fail++ )) || true
    reasons+=("systemd service not active")
fi

if ! pgrep -f "python.*main\.py" > /dev/null 2>&1; then
    (( fail++ )) || true
    reasons+=("main.py not running")
fi

if ! pgrep -f "rtmp://" > /dev/null 2>&1; then
    (( fail++ )) || true
    reasons+=("FFmpeg→RTMP not running")
fi

if ! pgrep -f "chromium" > /dev/null 2>&1; then
    (( fail++ )) || true
    reasons+=("Chromium not running")
fi

if ! ss -tnl 2>/dev/null | grep -q ':8765 '; then
    (( fail++ )) || true
    reasons+=("WebSocket :8765 not responding")
fi

# ── Décision : crash si service/main.py/ffmpeg mort, sinon alerte ───────────
critical_fail=0
for r in "${reasons[@]}"; do
    case "$r" in
        "systemd service not active"|"main.py not running"|"FFmpeg→RTMP not running")
            (( critical_fail++ )) || true ;;
    esac
done

if [ "$critical_fail" -gt 0 ] || [ "$fail" -ge 2 ]; then
    log "CRASH ($fail checks): ${reasons[*]} — restart."
    telegram_alert "🚨 ChatGPT Radio — CRASH détecté : ${reasons[*]}. Redémarrage en cours..."
    bash "$RESTART_SCRIPT" >> "$LOGFILE" 2>&1
    restart_exit=$?
    log "Restart terminé (exit: ${restart_exit})"
    if [ "$restart_exit" -eq 0 ]; then
        telegram_alert "✅ ChatGPT Radio — Stream redémarré avec succès."
    else
        telegram_alert "❌ ChatGPT Radio — Redémarrage échoué (exit ${restart_exit}). Intervention manuelle requise."
    fi
elif [ "$fail" -eq 1 ]; then
    log "WARN (1 check): ${reasons[*]} — en dessous du seuil de restart."
    telegram_alert "⚠️ ChatGPT Radio — Alerte : ${reasons[*]}. En surveillance."
else
    log "OK — tous les checks passés."
fi
