#!/usr/bin/env python3
"""Claude Code Dashboard - Rich TUI for Ghostty split pane.

Reads events from ~/.claude/dashboard/events.jsonl and displays
real-time file activity, tool calls, agent status, and session stats.

Responsive layout:
  - Compact mode (< 50 cols): streamlined activity feed + stats bar
  - Standard mode (>= 50 cols): full panels with project file tree
"""

import argparse
import json
import os
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

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

# --- Paths ---
EVENTS_FILE = Path.home() / ".claude" / "dashboard" / "events.jsonl"
PROJECT_PATH_FILE = Path.home() / ".claude" / "dashboard" / ".project_path"

# --- Layout config ---
REFRESH_INTERVAL = 1.5
MAX_FILE_ENTRIES = 15
MAX_TOOL_ENTRIES = 15
COMPACT_THRESHOLD = 50  # columns — auto-compact below this

# --- File tree config ---
TREE_SCAN_INTERVAL = 5.0
TREE_MAX_DEPTH = 3
TREE_MAX_ENTRIES = 60
TREE_IGNORE = {
    ".git", "__pycache__", "node_modules", "venv", ".venv",
    ".mypy_cache", ".pytest_cache", ".tox", "dist", "build",
    ".eggs", ".egg-info", ".DS_Store", ".ruff_cache", ".cache",
    "target", ".next", ".nuxt", ".output", ".turbo",
    "coverage", ".coverage", "htmlcov", ".idea", ".vscode",
}

FILE_ICONS = {
    ".py": "\ue73c", ".js": "\ue74e", ".ts": "\ue628", ".tsx": "\ue7ba",
    ".jsx": "\ue7ba", ".json": "\ue60b", ".md": "\ue73e", ".sh": "\ue795",
    ".bash": "\ue795", ".zsh": "\ue795", ".fish": "\ue795",
    ".html": "\ue736", ".css": "\ue749", ".scss": "\ue749",
    ".yaml": "\ue60b", ".yml": "\ue60b", ".toml": "\ue60b",
    ".rs": "\ue7a8", ".go": "\ue626", ".rb": "\ue739", ".swift": "\ue755",
    ".java": "\ue738", ".c": "\ue61e", ".cpp": "\ue61d", ".h": "\ue61e",
    ".sql": "\ue706", ".xml": "\ue619", ".svg": "\ue60b",
    ".txt": "\uf0f6", ".lock": "\uf023", ".env": "\uf462",
    ".png": "\uf03e", ".jpg": "\uf03e", ".gif": "\uf03e",
    ".wasm": "\ue6a1", ".r": "\uf25d", ".lua": "\ue620",
}
FOLDER_ICON = "\uf07b"
DEFAULT_FILE_ICON = "\uf0f6"


# ============================================================
# File Tree Scanner
# ============================================================

class FileTree:
    """Scans and caches a project directory tree."""

    def __init__(self):
        self.entries = []  # [(depth, name, is_dir, full_path)]
        self.root = None
        self._last_scan = 0.0

    def update(self, root_path: str, force: bool = False):
        """Rescan if root changed or interval elapsed."""
        now = time.time()
        if not root_path:
            return
        if (not force
                and self.root == root_path
                and now - self._last_scan < TREE_SCAN_INTERVAL):
            return

        self.root = root_path
        self._last_scan = now
        self.entries = []
        self._scan(Path(root_path), 0)

    def _scan(self, path: Path, depth: int):
        if depth > TREE_MAX_DEPTH or len(self.entries) >= TREE_MAX_ENTRIES:
            return
        try:
            items = sorted(
                path.iterdir(),
                key=lambda p: (not p.is_dir(), p.name.lower()),
            )
        except (PermissionError, OSError):
            return

        for item in items:
            name = item.name
            if name in TREE_IGNORE or (name.startswith(".") and name != ".env"):
                continue
            if len(self.entries) >= TREE_MAX_ENTRIES:
                return

            is_dir = item.is_dir()
            self.entries.append((depth, name, is_dir, str(item)))

            if is_dir and depth < TREE_MAX_DEPTH:
                self._scan(item, depth + 1)


# ============================================================
# Dashboard State
# ============================================================

class DashboardState:
    """Tracks session state from parsed events."""

    def __init__(self):
        self.reset()
        self._file_pos = 0
        self._file_inode = None
        self.file_tree = FileTree()

    def reset(self):
        self.session_id = None
        self.model = ""
        self.cwd = ""
        self.session_start_time = None
        self.file_events = []
        self.tool_events = []
        self.active_agents = {}
        self.completed_agents = []
        self.errors = []
        self.stop_count = 0
        self.files_touched = set()
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
                "timestamp": ts, "tool": tool,
                "detail": detail, "category": category,
            })

            if file_path:
                self.files_touched.add(file_path)
                self.file_events.append({
                    "timestamp": ts, "tool": tool,
                    "file_path": file_path, "category": category,
                })

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

    def poll_events(self):
        """Incrementally read new lines from events.jsonl."""
        if not EVENTS_FILE.exists():
            return

        try:
            stat = EVENTS_FILE.stat()
        except OSError:
            return

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

    def get_project_root(self) -> str:
        """Get project root from .project_path file or session CWD."""
        if PROJECT_PATH_FILE.exists():
            try:
                p = PROJECT_PATH_FILE.read_text().strip()
                if p and Path(p).is_dir():
                    return p
            except OSError:
                pass
        return self.cwd

    def update_tree(self):
        root = self.get_project_root()
        if root:
            self.file_tree.update(root)


# ============================================================
# Helpers
# ============================================================

def format_time(ts_str: str) -> str:
    if not ts_str:
        return ""
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        local = dt.astimezone()
        return local.strftime("%H:%M")
    except (ValueError, OSError):
        return ts_str[:5] if len(ts_str) >= 5 else ts_str


def get_duration(start_ts: str) -> str:
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


def get_git_info(cwd: str) -> tuple:
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
    if not path:
        return ""
    if len(path) <= max_len:
        return path
    parts = Path(path).parts
    if len(parts) <= 2:
        return path[-max_len:]
    return str(Path("...", *parts[-2:]))


def category_icon(category: str) -> tuple:
    icons = {
        "file_write":  ("\uf044", COLORS["green"]),
        "file_modify": ("\uf044", COLORS["yellow"]),
        "file_read":   ("\uf06e", COLORS["blue"]),
        "file_search": ("\uf002", COLORS["cyan"]),
        "bash":        ("\ue795", COLORS["orange"]),
        "web":         ("\uf0ac", COLORS["magenta"]),
        "task":        ("\uf085", COLORS["cyan"]),
        "other":       ("\uf069", COLORS["dim"]),
    }
    return icons.get(category, icons["other"])


def tool_label(tool: str) -> str:
    labels = {
        "Write": "WRITE", "Edit": "EDIT", "Read": "READ",
        "Glob": "GLOB", "Grep": "GREP", "Bash": "BASH",
        "WebFetch": "FETCH", "WebSearch": "SEARCH", "Task": "AGENT",
    }
    return labels.get(tool, tool.upper()[:6])


def get_file_icon(name: str) -> str:
    if name.lower() == "dockerfile":
        return "\ue7b0"
    if name.lower() == "makefile":
        return "\ue779"
    ext = Path(name).suffix.lower()
    return FILE_ICONS.get(ext, DEFAULT_FILE_ICON)


# ============================================================
# Panel Builders — Standard Mode
# ============================================================

def build_header(state: DashboardState) -> Panel:
    parts = []

    model_display = state.model or "Claude"
    if "opus" in model_display.lower():
        model_display = "Opus"
    elif "sonnet" in model_display.lower():
        model_display = "Sonnet"
    elif "haiku" in model_display.lower():
        model_display = "Haiku"

    parts.append(Text.assemble(
        ("\uf10c ", COLORS["cyan"]),
        (model_display, f"bold {COLORS['cyan']}"),
    ))

    dur = get_duration(state.session_start_time)
    if dur:
        parts.append(Text.assemble(
            ("\uf017 ", COLORS["dim"]),
            (dur, COLORS["fg"]),
        ))

    branch, dirty = get_git_info(state.get_project_root())
    if branch:
        dirty_marker = " *" if dirty else ""
        parts.append(Text.assemble(
            ("\ue725 ", COLORS["orange"]),
            (f"{branch}{dirty_marker}", COLORS["orange"]),
        ))

    header_line = Text(" ")
    for i, part in enumerate(parts):
        if i > 0:
            header_line.append("  ")
        header_line.append_text(part)

    # Full project path on its own line
    root = state.get_project_root()
    if root:
        path_line = Text.assemble(
            (" \uf07b ", COLORS["dim"]),
            (root, f"bold {COLORS['dim']}"),
        )
        content = Text.assemble(header_line, "\n", path_line)
        h = 4
    else:
        content = header_line
        h = 3

    return Panel(
        content,
        title="[bold]CLAUDE CODE[/bold]",
        title_align="left",
        border_style=COLORS["border"],
        height=h,
    )


def build_tree_panel(state: DashboardState, max_lines: int = 12) -> Panel:
    entries = state.file_tree.entries
    touched = state.files_touched

    if not entries:
        root = state.get_project_root()
        if root:
            msg = Text(f"Scanning {Path(root).name}/...", style=COLORS["dim"])
        else:
            msg = Text("No project directory", style=COLORS["dim"])
        return Panel(
            msg,
            title="[bold]PROJECT[/bold]",
            title_align="left",
            border_style=COLORS["border"],
        )

    lines = []
    for depth, name, is_dir, full_path in entries[:max_lines]:
        indent = "  " * depth
        if is_dir:
            icon = FOLDER_ICON
            style = f"bold {COLORS['cyan']}"
            icon_style = COLORS["cyan"]
        else:
            icon = get_file_icon(name)
            if full_path in touched:
                style = f"bold {COLORS['green']}"
                icon_style = COLORS["green"]
            else:
                style = COLORS["fg"]
                icon_style = COLORS["dim"]

        line = Text()
        line.append(indent)
        line.append(f"{icon} ", style=icon_style)
        line.append(name, style=style)
        if full_path in touched:
            line.append(" \u25c0", style=COLORS["green"])
        lines.append(line)

    remaining = len(entries) - max_lines
    if remaining > 0:
        lines.append(Text(f"  ... +{remaining} more", style=COLORS["dim"]))

    content = Text("\n").join(lines)

    root_name = Path(state.file_tree.root).name if state.file_tree.root else "PROJECT"
    return Panel(
        content,
        title=f"[bold]{root_name.upper()}[/bold]",
        title_align="left",
        border_style=COLORS["border"],
    )


def build_file_panel(state: DashboardState) -> Panel:
    table = Table(
        show_header=False, show_edge=False,
        box=None, padding=(0, 1), expand=True,
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
    table = Table(
        show_header=False, show_edge=False,
        box=None, padding=(0, 1), expand=True,
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
    lines = []
    if state.active_agents:
        for aid, info in state.active_agents.items():
            dur = get_duration(info["start_time"])
            lines.append(Text.assemble(
                ("\u25cf ", COLORS["green"]),
                (f"{info['type']}", f"bold {COLORS['cyan']}"),
                (f"  {dur}", COLORS["dim"]),
            ))
    else:
        lines.append(Text("No active agents", style=COLORS["dim"]))

    if state.completed_agents:
        lines.append(Text(""))
        for agent in state.completed_agents[-3:]:
            lines.append(Text.assemble(
                ("\u25cb ", COLORS["dim"]),
                (f"{agent['type']}", COLORS["fg"]),
            ))

    content = Text("\n").join(lines)
    return Panel(
        content,
        title="[bold]AGENTS[/bold]",
        title_align="left",
        border_style=COLORS["border"],
    )


def build_stats_panel(state: DashboardState) -> Panel:
    lines = []

    total_tools = sum(state.tool_counts.values())
    lines.append(Text.assemble(
        ("Tool calls: ", COLORS["dim"]),
        (str(total_tools), f"bold {COLORS['cyan']}"),
    ))

    if state.tool_counts:
        sorted_tools = sorted(state.tool_counts.items(), key=lambda x: x[1], reverse=True)
        for tool, count in sorted_tools[:4]:
            bar_len = min(int(count / max(total_tools, 1) * 12), 12)
            bar = "\u2588" * bar_len + "\u2591" * (12 - bar_len)
            lines.append(Text.assemble(
                (f"  {tool:<8} ", COLORS["fg"]),
                (bar, COLORS["cyan"]),
                (f" {count}", COLORS["dim"]),
            ))

    lines.append(Text(""))
    lines.append(Text.assemble(
        ("Files touched: ", COLORS["dim"]),
        (str(len(state.files_touched)), f"bold {COLORS['green']}"),
    ))
    lines.append(Text.assemble(
        ("Responses: ", COLORS["dim"]),
        (str(state.stop_count), f"bold {COLORS['yellow']}"),
    ))

    error_count = len(state.errors)
    error_color = COLORS["red"] if error_count > 0 else COLORS["dim"]
    lines.append(Text.assemble(
        ("Errors: ", COLORS["dim"]),
        (str(error_count), f"bold {error_color}"),
    ))

    if state.errors:
        last_err = state.errors[-1]
        err_text = last_err["error"][:50]
        lines.append(Text(f"  \u2514 {err_text}", style=COLORS["red"]))

    content = Text("\n").join(lines)
    return Panel(
        content,
        title="[bold]STATS[/bold]",
        title_align="left",
        border_style=COLORS["border"],
    )


# ============================================================
# Panel Builders — Compact Mode
# ============================================================

def build_compact_header(state: DashboardState) -> Panel:
    model_display = state.model or "Claude"
    if "opus" in model_display.lower():
        model_display = "Opus"
    elif "sonnet" in model_display.lower():
        model_display = "Sonnet"
    elif "haiku" in model_display.lower():
        model_display = "Haiku"

    dur = get_duration(state.session_start_time)

    branch, dirty = get_git_info(state.get_project_root())
    branch_str = f" {branch}{'*' if dirty else ''}" if branch else ""

    header = Text.assemble(
        ("\uf10c ", COLORS["cyan"]),
        (model_display, f"bold {COLORS['cyan']}"),
        (" \u2502 ", COLORS["dim"]),
        (dur or "0s", COLORS["fg"]),
        (f" \u2502 {branch_str}", COLORS["orange"]) if branch_str else ("", ""),
    )

    return Panel(
        header,
        border_style=COLORS["border"],
        height=3,
    )


def build_compact_activity(state: DashboardState, max_items: int = 20) -> Panel:
    """Combined file + tool activity for compact mode."""
    table = Table(
        show_header=False, show_edge=False,
        box=None, padding=(0, 0), expand=True,
    )
    table.add_column("time", width=5, style=COLORS["dim"])
    table.add_column("act", width=6)
    table.add_column("detail", ratio=1)

    # Merge file and tool events, sort by timestamp, take most recent
    all_events = []
    for ev in state.file_events:
        fname = os.path.basename(ev["file_path"]) if ev.get("file_path") else ""
        all_events.append((ev["timestamp"], ev["tool"], ev["category"], fname))
    for ev in state.tool_events:
        if ev.get("category") not in ("file_write", "file_modify", "file_read", "file_search"):
            detail = ev.get("detail", "")
            if len(detail) > 30:
                detail = detail[:27] + "..."
            all_events.append((ev["timestamp"], ev["tool"], ev["category"], detail))

    # Deduplicate by timestamp+tool (file events may duplicate tool events)
    seen = set()
    unique = []
    for ts, tool, cat, detail in all_events:
        key = (ts, tool, detail)
        if key not in seen:
            seen.add(key)
            unique.append((ts, tool, cat, detail))

    unique.sort(key=lambda x: x[0])
    recent = unique[-max_items:]

    for ts, tool, cat, detail in reversed(recent):
        _, color = category_icon(cat)
        table.add_row(
            format_time(ts),
            Text(tool_label(tool), style=f"bold {color}"),
            Text(detail, style=COLORS["fg"]),
        )

    if not recent:
        table.add_row("", "", Text("Waiting for activity...", style=COLORS["dim"]))

    return Panel(
        table,
        title="[bold]ACTIVITY[/bold]",
        title_align="left",
        border_style=COLORS["border"],
    )


def build_compact_stats(state: DashboardState) -> Panel:
    total = sum(state.tool_counts.values())
    files = len(state.files_touched)
    errs = len(state.errors)

    agents_active = len(state.active_agents)
    agent_str = f" \u2502 \u25cf {agents_active} agents" if agents_active > 0 else ""

    stats = Text.assemble(
        (f" {total} calls", COLORS["cyan"]),
        (" \u2502 ", COLORS["dim"]),
        (f"{files} files", COLORS["green"]),
        (" \u2502 ", COLORS["dim"]),
        (f"{errs} err", COLORS["red"] if errs > 0 else COLORS["dim"]),
        (agent_str, COLORS["green"]) if agent_str else ("", ""),
    )

    return Panel(
        stats,
        border_style=COLORS["border"],
        height=3,
    )


# ============================================================
# Layout Builders
# ============================================================

def build_standard_layout(state: DashboardState, height: int) -> Layout:
    layout = Layout()

    has_tree = bool(state.file_tree.entries)
    header_h = 4 if state.get_project_root() else 3

    # Decide how much space for file tree based on terminal height
    if has_tree and height >= 35:
        tree_lines = min(len(state.file_tree.entries) + 2, 14)
        layout.split_column(
            Layout(name="header", size=header_h),
            Layout(name="tree", size=tree_lines),
            Layout(name="files", ratio=1),
            Layout(name="tools", ratio=1),
            Layout(name="lower", size=10),
            Layout(name="footer", size=3),
        )
        layout["tree"].update(build_tree_panel(state, max_lines=tree_lines - 2))
    elif has_tree and height >= 28:
        # Shorter terminal: smaller tree
        layout.split_column(
            Layout(name="header", size=header_h),
            Layout(name="tree", size=8),
            Layout(name="files", ratio=1),
            Layout(name="tools", ratio=1),
            Layout(name="lower", size=10),
            Layout(name="footer", size=3),
        )
        layout["tree"].update(build_tree_panel(state, max_lines=6))
    else:
        # No tree — too short or no project
        layout.split_column(
            Layout(name="header", size=header_h),
            Layout(name="files", ratio=1),
            Layout(name="tools", ratio=1),
            Layout(name="lower", size=12),
            Layout(name="footer", size=3),
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
        (f"  \u2502  {now}", COLORS["dim"]),
        (f"  \u2502  {sid_short}", COLORS["dim"]) if sid_short else ("", ""),
        (f"  \u2502  Refresh: {REFRESH_INTERVAL}s", COLORS["dim"]),
    )
    layout["footer"].update(Panel(footer, border_style=COLORS["border"], height=3))

    return layout


def build_compact_layout(state: DashboardState, height: int) -> Layout:
    layout = Layout()

    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="activity"),
        Layout(name="stats", size=3),
    )

    layout["header"].update(build_compact_header(state))
    layout["activity"].update(build_compact_activity(state, max_items=height - 8))
    layout["stats"].update(build_compact_stats(state))

    return layout


def build_layout(state: DashboardState, width: int, height: int,
                 force_compact: bool = False) -> Layout:
    if force_compact or width < COMPACT_THRESHOLD:
        return build_compact_layout(state, height)
    return build_standard_layout(state, height)


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Claude Code Dashboard")
    parser.add_argument("--project", "-p",
                        help="Project directory to monitor")
    parser.add_argument("--compact", "-c", action="store_true",
                        help="Force compact mode regardless of terminal width")
    args = parser.parse_args()

    console = Console()
    state = DashboardState()

    if args.project:
        project = str(Path(args.project).resolve())
        if Path(project).is_dir():
            PROJECT_PATH_FILE.write_text(project)

    # Initial read
    state.poll_events()
    state.update_tree()

    console.clear()

    try:
        with Live(
            build_layout(state, *console.size, force_compact=args.compact),
            console=console,
            screen=True,
            refresh_per_second=1,
        ) as live:
            while True:
                state.poll_events()
                state.update_tree()
                w, h = console.size
                live.update(build_layout(state, w, h, force_compact=args.compact))
                time.sleep(REFRESH_INTERVAL)
    except KeyboardInterrupt:
        console.clear()
        console.print(f"[{COLORS['dim']}]Dashboard stopped.[/]")


if __name__ == "__main__":
    main()
