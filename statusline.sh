#!/usr/bin/env bash
# Claude Code status line for Ghostty - Citruszest themed
# Reads status JSON from stdin, outputs a compact ANSI-colored one-liner
set -euo pipefail

INPUT=$(cat)
EVENTS_FILE="$HOME/.claude/dashboard/events.jsonl"

# Extract fields
MODEL=$(echo "$INPUT" | jq -r '.model.display_name // "Claude"')
COST=$(echo "$INPUT" | jq -r '.cost.total_cost_usd // 0')
DURATION_MS=$(echo "$INPUT" | jq -r '.cost.total_duration_ms // 0')
LINES_ADD=$(echo "$INPUT" | jq -r '.cost.total_lines_added // 0')
LINES_DEL=$(echo "$INPUT" | jq -r '.cost.total_lines_removed // 0')
USED_PCT=$(echo "$INPUT" | jq -r '.context_window.used_percentage // 0')
INPUT_TOKENS=$(echo "$INPUT" | jq -r '.context_window.total_input_tokens // 0')
OUTPUT_TOKENS=$(echo "$INPUT" | jq -r '.context_window.total_output_tokens // 0')

# Last edited file (from events.jsonl)
LAST_FILE=""
if [ -f "$EVENTS_FILE" ]; then
  LAST_FILE=$(tail -50 "$EVENTS_FILE" | jq -r 'select(.category == "file_write" or .category == "file_modify") | .file_path' 2>/dev/null | tail -1)
fi

# Format cost
if (( $(echo "$COST < 0.01" | bc -l 2>/dev/null || echo 0) )); then
  COST_FMT=$(printf '$%.4f' "$COST")
else
  COST_FMT=$(printf '$%.2f' "$COST")
fi

# Format duration (ms -> Xm Ys)
DURATION_SEC=$((DURATION_MS / 1000))
if [ "$DURATION_SEC" -ge 60 ]; then
  MINS=$((DURATION_SEC / 60))
  SECS=$((DURATION_SEC % 60))
  DUR_FMT="${MINS}m${SECS}s"
else
  DUR_FMT="${DURATION_SEC}s"
fi

# Format tokens (K suffix)
format_tokens() {
  local t=$1
  if [ "$t" -ge 1000 ]; then
    echo "$((t / 1000))K"
  else
    echo "$t"
  fi
}
IN_FMT=$(format_tokens "$INPUT_TOKENS")
OUT_FMT=$(format_tokens "$OUTPUT_TOKENS")

# Context window bar (10 chars wide)
FILLED=$((USED_PCT / 10))
EMPTY=$((10 - FILLED))
BAR=""
for ((i=0; i<FILLED; i++)); do BAR+="█"; done
for ((i=0; i<EMPTY; i++)); do BAR+="░"; done

# Color coding for context bar
RST='\033[0m'
CYAN='\033[36m'
GREEN='\033[32m'
YELLOW='\033[33m'
RED='\033[31m'
DIM='\033[2m'

if [ "$USED_PCT" -ge 90 ]; then
  BAR_COLOR="$RED"
elif [ "$USED_PCT" -ge 70 ]; then
  BAR_COLOR="$YELLOW"
else
  BAR_COLOR="$GREEN"
fi

# Nerd Font glyph for AI/model
MODEL_GLYPH="󰧑"

# Full file path for display (~ for home, no truncation)
FULL_FILE=""
if [ -n "$LAST_FILE" ]; then
  FULL_FILE="${LAST_FILE/#$HOME/~}"
fi

# Build the status line
printf "${CYAN}${MODEL_GLYPH} %s${RST}" "$MODEL"
if [ -n "$FULL_FILE" ]; then
  printf " ${DIM}│${RST} ${CYAN} %s${RST}" "$FULL_FILE"
fi
printf "\n${BAR_COLOR}%s${RST} %s%% ${DIM}│${RST} %s/%s" \
  "$BAR" "$USED_PCT" "$IN_FMT" "$OUT_FMT"
