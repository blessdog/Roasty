#!/usr/bin/env bash
# Roasty installer — no Homebrew, no Xcode required
set -euo pipefail

REPO="https://github.com/blessdog/Roasty"
DASHBOARD_DIR="$HOME/.claude/dashboard"

RED='\033[31m'
GREEN='\033[32m'
CYAN='\033[36m'
BOLD='\033[1m'
DIM='\033[2m'
RST='\033[0m'

info()  { printf "${CYAN}=>${RST} %s\n" "$*"; }
ok()    { printf "${GREEN}=>${RST} %s\n" "$*"; }
err()   { printf "${RED}=>${RST} %s\n" "$*" >&2; }

echo ""
printf "${BOLD}${CYAN}  Roasty Installer${RST}\n"
echo ""

# Check for python3
if ! command -v python3 >/dev/null 2>&1; then
  err "Python 3 is required. Install it from https://www.python.org/downloads/"
  exit 1
fi

# Check for jq
if ! command -v jq >/dev/null 2>&1; then
  err "jq is required but not found."
  echo ""
  echo "  Install options:"
  echo "    macOS:  curl -sL https://github.com/jqlang/jq/releases/download/jq-1.7.1/jq-macos-arm64 -o /usr/local/bin/jq && chmod +x /usr/local/bin/jq"
  echo "    Linux:  sudo apt install jq  OR  sudo yum install jq"
  echo ""
  exit 1
fi

# Download
if command -v git >/dev/null 2>&1; then
  info "Cloning Roasty..."
  if [ -d "$DASHBOARD_DIR/.git" ]; then
    cd "$DASHBOARD_DIR" && git pull --quiet
  else
    rm -rf "$DASHBOARD_DIR"
    git clone --quiet "$REPO.git" "$DASHBOARD_DIR"
  fi
else
  info "Downloading Roasty..."
  TMPFILE=$(mktemp -d)
  curl -sL "$REPO/archive/refs/heads/main.tar.gz" | tar xz -C "$TMPFILE"
  rm -rf "$DASHBOARD_DIR"
  mv "$TMPFILE/Roasty-main" "$DASHBOARD_DIR"
  rm -rf "$TMPFILE"
fi

# Make scripts executable
chmod +x "$DASHBOARD_DIR/bin/roasty"
chmod +x "$DASHBOARD_DIR/statusline.sh"
chmod +x "$DASHBOARD_DIR/dashboard.py"
chmod +x "$DASHBOARD_DIR/hooks/"*.sh

# Create venv + install Rich
info "Setting up Python environment..."
if [ ! -f "$DASHBOARD_DIR/venv/bin/python3" ]; then
  python3 -m venv "$DASHBOARD_DIR/venv"
fi
"$DASHBOARD_DIR/venv/bin/pip" install --quiet rich

# Create events file
touch "$DASHBOARD_DIR/events.jsonl"

# Add to PATH (symlink to a common location)
SYMLINK_DIR=""
if [ -d "/usr/local/bin" ] && [ -w "/usr/local/bin" ]; then
  SYMLINK_DIR="/usr/local/bin"
elif [ -d "$HOME/.local/bin" ]; then
  SYMLINK_DIR="$HOME/.local/bin"
elif [ -d "$HOME/bin" ]; then
  SYMLINK_DIR="$HOME/bin"
else
  mkdir -p "$HOME/.local/bin"
  SYMLINK_DIR="$HOME/.local/bin"
fi

if [ -n "$SYMLINK_DIR" ]; then
  ln -sf "$DASHBOARD_DIR/bin/roasty" "$SYMLINK_DIR/roasty"
  info "Linked roasty to $SYMLINK_DIR/roasty"
fi

# Configure Claude Code
info "Configuring Claude Code hooks..."
"$DASHBOARD_DIR/bin/roasty" setup 2>/dev/null || true

echo ""
ok "Roasty installed!"
echo ""

# Check if roasty is on PATH
if command -v roasty >/dev/null 2>&1; then
  printf "  Run ${CYAN}roasty${RST} to launch the dashboard.\n"
else
  printf "  Run ${CYAN}~/.claude/dashboard/bin/roasty${RST} to launch.\n"
  echo ""
  printf "  ${DIM}To add to PATH, add this to your shell profile:${RST}\n"
  printf "  ${DIM}export PATH=\"\$HOME/.local/bin:\$PATH\"${RST}\n"
fi
echo ""
