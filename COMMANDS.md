# 🕹️ Complete Command & Operations Reference
## Autonomous SDET Job Application Agent

This reference compiles **every command** available across the project—including **Telegram Mobile Commands**, **Terminal CLI Commands**, **macOS Service Management**, **Testing Commands**, and **Agent Slash Commands**.

---

## 📱 1. Telegram Mobile Commands (Control from Phone)
> Send these messages directly in your private **JobApply** channel or DM to **`@applyJobs3795_bot`**.

| Command | Description | What It Does |
|---|---|---|
| **`/status`** | Real-Time Dashboard | Instantly shows Total Applied, Ready-to-Apply queue (Pune/Remote top priority), and remaining daily quotas (out of 50). |
| **`/external`** | 1-Click External Jobs | Instantly sends the top Pune & Remote external portal links (Workday/Taleo) + attaches `EXTERNAL_JOBS.md` directly in Telegram. |
| **`/run`** or **`/auto`** | Full Autonomous Cycle | Triggers complete cycle: searches LinkedIn & Naukri (<24h), scores roles, auto-applies to top matches, and posts the audit summary + `EXTERNAL_JOBS.md`. |
| **`/apply`** | Fast Application Pass | Applies immediately to high-match jobs ($\ge 70\%$) waiting in your queue without waiting for a new search. |
| **`/search`** | Fresh Job Discovery | Scrapes fresh (<24h) postings on LinkedIn & Naukri, scores them, and updates `APPLICATIONS.md` without applying. |
| **`/history`** | Run Audit Logs | Shows execution durations and statistics from recent autonomous cycles. |
| **`/help`** | Command Guide | Displays quick in-chat instructions and current safety limits. |

---

## 💻 2. Terminal CLI Commands (`run.py`)
> Run these commands from the project root (`ApplyJob/`) using your project's virtual environment.

### 🚀 Autonomous Execution
```bash
# Run a single autonomous pass (Search <24h -> Match -> Apply -> Telegram Report)
./.venv/bin/python run.py auto --min-score 75.0

# Run with custom timeout (e.g. 20 minutes)
./.venv/bin/python run.py auto --min-score 75.0 --timeout-minutes 20.0

# Run in continuous background loop (Every 10 hours + Telegram listener active)
./.venv/bin/python run.py auto --daemon --interval-hours 10

# Search & score only, without auto-submitting applications
./.venv/bin/python run.py auto --no-apply
```

---

### 🎯 Targeted Application & Search
```bash
# Apply to queued high-match jobs (Auto-submits with 📍 Pune & 🏡 Remote prioritized)
./.venv/bin/python run.py apply --auto --min-score 75.0

# Apply with review mode (Pauses in browser before each final submission for manual review)
./.venv/bin/python run.py apply --min-score 75.0

# Search fresh jobs on both platforms (<24 hours)
./.venv/bin/python run.py search --platform all

# Search fresh jobs on LinkedIn only (<24 hours)
./.venv/bin/python run.py search --platform linkedin

# Search fresh jobs on Naukri only (<24 hours)
./.venv/bin/python run.py search --platform naukri
```

---

### 📊 Status, Reports & History
```bash
# View terminal summary dashboard (Applied, Pune/Remote Queue, Quotas Used)
./.venv/bin/python run.py status

# View historical run logs, runtime durations, and audit report links
./.venv/bin/python run.py history

# Regenerate master tracker report (APPLICATIONS.md & data/applications.csv)
./.venv/bin/python run.py report
```

---

### 🛑 Starting, Stopping & Removing the Bot & Background Service

#### A. macOS Background Service (`~/Library/LaunchAgents`)
```bash
# 1. Check if the background service is active and running:
./.venv/bin/python run.py service-status
# (or native Mac command): launchctl list | grep applyjob

# 2. Start / Install the background service:
./.venv/bin/python run.py service-install

# 3. STOP & COMPLETELY REMOVE from Library (1-command clean uninstall):
./.venv/bin/python run.py service-uninstall

# 4. Direct native macOS commands to stop & remove manually:
launchctl unload ~/Library/LaunchAgents/com.shubham.applyjob.bot.plist
rm ~/Library/LaunchAgents/com.shubham.applyjob.bot.plist
```

#### B. Manual Terminal Bot (`run.py bot`)
```bash
# Start bot listener in terminal:
./.venv/bin/python run.py bot

# Stop bot listener in terminal:
# Press Ctrl + C in the running terminal tab

# Force kill all running bot processes immediately:
pkill -f "run.py bot"

# Verify no bot process is running on your Mac:
ps aux | grep "run.py" | grep -v grep
```

---

### 🤖 Telegram Bot Management
```bash
# Start standalone interactive Telegram command listener in terminal
./.venv/bin/python run.py bot

# Send a test ping message to verify Telegram channel connectivity
./.venv/bin/python run.py telegram-test

# Interactive wizard to reconfigure Telegram bot token or channel ID
./.venv/bin/python run.py telegram-setup
```

---

### 🔑 Authentication & Login Sessions
```bash
# Launch headed browser to log in to LinkedIn & Naukri and save persistent session cookies
./.venv/bin/python run.py setup
```

---

## 🧪 3. Testing & QA Commands (`pytest`)
> Run unit tests to verify matcher logic, screener accuracy, database ACID safety, and Telegram mocks.

```bash
# Run all 30 unit tests with verbose output
./.venv/bin/pytest tests/ -v

# Run matcher tests only (C# symbol matching, weights, tech stack scoring)
./.venv/bin/pytest tests/test_matcher.py -v

# Run screener tests only (zero-fabrication, notice period, shift willingness)
./.venv/bin/pytest tests/test_screener.py -v

# Run Telegram notifier & listener tests (mocked networking, mutex locks)
./.venv/bin/pytest tests/test_notifier.py tests/test_telegram_listener.py -v

# Run database & quota limit tests
./.venv/bin/pytest tests/test_db.py -v
```

---

## 🗄️ 4. Data & Log Inspection Commands

```bash
# Live monitor real-time application logs
tail -f logs/applyjob.log

# View last 30 lines of service execution logs
tail -n 30 logs/service_stdout.log

# Inspect SQLite database directly (e.g. view applied jobs count)
sqlite3 data/job_tracker.db "SELECT count(*), status FROM jobs GROUP BY status;"

# View today's application counts by platform
sqlite3 data/job_tracker.db "SELECT platform, count(*) FROM jobs WHERE status='applied' AND date(applied_at) = date('now') GROUP BY platform;"

# View individual per-run markdown reports
ls -la reports/runs/
```

---

## 🤖 5. Antigravity Agent Slash Commands (Chat UI)
> Type these commands in the Antigravity chat box to activate advanced agent behaviors:

| Slash Command | When to Use |
|---|---|
| **`/schedule`** | Set up recurring agent timer or scheduled prompt runs directly in the chat environment. |
| **`/goal`** | Trigger deep overnight agent runs where the agent will not stop until full completion. |
| **`/browser`** | Engage autonomous browser research and web inspection workflows. |
| **`/grill-me`** | Conduct an interactive mock interview on technical SDET architecture decisions. |
| **`/learn`** | Save customized rules or persistent instructions for all future tasks. |
| **`/boost`** | Request deep architectural reasoning, refactoring, and multi-perspective verification. |

---

## 🛡️ Non-Negotiable Safety Invariants Summary
- **Daily Application Caps:** Strictly $\le 50$ on LinkedIn and $\le 50$ on Naukri.
- **Freshness Window:** Only jobs posted $< 24\text{ hours}$ (`f_TPR=r86400` / `postDate=1`).
- **Zero Fabrication:** Only verified resume facts used; zero guessing on screening forms.
- **Relocation & Shifts:** Always answered **"Yes"** to maximize interview invitations.
- **Runtime Circuit Breaker:** Hard 30-minute timeout per run to prevent hanging browser sessions.
- **Priority Queue:** **📍 Pune** and **🏡 Remote / WFH** opportunities always pinned to the top.
