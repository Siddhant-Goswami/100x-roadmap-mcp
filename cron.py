"""
Daily drift + milestone check.

Run once a day (launchd, cron, or by hand). For each mentee on the
roster, checks three things and sends one email per event to the mentor:

  1. Milestone completed today (any milestone where completed_at == today).
  2. Inactivity (no log in >= INACTIVITY_DAYS days).
  3. Pace drift (any non-completed milestone whose target_week is more
     than 1 week behind the mentee's current week).

If RESEND_API_KEY is unset, events print to stdout instead of sending.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import yaml

# Reuse module-level state from the MCP server package
import storage

INACTIVITY_DAYS = int(os.environ.get("INACTIVITY_DAYS", "3"))
PACE_SLACK_WEEKS = int(os.environ.get("PACE_SLACK_WEEKS", "1"))
MENTOR_EMAIL = os.environ.get("MENTOR_EMAIL", "")
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
FROM_EMAIL = os.environ.get("FROM_EMAIL", "pilot@medianmirror.local")
REPO_LINK_BASE = os.environ.get("REPO_LINK_BASE", "")  # e.g. github URL prefix

LOG_HEADER_RE = re.compile(r"^##\s+(\d{4}-\d{2}-\d{2})", re.MULTILINE)


@dataclass
class Event:
    mentee_id: str
    kind: str          # "milestone" | "inactivity" | "pace"
    subject: str
    body: str


def _split_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    return (yaml.safe_load(text[4:end]) or {}), text[end + 5:]


def _current_week(fm: dict) -> int:
    approved = fm.get("approved_at")
    if not approved:
        return 1
    try:
        start = datetime.fromisoformat(str(approved)).date()
    except ValueError:
        return 1
    return max(1, ((date.today() - start).days // 7) + 1)


def _last_log_date(log_text: str) -> date | None:
    dates = LOG_HEADER_RE.findall(log_text or "")
    if not dates:
        return None
    try:
        return datetime.fromisoformat(max(dates)).date()
    except ValueError:
        return None


def _link(relpath: str) -> str:
    if REPO_LINK_BASE:
        return f"{REPO_LINK_BASE.rstrip('/')}/{relpath}"
    return str((storage.PILOT_REPO / relpath).resolve())


def check_mentee(mid: str) -> list[Event]:
    events: list[Event] = []
    roadmap_text = storage.read_file(f"mentees/{mid}/roadmap.md")
    if not roadmap_text:
        return events
    fm, _ = _split_frontmatter(roadmap_text)
    if fm.get("status") != "active":
        return events  # drafts and awaiting_draft don't trigger drift

    today = date.today().isoformat()
    current_week = _current_week(fm)
    roadmap_link = _link(f"mentees/{mid}/roadmap.md")
    log_link = _link(f"mentees/{mid}/progress-log.md")

    # 1) Milestone completed today
    for m in fm.get("milestones", []):
        if m.get("status") == "completed" and str(m.get("completed_at")) == today:
            events.append(Event(
                mid, "milestone",
                f"[MedianMirror] {mid}: shipped {m.get('id')}",
                (f"{mid} marked milestone {m.get('id')!r} completed today: "
                 f"{m.get('title')!r}.\n\nLog: {log_link}\nRoadmap: {roadmap_link}"),
            ))

    # 2) Inactivity
    log_text = storage.read_file(f"mentees/{mid}/progress-log.md")
    last = _last_log_date(log_text)
    if last is None:
        days = (date.today() - datetime.fromisoformat(
            str(fm.get("approved_at", today))).date()).days
        if days >= INACTIVITY_DAYS:
            events.append(Event(
                mid, "inactivity",
                f"[MedianMirror] {mid}: no logs since approval ({days}d)",
                f"{mid} has not logged since their roadmap was approved {days} days ago.\n"
                f"Roadmap: {roadmap_link}",
            ))
    else:
        gap = (date.today() - last).days
        if gap >= INACTIVITY_DAYS:
            events.append(Event(
                mid, "inactivity",
                f"[MedianMirror] {mid}: {gap}d since last log",
                f"{mid}'s last log was {last.isoformat()} ({gap} days ago).\n"
                f"Log: {log_link}\nRoadmap: {roadmap_link}",
            ))

    # 3) Pace drift — any non-completed milestone whose target_week is
    #    more than PACE_SLACK_WEEKS behind current_week.
    for m in fm.get("milestones", []):
        if m.get("status") == "completed":
            continue
        target = m.get("target_week")
        if not isinstance(target, int):
            continue
        if current_week - target > PACE_SLACK_WEEKS:
            events.append(Event(
                mid, "pace",
                f"[MedianMirror] {mid}: milestone {m.get('id')} "
                f"is {current_week - target}w overdue",
                (f"{mid} is in week {current_week}; milestone {m.get('id')!r} "
                 f"({m.get('title')!r}) was targeted for week {target} and "
                 f"is still {m.get('status')!r}.\n\nRoadmap: {roadmap_link}"),
            ))

    return events


def send_event(ev: Event) -> None:
    if not MENTOR_EMAIL or not RESEND_API_KEY:
        print(f"\n[would email] to={MENTOR_EMAIL or '<unset>'}")
        print(f"subject: {ev.subject}")
        print(ev.body)
        return

    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=json.dumps({
            "from": FROM_EMAIL,
            "to": [MENTOR_EMAIL],
            "subject": ev.subject,
            "text": ev.body,
        }).encode(),
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        if resp.status >= 300:
            print(f"resend failed: {resp.status} {resp.read()!r}", file=sys.stderr)


def main() -> int:
    mentees = storage.list_mentees()
    all_events: list[Event] = []
    for mid in mentees:
        all_events.extend(check_mentee(mid))

    if not all_events:
        print(f"[{date.today()}] no events across {len(mentees)} mentee(s)")
        return 0

    print(f"[{date.today()}] {len(all_events)} event(s) across "
          f"{len(mentees)} mentee(s)")
    for ev in all_events:
        send_event(ev)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
