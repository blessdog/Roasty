#!/usr/bin/env bash
# Stop hook: marks response completions
set -euo pipefail

EVENTS_FILE="$HOME/.claude/dashboard/events.jsonl"
INPUT=$(cat)

SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty')

jq -n --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
      --arg event "stop" \
      --arg sid "$SESSION_ID" \
  '{timestamp: $ts, event: $event, session_id: $sid}' \
  >> "$EVENTS_FILE" 2>/dev/null

exit 0
