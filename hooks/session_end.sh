#!/usr/bin/env bash
# Session end hook: logs session cleanup
set -euo pipefail

EVENTS_FILE="$HOME/.claude/dashboard/events.jsonl"
INPUT=$(cat)

SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty')
REASON=$(echo "$INPUT" | jq -r '.reason // empty')

jq -n --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
      --arg event "session_end" \
      --arg sid "$SESSION_ID" \
      --arg reason "$REASON" \
  '{timestamp: $ts, event: $event, session_id: $sid, reason: $reason}' \
  >> "$EVENTS_FILE" 2>/dev/null

exit 0
