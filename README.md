# Roasty 󰧑

**A real-time dashboard for Claude Code sessions in Ghostty.**

See what Claude is doing at a glance — file tree, file edits, tool calls, agent spawns, errors, and session stats — in a split pane next to your working session. The dashboard auto-adapts to your pane size with responsive compact and standard layouts.

```
Ghostty Terminal
┌──────────────────────────┬──────────────────────────────┐
│  Claude Code (main)      │  Dashboard TUI (split pane)  │
│                          │  ┌────────────────────────┐  │
│  Working on your code... │  │ 󰧑 Opus  12m  main *   │  │
│                          │  ├────────────────────────┤  │
│                          │  │ PROJECT                │  │
│                          │  │  src/                  │  │
│                          │  │   main.py ◀ modified  │  │
│                          │  │   utils.py            │  │
│                          │  │  README.md             │  │
│                          │  ├────────────────────────┤  │
│                          │  │ FILE ACTIVITY          │  │
│                          │  │  20:16  EDIT app.ts   │  │
│                          │  │  20:15  WRITE utils.ts│  │
│                          │  ├────────────────────────┤  │
│                          │  │ TOOL ACTIVITY          │  │
│                          │  │  20:16  BASH npm test │  │
│                          │  │  20:15  GREP import.* │  │
│                          │  ├────────────────────────┤  │
│  [═══ status line ═══]   │  │ AGENTS │ STATS         │  │
│                          │  └────────────────────────┘  │
└──────────────────────────┴──────────────────────────────┘
```

## Install

### One-liner (recommended)

```bash
curl -sL https://raw.githubusercontent.com/blessdog/Roasty/main/install.sh | bash
```

One command — installs everything, configures hooks, sets up PATH. No Homebrew or Xcode required. Just Python 3 (jq is auto-installed if missing).

### Homebrew

```bash
brew install blessdog/tap/roasty
roasty setup
```

### Manual

```bash
git clone https://github.com/blessdog/Roasty.git ~/.claude/dashboard
~/.claude/dashboard/bin/roasty setup
```

## Quick Start

```bash
# Open a project and launch Claude Code:
roasty open ~/Projects/my-app

# Split pane (Cmd+D in Ghostty), then in the new pane:
roasty

# Navigate back: Cmd+H  |  Resize panes: Ctrl+Cmd+Left/Right
```

## Commands

| Command | Description |
|---------|-------------|
| `roasty` | Launch the dashboard (default) |
| `roasty open <dir>` | Open a project — sets directory and launches Claude Code |
| `roasty setup` | Install hooks, create venv, configure Claude Code |
| `roasty ghostty` | Install recommended Ghostty config (Citruszest theme, splits, resize) |
| `roasty status` | Check if everything is configured |
| `roasty uninstall` | Remove hooks and dashboard files |
| `roasty help` | Show help with all commands and keybindings |

### Dashboard Flags

| Flag | Description |
|------|-------------|
| `--compact`, `-c` | Force compact mode regardless of terminal width |
| `--project <dir>`, `-p <dir>` | Set project directory for the file tree panel |

## Features

### Responsive Layout

The dashboard auto-detects your terminal width and adapts:

- **Standard mode** (≥ 50 cols): Full panels with project file tree, file activity, tool activity, agents, and stats
- **Compact mode** (< 50 cols): Streamlined combined activity feed with a one-line stats bar

Resize your Ghostty split and the dashboard switches seamlessly.

### Project File Tree

Shows your project's directory structure with Nerd Font file-type icons. Files that Claude touches during the session are highlighted in green with a `◀` marker. The tree:

- Scans every 5 seconds for changes
- Respects common ignore patterns (`.git`, `node_modules`, `__pycache__`, `venv`, etc.)
- Limits to 3 levels deep, 60 entries max
- Auto-sizes based on terminal height

### Ghostty Keybindings

Run `roasty ghostty` to install these (or add to your existing config):

| Shortcut | Action |
|----------|--------|
| `Cmd+D` | Split right |
| `Cmd+Shift+D` | Split down |
| `Cmd+H/L/K/J` | Navigate splits (vim-style) |
| `Ctrl+Cmd+Left/Right` | Resize panes horizontally |
| `Ctrl+Cmd+Up/Down` | Resize panes vertically |
| `Ctrl+Cmd+=` | Equalize all panes |
| `Cmd+Shift+F` | Zoom/unzoom focused pane |

## How It Works

Three integration points, zero interference with Claude:

1. **Claude Code Hooks** — Bash scripts that fire on tool use, agent spawns, session start/end. Each appends a compact JSON line to `events.jsonl`. They always `exit 0` so they never block Claude.

2. **Status Line** — A compact ANSI-colored bar at the bottom of your Claude Code pane showing model, cost, duration, lines changed, and a context window usage meter.

3. **Rich TUI Dashboard** — A Python script using [Rich](https://github.com/Textualize/rich) that tails `events.jsonl` and renders live-updating panels with responsive layout.

```
Hooks (bash, jq -cn) → events.jsonl (JSONL) → Dashboard (Python/Rich)
.project_path file  → File tree scanner
```

## Dashboard Panels

| Panel | What it shows |
|-------|---------------|
| **Header** | Model name, session duration, git branch + dirty status, working directory |
| **Project** | File tree with Nerd Font icons, modified files highlighted in green |
| **File Activity** | Recent file reads, writes, and edits with timestamps |
| **Tool Activity** | All tool calls (Bash, Grep, Glob, WebSearch, etc.) with details |
| **Agents** | Active subagents with duration, recently completed agents |
| **Stats** | Tool call counts with usage bars, files touched, responses, errors |

## Status Line

The status line renders at the bottom of your Claude Code pane:

```
󰧑 Opus │ $0.05 │ 5m32s │ +142/-37 │ ████░░░░░░ 42% │ 50K/12K
```

- Context bar turns green (<70%), yellow (70-89%), red (90%+)
- Requires a [Nerd Font](https://www.nerdfonts.com/) (the dashboard uses JetBrainsMono Nerd Font glyphs)

## Requirements

- **Claude Code** with hooks support
- **Python 3.9+**
- **jq** (auto-installed by the curl installer if missing)
- **Ghostty** (or any terminal with split panes — iTerm2, tmux, etc.)
- A [Nerd Font](https://www.nerdfonts.com/) for icons (optional but recommended)

## Hooks Reference

| Hook | Event | What it logs |
|------|-------|-------------|
| `post_tool_use.sh` | Every tool call | Tool name, category, file path, detail |
| `post_tool_use_failure.sh` | Tool failures | Tool name, error message |
| `subagent_start.sh` | Agent spawns | Agent ID, type (Explore, Bash, Plan, etc.) |
| `subagent_stop.sh` | Agent completions | Agent ID, type |
| `stop.sh` | Response complete | Session ID |
| `session_start.sh` | Session init | Model, source, CWD; also rotates logs >5MB |
| `session_end.sh` | Session cleanup | Reason (exit, clear, logout) |

All hooks use `jq -cn` for compact single-line JSON output to `~/.claude/dashboard/events.jsonl`.

## Customization

**Colors** — The dashboard uses a Citruszest-inspired palette. Edit the `COLORS` dict at the top of `dashboard.py`.

**Refresh rate** — Change `REFRESH_INTERVAL` in `dashboard.py` (default: 1.5s).

**Max entries** — Change `MAX_FILE_ENTRIES` and `MAX_TOOL_ENTRIES` in `dashboard.py` (default: 15 each).

**File tree** — Adjust `TREE_MAX_DEPTH`, `TREE_MAX_ENTRIES`, `TREE_SCAN_INTERVAL`, or add directories to `TREE_IGNORE` in `dashboard.py`.

## Manual Configuration

If you installed manually (without `roasty setup`), merge this into `~/.claude/settings.json`:

<details>
<summary>Click to expand settings.json config</summary>

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "",
        "hooks": [{ "type": "command", "command": "~/.claude/dashboard/hooks/post_tool_use.sh" }]
      }
    ],
    "PostToolUseFailure": [
      {
        "matcher": "",
        "hooks": [{ "type": "command", "command": "~/.claude/dashboard/hooks/post_tool_use_failure.sh" }]
      }
    ],
    "SubagentStart": [
      {
        "matcher": "",
        "hooks": [{ "type": "command", "command": "~/.claude/dashboard/hooks/subagent_start.sh" }]
      }
    ],
    "SubagentStop": [
      {
        "matcher": "",
        "hooks": [{ "type": "command", "command": "~/.claude/dashboard/hooks/subagent_stop.sh" }]
      }
    ],
    "Stop": [
      {
        "hooks": [{ "type": "command", "command": "~/.claude/dashboard/hooks/stop.sh" }]
      }
    ],
    "SessionStart": [
      {
        "matcher": "",
        "hooks": [{ "type": "command", "command": "~/.claude/dashboard/hooks/session_start.sh" }]
      }
    ],
    "SessionEnd": [
      {
        "matcher": "",
        "hooks": [{ "type": "command", "command": "~/.claude/dashboard/hooks/session_end.sh" }]
      }
    ]
  },
  "statusLine": {
    "type": "command",
    "command": "~/.claude/dashboard/statusline.sh",
    "padding": 2
  }
}
```

</details>

## File Structure

```
~/.claude/dashboard/
├── bin/roasty             # CLI entry point
├── dashboard.py           # Rich TUI dashboard (responsive layout)
├── statusline.sh          # Claude Code status line script
├── ghostty.config         # Recommended Ghostty config
├── install.sh             # Curl installer (all-in-one bootstrap)
├── .project_path          # Current project dir (runtime, written by roasty open)
├── events.jsonl           # Event log (runtime, written by hooks)
└── hooks/
    ├── post_tool_use.sh
    ├── post_tool_use_failure.sh
    ├── subagent_start.sh
    ├── subagent_stop.sh
    ├── stop.sh
    ├── session_start.sh
    └── session_end.sh
```

## License

MIT
