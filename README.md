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
Every 3 days → cron runs life_os_report.py → HTML email to your inbox
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
```

Edit `life_os_report.py` — update the `PROJECTS` list to match your actual project folders:

```python
PROJECTS = [
    {"name": "Project One",   "path": "folder-one"},
    {"name": "Project Two",   "path": "folder-two"},
    # add as many as you have
]
```

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

### 7. Schedule the email report

Add a cron job to run every 3 days at 8am:

```bash
# Open cron editor
crontab -e

# Add this line (adjust path to match your setup):
30 2 */3 * * /usr/bin/python3 "/path/to/life_os_report.py" >> /tmp/life_os_report.log 2>&1
```

Note: `30 2` = 2:30am UTC = 8am IST. Adjust for your timezone.

### 8. Test it

```bash
python3 life_os_report.py
```

You should see `Sent to your@email.com` and receive the email within seconds.

---

## File Structure

```
your-projects/
├── life_os_report.py        ← report script (run via cron)
├── .env                     ← API key + config (gitignored)
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
| Recent Decisions | Permanent log of decisions made across projects |
| Time This Period | Hours logged per project in the last 3 days |
| Needs Attention | Projects untouched for 14+ days |

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

Change `*/3` in the cron job to any interval:

```bash
30 2 */1 * *   # every day
30 2 */3 * *   # every 3 days (default)
30 2 */7 * *   # every week
```

---

## Privacy

Everything runs locally. No data leaves your machine except the email send via Resend's API. The `.context.md`, `decisions.md`, and `.sessions.json` files are gitignored and never leave your machine.

---

## Tech Stack

- **Claude Code** — context switching via global `~/.claude/CLAUDE.md`
- **Python 3** — report generation
- **Resend API** — email delivery
- **cron** — scheduling

No database. No server. No dependencies beyond `requests`.
