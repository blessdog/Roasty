#!/usr/bin/env bash
# Launch Claude Code Dashboard
set -euo pipefail

DASHBOARD_DIR="$HOME/.claude/dashboard"
VENV_PYTHON="$DASHBOARD_DIR/venv/bin/python3"

if [ ! -f "$VENV_PYTHON" ]; then
  echo "Dashboard not set up yet. Run: ~/.claude/dashboard/setup.sh"
  exit 1
fi

exec "$VENV_PYTHON" "$DASHBOARD_DIR/dashboard.py" "$@"
