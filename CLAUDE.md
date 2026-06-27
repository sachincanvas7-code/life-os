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
- This project is a template/tool for others — keep the code generic and configurable via .env
- `life_os_report.py` must work with zero dependencies beyond `requests`
- Never hardcode paths — always use WORK_DIR from .env
- Test email output by running the script directly: `python3 life_os_report.py`
- The PROJECTS list in life_os_report.py is the user-editable config — keep it simple

## Architecture
```
.env                    ← RESEND_API_KEY, TO_EMAIL, WORK_DIR (gitignored)
life_os_report.py       ← reads .context.md + .sessions.json from each project folder
global_claude.md        ← template for ~/.claude/CLAUDE.md
README.md               ← setup guide
```
