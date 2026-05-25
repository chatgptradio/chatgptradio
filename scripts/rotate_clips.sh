#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
CLIPS_DIR="$REPO/streams/audio"
DB_PATH="$REPO/streams/state.db"
MAX_AGE_DAYS="${MAX_AGE_DAYS:-7}"
MAX_GB="${MAX_GB:-2}"

# Delete clips older than MAX_AGE_DAYS and remove their DB rows
find "$CLIPS_DIR" -name "*.mp3" -mtime "+${MAX_AGE_DAYS}" -print0 | while IFS= read -r -d '' clip; do
    sqlite3 "$DB_PATH" "DELETE FROM audio_clips WHERE path = '${clip//\'/\'\'}'" 2>/dev/null || true
    rm -f "$clip"
    logger -t chatgpt-radio-rotate "Deleted old clip: $clip"
done

# If still over MAX_GB, delete oldest clips by mtime until under limit
CURRENT_BYTES=$(du -sb "$CLIPS_DIR" 2>/dev/null | awk '{print $1}')
MAX_BYTES=$(( MAX_GB * 1073741824 ))
if [[ "$CURRENT_BYTES" -gt "$MAX_BYTES" ]]; then
    find "$CLIPS_DIR" -name "*.mp3" -printf "%T+ %p\n" | sort | head -20 | awk '{print $2}' | while read -r clip; do
        sqlite3 "$DB_PATH" "DELETE FROM audio_clips WHERE path = '${clip//\'/\'\'}'" 2>/dev/null || true
        rm -f "$clip"
        logger -t chatgpt-radio-rotate "Deleted clip (disk pressure): $clip"
    done
fi
