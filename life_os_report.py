#!/usr/bin/env python3
"""
Life OS Report
Reads all project folders, generates a rich HTML email, sends via Resend.
Scheduled daily via launchd; only actually sends every REPORT_EVERY_DAYS days
(default 3) unless run with --force.

Activity ("Last Active" / momentum) is derived from the capture signals the
session-end flow produces — the latest date in .sessions.json or the
"Last Updated" date in .context.md — NOT raw file mtime (which Finder, Spotlight
or backups can bump without any real work). File mtime is a last-resort fallback.

Configure via .env file:
  RESEND_API_KEY=re_...
  TO_EMAIL=your@email.com
  WORK_DIR=/path/to/your/projects
  REPORT_EVERY_DAYS=3        # optional, minimum days between sends + reporting window

Usage:
  python3 life_os_report.py            # send only if interval elapsed
  python3 life_os_report.py --force    # send now regardless
  python3 life_os_report.py --dry-run  # print computed metrics, do not send
"""

import os
import re
import json
import sys
import html
from pathlib import Path
from datetime import datetime, date, timedelta
import requests

# ── Config ────────────────────────────────────────────────────────────────────

def load_env(env_path):
    if Path(env_path).exists():
        for line in Path(env_path).read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

# Look for .env in same directory as this script, then parent
SCRIPT_DIR = Path(__file__).parent
load_env(SCRIPT_DIR / ".env")
load_env(SCRIPT_DIR.parent / ".env")

RESEND_API_KEY    = os.getenv("RESEND_API_KEY", "")
TO_EMAIL          = os.getenv("TO_EMAIL", "your@email.com")
FROM_EMAIL        = os.getenv("FROM_EMAIL", "onboarding@resend.dev")
WORK_DIR          = Path(os.getenv("WORK_DIR", str(SCRIPT_DIR.parent)))
REPORT_EVERY_DAYS = max(1, int(os.getenv("REPORT_EVERY_DAYS", "3")))
STATE_FILE        = SCRIPT_DIR / ".last_report"

# ── Projects ──────────────────────────────────────────────────────────────────
# Your real project list lives in projects.json (gitignored personal config).
# If it's missing, the generic example below is used. See projects.example.json.
# "name" is the display name. "path" is the folder path relative to WORK_DIR.

def load_projects():
    cfg = SCRIPT_DIR / "projects.json"
    if cfg.exists():
        try:
            return json.loads(cfg.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"WARNING: could not parse projects.json ({e}); using defaults")
    return [
        {"name": "Project One",    "path": "project-one"},
        {"name": "Project Two",    "path": "project-two"},
        {"name": "Project Three",  "path": "project-three"},
    ]

PROJECTS = load_projects()

DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")

def esc(s):
    """HTML-escape any dynamic text pulled from project files."""
    return html.escape(str(s), quote=True)

NONE_RE = re.compile(r"^none\b", re.IGNORECASE)

def is_none(text):
    """True for placeholder lines like 'None', 'None — ready to start', 'none.'"""
    return not text.strip() or bool(NONE_RE.match(text.strip()))

# ── File Reading ──────────────────────────────────────────────────────────────

def read_file(path, max_chars=8000):
    """Read from the START of the file so section headers always survive."""
    try:
        text = Path(path).read_text(encoding="utf-8")
        return text[:max_chars]
    except Exception:
        return ""

def parse_context(text):
    """Parse a .context.md into its sections plus the 'Last Updated' date."""
    sections = {"done": "", "decisions": [], "blockers": [], "next": "", "last_updated": None}
    if not text:
        return sections
    current = None
    for line in text.splitlines():
        l = line.strip()
        if l.lower().startswith("**last updated:") and sections["last_updated"] is None:
            m = DATE_RE.search(l)
            if m:
                sections["last_updated"] = m.group(1)
            continue
        if "## What Was Done" in l or "## Done" in l:
            current = "done"
        elif "## Open Decisions" in l:
            current = "decisions"
        elif "## Blockers" in l:
            current = "blockers"
        elif "## Next Action" in l:
            current = "next"
        elif l.startswith("## "):
            current = None  # unknown section — stop accumulating
        elif current == "done" and l and not l.startswith("#"):
            sections["done"] += l + " "
        elif current in ("decisions", "blockers") and l.startswith("- "):
            sections[current].append(l[2:].strip())
        elif current == "next" and l and not l.startswith("#"):
            sections["next"] += l + " "
    return sections

def load_decisions(folder):
    f = Path(folder) / "decisions.md"
    if not f.exists():
        return []
    lines = [l.strip()[2:].strip() for l in f.read_text().splitlines() if l.strip().startswith("- ")]
    return lines[-5:]

def load_sessions(folder):
    f = Path(folder) / ".sessions.json"
    if not f.exists():
        return []
    try:
        return json.loads(f.read_text()).get("sessions", [])
    except Exception:
        return []

def calc_hours(sessions, period_days):
    """Sum session durations within the last `period_days`. Handles overnight
    sessions and ignores impossible/garbage durations."""
    cutoff = (datetime.now() - timedelta(days=period_days)).date()
    total = 0.0
    for s in sessions:
        try:
            d = datetime.strptime(s["date"], "%Y-%m-%d").date()
            if d < cutoff:
                continue
            start = datetime.strptime(f"{s['date']} {s.get('start','00:00')}", "%Y-%m-%d %H:%M")
            end   = datetime.strptime(f"{s['date']} {s.get('end','00:00')}", "%Y-%m-%d %H:%M")
            hrs = (end - start).total_seconds() / 3600
            if hrs < 0:
                hrs += 24            # crossed midnight
            if 0 <= hrs <= 24:       # ignore garbage
                total += hrs
        except Exception:
            pass
    return round(total, 1)

# ── Activity / momentum ─────────────────────────────────────────────────────

def last_active_days(folder, sec, sessions):
    """Days since the project was last *worked on*, from capture signals.
    Priority: latest .sessions.json date > .context.md 'Last Updated' >
    .context.md mtime. Returns (days|None, source). days=None means no data /
    folder missing."""
    if not Path(folder).is_dir():
        return None, "missing"

    candidates = []
    for s in sessions:
        try:
            candidates.append(datetime.strptime(s["date"], "%Y-%m-%d").date())
        except Exception:
            pass
    if sec.get("last_updated"):
        try:
            candidates.append(datetime.strptime(sec["last_updated"], "%Y-%m-%d").date())
        except Exception:
            pass
    if candidates:
        return max(0, (date.today() - max(candidates)).days), "captured"

    ctxf = Path(folder) / ".context.md"
    if ctxf.exists():
        d = (datetime.now() - datetime.fromtimestamp(ctxf.stat().st_mtime)).days
        return max(0, d), "mtime"
    return None, "nodata"

def momentum(days):
    if days is None:
        return "No data",   "#94A3B8", "#F1F5F9", "#475569"
    if days <= 2:
        return "Active",    "#16A34A", "#DCFCE7", "#15803D"
    elif days <= 7:
        return "Slowing",   "#D97706", "#FEF9C3", "#B45309"
    elif days <= 14:
        return "Stalled",   "#DC2626", "#FEE2E2", "#B91C1C"
    else:
        return "Neglected", "#7F1D1D", "#FEE2E2", "#991B1B"

# ── HTML Builder ──────────────────────────────────────────────────────────────

def build_email(projects, all_blockers, all_decisions, time_data, period_days):
    today_str = date.today().strftime("%B %d, %Y")

    def in_range(p, lo, hi):
        return p["days"] is not None and lo <= p["days"] <= hi

    active_n    = sum(1 for p in projects if in_range(p, 0, 2))
    slowing_n   = sum(1 for p in projects if in_range(p, 3, 7))
    stalled_n   = sum(1 for p in projects if in_range(p, 8, 14))
    neglected_n = sum(1 for p in projects if p["days"] is not None and p["days"] > 14)

    def last_label(p):
        d = p["days"]
        if p["source"] == "missing":
            return "Folder missing"
        if d is None:
            return "No data"
        if d == 0:
            return "Today"
        if d == 1:
            return "Yesterday"
        return f"{d}d ago"

    # Goal health rows
    rows = ""
    for p in projects:
        label, _bg, pill_bg, text_c = momentum(p["days"])
        nxt_raw = p["next"] or "—"
        nxt = esc(nxt_raw[:72] + "…") if len(nxt_raw) > 72 else esc(nxt_raw)
        rows += f"""
        <tr style="border-bottom:1px solid #F3F4F6;">
          <td style="padding:13px 16px;font-weight:600;color:#111827;font-size:14px;">{esc(p["name"])}</td>
          <td style="padding:13px 16px;color:#6B7280;font-size:13px;white-space:nowrap;">{last_label(p)}</td>
          <td style="padding:13px 16px;">
            <span style="background:{pill_bg};color:{text_c};padding:3px 11px;border-radius:20px;font-size:11px;font-weight:700;letter-spacing:0.04em;">{label}</span>
          </td>
          <td style="padding:13px 16px;color:#4B5563;font-size:13px;line-height:1.4;">{nxt}</td>
        </tr>"""

    # Blockers
    if all_blockers:
        blk = ""
        for b in all_blockers:
            blk += f"""
            <div style="background:#FFF7ED;border-left:3px solid #F97316;padding:12px 16px;margin-bottom:8px;border-radius:0 6px 6px 0;">
              <p style="margin:0 0 3px;font-size:11px;font-weight:700;color:#92400E;text-transform:uppercase;letter-spacing:0.06em;">{esc(b["project"])}</p>
              <p style="margin:0;color:#374151;font-size:14px;">{esc(b["blocker"])}</p>
            </div>"""
    else:
        blk = '<p style="color:#16A34A;font-weight:600;font-size:14px;">No active blockers. Clean slate.</p>'

    # Open decisions (pending choices pulled from .context.md)
    if all_decisions:
        dec = ""
        for d in all_decisions:
            dec += f"""
            <div style="display:flex;gap:16px;padding:10px 0;border-bottom:1px solid #F3F4F6;align-items:baseline;">
              <span style="color:#9CA3AF;font-size:12px;min-width:110px;font-weight:600;flex-shrink:0;">{esc(d["project"])}</span>
              <span style="color:#374151;font-size:14px;line-height:1.5;">{esc(d["decision"])}</span>
            </div>"""
    else:
        dec = '<p style="color:#16A34A;font-weight:600;font-size:14px;">No open decisions. Nothing waiting on you.</p>'

    # Time bars — degrade gracefully when nothing is logged
    logged = [t for t in time_data if t["hours"] > 0]
    if logged:
        max_h = max(t["hours"] for t in logged)
        time_rows = ""
        for t in sorted(logged, key=lambda x: x["hours"], reverse=True):
            pct = int((t["hours"] / max_h) * 180) if max_h else 0
            time_rows += f"""
        <tr>
          <td style="padding:8px 16px 8px 0;font-size:13px;color:#374151;width:130px;white-space:nowrap;">{esc(t["project"])}</td>
          <td style="padding:8px 0;">
            <div style="background:#F3F4F6;border-radius:4px;height:8px;width:200px;">
              <div style="background:#2563EB;border-radius:4px;height:8px;width:{pct}px;"></div>
            </div>
          </td>
          <td style="padding:8px 0 8px 12px;font-size:13px;color:#6B7280;font-variant-numeric:tabular-nums;">{t['hours']}h</td>
        </tr>"""
        rest = len(time_data) - len(logged)
        rest_note = f" · {rest} project{'s' if rest != 1 else ''} with no logged time" if rest else ""
        time_block = f'<table cellpadding="0" cellspacing="0">{time_rows}</table>' \
                     f'<p style="margin:12px 0 0;font-size:11px;color:#9CA3AF;">Based on .sessions.json, last {period_days} days{rest_note}.</p>'
    else:
        time_block = ('<p style="color:#6B7280;font-style:italic;font-size:14px;margin:0;">'
                      'No session time logged this period. Time tracking fills in as '
                      'sessions are recorded to .sessions.json via the wrap-session flow.</p>')

    # Needs attention — neglected + missing folders, distinctly
    neglected = [p for p in projects if p["days"] is not None and p["days"] > 14]
    missing   = [p for p in projects if p["source"] == "missing"]
    if neglected or missing:
        att = "<ul style='margin:0;padding-left:18px;'>"
        for n in sorted(neglected, key=lambda x: x["days"], reverse=True):
            att += f"<li style='padding:5px 0;color:#374151;font-size:14px;'><strong>{esc(n['name'])}</strong> — {n['days']} days untouched</li>"
        for n in missing:
            att += f"<li style='padding:5px 0;color:#B91C1C;font-size:14px;'><strong>{esc(n['name'])}</strong> — folder not found (check projects.json path)</li>"
        att += "</ul>"
    else:
        att = '<p style="color:#16A34A;font-weight:600;font-size:14px;">All goals touched in the last 14 days.</p>'

    cadence = "Daily" if period_days == 1 else f"{period_days}-Day"

    def kpi(num, label, color):
        return f"""<td align="center" style="padding:18px 0;border-right:1px solid #334155;">
        <p style="margin:0;font-size:28px;font-weight:800;color:{color};">{num}</p>
        <p style="margin:3px 0 0;font-size:10px;color:#64748B;text-transform:uppercase;letter-spacing:0.1em;">{label}</p>
      </td>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Life OS Report — {today_str}</title>
</head>
<body style="margin:0;padding:0;background:#F1F5F9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;">

<table width="100%" cellpadding="0" cellspacing="0" style="background:#F1F5F9;padding:32px 16px;">
<tr><td align="center">
<table width="640" cellpadding="0" cellspacing="0" style="max-width:640px;width:100%;">

  <!-- Header -->
  <tr><td style="background:#0F172A;border-radius:14px 14px 0 0;padding:36px 40px 28px;">
    <p style="margin:0 0 8px;font-size:11px;letter-spacing:0.14em;text-transform:uppercase;color:#475569;font-family:'SF Mono',Consolas,monospace;">LIFE OS REPORT</p>
    <h1 style="margin:0 0 6px;font-size:32px;font-weight:800;color:#F8FAFC;letter-spacing:-0.04em;line-height:1.1;">Your {cadence} Brief</h1>
    <p style="margin:0;color:#64748B;font-size:14px;">{today_str}</p>
  </td></tr>

  <!-- Stats bar -->
  <tr><td style="background:#1E293B;padding:0 40px;border-top:1px solid #334155;">
    <table width="100%" cellpadding="0" cellspacing="0"><tr>
      {kpi(active_n, "Active", "#4ADE80")}
      {kpi(slowing_n, "Slowing", "#FBBF24")}
      {kpi(stalled_n, "Stalled", "#F87171")}
      <td align="center" style="padding:18px 0;">
        <p style="margin:0;font-size:28px;font-weight:800;color:#FB923C;">{neglected_n}</p>
        <p style="margin:3px 0 0;font-size:10px;color:#64748B;text-transform:uppercase;letter-spacing:0.1em;">Neglected</p>
      </td>
    </tr></table>
  </td></tr>

  <!-- Goal Health -->
  <tr><td style="background:#FFFFFF;padding:32px 40px 24px;">
    <p style="margin:0 0 18px;font-size:10px;letter-spacing:0.14em;text-transform:uppercase;color:#94A3B8;font-family:'SF Mono',Consolas,monospace;">01 — GOAL HEALTH</p>
    <div style="border:1px solid #E5E7EB;border-radius:10px;overflow:hidden;">
    <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
      <tr style="background:#F9FAFB;">
        <th style="padding:10px 16px;text-align:left;font-size:11px;color:#6B7280;text-transform:uppercase;letter-spacing:0.07em;font-weight:600;border-bottom:1px solid #E5E7EB;">Project</th>
        <th style="padding:10px 16px;text-align:left;font-size:11px;color:#6B7280;text-transform:uppercase;letter-spacing:0.07em;font-weight:600;border-bottom:1px solid #E5E7EB;">Last Active</th>
        <th style="padding:10px 16px;text-align:left;font-size:11px;color:#6B7280;text-transform:uppercase;letter-spacing:0.07em;font-weight:600;border-bottom:1px solid #E5E7EB;">Status</th>
        <th style="padding:10px 16px;text-align:left;font-size:11px;color:#6B7280;text-transform:uppercase;letter-spacing:0.07em;font-weight:600;border-bottom:1px solid #E5E7EB;">Next Action</th>
      </tr>
      {rows}
    </table>
    </div>
  </td></tr>

  <!-- Blockers -->
  <tr><td style="background:#FFFFFF;padding:0 40px 28px;">
    <div style="border-top:1px solid #F3F4F6;padding-top:28px;">
      <p style="margin:0 0 16px;font-size:10px;letter-spacing:0.14em;text-transform:uppercase;color:#94A3B8;font-family:'SF Mono',Consolas,monospace;">02 — ACTIVE BLOCKERS</p>
      {blk}
    </div>
  </td></tr>

  <!-- Open Decisions -->
  <tr><td style="background:#FFFFFF;padding:0 40px 28px;">
    <div style="border-top:1px solid #F3F4F6;padding-top:28px;">
      <p style="margin:0 0 16px;font-size:10px;letter-spacing:0.14em;text-transform:uppercase;color:#94A3B8;font-family:'SF Mono',Consolas,monospace;">03 — OPEN DECISIONS</p>
      {dec}
    </div>
  </td></tr>

  <!-- Time -->
  <tr><td style="background:#FFFFFF;padding:0 40px 28px;">
    <div style="border-top:1px solid #F3F4F6;padding-top:28px;">
      <p style="margin:0 0 16px;font-size:10px;letter-spacing:0.14em;text-transform:uppercase;color:#94A3B8;font-family:'SF Mono',Consolas,monospace;">04 — TIME THIS PERIOD</p>
      {time_block}
    </div>
  </td></tr>

  <!-- Needs Attention -->
  <tr><td style="background:#FFFFFF;padding:0 40px 36px;border-radius:0 0 14px 14px;">
    <div style="border-top:1px solid #F3F4F6;padding-top:28px;">
      <p style="margin:0 0 16px;font-size:10px;letter-spacing:0.14em;text-transform:uppercase;color:#94A3B8;font-family:'SF Mono',Consolas,monospace;">05 — NEEDS ATTENTION</p>
      {att}
    </div>
  </td></tr>

  <!-- Footer -->
  <tr><td style="padding:24px 0;text-align:center;">
    <p style="margin:0;color:#94A3B8;font-size:12px;line-height:1.6;">Life OS · Sent every {period_days} days</p>
  </td></tr>

</table>
</td></tr>
</table>

</body>
</html>"""

# ── Data assembly ─────────────────────────────────────────────────────────────

def gather():
    projects, all_blockers, all_decisions, time_data = [], [], [], []
    for p in PROJECTS:
        folder   = WORK_DIR / p["path"]
        ctx      = read_file(folder / ".context.md")
        sec      = parse_context(ctx)
        sessions = load_sessions(folder)
        days, source = last_active_days(folder, sec, sessions)
        hours    = calc_hours(sessions, REPORT_EVERY_DAYS)

        for b in sec["blockers"]:
            if not is_none(b):
                all_blockers.append({"project": p["name"], "blocker": b.strip()})

        # Open decisions are the pending choices captured in .context.md; fall
        # back to the decisions.md log if a project keeps one. Cap 2 per project.
        decs = sec["decisions"] or load_decisions(folder)
        for d in [x for x in decs if not is_none(x)][:2]:
            all_decisions.append({"project": p["name"], "decision": d.strip()})

        projects.append({
            "name": p["name"], "days": days, "source": source,
            "next": sec["next"].strip(), "done": sec["done"].strip(),
        })
        time_data.append({"project": p["name"], "hours": hours})
    return projects, all_blockers, all_decisions, time_data

# ── Main ──────────────────────────────────────────────────────────────────────

def interval_elapsed():
    """True if at least REPORT_EVERY_DAYS have passed since the last send."""
    if not STATE_FILE.exists():
        return True
    try:
        last = datetime.fromisoformat(STATE_FILE.read_text().strip())
    except Exception:
        return True
    threshold = REPORT_EVERY_DAYS * 86400 - 3600  # 1h slack for scheduler drift
    return (datetime.now() - last).total_seconds() >= threshold

def main():
    force   = "--force" in sys.argv
    dry_run = "--dry-run" in sys.argv

    if not dry_run and (not RESEND_API_KEY or RESEND_API_KEY == "re_your_key_here"):
        print("ERROR: RESEND_API_KEY not set in .env file")
        sys.exit(1)

    if not force and not dry_run and not interval_elapsed():
        last = STATE_FILE.read_text().strip()
        print(f"Skipping: last report {last} — under {REPORT_EVERY_DAYS}-day interval. Use --force to override.")
        sys.exit(0)

    projects, all_blockers, all_decisions, time_data = gather()

    if dry_run:
        print(f"{'PROJECT':16}{'LAST ACTIVE':>14}{'SOURCE':>10}{'STATUS':>11}{'HOURS':>7}")
        for p in projects:
            label = momentum(p["days"])[0]
            da = "missing" if p["source"] == "missing" else (f"{p['days']}d" if p["days"] is not None else "—")
            hrs = next(t["hours"] for t in time_data if t["project"] == p["name"])
            print(f"{p['name']:16}{da:>14}{p['source']:>10}{label:>11}{hrs:>7}")
        print(f"\nBlockers: {len(all_blockers)} | Open decisions: {len(all_decisions)} | "
              f"Total hours: {round(sum(t['hours'] for t in time_data),1)}")
        return

    html_body = build_email(projects, all_blockers, all_decisions, time_data, REPORT_EVERY_DAYS)

    resp = requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "from":    FROM_EMAIL,
            "to":      TO_EMAIL,
            "subject": f"Life OS — {date.today().strftime('%d %b %Y')}",
            "html":    html_body
        },
        timeout=15
    )

    if resp.status_code in (200, 201):
        STATE_FILE.write_text(datetime.now().isoformat())
        print(f"Sent to {TO_EMAIL}")
    else:
        print(f"Failed {resp.status_code}: {resp.text}")
        sys.exit(1)

if __name__ == "__main__":
    main()
