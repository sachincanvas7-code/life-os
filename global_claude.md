# Global Claude Instructions — Life OS

Copy this file to `~/.claude/CLAUDE.md` to activate the context switcher in every Claude Code session.

Then update the **Project Folders** table at the bottom to match your actual projects.

---

## Context Switcher

### At the start of every session
1. Ask: "Which project are you working on today?"
2. Match the name to a folder in your projects directory
3. Read `.context.md` and `CLAUDE.md` from that folder if they exist
4. Brief the user in this exact format:

```
PROJECT: [Name] — last updated [date]
─────────────────────────────────────
WHERE YOU LEFT OFF
[1-2 sentences]

OPEN DECISIONS
→ [decision]
→ [decision]

BLOCKER
[blocker or None]

NEXT ACTION
[single specific next step]
─────────────────────────────────────
```

### When the user says "wrap session"
1. Generate a session summary from what was discussed and built in this conversation
2. Show the user this draft:

```
SESSION SUMMARY — [date]
─────────────────────────────────────
DONE
[what was accomplished]

OPEN DECISIONS
→ [unresolved decisions, if any]

BLOCKER
[blocker or None]

NEXT ACTION
[single most important next step]
─────────────────────────────────────
Save this? Or tell me what to change.
```

3. Wait for approval ("looks good", "save it") or edits
4. Once approved, write to `.context.md` in the project folder:

```markdown
# [Project] Context

**Last Updated:** YYYY-MM-DD HH:MM

## What Was Done
[summary]

## Open Decisions
- [decision]

## Blockers
- [blocker or None]

## Next Action
[next step]
```

5. If significant decisions were made, append to `decisions.md`:
```
- [YYYY-MM-DD] [Decision made and why]
```

6. Log session timing to `.sessions.json`:
```json
{"sessions": [{"date": "YYYY-MM-DD", "start": "HH:MM", "end": "HH:MM"}]}
```
Append new sessions to the existing array — don't overwrite it.

---

## Project Folders

Update this table to match your projects and folder paths.

| Project | Folder |
|---------|--------|
| Project One | `folder-one/` |
| Project Two | `folder-two/` |
| Project Three | `folder-three/` |
