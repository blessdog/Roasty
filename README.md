# Roasty 󰧑

**A real-time dashboard for Claude Code sessions in Ghostty.**

See what Claude is doing at a glance — file edits, tool calls, agent spawns, errors, and session stats — in a split pane next to your working session.

```
Ghostty Terminal
┌──────────────────────────┬──────────────────────────────┐
│  Claude Code (main)      │  Dashboard TUI (split pane)  │
│                          │  ┌────────────────────────┐  │
│  Working on your code... │  │ 󰧑 Opus  12m  main *   │  │
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

### Homebrew (recommended)

```bash
brew install blessdog/tap/roasty
roasty setup
```

That's it. `roasty setup` creates a Python venv, installs Rich, configures Claude Code hooks, and sets up the status line — all automatically.

### Manual

```bash
git clone https://github.com/blessdog/Roasty.git ~/.claude/dashboard
~/.claude/dashboard/setup.sh
```

Then manually merge the hooks config into `~/.claude/settings.json` — see [Manual Configuration](#manual-configuration) below.

## Usage

```bash
# In Ghostty:
# 1. Cmd+D to split right
# 2. In the right pane:
roasty

# 3. Cmd+H to go back to the left pane
# 4. Start claude and code — dashboard updates in real-time
```

### Commands

| Command | Description |
|---------|-------------|
| `roasty` | Launch the dashboard (default) |
| `roasty setup` | Install hooks, create venv, configure Claude Code |
| `roasty status` | Check if everything is configured |
| `roasty uninstall` | Remove hooks and dashboard files |
| `roasty help` | Show help |

## How It Works

Three integration points, zero interference with Claude:

1. **Claude Code Hooks** — Bash scripts that fire on tool use, agent spawns, session start/end. Each appends a JSON line to `events.jsonl`. They always `exit 0` so they never block Claude.

2. **Status Line** — A compact ANSI-colored bar at the bottom of your Claude Code pane showing model, cost, duration, lines changed, and a context window usage meter.

3. **Rich TUI Dashboard** — A Python script using [Rich](https://github.com/Textualize/rich) that tails `events.jsonl` and renders five live-updating panels.

```
Hooks (bash) → events.jsonl → Dashboard (Python/Rich)
```

## Dashboard Panels

| Panel | What it shows |
|-------|---------------|
| **Header** | Model name, session duration, git branch + dirty status, working directory |
| **File Activity** | Recent file reads, writes, and edits with timestamps and Nerd Font icons |
| **Tool Activity** | All tool calls (Bash, Grep, Glob, WebSearch, etc.) with details |
| **Agents** | Active subagents with duration, recently completed agents |
| **Stats** | Tool call counts with usage bars, files touched, responses, errors with last error detail |

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
- **jq** (for hook scripts — installed automatically with `brew`)
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

All events are written as JSONL to `~/.claude/dashboard/events.jsonl`.

## Customization

**Colors** — The dashboard uses a Citruszest-inspired palette. Edit the `COLORS` dict at the top of `dashboard.py`.

**Refresh rate** — Change `REFRESH_INTERVAL` in `dashboard.py` (default: 1.5s).

**Max entries** — Change `MAX_FILE_ENTRIES` and `MAX_TOOL_ENTRIES` in `dashboard.py` (default: 15 each).

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
├── dashboard.py           # Rich TUI dashboard
├── statusline.sh          # Claude Code status line script
├── setup.sh               # Manual setup (alternative to roasty setup)
├── launch.sh              # Manual launcher (alternative to roasty)
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
