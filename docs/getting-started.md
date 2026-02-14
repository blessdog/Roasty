# Getting Started with Roasty

A complete guide from zero to building your first app — with a real-time dashboard showing everything the AI is doing.

## What is Roasty?

Roasty turns your terminal into a lightweight IDE. Think VS Code's file explorer and activity panel, but running in a fast terminal with zero bloat. You talk to Claude Code on one side, and Roasty shows you what it's building on the other.

```
┌─────────────────────────┬────────────────────────┐
│  Claude Code            │  Roasty Dashboard      │
│                         │                        │
│  You talk to Claude     │  PROJECT               │
│  here. Ask it to build  │   src/                 │
│  things, fix bugs,      │    main.py ◀          │
│  refactor code.         │    utils.py            │
│                         │  FILE ACTIVITY          │
│  It has full access     │   EDIT  main.py        │
│  to your project —      │   WRITE utils.py       │
│  reads, writes, runs    │  TOOL ACTIVITY          │
│  commands, searches.    │   BASH  pip install    │
│                         │   GREP  import.*       │
│                         │  AGENTS │ STATS         │
│  [═══ status line ═══]  │  ● Explore │ 42 calls  │
└─────────────────────────┴────────────────────────┘
```

---

## Part 1: Setup (5 minutes)

### Prerequisites

You need a Mac and three things installed:

| What | How to get it |
|------|---------------|
| **Homebrew** | `/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"` |
| **Node.js** | `brew install node` |
| **Claude Pro or Max** | Sign up at [claude.ai](https://claude.ai) |

### Install everything

Open **Terminal** (or any terminal app) and run these commands:

```bash
# 1. Install Claude Code (the AI coding assistant)
npm install -g @anthropic-ai/claude-code

# 2. Install Ghostty (a fast, modern terminal)
brew install --cask ghostty

# 3. Install the icon font (makes the dashboard look great)
brew install --cask font-jetbrains-mono-nerd-font

# 4. Install Roasty
brew install blessdog/tap/roasty
roasty setup
roasty ghostty
```

> **No Homebrew?** Use the one-liner instead:
> ```bash
> curl -sL https://raw.githubusercontent.com/blessdog/Roasty/main/install.sh | bash
> ```

### Verify it works

```bash
roasty status
```

You should see all green checkmarks. If anything's missing, `roasty setup` will fix it.

Now **quit your terminal** and **open Ghostty** instead. Ghostty is where the magic happens — it supports split panes that let the dashboard live alongside Claude.

---

## Part 2: Your First Session (2 minutes)

### Open a project

```bash
# Create a new project (or use an existing one)
mkdir -p ~/Projects/my-first-app

# Launch Claude Code in that project
roasty open ~/Projects/my-first-app
```

This does two things:
1. Tells the dashboard which project to show in the file tree
2. Starts Claude Code inside that directory

### Open the dashboard

Now split your terminal and launch the dashboard:

```
Cmd+D          Split the window (dashboard goes on the right)
roasty         Start the dashboard
Cmd+H          Go back to Claude on the left
```

That's it — you're set up. Claude on the left, dashboard on the right.

### Resize the panes

The dashboard doesn't need to be huge. Shrink it to save space:

| Shortcut | What it does |
|----------|-------------|
| `Ctrl+Cmd+Left` | Shrink the right pane (dashboard smaller) |
| `Ctrl+Cmd+Right` | Grow the right pane (dashboard bigger) |
| `Ctrl+Cmd+=` | Make both panes equal |
| `Cmd+Shift+F` | Fullscreen the focused pane (toggle) |

The dashboard automatically switches to **compact mode** when the pane gets narrow, showing a streamlined activity feed.

---

## Part 3: Build Something

### Talk to Claude

In the Claude Code pane (left side), just describe what you want to build. Be specific or vague — Claude adapts:

**Simple start:**
```
Create a Python web app with Flask that has a homepage saying "Hello World"
```

**Ambitious:**
```
Build me a full-stack iOS app with SwiftUI and a Python FastAPI backend.
It should be a task manager where I can add tasks with titles and due dates,
mark them complete, and see a list. Use CoreData for local storage and sync
with the API. Set up both the Xcode project and the backend server.
```

**Iterating on existing code:**
```
Look at the code in this project and add user authentication with JWT tokens
```

Once you send a message, **watch the dashboard** — it lights up in real time.

---

## Part 4: Understanding the Dashboard

### The Header

```
┌─ CLAUDE CODE ─────────────────────────┐
│ ○ Opus  ⏱ 12m  🔀 main *  📁 ~/proj  │
└───────────────────────────────────────┘
```

| Item | Meaning |
|------|---------|
| **Model** | Which Claude model is running (Opus, Sonnet, Haiku) |
| **Timer** | How long this session has been going |
| **Branch** | Your git branch — `*` means you have uncommitted changes |
| **Path** | The project directory Claude is working in |

---

### File Activity

```
┌─ FILE ACTIVITY ───────────────────────┐
│ 17:42   EDIT   main.py               │
│ 17:41   WRITE  utils.py              │
│ 17:41   READ   config.json           │
│ 17:40   GLOB   **/*.py               │
│ 17:40   GREP   import.*              │
└───────────────────────────────────────┘
```

This panel shows **every file Claude touches** in real time.

| Label | What happened | Color |
|-------|---------------|-------|
| **WRITE** | Claude created a new file | 🟢 Green |
| **EDIT** | Claude modified an existing file | 🟡 Yellow |
| **READ** | Claude read a file to understand it | 🔵 Blue |
| **GLOB** | Claude searched for files by name pattern | 🔵 Cyan |
| **GREP** | Claude searched inside files for content | 🔵 Cyan |

**How to use this:**
- Watch for **WRITE** entries — those are brand new files Claude is creating for your project
- **EDIT** entries show Claude changing existing code — if you see rapid edits to the same file, it's iterating on a solution
- **READ** entries show Claude studying your code before making changes — this is a good sign, it means it's understanding context first
- If you see Claude reading files you didn't expect, it's exploring to understand your project structure

---

### Tool Activity

```
┌─ TOOL ACTIVITY ───────────────────────┐
│ 17:42   BASH   npm install express    │
│ 17:42   BASH   Run test suite         │
│ 17:41   FETCH  https://docs.python... │
│ 17:41   SEARCH React hooks guide      │
│ 17:40   AGENT  Explore codebase       │
└───────────────────────────────────────┘
```

This panel shows **everything Claude is doing** beyond just reading/writing files.

| Label | What it means |
|-------|---------------|
| **BASH** | Claude ran a terminal command — installing packages, running tests, building, git operations |
| **FETCH** | Claude fetched a webpage to read documentation or check an API |
| **SEARCH** | Claude searched the web for information |
| **AGENT** | Claude spawned a sub-agent to work on a task in parallel (see Agents below) |
| **READ/EDIT/WRITE** | File operations (same as File Activity but with more detail) |

**How to use this:**
- **BASH** entries tell you what Claude is running on your machine. You'll see package installs, test runs, build commands, git operations
- If you see **SEARCH** or **FETCH**, Claude is looking up documentation — it does this when it needs to verify an API or find the right approach
- **AGENT** entries mean Claude is doing something complex enough to split into parallel work (see below)

---

### Agents Panel

```
┌─ AGENTS ──────────────────────────────┐
│ ● Explore  12s                        │
│ ● Bash     3s                         │
│                                       │
│ ○ Plan                                │
│ ○ Explore                             │
└───────────────────────────────────────┘
```

**What are agents?** When Claude faces a complex task, it can spawn **sub-agents** — smaller copies of itself that work on specific parts of the problem in parallel. Think of them as assistants the main Claude delegates work to.

| Symbol | Meaning |
|--------|---------|
| **● green** | Agent is currently running (with duration) |
| **○ dimmed** | Agent finished recently |

**Agent types you'll see:**

| Agent | What it does | When it appears |
|-------|-------------|-----------------|
| **Explore** | Searches and reads files across the codebase to understand patterns | When Claude needs to find files, understand architecture, or locate specific code |
| **Bash** | Runs terminal commands | When Claude needs to execute shell operations |
| **Plan** | Designs an implementation strategy before coding | When Claude faces a complex feature that needs architectural decisions |
| **general-purpose** | Multi-step tasks combining research and execution | When Claude needs to do something that requires several different operations |

**How to trigger agents:**
- Ask Claude to do something complex: *"Refactor the entire authentication system to use JWT"*
- Ask it to explore: *"What patterns does this codebase use for error handling?"*
- Ask it to work on multiple things: *"Add tests for all the API endpoints"*
- Agents spawn automatically — you don't need to do anything special

**What "No active agents" means:**
- Claude is working directly without needing to delegate. This is normal for straightforward tasks like editing a single file or answering a question. Not every task needs agents.

---

### Stats Panel

```
┌─ STATS ───────────────────────────────┐
│ Tool calls: 47                        │
│   Read     ████████████████░░ 22      │
│   Edit     ██████████░░░░░░░░ 12      │
│   Bash     ██████░░░░░░░░░░░░  8      │
│   Grep     ████░░░░░░░░░░░░░░  5      │
│                                       │
│ Files touched: 14                     │
│ Responses: 3                          │
│ Errors: 0                             │
└───────────────────────────────────────┘
```

| Stat | What it means |
|------|---------------|
| **Tool calls** | Total number of operations Claude has performed this session |
| **Usage bars** | Visual breakdown of which tools Claude used most. Heavy Read = studying code. Heavy Edit = making changes. Heavy Bash = running commands. |
| **Files touched** | Unique files Claude has read or modified |
| **Responses** | Number of complete answers Claude has given (each time it stops and waits for you) |
| **Errors** | Tool failures — if this is > 0, the last error message is shown below |

**How to read the stats:**
- Lots of **Read** calls early on = Claude is exploring your project (good, it's understanding first)
- Lots of **Edit/Write** calls = Claude is actively building
- High **Bash** count = Claude is running tests, installing things, or running build commands
- **Errors > 0** doesn't mean something is broken — Claude often recovers from errors automatically (e.g., a test fails, it reads the error, fixes the code, re-runs)

---

### The Status Line

At the bottom of the **Claude Code pane** (not the dashboard), you'll see:

```
󰧑 Opus │ $0.05 │ 5m32s │ +142/-37 │ ████░░░░░░ 42% │ 50K/12K
```

| Item | Meaning |
|------|---------|
| **Model** | Which Claude model |
| **Cost** | How much this session has cost so far |
| **Duration** | Session length |
| **+142/-37** | Lines of code added/removed |
| **Bar + %** | Context window usage — green is fine, yellow means getting full, red means Claude may need to start a new session |
| **50K/12K** | Input/output tokens used |

---

## Part 5: Project File Tree

```
┌─ MY-APP ──────────────────────────────┐
│ 📁 src/                               │
│    main.py ◀                         │
│    utils.py                          │
│    config.json                       │
│ 📁 tests/                             │
│    test_main.py ◀                    │
│ 📄 requirements.txt ◀                 │
│ 📄 README.md                          │
└───────────────────────────────────────┘
```

The file tree shows your project's directory structure, like VS Code's sidebar.

| Visual | Meaning |
|--------|---------|
| 📁 Cyan folder names | Directories |
| File-type icons | Python, JavaScript, JSON, etc. — each has a unique icon |
| **Green + ◀** | This file was touched by Claude during the current session |
| Normal white | File exists but hasn't been touched this session |

**The tree updates automatically** every 5 seconds, so when Claude creates new files, they appear in the tree shortly after.

---

## Tips

### Make the dashboard smaller
You don't need the dashboard taking half the screen. Shrink it:
```
Ctrl+Cmd+Left    (repeat to make it smaller)
```
It'll switch to compact mode automatically when narrow enough.

### Fullscreen toggle
When you need to focus on Claude's output, zoom the left pane:
```
Cmd+Shift+F      (toggle fullscreen on focused pane)
```
Press again to bring the dashboard back.

### Working on an existing project
```bash
roasty open ~/Projects/existing-project
# The file tree immediately shows your project structure
```

### Multiple projects
Each time you run `roasty open <dir>`, the dashboard switches to that project. The file tree, git branch, and path all update.

### When something goes wrong
If the dashboard shows errors or isn't updating:
```bash
roasty status      # check if hooks are configured
roasty setup       # re-run setup to fix issues
```

---

## Example Session

Here's what a real session looks like when building an app:

**You say:** *"Build a REST API with Flask that has user registration, login, and a protected endpoint"*

**Dashboard shows (in order):**
1. 📖 READ — Claude reads any existing files in your project
2. ✏️ WRITE `requirements.txt` — creates dependencies file
3. ✏️ WRITE `app.py` — creates the main application
4. ✏️ WRITE `models.py` — creates database models
5. ✏️ WRITE `auth.py` — creates authentication logic
6. 🖥️ BASH `pip install -r requirements.txt` — installs dependencies
7. ✏️ WRITE `test_app.py` — creates tests
8. 🖥️ BASH `python -m pytest` — runs the tests
9. ✏️ EDIT `app.py` — fixes any test failures
10. 🖥️ BASH `python -m pytest` — re-runs tests (passing now)

The file tree lights up with green markers on each new file. Stats show the tool breakdown. If Claude spawned any Explore agents to research Flask patterns, you'd see them in the Agents panel.

**You're watching an AI build your app in real time.** That's Roasty.
