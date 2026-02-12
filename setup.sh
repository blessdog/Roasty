#!/usr/bin/env bash
# One-time setup for Claude Code Dashboard
set -euo pipefail

DASHBOARD_DIR="$HOME/.claude/dashboard"

echo "Setting up Claude Code Dashboard..."

# Create Python venv
echo "Creating Python virtual environment..."
python3 -m venv "$DASHBOARD_DIR/venv"

# Install Rich
echo "Installing Rich library..."
"$DASHBOARD_DIR/venv/bin/pip" install --quiet rich

# Set executable permissions
echo "Setting permissions..."
chmod +x "$DASHBOARD_DIR/launch.sh"
chmod +x "$DASHBOARD_DIR/statusline.sh"
chmod +x "$DASHBOARD_DIR/dashboard.py"
chmod +x "$DASHBOARD_DIR/hooks/"*.sh

# Create empty events file
touch "$DASHBOARD_DIR/events.jsonl"

echo ""
echo "Setup complete!"
echo ""
echo "Usage:"
echo "  1. Open Ghostty"
echo "  2. Cmd+D to create a right split"
echo "  3. In right pane: ~/.claude/dashboard/launch.sh"
echo "  4. Cmd+H to focus left pane"
echo "  5. Start 'claude' and code -- dashboard updates in real-time"
