#!/usr/bin/env python3
"""Claude Code Dashboard - Rich TUI for Ghostty split pane.

Reads events from ~/.claude/dashboard/events.jsonl and displays
real-time file mutations, live preview, continuity file status.

Responsive layout (panels appear as height allows):
  - Always: header + changed + activity + footer
  - Height >= 25: + preview
  - Height >= 35: + continuity
  - Height >= 50: + file tree
  - Width < 50: compact mode
"""

import argparse
import json
import os
import subprocess
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

try:
    from rich.syntax import Syntax
    _HAS_SYNTAX = True
except ImportError:
    _HAS_SYNTAX = False

# --- Citruszest-inspired color palette ---
COLORS = {
    "bg": "#1a1a2e", "fg": "#e0e0e0", "cyan": "#00d4ff",
    "green": "#a6e22e", "yellow": "#e6db74", "orange": "#fd971f",
    "red": "#f92672", "magenta": "#ae81ff", "dim": "#75715e",
    "blue": "#66d9ef", "border": "#3a3a5c",
}

# --- Paths ---
EVENTS_FILE = Path.home() / ".claude" / "dashboard" / "events.jsonl"
PROJECT_PATH_FILE = Path.home() / ".claude" / "dashboard" / ".project_path"

# --- Config ---
REFRESH_INTERVAL = 1.5
MAX_ACTIVITY_ENTRIES = 12
COMPACT_THRESHOLD = 50
PREVIEW_MAX_LINES = 10
CONTINUITY_SCAN_INTERVAL = 10.0
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

LEXER_MAP = {
    ".py": "python", ".js": "javascript", ".ts": "typescript",
    ".tsx": "typescript", ".jsx": "javascript",
    ".md": "markdown", ".json": "json", ".sh": "bash",
    ".yaml": "yaml", ".yml": "yaml", ".toml": "toml",
    ".html": "html", ".css": "css", ".rs": "rust", ".go": "go",
    ".rb": "ruby", ".java": "java", ".c": "c", ".cpp": "cpp",
    ".sql": "sql", ".lua": "lua",
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
    def __init__(self):
        self.entries = []
        self.root = None
        self._last_scan = 0.0

    def update(self, root_path: str, force: bool = False):
        now = time.time()
        if not root_path:
            return
        if (not force and self.root == root_path
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
            items = sorted(path.iterdir(),
                           key=lambda p: (not p.is_dir(), p.name.lower()))
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
    def __init__(self, project_root=""):
        self._project_override = project_root
        self._project_sessions = set()
        self.reset()
        self._file_pos = 0
        self._file_inode = None
        self.file_tree = FileTree()

    def reset(self):
        self.sessions = {}          # sid → {model, cwd, start_time}
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
        self.files_changed = {}
        self._preview_path = ""
        self._preview_mtime = 0.0
        self._preview_content = ""
        self._continuity_files = []
        self._continuity_last_scan = 0.0

    def _event_matches_project(self, event: dict) -> bool:
        """Check if event belongs to this dashboard's project.

        Strategy: match by file_path first (most accurate), then by
        session association.  Once a session touches a file under our
        project root, all its events are accepted.
        """
        if not self._project_override:
            return True
        root = self._project_override
        sid = event.get("session_id", "")

        # File path is the strongest signal
        fp = event.get("file_path", "")
        if fp and (fp.startswith(root + "/") or fp == root):
            self._project_sessions.add(sid)
            return True

        # Accept all events from sessions already associated with this project
        if sid in self._project_sessions:
            return True

        # session_start: accept if cwd matches (lets us pick up the session early)
        cwd = event.get("cwd", "")
        if cwd and (cwd == root or cwd.startswith(root + "/")):
            self._project_sessions.add(sid)
            return True

        return False

    def process_event(self, event: dict):
        ts = event.get("timestamp", "")
        etype = event.get("event", "")
        event_sid = event.get("session_id", "")

        if etype == "session_start":
            self.sessions[event_sid] = {
                "model": event.get("model", ""),
                "cwd": event.get("cwd", ""),
                "start_time": ts,
            }
            if not self._event_matches_project(event):
                return
            model = event.get("model", "")
            cwd = event.get("cwd", "")
            if model:
                self.model = model
            if cwd:
                self.cwd = cwd
            if not self.session_start_time:
                self.session_start_time = ts
            return

        if not self._event_matches_project(event):
            return

        if not self.session_start_time:
            self.session_start_time = ts

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
                if category in ("file_write", "file_modify"):
                    existing = self.files_changed.get(file_path)
                    if not existing or existing["category"] != "file_write":
                        self.files_changed[file_path] = {
                            "tool": tool, "timestamp": ts,
                            "category": category,
                        }

            if len(self.tool_events) > MAX_ACTIVITY_ENTRIES * 3:
                self.tool_events = self.tool_events[-MAX_ACTIVITY_ENTRIES * 2:]
            if len(self.file_events) > MAX_ACTIVITY_ENTRIES * 3:
                self.file_events = self.file_events[-MAX_ACTIVITY_ENTRIES * 2:]

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
                        self.process_event(json.loads(line))
                    except json.JSONDecodeError:
                        continue
                self._file_pos = f.tell()
        except OSError:
            pass

    def get_project_root(self) -> str:
        if self._project_override:
            return self._project_override
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

    def get_preview(self):
        """Get cached preview of most recently changed file."""
        if not self.files_changed:
            return None
        latest_path = max(self.files_changed,
                          key=lambda p: self.files_changed[p]["timestamp"])
        info = self.files_changed[latest_path]
        try:
            mtime = os.path.getmtime(latest_path)
        except OSError:
            return None
        if latest_path != self._preview_path or mtime != self._preview_mtime:
            try:
                with open(latest_path, "r", errors="replace") as f:
                    self._preview_content = f.read(4096)
            except OSError:
                self._preview_content = "(unable to read)"
            self._preview_path = latest_path
            self._preview_mtime = mtime
        name = os.path.basename(latest_path)
        ext = Path(name).suffix.lower()
        return (name, self._preview_content, LEXER_MAP.get(ext, ""),
                info["timestamp"], info["category"])

    def scan_continuity(self):
        """Scan for key .md continuity files (cached)."""
        now = time.time()
        if now - self._continuity_last_scan < CONTINUITY_SCAN_INTERVAL:
            return self._continuity_files
        self._continuity_last_scan = now
        files = []
        root = self.get_project_root()
        if root:
            claude_md = Path(root) / "CLAUDE.md"
            if claude_md.exists():
                files.append(self._cont_entry(claude_md, "project"))
        if root:
            key = root.replace("/", "-")
            mem_dir = Path.home() / ".claude" / "projects" / key / "memory"
            if mem_dir.exists() and mem_dir.is_dir():
                for f in sorted(mem_dir.iterdir()):
                    if f.suffix == ".md" and f.is_file():
                        files.append(self._cont_entry(f, "memory"))
        known = {f["path"] for f in files}
        for path in self.files_changed:
            if path.endswith(".md") and path not in known:
                p = Path(path)
                if p.exists():
                    files.append(self._cont_entry(p, "session"))
        self._continuity_files = files
        return files

    @staticmethod
    def _cont_entry(path: Path, category: str) -> dict:
        try:
            stat = path.stat()
            with open(path, "r", errors="replace") as f:
                lines = sum(1 for _ in f)
            return {"path": str(path), "name": path.name,
                    "lines": lines, "age_secs": time.time() - stat.st_mtime,
                    "stale": (time.time() - stat.st_mtime) > 86400,
                    "category": category}
        except OSError:
            return {"path": str(path), "name": path.name,
                    "lines": 0, "age_secs": 0, "stale": True,
                    "category": category}


# ============================================================
# Helpers
# ============================================================

def relative_time(secs: float) -> str:
    s = int(secs)
    if s < 5: return "just now"
    if s < 60: return f"{s}s ago"
    m = s // 60
    if m < 60: return f"{m}m ago"
    h = m // 60
    if h < 24: return f"{h}h ago"
    return f"{h // 24}d ago"


def relative_time_ts(ts_str: str) -> str:
    if not ts_str:
        return ""
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        return relative_time((datetime.now(timezone.utc) - dt).total_seconds())
    except (ValueError, OSError):
        return ""


def get_duration(start_ts: str) -> str:
    if not start_ts:
        return ""
    try:
        start = datetime.fromisoformat(start_ts.replace("Z", "+00:00"))
        total = int((datetime.now(timezone.utc) - start).total_seconds())
        if total < 0: return "0s"
        m, s = divmod(total, 60)
        h, m = divmod(m, 60)
        if h: return f"{h}h{m}m"
        if m: return f"{m}m{s}s"
        return f"{s}s"
    except (ValueError, OSError):
        return ""


def get_git_info(cwd: str) -> tuple:
    if not cwd:
        return "", False
    try:
        b = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                           capture_output=True, text=True, cwd=cwd, timeout=2)
        if b.returncode != 0: return "", False
        s = subprocess.run(["git", "status", "--porcelain"],
                           capture_output=True, text=True, cwd=cwd, timeout=2)
        return b.stdout.strip(), bool(s.stdout.strip())
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return "", False


def tool_label(tool: str) -> str:
    return {"Write": "WRITE", "Edit": "EDIT", "Read": "READ",
            "Glob": "GLOB", "Grep": "GREP", "Bash": "BASH",
            "WebFetch": "FETCH", "WebSearch": "SEARCH",
            "Task": "AGENT"}.get(tool, tool.upper()[:6])


def get_file_icon(name: str) -> str:
    low = name.lower()
    if low == "dockerfile": return "\ue7b0"
    if low == "makefile": return "\ue779"
    return FILE_ICONS.get(Path(name).suffix.lower(), DEFAULT_FILE_ICON)


# ============================================================
# Panel Builders
# ============================================================

def build_header(state: DashboardState) -> Panel:
    parts = []
    model = state.model or "Claude"
    for k, v in [("opus", "Opus"), ("sonnet", "Sonnet"), ("haiku", "Haiku")]:
        if k in model.lower():
            model = v
            break
    parts.append(Text.assemble(
        ("\uf10c ", COLORS["cyan"]),
        (model, f"bold {COLORS['cyan']}")))
    dur = get_duration(state.session_start_time)
    if dur:
        parts.append(Text.assemble(
            ("\uf017 ", COLORS["dim"]), (dur, COLORS["fg"])))
    branch, dirty = get_git_info(state.get_project_root())
    if branch:
        parts.append(Text.assemble(
            ("\ue725 ", COLORS["orange"]),
            (f"{branch}{' *' if dirty else ''}", COLORS["orange"])))

    header_line = Text(" ")
    for i, p in enumerate(parts):
        if i > 0: header_line.append("  ")
        header_line.append_text(p)

    root = state.get_project_root()
    if root:
        path_line = Text.assemble(
            (" \uf07b ", COLORS["dim"]),
            (root, f"bold {COLORS['dim']}"))
        return Panel(Text.assemble(header_line, "\n", path_line),
                     title="[bold]CLAUDE CODE[/bold]", title_align="left",
                     border_style=COLORS["border"], height=4)
    return Panel(header_line, title="[bold]CLAUDE CODE[/bold]",
                 title_align="left", border_style=COLORS["border"], height=3)


def build_tree_panel(state: DashboardState, max_lines: int = 12) -> Panel:
    entries = state.file_tree.entries
    touched = state.files_touched
    if not entries:
        root = state.get_project_root()
        msg = Text(f"Scanning {Path(root).name}/..." if root else "No project",
                   style=COLORS["dim"])
        return Panel(msg, title="[bold]PROJECT[/bold]",
                     title_align="left", border_style=COLORS["border"])

    lines = []
    for depth, name, is_dir, full_path in entries[:max_lines]:
        indent = "  " * depth
        if is_dir:
            icon, style, ic = FOLDER_ICON, f"bold {COLORS['cyan']}", COLORS["cyan"]
        elif full_path in touched:
            icon = get_file_icon(name)
            style, ic = f"bold {COLORS['green']}", COLORS["green"]
        else:
            icon, style, ic = get_file_icon(name), COLORS["fg"], COLORS["dim"]
        line = Text()
        line.append(indent)
        line.append(f"{icon} ", style=ic)
        line.append(name, style=style)
        if full_path in touched:
            line.append(" \u25c0", style=COLORS["green"])
        lines.append(line)

    rem = len(entries) - max_lines
    if rem > 0:
        lines.append(Text(f"  ... +{rem} more", style=COLORS["dim"]))

    root_name = Path(state.file_tree.root).name if state.file_tree.root else "PROJECT"
    return Panel(Text("\n").join(lines),
                 title=f"[bold]{root_name.upper()}[/bold]",
                 title_align="left", border_style=COLORS["border"])


def build_changed_panel(state: DashboardState) -> Panel:
    changed = state.files_changed
    if not changed:
        return Panel(Text(" No files changed yet", style=COLORS["dim"]),
                     title="[bold]CHANGED[/bold]",
                     title_align="left", border_style=COLORS["border"])
    lines = []
    for path, info in changed.items():
        cat = info["category"]
        name = os.path.basename(path)
        icon = get_file_icon(name)
        if cat == "file_write":
            mk, ms, ns = " + ", f"bold {COLORS['green']}", COLORS["green"]
        else:
            mk, ms, ns = " ~ ", f"bold {COLORS['yellow']}", COLORS["yellow"]
        line = Text()
        line.append(mk, style=ms)
        line.append(f"{icon} ", style=COLORS["dim"])
        line.append(name, style=ns)
        lines.append(line)
    return Panel(Text("\n").join(lines),
                 title=f"[bold]CHANGED ({len(changed)})[/bold]",
                 title_align="left", border_style=COLORS["border"])


def build_preview_panel(state: DashboardState) -> Panel:
    preview = state.get_preview()
    if not preview:
        return Panel(Text("  Waiting for changes...", style=COLORS["dim"]),
                     title="[bold]PREVIEW[/bold]",
                     title_align="left", border_style=COLORS["border"])

    name, raw, lexer, timestamp, category = preview
    icon = get_file_icon(name)
    rel = relative_time_ts(timestamp)
    mk = "+" if category == "file_write" else "~"
    mc = COLORS["green"] if category == "file_write" else COLORS["yellow"]

    content_lines = raw.split("\n")[:PREVIEW_MAX_LINES]
    truncated = "\n".join(content_lines)

    if _HAS_SYNTAX and lexer:
        try:
            widget = Syntax(truncated, lexer, theme="monokai",
                            line_numbers=True, word_wrap=False)
        except Exception:
            widget = _plain_preview(content_lines)
    else:
        widget = _plain_preview(content_lines)

    title = f"[bold {mc}] {mk} [/] {icon} [bold]{name}[/]  [{COLORS['dim']}]{rel}[/]"
    return Panel(widget, title=title, title_align="left",
                 border_style=COLORS["border"])


def _plain_preview(lines: list) -> Text:
    text = Text()
    for i, line in enumerate(lines, 1):
        text.append(f" {i:3} ", style=COLORS["dim"])
        text.append(f"{line}\n", style=COLORS["fg"])
    return text


def build_continuity_panel(state: DashboardState) -> Panel:
    files = state.scan_continuity()
    if not files:
        return Panel(Text(" No continuity files found", style=COLORS["dim"]),
                     title="[bold]CONTINUITY[/bold]",
                     title_align="left", border_style=COLORS["border"])
    lines = []
    for f in files:
        stale = f["stale"]
        dot = "\u25cb" if stale else "\u25cf"
        dc = COLORS["orange"] if stale else COLORS["green"]
        nc = COLORS["orange"] if stale else COLORS["fg"]
        rel = relative_time(f["age_secs"])
        line = Text()
        line.append(f" {dot} ", style=dc)
        line.append("\ue73e ", style=COLORS["dim"])
        line.append(f"{f['name']:<16}", style=nc)
        line.append(f" {rel:<10}", style=COLORS["dim"])
        line.append(f" {f['lines']}L", style=COLORS["dim"])
        lines.append(line)
    return Panel(Text("\n").join(lines),
                 title=f"[bold]CONTINUITY ({len(files)})[/bold]",
                 title_align="left", border_style=COLORS["border"])


def build_activity_panel(state: DashboardState) -> Panel:
    table = Table(show_header=False, show_edge=False,
                  box=None, padding=(0, 1), expand=True)
    table.add_column("m", width=1)
    table.add_column("act", width=6)
    table.add_column("file", ratio=1)
    recent = state.file_events[-MAX_ACTIVITY_ENTRIES:]
    for ev in reversed(recent):
        cat = ev["category"]
        fname = os.path.basename(ev["file_path"]) if ev["file_path"] else ""
        if cat == "file_write":
            m, ls, ns = Text("+", style=f"bold {COLORS['green']}"), \
                f"bold {COLORS['green']}", COLORS["fg"]
        elif cat == "file_modify":
            m, ls, ns = Text(" "), f"bold {COLORS['yellow']}", COLORS["fg"]
        else:
            m, ls, ns = Text(" "), COLORS["dim"], COLORS["dim"]
        table.add_row(m, Text(tool_label(ev["tool"]), style=ls),
                      Text(fname, style=ns))
    if not recent:
        table.add_row("", "", Text("No file activity yet", style=COLORS["dim"]))
    return Panel(table, title="[bold]ACTIVITY[/bold]",
                 title_align="left", border_style=COLORS["border"])


def build_footer(state: DashboardState) -> Panel:
    changed = len(state.files_changed)
    errs = len(state.errors)
    ec = COLORS["red"] if errs > 0 else COLORS["dim"]
    parts = Text(" ")
    parts.append(f"{changed} changed", style=COLORS["green"])
    parts.append(" \u00b7 ", style=COLORS["dim"])
    parts.append(f"{errs} err", style=ec)
    aa = len(state.active_agents)
    if aa > 0:
        parts.append(" \u00b7 ", style=COLORS["dim"])
        parts.append(f"\u25cf {aa} agent{'s' if aa != 1 else ''}",
                     style=COLORS["cyan"])
    return Panel(parts, border_style=COLORS["border"], height=3)


# ============================================================
# Compact Mode
# ============================================================

def build_compact_header(state: DashboardState) -> Panel:
    model = state.model or "Claude"
    for k, v in [("opus", "Opus"), ("sonnet", "Sonnet"), ("haiku", "Haiku")]:
        if k in model.lower():
            model = v
            break
    dur = get_duration(state.session_start_time)
    branch, dirty = get_git_info(state.get_project_root())
    bs = f" {branch}{'*' if dirty else ''}" if branch else ""
    header = Text.assemble(
        ("\uf10c ", COLORS["cyan"]),
        (model, f"bold {COLORS['cyan']}"),
        (" \u2502 ", COLORS["dim"]),
        (dur or "0s", COLORS["fg"]),
        (f" \u2502 {bs}", COLORS["orange"]) if bs else ("", ""))
    return Panel(header, border_style=COLORS["border"], height=3)


def build_compact_activity(state: DashboardState, max_items: int = 20) -> Panel:
    table = Table(show_header=False, show_edge=False,
                  box=None, padding=(0, 0), expand=True)
    table.add_column("m", width=1)
    table.add_column("act", width=6)
    table.add_column("f", ratio=1)
    recent = state.file_events[-max_items:]
    for ev in reversed(recent):
        cat = ev["category"]
        fname = os.path.basename(ev["file_path"]) if ev.get("file_path") else ""
        if cat == "file_write":
            m, ls, ds = Text("+", style=f"bold {COLORS['green']}"), \
                f"bold {COLORS['green']}", COLORS["fg"]
        elif cat == "file_modify":
            m, ls, ds = Text(" "), f"bold {COLORS['yellow']}", COLORS["fg"]
        else:
            m, ls, ds = Text(" "), COLORS["dim"], COLORS["dim"]
        table.add_row(m, Text(tool_label(ev["tool"]), style=ls),
                      Text(fname, style=ds))
    if not recent:
        table.add_row("", "", Text("Waiting...", style=COLORS["dim"]))
    return Panel(table, title="[bold]ACTIVITY[/bold]",
                 title_align="left", border_style=COLORS["border"])


# ============================================================
# Layout Builders
# ============================================================

def build_waiting_panel() -> Panel:
    lines = [
        Text(""),
        Text.assemble(("  \uf10c ", COLORS["cyan"]),
                       ("Watching for Claude Code activity...", COLORS["dim"])),
        Text(""),
        Text("  As Claude works, you'll see:", style=COLORS["dim"]),
        Text(""),
        Text.assemble(("  + ", f"bold {COLORS['green']}"),
                       ("New files created", COLORS["fg"])),
        Text.assemble(("  ~ ", f"bold {COLORS['yellow']}"),
                       ("Files edited", COLORS["fg"])),
        Text.assemble(("  \uf06e ", COLORS["blue"]),
                       ("Live preview of changes", COLORS["fg"])),
        Text.assemble(("  \ue73e ", COLORS["dim"]),
                       ("Continuity file tracking", COLORS["fg"])),
    ]
    return Panel(Text("\n").join(lines), border_style=COLORS["border"])


def build_standard_layout(state: DashboardState, height: int) -> Layout:
    layout = Layout()
    has_tree = bool(state.file_tree.entries)
    has_activity = bool(state.file_events or state.files_changed)
    header_h = 4 if state.get_project_root() else 3

    if not has_activity:
        if has_tree:
            tl = min(len(state.file_tree.entries) + 2, 14)
            layout.split_column(
                Layout(name="header", size=header_h),
                Layout(name="tree", size=tl),
                Layout(name="waiting"),
                Layout(name="footer", size=3))
            layout["tree"].update(build_tree_panel(state, max_lines=tl - 2))
        else:
            layout.split_column(
                Layout(name="header", size=header_h),
                Layout(name="waiting"),
                Layout(name="footer", size=3))
        layout["header"].update(build_header(state))
        layout["waiting"].update(build_waiting_panel())
        layout["footer"].update(build_footer(state))
        return layout

    # Responsive panel selection based on height
    ch_count = len(state.files_changed)
    ch_h = min(max(ch_count + 2, 3), 10)
    cont_files = state.scan_continuity()
    cont_h = min(max(len(cont_files) + 2, 3), 8)
    prev_h = min(PREVIEW_MAX_LINES + 2, 12)

    show_tree = has_tree and height >= 50
    show_preview = height >= 25
    show_cont = height >= 35

    parts = [("header", header_h)]
    if show_tree:
        tl = min(len(state.file_tree.entries) + 2, 10)
        parts.append(("tree", tl))
    parts.append(("changed", ch_h))
    if show_preview:
        parts.append(("preview", prev_h))
    if show_cont:
        parts.append(("continuity", cont_h))
    parts.append(("activity", None))
    parts.append(("footer", 3))

    layout.split_column(*[
        Layout(name=n, ratio=1) if s is None else Layout(name=n, size=s)
        for n, s in parts
    ])

    layout["header"].update(build_header(state))
    if show_tree:
        layout["tree"].update(build_tree_panel(state, max_lines=tl - 2))
    layout["changed"].update(build_changed_panel(state))
    if show_preview:
        layout["preview"].update(build_preview_panel(state))
    if show_cont:
        layout["continuity"].update(build_continuity_panel(state))
    layout["activity"].update(build_activity_panel(state))
    layout["footer"].update(build_footer(state))
    return layout


def build_compact_layout(state: DashboardState, height: int) -> Layout:
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="activity"),
        Layout(name="footer", size=3))
    layout["header"].update(build_compact_header(state))
    layout["activity"].update(build_compact_activity(state, max_items=height - 8))
    layout["footer"].update(build_footer(state))
    return layout


def build_layout(state, width, height, force_compact=False):
    if force_compact or width < COMPACT_THRESHOLD:
        return build_compact_layout(state, height)
    return build_standard_layout(state, height)


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Claude Code Dashboard")
    parser.add_argument("--project", "-p", help="Project directory to monitor")
    parser.add_argument("--compact", "-c", action="store_true",
                        help="Force compact mode")
    args = parser.parse_args()

    console = Console()

    project_root = ""
    if args.project:
        p = Path(args.project).resolve()
        if p.is_dir():
            project_root = str(p)
    state = DashboardState(project_root=project_root)

    state.poll_events()
    state.update_tree()
    console.clear()

    try:
        with Live(build_layout(state, *console.size, force_compact=args.compact),
                  console=console, screen=True, refresh_per_second=1) as live:
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
