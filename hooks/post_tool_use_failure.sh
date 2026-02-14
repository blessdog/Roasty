#!/usr/bin/env bash
# Post-tool-use failure hook: logs tool failures to events.jsonl
set -euo pipefail

EVENTS_FILE="$HOME/.claude/dashboard/events.jsonl"
INPUT=$(cat)

TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty')
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty')
ERROR=$(echo "$INPUT" | jq -r '.error // empty' | head -c 200)

jq -cn --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
      --arg event "tool_failure" \
      --arg sid "$SESSION_ID" \
      --arg tool "$TOOL_NAME" \
      --arg error "$ERROR" \
  '{timestamp: $ts, event: $event, session_id: $sid, tool_name: $tool, error: $error}' \
  >> "$EVENTS_FILE" 2>/dev/null

exit 0
