#!/usr/bin/env bash
# Roasty installer — one command, fully configured
# curl -sL https://raw.githubusercontent.com/blessdog/Roasty/main/install.sh | bash
set -euo pipefail

REPO="https://github.com/blessdog/Roasty"
DASHBOARD_DIR="$HOME/.claude/dashboard"

RED='\033[31m'
GREEN='\033[32m'
YELLOW='\033[33m'
CYAN='\033[36m'
BOLD='\033[1m'
DIM='\033[2m'
RST='\033[0m'

info()  { printf "${CYAN}=>${RST} %s\n" "$*"; }
ok()    { printf "${GREEN}=>${RST} %s\n" "$*"; }
warn()  { printf "${YELLOW}=>${RST} %s\n" "$*"; }
err()   { printf "${RED}=>${RST} %s\n" "$*" >&2; }

echo ""
printf "${BOLD}${CYAN}  Roasty Installer${RST}\n"
printf "  ${DIM}Claude Code Dashboard for Ghostty${RST}\n"
echo ""

# ---- Preflight checks ----

# Python 3
if ! command -v python3 >/dev/null 2>&1; then
  err "Python 3 is required."
  echo "  Install: https://www.python.org/downloads/"
  echo "  Or: brew install python3"
  exit 1
fi
ok "Python 3 found: $(python3 --version 2>&1)"

# jq
if ! command -v jq >/dev/null 2>&1; then
  info "jq not found — installing..."
  if command -v brew >/dev/null 2>&1; then
    brew install jq --quiet
  else
    # Direct binary download for macOS
    ARCH="$(uname -m)"
    if [ "$ARCH" = "arm64" ]; then
      JQ_URL="https://github.com/jqlang/jq/releases/download/jq-1.7.1/jq-macos-arm64"
    else
      JQ_URL="https://github.com/jqlang/jq/releases/download/jq-1.7.1/jq-macos-amd64"
    fi
    mkdir -p "$HOME/.local/bin"
    curl -sL "$JQ_URL" -o "$HOME/.local/bin/jq" && chmod +x "$HOME/.local/bin/jq"
    export PATH="$HOME/.local/bin:$PATH"
  fi
fi
ok "jq available"

# ---- Download ----

if command -v git >/dev/null 2>&1; then
  if [ -d "$DASHBOARD_DIR/.git" ]; then
    info "Updating existing installation..."
    cd "$DASHBOARD_DIR" && git pull --quiet
  else
    info "Cloning Roasty..."
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
ok "Files installed to ~/.claude/dashboard/"

# ---- Make everything executable ----

chmod +x "$DASHBOARD_DIR/bin/roasty"
chmod +x "$DASHBOARD_DIR/statusline.sh"
chmod +x "$DASHBOARD_DIR/dashboard.py"
chmod +x "$DASHBOARD_DIR/hooks/"*.sh

# ---- Python venv + Rich ----

info "Setting up Python environment..."
if [ ! -f "$DASHBOARD_DIR/venv/bin/python3" ]; then
  python3 -m venv "$DASHBOARD_DIR/venv"
fi

if ! "$DASHBOARD_DIR/venv/bin/python3" -c "import rich" 2>/dev/null; then
  "$DASHBOARD_DIR/venv/bin/pip" install --quiet rich
fi
ok "Python venv ready with Rich"

# ---- Events file ----

touch "$DASHBOARD_DIR/events.jsonl"

# ---- Add to PATH ----

SYMLINK_DIR=""
if [ -d "/usr/local/bin" ] && [ -w "/usr/local/bin" ]; then
  SYMLINK_DIR="/usr/local/bin"
elif [ -d "$HOME/.local/bin" ]; then
  SYMLINK_DIR="$HOME/.local/bin"
else
  mkdir -p "$HOME/.local/bin"
  SYMLINK_DIR="$HOME/.local/bin"
fi

if [ -n "$SYMLINK_DIR" ]; then
  ln -sf "$DASHBOARD_DIR/bin/roasty" "$SYMLINK_DIR/roasty"
  ok "Linked roasty to $SYMLINK_DIR/roasty"
fi

# Ensure ~/.local/bin is in PATH for current shell profiles
if [ "$SYMLINK_DIR" = "$HOME/.local/bin" ]; then
  PATH_LINE='export PATH="$HOME/.local/bin:$PATH"'
  for rcfile in "$HOME/.zshrc" "$HOME/.bashrc"; do
    if [ -f "$rcfile" ] && ! grep -q '.local/bin' "$rcfile" 2>/dev/null; then
      echo "" >> "$rcfile"
      echo "# Roasty" >> "$rcfile"
      echo "$PATH_LINE" >> "$rcfile"
      ok "Added ~/.local/bin to PATH in $(basename "$rcfile")"
    fi
  done
  export PATH="$HOME/.local/bin:$PATH"
fi

# ---- Configure Claude Code hooks + statusline ----

info "Configuring Claude Code hooks..."
"$DASHBOARD_DIR/bin/roasty" setup 2>/dev/null || true

# ---- Done ----

echo ""
printf "${BOLD}${GREEN}  Roasty is ready!${RST}\n"
echo ""
printf "  ${BOLD}Quick start:${RST}\n"
echo ""

if command -v roasty >/dev/null 2>&1; then
  printf "    ${DIM}1.${RST} Open a project:   ${CYAN}roasty open ~/Projects/my-app${RST}\n"
  printf "    ${DIM}2.${RST} Split pane:        ${DIM}Cmd+D${RST}\n"
  printf "    ${DIM}3.${RST} Launch dashboard:  ${CYAN}roasty${RST}\n"
  printf "    ${DIM}4.${RST} Resize panes:      ${DIM}Cmd+Shift+←/→${RST}\n"
else
  printf "    ${DIM}1.${RST} ${CYAN}~/.claude/dashboard/bin/roasty open ~/Projects/my-app${RST}\n"
  printf "    ${DIM}2.${RST} Split pane:        ${DIM}Cmd+D${RST}\n"
  printf "    ${DIM}3.${RST} Launch dashboard:  ${CYAN}~/.claude/dashboard/bin/roasty${RST}\n"
  echo ""
  printf "  ${DIM}To add to PATH:${RST}\n"
  printf "  ${DIM}export PATH=\"\$HOME/.local/bin:\$PATH\"${RST}\n"
fi

echo ""
printf "  ${DIM}Optional: install Ghostty config for Citruszest theme + keybindings:${RST}\n"
printf "    ${CYAN}roasty ghostty${RST}\n"
echo ""
