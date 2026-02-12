#!/usr/bin/env bash
# Session start hook: logs session init + handles log rotation
set -euo pipefail

EVENTS_FILE="$HOME/.claude/dashboard/events.jsonl"
INPUT=$(cat)

SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty')
MODEL=$(echo "$INPUT" | jq -r '.model // empty')
SOURCE=$(echo "$INPUT" | jq -r '.source // empty')
CWD=$(echo "$INPUT" | jq -r '.cwd // empty')

# Log rotation: if events.jsonl > 5MB, keep last 1000 lines
if [ -f "$EVENTS_FILE" ]; then
  FILE_SIZE=$(stat -f%z "$EVENTS_FILE" 2>/dev/null || stat -c%s "$EVENTS_FILE" 2>/dev/null || echo 0)
  if [ "$FILE_SIZE" -gt 5242880 ]; then
    TMPFILE=$(mktemp)
    tail -n 1000 "$EVENTS_FILE" > "$TMPFILE" && mv "$TMPFILE" "$EVENTS_FILE"
  fi
fi

# Ensure file exists
touch "$EVENTS_FILE"

jq -n --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
      --arg event "session_start" \
      --arg sid "$SESSION_ID" \
      --arg model "$MODEL" \
      --arg source "$SOURCE" \
      --arg cwd "$CWD" \
  '{timestamp: $ts, event: $event, session_id: $sid, model: $model, source: $source, cwd: $cwd}' \
  >> "$EVENTS_FILE" 2>/dev/null

exit 0
