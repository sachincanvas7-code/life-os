#!/usr/bin/env python3
"""
Life OS Report
Reads all project folders, generates a rich HTML email, sends via Resend.
Run every 3 days via cron.

Configure via .env file:
  RESEND_API_KEY=re_...
  TO_EMAIL=your@email.com
  WORK_DIR=/path/to/your/projects
"""

import os
import json
import sys
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

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
TO_EMAIL       = os.getenv("TO_EMAIL", "your@email.com")
FROM_EMAIL     = os.getenv("FROM_EMAIL", "onboarding@resend.dev")
WORK_DIR       = Path(os.getenv("WORK_DIR", str(SCRIPT_DIR.parent)))

# ── Projects ──────────────────────────────────────────────────────────────────
# Edit this list to match your project folders.
# "name" is the display name. "path" is the folder path relative to WORK_DIR.

PROJECTS = [
    {"name": "Project One",    "path": "project-one"},
    {"name": "Project Two",    "path": "project-two"},
    {"name": "Project Three",  "path": "project-three"},
    # Add more projects here...
]

# ── File Reading ──────────────────────────────────────────────────────────────

def read_file(path, max_chars=4000):
    try:
        text = Path(path).read_text(encoding="utf-8")
        return text[-max_chars:] if len(text) > max_chars else text
    except Exception:
        return ""

def days_since_modified(folder):
    skip = {".git", "__pycache__", ".DS_Store", "node_modules"}
    try:
        times = [
            f.stat().st_mtime
            for f in Path(folder).rglob("*")
            if f.is_file() and not any(s in str(f) for s in skip)
        ]
        if not times:
            return 999
        return round((datetime.now().timestamp() - max(times)) / 86400)
    except Exception:
        return 999

def parse_context(text):
    sections = {"done": "", "decisions": [], "blockers": [], "next": ""}
    if not text:
        return sections
    current = None
    for line in text.splitlines():
        l = line.strip()
        if "## What Was Done" in l or "## Done" in l:
            current = "done"
        elif "## Open Decisions" in l:
            current = "decisions"
        elif "## Blockers" in l:
            current = "blockers"
        elif "## Next Action" in l:
            current = "next"
        elif current == "done" and l and not l.startswith("#"):
            sections["done"] += l + " "
        elif current in ("decisions", "blockers") and l.startswith("- "):
            sections[current].append(l[2:])
        elif current == "next" and l and not l.startswith("#"):
            sections["next"] += l + " "
    return sections

def load_decisions(folder):
    f = Path(folder) / "decisions.md"
    if not f.exists():
        return []
    lines = [l.strip()[2:] for l in f.read_text().splitlines() if l.strip().startswith("- ")]
    return lines[-5:]

def load_sessions(folder):
    f = Path(folder) / ".sessions.json"
    if not f.exists():
        return []
    try:
        return json.loads(f.read_text()).get("sessions", [])
    except Exception:
        return []

def calc_hours(sessions, period_days=3):
    cutoff = datetime.now() - timedelta(days=period_days)
    total = 0.0
    for s in sessions:
        try:
            d = datetime.strptime(s["date"], "%Y-%m-%d")
            if d >= cutoff:
                start = datetime.strptime(f"{s['date']} {s.get('start','00:00')}", "%Y-%m-%d %H:%M")
                end   = datetime.strptime(f"{s['date']} {s.get('end','00:00')}", "%Y-%m-%d %H:%M")
                total += max(0, (end - start).seconds / 3600)
        except Exception:
            pass
    return round(total, 1)

# ── Momentum ──────────────────────────────────────────────────────────────────

def momentum(days):
    if days <= 2:
        return "Active",    "#16A34A", "#DCFCE7", "#15803D"
    elif days <= 7:
        return "Slowing",   "#D97706", "#FEF9C3", "#B45309"
    elif days <= 14:
        return "Stalled",   "#DC2626", "#FEE2E2", "#B91C1C"
    else:
        return "Neglected", "#7F1D1D", "#FEE2E2", "#991B1B"

# ── HTML Builder ──────────────────────────────────────────────────────────────

def build_email(projects, all_blockers, all_decisions, time_data):
    today_str  = date.today().strftime("%B %d, %Y")
    active_n   = sum(1 for p in projects if p["days"] <= 2)
    slowing_n  = sum(1 for p in projects if 2 < p["days"] <= 7)
    stalled_n  = sum(1 for p in projects if p["days"] > 7)
    blocker_n  = len(all_blockers)

    # Goal health rows
    rows = ""
    for p in projects:
        label, bg, pill_bg, text_c = momentum(p["days"])
        last = "Today" if p["days"] == 0 else ("Yesterday" if p["days"] == 1 else f"{p['days']}d ago")
        nxt  = (p["next"][:72] + "…") if len(p["next"]) > 72 else (p["next"] or "—")
        rows += f"""
        <tr style="border-bottom:1px solid #F3F4F6;">
          <td style="padding:13px 16px;font-weight:600;color:#111827;font-size:14px;">{p["name"]}</td>
          <td style="padding:13px 16px;color:#6B7280;font-size:13px;white-space:nowrap;">{last}</td>
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
              <p style="margin:0 0 3px;font-size:11px;font-weight:700;color:#92400E;text-transform:uppercase;letter-spacing:0.06em;">{b["project"]}</p>
              <p style="margin:0;color:#374151;font-size:14px;">{b["blocker"]}</p>
            </div>"""
    else:
        blk = '<p style="color:#16A34A;font-weight:600;font-size:14px;">No active blockers. Clean slate.</p>'

    # Decisions
    if all_decisions:
        dec = ""
        for d in all_decisions:
            dec += f"""
            <div style="display:flex;gap:16px;padding:10px 0;border-bottom:1px solid #F3F4F6;align-items:baseline;">
              <span style="color:#9CA3AF;font-size:12px;min-width:110px;font-weight:600;flex-shrink:0;">{d["project"]}</span>
              <span style="color:#374151;font-size:14px;line-height:1.5;">{d["decision"]}</span>
            </div>"""
    else:
        dec = '<p style="color:#6B7280;font-style:italic;font-size:14px;">No decisions logged yet. Start capturing them at end of session.</p>'

    # Time bars
    max_h = max((t["hours"] for t in time_data), default=1) or 1
    time_rows = ""
    for t in sorted(time_data, key=lambda x: x["hours"], reverse=True):
        pct   = int((t["hours"] / max_h) * 180)
        color = "#2563EB" if t["hours"] > 0 else "#E5E7EB"
        hrs   = f"{t['hours']}h" if t["hours"] > 0 else "0h"
        time_rows += f"""
        <tr>
          <td style="padding:8px 16px 8px 0;font-size:13px;color:#374151;width:130px;white-space:nowrap;">{t["project"]}</td>
          <td style="padding:8px 0;">
            <div style="background:#F3F4F6;border-radius:4px;height:8px;width:200px;">
              <div style="background:{color};border-radius:4px;height:8px;width:{pct}px;"></div>
            </div>
          </td>
          <td style="padding:8px 0 8px 12px;font-size:13px;color:#6B7280;font-variant-numeric:tabular-nums;">{hrs}</td>
        </tr>"""

    # Needs attention
    neglected = [p for p in projects if p["days"] > 14]
    if neglected:
        att = "<ul style='margin:0;padding-left:18px;'>"
        for n in neglected:
            att += f"<li style='padding:5px 0;color:#374151;font-size:14px;'><strong>{n['name']}</strong> — {n['days']} days untouched</li>"
        att += "</ul>"
    else:
        att = '<p style="color:#16A34A;font-weight:600;font-size:14px;">All goals touched in the last 14 days.</p>'

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
    <h1 style="margin:0 0 6px;font-size:32px;font-weight:800;color:#F8FAFC;letter-spacing:-0.04em;line-height:1.1;">Your 3-Day Brief</h1>
    <p style="margin:0;color:#64748B;font-size:14px;">{today_str}</p>
  </td></tr>

  <!-- Stats bar -->
  <tr><td style="background:#1E293B;padding:0 40px;border-top:1px solid #334155;">
    <table width="100%" cellpadding="0" cellspacing="0"><tr>
      <td align="center" style="padding:18px 0;border-right:1px solid #334155;">
        <p style="margin:0;font-size:28px;font-weight:800;color:#4ADE80;">{active_n}</p>
        <p style="margin:3px 0 0;font-size:10px;color:#64748B;text-transform:uppercase;letter-spacing:0.1em;">Active</p>
      </td>
      <td align="center" style="padding:18px 0;border-right:1px solid #334155;">
        <p style="margin:0;font-size:28px;font-weight:800;color:#FBBF24;">{slowing_n}</p>
        <p style="margin:3px 0 0;font-size:10px;color:#64748B;text-transform:uppercase;letter-spacing:0.1em;">Slowing</p>
      </td>
      <td align="center" style="padding:18px 0;border-right:1px solid #334155;">
        <p style="margin:0;font-size:28px;font-weight:800;color:#F87171;">{stalled_n}</p>
        <p style="margin:3px 0 0;font-size:10px;color:#64748B;text-transform:uppercase;letter-spacing:0.1em;">Stalled</p>
      </td>
      <td align="center" style="padding:18px 0;">
        <p style="margin:0;font-size:28px;font-weight:800;color:#FB923C;">{blocker_n}</p>
        <p style="margin:3px 0 0;font-size:10px;color:#64748B;text-transform:uppercase;letter-spacing:0.1em;">Blockers</p>
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

  <!-- Decisions -->
  <tr><td style="background:#FFFFFF;padding:0 40px 28px;">
    <div style="border-top:1px solid #F3F4F6;padding-top:28px;">
      <p style="margin:0 0 16px;font-size:10px;letter-spacing:0.14em;text-transform:uppercase;color:#94A3B8;font-family:'SF Mono',Consolas,monospace;">03 — RECENT DECISIONS</p>
      {dec}
    </div>
  </td></tr>

  <!-- Time -->
  <tr><td style="background:#FFFFFF;padding:0 40px 28px;">
    <div style="border-top:1px solid #F3F4F6;padding-top:28px;">
      <p style="margin:0 0 16px;font-size:10px;letter-spacing:0.14em;text-transform:uppercase;color:#94A3B8;font-family:'SF Mono',Consolas,monospace;">04 — TIME THIS PERIOD</p>
      <table cellpadding="0" cellspacing="0">{time_rows}</table>
      <p style="margin:12px 0 0;font-size:11px;color:#9CA3AF;">Based on .sessions.json files per project.</p>
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
    <p style="margin:0;color:#94A3B8;font-size:12px;line-height:1.6;">Life OS · Sent every 3 days</p>
  </td></tr>

</table>
</td></tr>
</table>

</body>
</html>"""

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if not RESEND_API_KEY or RESEND_API_KEY == "re_your_key_here":
        print("ERROR: RESEND_API_KEY not set in .env file")
        sys.exit(1)

    projects      = []
    all_blockers  = []
    all_decisions = []
    time_data     = []

    for p in PROJECTS:
        folder   = WORK_DIR / p["path"]
        ctx      = read_file(folder / ".context.md")
        sec      = parse_context(ctx)
        days     = days_since_modified(folder)
        sessions = load_sessions(folder)
        hours    = calc_hours(sessions, period_days=3)

        for b in sec["blockers"]:
            if b.strip() and b.strip().lower() != "none":
                all_blockers.append({"project": p["name"], "blocker": b.strip()})

        for d in load_decisions(folder)[-2:]:
            all_decisions.append({"project": p["name"], "decision": d})

        projects.append({
            "name": p["name"],
            "days": days,
            "next": sec["next"].strip(),
            "done": sec["done"].strip(),
        })
        time_data.append({"project": p["name"], "hours": hours})

    html = build_email(projects, all_blockers, all_decisions, time_data)

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
            "html":    html
        },
        timeout=15
    )

    if resp.status_code in (200, 201):
        print(f"Sent to {TO_EMAIL}")
    else:
        print(f"Failed {resp.status_code}: {resp.text}")
        sys.exit(1)

if __name__ == "__main__":
    main()
