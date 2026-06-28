# Life OS

A lightweight personal operating system for people running multiple projects simultaneously.

Two components:
- **Context Switcher** — tells Claude exactly where you left off on any project, the moment you open a terminal
- **Email Report** — a rich HTML digest delivered every 3 days covering goal health, blockers, decisions, time, and what needs attention

No app. No subscription. Runs entirely on your machine using Claude Code and a single Python script.

---

## How It Works

```
Open terminal anywhere
        ↓
Claude reads ~/.claude/CLAUDE.md (always loaded globally)
        ↓
Asks: "Which project are you working on?"
        ↓
Reads that project's .context.md
        ↓
Briefs you: where you left off, open decisions, blocker, next action
        ↓
        ... you work ...
        ↓
You say "wrap session"
        ↓
Claude generates session summary from conversation
        ↓
Shows draft → you approve or edit
        ↓
Writes back to .context.md + decisions.md + .sessions.json
        ↓
Daily → launchd runs life_os_report.py → sends only every 3 days → HTML email to your inbox
```

---

## Setup

### 1. Prerequisites

- [Claude Code](https://claude.ai/code) installed
- Python 3.9+
- A [Resend](https://resend.com) account (free — 100 emails/day)

### 2. Clone this repo

```bash
git clone https://github.com/sachincanvas7-code/life-os.git
cd life-os
```

### 3. Install dependencies

```bash
pip3 install requests
```

### 4. Configure

Copy the example env file and fill in your values:

```bash
cp .env.example .env
```

Edit `.env`:

```env
RESEND_API_KEY=re_your_key_here
TO_EMAIL=your@email.com
WORK_DIR=/path/to/your/projects
REPORT_EVERY_DAYS=3
```

Then create your project list. Copy the example and edit it (this file is gitignored, so your real project names stay private):

```bash
cp projects.example.json projects.json
```

```json
[
  {"name": "Project One", "path": "folder-one"},
  {"name": "Project Two", "path": "folder-two"}
]
```

If `projects.json` is missing, the script falls back to a generic built-in list.

### 5. Set up the global Claude instruction

Copy `global_claude.md` to `~/.claude/CLAUDE.md`:

```bash
cp global_claude.md ~/.claude/CLAUDE.md
```

Then edit `~/.claude/CLAUDE.md` — update the project folder table at the bottom to match your projects and paths.

### 6. Seed your projects

For each project folder, create a `.context.md` file:

```markdown
# Project Name Context

**Last Updated:** YYYY-MM-DD

## What Was Done
[brief summary of where you are]

## Open Decisions
- [unresolved decision]

## Blockers
- [blocker or None]

## Next Action
[single next step]
```

This seeds the context. After your first session using the switcher, Claude will keep it updated automatically.

### 7. Schedule the email report (macOS — launchd)

launchd is preferred over cron on macOS: it runs in your user session (no Full
Disk Access hassle) and **catches up missed runs** if your Mac was asleep at the
scheduled time — so you never silently miss a digest.

Create `~/Library/LaunchAgents/com.you.lifeos.plist`. It fires **daily at 20:00**;
the script's built-in gate only actually sends every `REPORT_EVERY_DAYS` days:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.you.lifeos</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/path/to/life-os/life_os_report.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/path/to/life-os</string>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key><integer>20</integer>
        <key>Minute</key><integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>/path/to/life-os/report.log</string>
    <key>StandardErrorPath</key>
    <string>/path/to/life-os/report.log</string>
</dict>
</plist>
```

Load it:

```bash
launchctl load ~/Library/LaunchAgents/com.you.lifeos.plist
launchctl list | grep lifeos   # confirm it's registered
```

### 8. Test it

```bash
python3 life_os_report.py --force
```

`--force` bypasses the 3-day gate. You should see `Sent to your@email.com` and
receive the email within seconds. (Without `--force`, the script skips if it sent
within the last `REPORT_EVERY_DAYS` days.)

---

## File Structure

```
your-projects/
├── life_os_report.py        ← report script (run via launchd)
├── .env                     ← API key + config (gitignored)
├── projects.json            ← your project list (gitignored)
├── projects.example.json    ← template project list
│
├── project-one/
│   ├── CLAUDE.md            ← project context for Claude
│   ├── .context.md          ← live session state (auto-updated)
│   ├── decisions.md         ← permanent decision log
│   └── .sessions.json       ← session timestamps for time tracking
│
├── project-two/
│   └── ...
│
└── ...
```

---

## The Email Report

Delivered every 3 days. Contains five sections:

| Section | What it shows |
|---------|--------------|
| Goal Health | All projects with last-active date and momentum status |
| Active Blockers | Things currently preventing progress, by project |
| Open Decisions | Pending choices waiting on you, pulled from each `.context.md` |
| Time This Period | Hours logged per project in the reporting window |
| Needs Attention | Projects untouched for 14+ days, plus any missing folders |

**"Last Active" is measured from capture signals** — the latest date in
`.sessions.json` or the `Last Updated:` line in `.context.md` — *not* raw file
mtime (which Finder/Spotlight/backups can bump without any real work). File mtime
is only a last-resort fallback when a project has neither.

Momentum thresholds:

| Status | Meaning |
|--------|---------|
| Active | Worked on in the last 2 days |
| Slowing | 3–7 days since last session |
| Stalled | 8–14 days since last session |
| Neglected | 14+ days since last session |

---

## The Context Switcher

Powered by a global instruction in `~/.claude/CLAUDE.md`. Claude Code reads this file in every session regardless of which folder you open the terminal in.

**Session start format:**
```
PROJECT: Trading — last updated 2 days ago
─────────────────────────────────────────
WHERE YOU LEFT OFF
Watching CHoCH at support on Nifty. Waiting for confirmation.

OPEN DECISIONS
→ Max drawdown per trade still undefined

BLOCKER
None

NEXT ACTION
Log last week's paper trade journal entry on Neostox
─────────────────────────────────────────
```

**Session end — Claude generates a draft, you approve:**
```
SESSION SUMMARY — 2026-06-27
─────────────────────────────────────────
DONE
Reviewed 3 SMC setups on Nifty. Decided 1-hour timeframe for entries.

OPEN DECISIONS
→ None

BLOCKER
None

NEXT ACTION
Paper trade the setup tomorrow morning on Neostox
─────────────────────────────────────────
Save this? Or tell me what to change.
```

Once approved, Claude writes it back to `.context.md` automatically.

---

## Decisions Log

Every significant decision gets appended to `decisions.md` in the relevant project folder:

```markdown
- 2026-06-27 Decided to use 1-hour timeframe for all SMC entries
- 2026-06-25 Targeting Whitefield and Sarjapur for real estate, not HSR
```

This is permanent. Session context gets overwritten. Decisions don't.

---

## Session Time Tracking

Each session logs to `.sessions.json`:

```json
{
  "sessions": [
    {"date": "2026-06-27", "start": "10:30", "end": "12:15"},
    {"date": "2026-06-25", "start": "09:00", "end": "10:30"}
  ]
}
```

The report script reads these and shows hours per project for the period.

---

## Customising the Report Frequency

The LaunchAgent fires daily at 20:00; spacing is controlled by `REPORT_EVERY_DAYS`
in `.env`:

```env
REPORT_EVERY_DAYS=1    # every day
REPORT_EVERY_DAYS=3    # every 3 days (default)
REPORT_EVERY_DAYS=7    # every week
```

To change the time of day, edit the `Hour`/`Minute` in the plist, then reload:

```bash
launchctl unload ~/Library/LaunchAgents/com.you.lifeos.plist
launchctl load   ~/Library/LaunchAgents/com.you.lifeos.plist
```

---

## Privacy

Everything runs locally. No data leaves your machine except the email send via Resend's API. The `.context.md`, `decisions.md`, and `.sessions.json` files are gitignored and never leave your machine.

---

## Tech Stack

- **Claude Code** — context switching via global `~/.claude/CLAUDE.md`
- **Python 3** — report generation
- **Resend API** — email delivery
- **launchd** — scheduling (macOS)

No database. No server. No dependencies beyond `requests`.
