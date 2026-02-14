#!/usr/bin/env bash
# Subagent stop hook: logs agent completions to events.jsonl
set -euo pipefail

EVENTS_FILE="$HOME/.claude/dashboard/events.jsonl"
INPUT=$(cat)

AGENT_ID=$(echo "$INPUT" | jq -r '.agent_id // empty')
AGENT_TYPE=$(echo "$INPUT" | jq -r '.agent_type // empty')
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty')

jq -cn --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
      --arg event "subagent_stop" \
      --arg sid "$SESSION_ID" \
      --arg aid "$AGENT_ID" \
      --arg atype "$AGENT_TYPE" \
  '{timestamp: $ts, event: $event, session_id: $sid, agent_id: $aid, agent_type: $atype}' \
  >> "$EVENTS_FILE" 2>/dev/null

exit 0
