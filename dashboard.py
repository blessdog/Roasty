#!/usr/bin/env python3
"""Claude Code Dashboard - Rich TUI for Ghostty split pane.

Reads events from ~/.claude/dashboard/events.jsonl and displays
real-time file activity, tool calls, agent status, and session stats.
"""

import json
import os
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from rich.align import Align
from rich.columns import Columns
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# --- Citruszest-inspired color palette ---
COLORS = {
    "bg": "#1a1a2e",
    "fg": "#e0e0e0",
    "cyan": "#00d4ff",
    "green": "#a6e22e",
    "yellow": "#e6db74",
    "orange": "#fd971f",
    "red": "#f92672",
    "magenta": "#ae81ff",
    "dim": "#75715e",
    "blue": "#66d9ef",
    "border": "#3a3a5c",
    "header_bg": "#2a2a4a",
}

EVENTS_FILE = Path.home() / ".claude" / "dashboard" / "events.jsonl"
REFRESH_INTERVAL = 1.5
MAX_FILE_ENTRIES = 15
MAX_TOOL_ENTRIES = 15


class DashboardState:
    """Tracks session state from parsed events."""

    def __init__(self):
        self.reset()
        self._file_pos = 0
        self._file_inode = None

    def reset(self):
        self.session_id = None
        self.model = ""
        self.cwd = ""
        self.session_start_time = None
        self.file_events = []       # [{timestamp, tool, file_path, category}]
        self.tool_events = []       # [{timestamp, tool, detail, category}]
        self.active_agents = {}     # agent_id -> {type, start_time}
        self.completed_agents = []  # [{type, start_time, end_time}]
        self.errors = []            # [{timestamp, tool, error}]
        self.stop_count = 0
        self.files_touched = set()
        self.lines_added = 0
        self.lines_removed = 0
        self.tool_counts = defaultdict(int)

    def process_event(self, event: dict):
        ts = event.get("timestamp", "")
        etype = event.get("event", "")

        if etype == "session_start":
            self.reset()
            self.session_id = event.get("session_id")
            self.model = event.get("model", "")
            self.cwd = event.get("cwd", "")
            self.session_start_time = ts
            return

        # Only process events for current session
        if self.session_id and event.get("session_id") != self.session_id:
            return

        if etype == "tool_use":
            tool = event.get("tool_name", "")
            category = event.get("category", "")
            detail = event.get("detail", "")
            file_path = event.get("file_path", "")
            cwd = event.get("cwd", "")

            if not self.cwd and cwd:
                self.cwd = cwd

            self.tool_counts[tool] += 1
            self.tool_events.append({
                "timestamp": ts,
                "tool": tool,
                "detail": detail,
                "category": category,
            })

            if file_path:
                self.files_touched.add(file_path)
                self.file_events.append({
                    "timestamp": ts,
                    "tool": tool,
                    "file_path": file_path,
                    "category": category,
                })

            # Trim to max
            if len(self.tool_events) > MAX_TOOL_ENTRIES * 2:
                self.tool_events = self.tool_events[-MAX_TOOL_ENTRIES:]
            if len(self.file_events) > MAX_FILE_ENTRIES * 2:
                self.file_events = self.file_events[-MAX_FILE_ENTRIES:]

        elif etype == "tool_failure":
            self.errors.append({
                "timestamp": ts,
                "tool": event.get("tool_name", ""),
                "error": event.get("error", ""),
            })

        elif etype == "subagent_start":
            aid = event.get("agent_id", "")
            self.active_agents[aid] = {
                "type": event.get("agent_type", ""),
                "start_time": ts,
            }

        elif etype == "subagent_stop":
            aid = event.get("agent_id", "")
            if aid in self.active_agents:
                agent = self.active_agents.pop(aid)
                self.completed_agents.append({
                    "type": agent["type"],
                    "start_time": agent["start_time"],
                    "end_time": ts,
                })

        elif etype == "stop":
            self.stop_count += 1

        elif etype == "session_end":
            pass  # Keep showing last state

    def poll_events(self):
        """Incrementally read new lines from events.jsonl."""
        if not EVENTS_FILE.exists():
            return

        try:
            stat = EVENTS_FILE.stat()
        except OSError:
            return

        # Detect file rotation (inode change or file shrunk)
        current_inode = stat.st_ino
        if self._file_inode is not None and (
            current_inode != self._file_inode or stat.st_size < self._file_pos
        ):
            self._file_pos = 0
        self._file_inode = current_inode

        if stat.st_size <= self._file_pos:
            return

        try:
            with open(EVENTS_FILE, "r") as f:
                f.seek(self._file_pos)
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                        self.process_event(event)
                    except json.JSONDecodeError:
                        continue
                self._file_pos = f.tell()
        except OSError:
            pass


def format_time(ts_str: str) -> str:
    """Format ISO timestamp to HH:MM local time."""
    if not ts_str:
        return ""
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        local = dt.astimezone()
        return local.strftime("%H:%M")
    except (ValueError, OSError):
        return ts_str[:5] if len(ts_str) >= 5 else ts_str


def get_duration(start_ts: str) -> str:
    """Get human-readable duration from start timestamp to now."""
    if not start_ts:
        return ""
    try:
        start = datetime.fromisoformat(start_ts.replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - start
        total_secs = int(delta.total_seconds())
        if total_secs < 0:
            return "0s"
        mins, secs = divmod(total_secs, 60)
        hours, mins = divmod(mins, 60)
        if hours > 0:
            return f"{hours}h{mins}m"
        elif mins > 0:
            return f"{mins}m{secs}s"
        else:
            return f"{secs}s"
    except (ValueError, OSError):
        return ""


def get_git_info(cwd: str) -> tuple[str, bool]:
    """Get git branch name and dirty status."""
    if not cwd:
        return "", False
    try:
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, cwd=cwd, timeout=2,
        )
        if branch.returncode != 0:
            return "", False
        branch_name = branch.stdout.strip()

        status = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, cwd=cwd, timeout=2,
        )
        dirty = bool(status.stdout.strip())
        return branch_name, dirty
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return "", False


def shorten_path(path: str, max_len: int = 40) -> str:
    """Shorten a file path for display."""
    if not path:
        return ""
    if len(path) <= max_len:
        return path
    parts = Path(path).parts
    if len(parts) <= 2:
        return path[-max_len:]
    return str(Path("..." , *parts[-2:]))


def category_icon(category: str) -> tuple[str, str]:
    """Return (icon, color) for a tool category."""
    icons = {
        "file_write":  ("", COLORS["green"]),
        "file_modify": ("", COLORS["yellow"]),
        "file_read":   ("", COLORS["blue"]),
        "file_search": ("", COLORS["cyan"]),
        "bash":        ("", COLORS["orange"]),
        "web":         ("󰖟", COLORS["magenta"]),
        "task":        ("󰜎", COLORS["cyan"]),
        "other":       ("", COLORS["dim"]),
    }
    return icons.get(category, icons["other"])


def tool_label(tool: str) -> str:
    """Short label for tool names."""
    labels = {
        "Write": "WRITE",
        "Edit": "EDIT",
        "Read": "READ",
        "Glob": "GLOB",
        "Grep": "GREP",
        "Bash": "BASH",
        "WebFetch": "FETCH",
        "WebSearch": "SEARCH",
        "Task": "AGENT",
    }
    return labels.get(tool, tool.upper()[:6])


def build_header(state: DashboardState) -> Panel:
    """Build the header panel with session info."""
    parts = []

    # Model
    model_display = state.model or "Claude"
    # Clean up model ID to display name
    if "opus" in model_display.lower():
        model_display = "Opus"
    elif "sonnet" in model_display.lower():
        model_display = "Sonnet"
    elif "haiku" in model_display.lower():
        model_display = "Haiku"

    parts.append(Text.assemble(
        ("󰧑 ", COLORS["cyan"]),
        (model_display, f"bold {COLORS['cyan']}"),
    ))

    # Duration
    dur = get_duration(state.session_start_time)
    if dur:
        parts.append(Text.assemble(
            ("  ", COLORS["dim"]),
            (dur, COLORS["fg"]),
        ))

    # Git info
    branch, dirty = get_git_info(state.cwd)
    if branch:
        dirty_marker = " *" if dirty else ""
        parts.append(Text.assemble(
            ("  ", COLORS["orange"]),
            (f"{branch}{dirty_marker}", COLORS["orange"]),
        ))

    # Working directory
    if state.cwd:
        short_cwd = shorten_path(state.cwd, 30)
        parts.append(Text.assemble(
            ("  ", COLORS["dim"]),
            (short_cwd, COLORS["dim"]),
        ))

    header_text = Text(" ")
    for i, part in enumerate(parts):
        if i > 0:
            header_text.append("  ")
        header_text.append_text(part)

    return Panel(
        header_text,
        title="[bold]CLAUDE CODE[/bold]",
        title_align="left",
        border_style=COLORS["border"],
        height=3,
    )


def build_file_panel(state: DashboardState) -> Panel:
    """Build the file activity panel."""
    table = Table(
        show_header=False,
        show_edge=False,
        box=None,
        padding=(0, 1),
        expand=True,
    )
    table.add_column("time", width=5, style=COLORS["dim"])
    table.add_column("icon", width=2)
    table.add_column("action", width=6)
    table.add_column("file", ratio=1)

    events = state.file_events[-MAX_FILE_ENTRIES:]
    for ev in reversed(events):
        icon, color = category_icon(ev["category"])
        fname = os.path.basename(ev["file_path"]) if ev["file_path"] else ""
        table.add_row(
            format_time(ev["timestamp"]),
            Text(icon, style=color),
            Text(tool_label(ev["tool"]), style=f"bold {color}"),
            Text(fname, style=COLORS["fg"]),
        )

    if not events:
        table.add_row("", "", "", Text("No file activity yet", style=COLORS["dim"]))

    return Panel(
        table,
        title="[bold]FILE ACTIVITY[/bold]",
        title_align="left",
        border_style=COLORS["border"],
    )


def build_tool_panel(state: DashboardState) -> Panel:
    """Build the tool activity panel."""
    table = Table(
        show_header=False,
        show_edge=False,
        box=None,
        padding=(0, 1),
        expand=True,
    )
    table.add_column("time", width=5, style=COLORS["dim"])
    table.add_column("icon", width=2)
    table.add_column("tool", width=6)
    table.add_column("detail", ratio=1)

    events = state.tool_events[-MAX_TOOL_ENTRIES:]
    for ev in reversed(events):
        icon, color = category_icon(ev["category"])
        detail = ev.get("detail", "")
        if len(detail) > 50:
            detail = detail[:47] + "..."
        table.add_row(
            format_time(ev["timestamp"]),
            Text(icon, style=color),
            Text(tool_label(ev["tool"]), style=f"bold {color}"),
            Text(detail, style=COLORS["fg"]),
        )

    if not events:
        table.add_row("", "", "", Text("No tool activity yet", style=COLORS["dim"]))

    return Panel(
        table,
        title="[bold]TOOL ACTIVITY[/bold]",
        title_align="left",
        border_style=COLORS["border"],
    )


def build_agents_panel(state: DashboardState) -> Panel:
    """Build the agents panel showing active and recent agents."""
    lines = []

    # Active agents
    if state.active_agents:
        for aid, info in state.active_agents.items():
            dur = get_duration(info["start_time"])
            lines.append(Text.assemble(
                ("● ", COLORS["green"]),
                (f"{info['type']}", f"bold {COLORS['cyan']}"),
                (f"  {dur}", COLORS["dim"]),
            ))
    else:
        lines.append(Text("No active agents", style=COLORS["dim"]))

    # Recently completed (last 5)
    if state.completed_agents:
        lines.append(Text(""))
        lines.append(Text("Recently completed:", style=COLORS["dim"]))
        for agent in state.completed_agents[-5:]:
            lines.append(Text.assemble(
                ("○ ", COLORS["dim"]),
                (f"{agent['type']}", COLORS["fg"]),
            ))

    content = Text("\n").join(lines) if lines else Text("No agents", style=COLORS["dim"])

    return Panel(
        content,
        title="[bold]AGENTS[/bold]",
        title_align="left",
        border_style=COLORS["border"],
    )


def build_stats_panel(state: DashboardState) -> Panel:
    """Build the stats panel."""
    lines = []

    # Tool usage breakdown
    total_tools = sum(state.tool_counts.values())
    lines.append(Text.assemble(
        ("Tool calls: ", COLORS["dim"]),
        (str(total_tools), f"bold {COLORS['cyan']}"),
    ))

    # Top tools
    if state.tool_counts:
        sorted_tools = sorted(state.tool_counts.items(), key=lambda x: x[1], reverse=True)
        for tool, count in sorted_tools[:5]:
            bar_len = min(int(count / max(total_tools, 1) * 15), 15)
            bar = "█" * bar_len + "░" * (15 - bar_len)
            lines.append(Text.assemble(
                (f"  {tool:<8} ", COLORS["fg"]),
                (bar, COLORS["cyan"]),
                (f" {count}", COLORS["dim"]),
            ))

    lines.append(Text(""))

    # Files touched
    lines.append(Text.assemble(
        ("Files touched: ", COLORS["dim"]),
        (str(len(state.files_touched)), f"bold {COLORS['green']}"),
    ))

    # Responses
    lines.append(Text.assemble(
        ("Responses: ", COLORS["dim"]),
        (str(state.stop_count), f"bold {COLORS['yellow']}"),
    ))

    # Errors
    error_count = len(state.errors)
    error_color = COLORS["red"] if error_count > 0 else COLORS["dim"]
    lines.append(Text.assemble(
        ("Errors: ", COLORS["dim"]),
        (str(error_count), f"bold {error_color}"),
    ))

    # Recent error detail
    if state.errors:
        last_err = state.errors[-1]
        err_text = last_err["error"][:60]
        lines.append(Text(f"  └ {err_text}", style=COLORS["red"]))

    content = Text("\n").join(lines)

    return Panel(
        content,
        title="[bold]STATS[/bold]",
        title_align="left",
        border_style=COLORS["border"],
    )


def build_layout(state: DashboardState) -> Layout:
    """Build the full dashboard layout."""
    layout = Layout()

    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="body"),
        Layout(name="bottom", size=3),
    )

    layout["body"].split_column(
        Layout(name="files", ratio=1),
        Layout(name="tools", ratio=1),
        Layout(name="lower", size=14),
    )

    layout["lower"].split_row(
        Layout(name="agents", ratio=1),
        Layout(name="stats", ratio=1),
    )

    layout["header"].update(build_header(state))
    layout["files"].update(build_file_panel(state))
    layout["tools"].update(build_tool_panel(state))
    layout["agents"].update(build_agents_panel(state))
    layout["stats"].update(build_stats_panel(state))

    # Footer
    now = datetime.now().strftime("%H:%M:%S")
    sid_short = (state.session_id or "")[:8]
    footer = Text.assemble(
        (" ", ""),
        ("Dashboard", f"bold {COLORS['dim']}"),
        (f"  │  {now}", COLORS["dim"]),
        (f"  │  Session: {sid_short}", COLORS["dim"]) if sid_short else ("", ""),
        (f"  │  Refresh: {REFRESH_INTERVAL}s", COLORS["dim"]),
    )
    layout["bottom"].update(Panel(footer, border_style=COLORS["border"], height=3))

    return layout


def main():
    console = Console()
    state = DashboardState()

    # Initial read of all existing events
    state.poll_events()

    console.clear()

    try:
        with Live(
            build_layout(state),
            console=console,
            screen=True,
            refresh_per_second=1,
        ) as live:
            while True:
                state.poll_events()
                live.update(build_layout(state))
                time.sleep(REFRESH_INTERVAL)
    except KeyboardInterrupt:
        console.clear()
        console.print(f"[{COLORS['dim']}]Dashboard stopped.[/]")


if __name__ == "__main__":
    main()
