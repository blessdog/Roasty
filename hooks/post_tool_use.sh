#!/usr/bin/env bash
# Post-tool-use hook: logs tool calls to events.jsonl
set -euo pipefail

EVENTS_FILE="$HOME/.claude/dashboard/events.jsonl"
INPUT=$(cat)

TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty')
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty')
CWD=$(echo "$INPUT" | jq -r '.cwd // empty')

# Categorize tool
case "$TOOL_NAME" in
  Write)       CATEGORY="file_write" ;;
  Edit)        CATEGORY="file_modify" ;;
  Read)        CATEGORY="file_read" ;;
  Glob|Grep)   CATEGORY="file_search" ;;
  Bash)        CATEGORY="bash" ;;
  WebFetch|WebSearch) CATEGORY="web" ;;
  Task)        CATEGORY="task" ;;
  *)           CATEGORY="other" ;;
esac

# Extract relevant detail based on tool type
FILE_PATH=""
DETAIL=""
case "$TOOL_NAME" in
  Write|Edit|Read)
    FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
    BASENAME=$(basename "$FILE_PATH" 2>/dev/null || echo "$FILE_PATH")
    DETAIL="$BASENAME"
    ;;
  Glob)
    DETAIL=$(echo "$INPUT" | jq -r '.tool_input.pattern // empty')
    ;;
  Grep)
    DETAIL=$(echo "$INPUT" | jq -r '.tool_input.pattern // empty')
    ;;
  Bash)
    DETAIL=$(echo "$INPUT" | jq -r '(.tool_input.description // .tool_input.command // empty) | tostring | .[0:80]')
    ;;
  WebFetch)
    DETAIL=$(echo "$INPUT" | jq -r '.tool_input.url // empty' | head -c 80)
    ;;
  WebSearch)
    DETAIL=$(echo "$INPUT" | jq -r '.tool_input.query // empty' | head -c 80)
    ;;
  Task)
    DETAIL=$(echo "$INPUT" | jq -r '.tool_input.description // empty' | head -c 80)
    ;;
  *)
    DETAIL="$TOOL_NAME"
    ;;
esac

jq -cn --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
      --arg event "tool_use" \
      --arg sid "$SESSION_ID" \
      --arg tool "$TOOL_NAME" \
      --arg cat "$CATEGORY" \
      --arg fp "$FILE_PATH" \
      --arg detail "$DETAIL" \
      --arg cwd "$CWD" \
  '{timestamp: $ts, event: $event, session_id: $sid, tool_name: $tool, category: $cat, file_path: $fp, detail: $detail, cwd: $cwd}' \
  >> "$EVENTS_FILE" 2>/dev/null

exit 0
