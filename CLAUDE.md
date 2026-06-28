# Life OS — Claude Instructions

## What This Project Is
A lightweight personal OS for people running multiple projects. Two components:
- **Context Switcher** — global CLAUDE.md that briefs you at session start and captures state at end
- **Email Report** — Python script that emails a 5-section HTML digest every 3 days via Resend

## Key Files
- `life_os_report.py` — main report script, reads all project folders, sends email
- `global_claude.md` — template CLAUDE.md for users to copy to ~/.claude/CLAUDE.md
- `README.md` — full setup guide

## Rules
- This project is a template/tool for others — keep the code generic and configurable via .env / projects.json
- `life_os_report.py` must work with zero dependencies beyond `requests`
- Never hardcode paths — always use WORK_DIR from .env
- Test without sending: `python3 life_os_report.py --dry-run` (prints per-project metrics). Force a real send: `--force` (plain run honors the 3-day gate and may skip)
- "Last Active"/momentum is derived from capture signals (.sessions.json date, .context.md "Last Updated"), NOT file mtime — mtime is fallback only. Don't reintroduce mtime as the primary source.
- All dynamic text from project files is HTML-escaped via esc(); keep it that way
- Open Decisions section reads `## Open Decisions` from .context.md (decisions.md is an optional fallback)
- Project list is user config in `projects.json` (gitignored); `projects.example.json` is the committed template

## Scheduling (this machine)
- Runs via **launchd**, not cron: `~/Library/LaunchAgents/com.sachin.lifeos.plist`
- Fires daily at 20:00; the script's `REPORT_EVERY_DAYS` gate (default 3) enforces actual send spacing via a `.last_report` state file
- launchd chosen over cron: no Full Disk Access hassle + catches up runs missed while the Mac was asleep
- Reload after editing the plist: `launchctl unload <plist> && launchctl load <plist>`
- Logs: `report.log` in this folder

## Architecture
```
.env                    ← RESEND_API_KEY, TO_EMAIL, WORK_DIR, REPORT_EVERY_DAYS (gitignored)
projects.json           ← personal project list (gitignored); projects.example.json is the template
life_os_report.py       ← reads .context.md + .sessions.json from each project folder; --force flag
.last_report            ← timestamp of last send, drives the interval gate (gitignored)
global_claude.md        ← template for ~/.claude/CLAUDE.md
README.md               ← setup guide
```
