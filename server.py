"""
MedianMirror Roadmap MCP.

Single local MCP server. Role is determined by env vars at launch:
  ROLE=mentor                    → mentor tools only, operates on any mentee
  ROLE=mentee MENTEE_ID=arjun    → mentee tools only, scoped to that id

Storage is a local git repo at PILOT_REPO_PATH. Every write is a commit.
Curriculum lives in pilot-data/curriculum/ and is read-only from here.
"""
from __future__ import annotations

import functools
import json
import os
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

import yaml
from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, TextContent

import curriculum
import storage

# ─── Role gating ────────────────────────────────────────────────────────────

ROLE = os.environ.get("ROLE", "mentee").lower()
MENTEE_ID_ENV = os.environ.get("MENTEE_ID", "")

if ROLE not in ("mentor", "mentee"):
    raise SystemExit(f"ROLE must be 'mentor' or 'mentee', got {ROLE!r}")
if ROLE == "mentee" and not MENTEE_ID_ENV:
    raise SystemExit("ROLE=mentee requires MENTEE_ID to be set")


def _author() -> str:
    return f"{ROLE}:{MENTEE_ID_ENV or 'mentor'}"


def _require_role(required: str):
    """Role gate. Uses functools.wraps so FastMCP's inspect.signature call
    follows __wrapped__ back to the real signature — otherwise the tool
    schema collapses to (*args, **kwargs) and clients can't call it."""
    def deco(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapped(*args, **kwargs):
            if ROLE != required:
                return {"error": f"this tool requires ROLE={required}, current ROLE={ROLE}"}
            return fn(*args, **kwargs)
        return wrapped
    return deco


def _resolve_mentee_id(mentee_id: str | None) -> str | None:
    """Mentee role ignores the arg and uses env id; mentor must pass one."""
    if ROLE == "mentee":
        return MENTEE_ID_ENV
    if not mentee_id:
        return None
    if mentee_id not in storage.list_mentees():
        # Mentor may be onboarding a new mentee — allow
        pass
    return mentee_id


# ─── Markdown / frontmatter helpers ─────────────────────────────────────────

def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    fm = yaml.safe_load(text[4:end]) or {}
    body = text[end + 5 :]
    return fm, body


def _join_frontmatter(fm: dict[str, Any], body: str) -> str:
    yaml_text = yaml.safe_dump(fm, sort_keys=False).strip()
    return f"---\n{yaml_text}\n---\n\n{body.lstrip()}"


def _roadmap_path(mid: str) -> str:
    return f"mentees/{mid}/roadmap.md"


def _progress_path(mid: str) -> str:
    return f"mentees/{mid}/progress-log.md"


def _current_week(fm: dict[str, Any]) -> int:
    """Weeks elapsed since approved_at (1-indexed). Falls back to 1."""
    approved = fm.get("approved_at")
    if not approved:
        return 1
    try:
        start = datetime.fromisoformat(str(approved)).date()
    except ValueError:
        return 1
    return max(1, ((date.today() - start).days // 7) + 1)


_WEEK_HEADER_RE = re.compile(
    r"^##\s+Week\s+(\d+)(?:\s*[–-]\s*(\d+))?\b",
    re.IGNORECASE | re.MULTILINE,
)


def _extract_week_section(body: str, week: int) -> str:
    """Return the markdown section (## Week N ...) that covers the given week."""
    matches = list(_WEEK_HEADER_RE.finditer(body))
    if not matches:
        return body[:1500]
    for i, m in enumerate(matches):
        start_w = int(m.group(1))
        end_w = int(m.group(2) or m.group(1))
        if start_w <= week <= end_w:
            start = m.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
            return body[start:end].strip()
    # Past the last section → return the last one
    last = matches[-1]
    return body[last.start():].strip()


_LOG_ENTRY_RE = re.compile(r"^##\s+(\d{4}-\d{2}-\d{2})", re.MULTILINE)


def _last_log_entries(log_text: str, n: int = 5) -> list[str]:
    """Split progress-log.md into dated blocks, newest first, return top n."""
    matches = list(_LOG_ENTRY_RE.finditer(log_text))
    if not matches:
        return []
    blocks: list[tuple[str, str]] = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(log_text)
        blocks.append((m.group(1), log_text[start:end].strip()))
    blocks.sort(key=lambda b: b[0], reverse=True)
    return [b[1] for b in blocks[:n]]


# Prompt guidance pulled verbatim from MVP spec §4.3.
QUERY_CURRICULUM_PROMPT = """\
You are a curriculum assistant for a 100xEngineers mentee. Answer their
question in a way that connects to where they are in their personalised
roadmap — not a generic curriculum answer.

Rules:
- ALWAYS anchor the answer to the mentee's current roadmap position. Open
  with something like "You're in Week X, which is exactly when Y matters".
- ALWAYS use the provided curriculum pages as the factual base. Do not
  invent curriculum content. If the pages don't cover the question, say so.
- NEVER give a generic answer that ignores the mentee's goal.
- NEVER advance the mentee past their current roadmap week. If they ask
  about something weeks ahead, give a short orientation and defer depth.
- KEEP answers to 100–300 words.
- END with one concrete next step tied to their roadmap, if natural.
"""


# ─── MCP UI hooks (kept from v1, wired to new tools) ────────────────────────

RESOURCE_MIME_TYPE = "text/html;profile=mcp-app"
ROADMAP_RESOURCE_URI = "ui://learning-coach/mcp-app.html"
UI_HTML_PATH = Path(__file__).parent / "ui" / "dist" / "mcp-app.html"

mcp = FastMCP("MedianMirror Roadmap", json_response=True)


# ═══════════════════════════════════════════════════════════════════════════
#  MENTEE TOOLS
# ═══════════════════════════════════════════════════════════════════════════

@mcp.tool()
@_require_role("mentee")
def declare_position(
    background: str,
    goal: str,
    hours_per_week: int,
) -> dict:
    """
    First-time setup for a mentee. Captures their starting position.
    Writes a draft roadmap stub with frontmatter that the mentor will
    later flesh out via generate_roadmap and approve.

    Args:
        background: Brief description of prior experience (e.g. "3 years backend, no ML")
        goal: What they want to ship/achieve (e.g. "ship an AI agent at work in 12 weeks")
        hours_per_week: Hours per week they can commit
    """
    mid = MENTEE_ID_ENV
    path = _roadmap_path(mid)
    existing = storage.read_file(path)
    fm, body = _split_frontmatter(existing) if existing else ({}, "")

    fm = {
        "mentee_id": mid,
        "status": "awaiting_draft",
        "version": fm.get("version", 0),
        "declared_position": {
            "background": background,
            "goal": goal,
            "hours_per_week": hours_per_week,
        },
        "declared_at": date.today().isoformat(),
        "milestones": fm.get("milestones", []),
    }
    body = body or f"# {mid.title()}'s Roadmap\n\n_Awaiting mentor draft._\n"
    storage.write_file(
        path,
        _join_frontmatter(fm, body),
        commit_msg=f"{mid}: declare position",
        author=_author(),
    )
    return {
        "status": "position declared",
        "next": "Your mentor will draft a roadmap for you. You'll hear back within a day.",
        "declared_position": fm["declared_position"],
    }


@mcp.tool()
@_require_role("mentee")
def log_progress(
    worked_on: str,
    duration_minutes: int,
    confidence: int,
    blockers: str = "",
    next_step: str = "",
    completed_milestone_id: str = "",
) -> dict:
    """
    Daily ritual tool. Append a dated entry to the mentee's progress log.
    If completed_milestone_id is set, also flip that milestone's status
    on the roadmap — the cron detects this and emails the mentor.

    Args:
        worked_on: What the mentee worked on today (free text)
        duration_minutes: Time spent, in minutes
        confidence: Self-rated 1-5 (1=lost, 3=okay, 5=solid)
        blockers: Any confusion points or blockers (optional)
        next_step: What the mentee plans to do next (optional)
        completed_milestone_id: ID of a milestone shipped today (optional)
    """
    mid = MENTEE_ID_ENV
    today = date.today().isoformat()
    hours = round(duration_minutes / 60, 1)
    entry_lines = [
        f"## {today}",
        f"**Worked on:** {worked_on}",
        f"**Duration:** {hours}h ({duration_minutes}m)",
        f"**Confidence:** {confidence}/5",
    ]
    if blockers:
        entry_lines.append(f"**Blockers:** {blockers}")
    if next_step:
        entry_lines.append(f"**Next:** {next_step}")
    if completed_milestone_id:
        entry_lines.append(f"**Shipped milestone:** {completed_milestone_id}")
    entry = "\n".join(entry_lines) + "\n"

    storage.append_file(
        _progress_path(mid),
        "\n" + entry,
        commit_msg=f"{mid}: log {today}",
        author=_author(),
    )

    milestone_result = None
    if completed_milestone_id:
        milestone_result = _mark_milestone_completed(mid, completed_milestone_id, today)

    return {
        "status": "logged",
        "date": today,
        "blockers_flagged": bool(blockers),
        "milestone": milestone_result,
        "hint": (
            "You flagged a blocker — want to call query_curriculum to get "
            "a roadmap-aware answer?" if blockers else None
        ),
    }


def _mark_milestone_completed(mid: str, milestone_id: str, today: str) -> dict:
    path = _roadmap_path(mid)
    text = storage.read_file(path)
    if not text:
        return {"error": "no roadmap"}
    fm, body = _split_frontmatter(text)
    found = False
    for m in fm.get("milestones", []):
        if m.get("id") == milestone_id:
            m["status"] = "completed"
            m["completed_at"] = today
            found = True
            break
    if not found:
        return {"error": f"milestone {milestone_id} not found"}
    storage.write_file(
        path,
        _join_frontmatter(fm, body),
        commit_msg=f"{mid}: milestone {milestone_id} completed",
        author=_author(),
    )
    return {"id": milestone_id, "status": "completed", "completed_at": today}


@mcp.tool()
@_require_role("mentee")
def query_curriculum(question: str) -> dict:
    """
    Answer a curriculum question in a way that anchors to the mentee's
    current roadmap position. Returns a structured context pack: the
    relevant section of the mentee's roadmap, their recent progress log,
    top curriculum pages, and the §4 prompt rules. The host Claude then
    composes the final answer per those rules.

    Args:
        question: The mentee's question in natural language.
    """
    mid = MENTEE_ID_ENV
    roadmap_text = storage.read_file(_roadmap_path(mid))
    if not roadmap_text:
        return {"error": "no roadmap yet; declare_position first"}
    fm, body = _split_frontmatter(roadmap_text)
    if fm.get("status") != "active":
        return {
            "error": f"roadmap status is {fm.get('status')!r}, not active yet"
        }

    week = _current_week(fm)
    section = _extract_week_section(body, week)
    logs = _last_log_entries(storage.read_file(_progress_path(mid)), n=5)
    hits = curriculum.search(question, k=3)

    return {
        "question": question,
        "prompt_guidance": QUERY_CURRICULUM_PROMPT,
        "roadmap_context": {
            "week": week,
            "goal": (fm.get("declared_position") or {}).get("goal"),
            "milestones": fm.get("milestones", []),
            "current_section_markdown": section,
        },
        "recent_progress_log": logs,
        "curriculum_pages": [
            {"slug": p.slug, "title": p.title, "content": p.content}
            for p in hits
        ],
        "instruction_to_claude": (
            "Compose the mentee's answer following prompt_guidance exactly. "
            "Use only the curriculum_pages as factual source. Anchor to "
            f"Week {week} and the mentee's goal. Keep it 100-300 words."
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════
#  MENTOR TOOLS
# ═══════════════════════════════════════════════════════════════════════════

@mcp.tool()
@_require_role("mentor")
def generate_roadmap(
    mentee_id: str,
    draft_markdown: str,
    milestones: list[dict],
) -> dict:
    """
    Write a draft roadmap for a mentee. The mentor (with Claude's help)
    composes draft_markdown using the mentee's declared_position and
    relevant curriculum pages (see resource 'curriculum://search').

    Args:
        mentee_id: Which mentee this roadmap is for
        draft_markdown: Full roadmap body in markdown (week-by-week plan,
            with relative links like ../../curriculum/concepts/xyz.md)
        milestones: List of {id, title, target_week} dicts
    """
    mid = _resolve_mentee_id(mentee_id)
    if not mid:
        return {"error": "mentee_id required"}

    path = _roadmap_path(mid)
    existing = storage.read_file(path)
    fm, _old_body = _split_frontmatter(existing) if existing else ({}, "")
    if not fm.get("declared_position"):
        return {"error": f"{mid} has not declared position yet"}

    fm["status"] = "draft"
    fm["version"] = int(fm.get("version", 0)) + 1
    fm["milestones"] = [
        {**m, "status": m.get("status", "not_started")} for m in milestones
    ]
    fm["drafted_at"] = date.today().isoformat()

    storage.write_file(
        path,
        _join_frontmatter(fm, draft_markdown),
        commit_msg=f"{mid}: draft roadmap v{fm['version']}",
        author=_author(),
    )
    return {
        "status": "draft written",
        "mentee_id": mid,
        "version": fm["version"],
        "next": "Review the draft, then call approve_roadmap to activate it.",
    }


@mcp.tool()
@_require_role("mentor")
def approve_roadmap(mentee_id: str) -> dict:
    """
    Human-in-the-loop gate #1. Flip the draft roadmap to 'active'.
    """
    mid = _resolve_mentee_id(mentee_id)
    if not mid:
        return {"error": "mentee_id required"}

    path = _roadmap_path(mid)
    existing = storage.read_file(path)
    if not existing:
        return {"error": f"no roadmap for {mid}"}
    fm, body = _split_frontmatter(existing)
    if fm.get("status") != "draft":
        return {"error": f"roadmap is {fm.get('status')}, expected draft"}

    fm["status"] = "active"
    fm["approved_at"] = date.today().isoformat()
    storage.write_file(
        path,
        _join_frontmatter(fm, body),
        commit_msg=f"{mid}: approve roadmap v{fm.get('version')}",
        author=_author(),
    )
    return {"status": "active", "mentee_id": mid, "version": fm.get("version")}


@mcp.tool()
@_require_role("mentor")
def give_feedback(
    mentee_id: str,
    subject: str,
    body: str,
) -> dict:
    """
    Human-in-the-loop gate #2. Append mentor feedback to the mentee's
    feedback log after a milestone hit or drift review.

    Args:
        mentee_id: Which mentee this feedback is for
        subject: Short subject line (e.g. "On milestone m1", "On 4-day drift")
        body: The feedback itself (prose, any length)
    """
    mid = _resolve_mentee_id(mentee_id)
    if not mid or mid not in storage.list_mentees():
        return {"error": f"unknown mentee_id: {mentee_id}"}

    today = date.today().isoformat()
    entry = f"\n## {today} — {subject}\n{body.strip()}\n"
    storage.append_file(
        f"mentees/{mid}/feedback-log.md",
        entry,
        commit_msg=f"{mid}: feedback — {subject}",
        author=_author(),
    )
    return {"status": "feedback recorded", "mentee_id": mid, "date": today}


@mcp.tool()
@_require_role("mentor")
def revise_roadmap(
    mentee_id: str,
    reason: str,
    draft_markdown: str,
    milestones: list[dict],
) -> dict:
    """
    Produce a revised roadmap draft. Triggered by drift or a significant
    feedback event. The old roadmap is preserved in git history; this
    overwrites roadmap.md with a new draft the mentor then approves.

    Args:
        mentee_id: Which mentee
        reason: Why the roadmap is being revised (captured in frontmatter)
        draft_markdown: New roadmap body in markdown
        milestones: Updated milestone list
    """
    mid = _resolve_mentee_id(mentee_id)
    if not mid:
        return {"error": "mentee_id required"}

    path = _roadmap_path(mid)
    existing = storage.read_file(path)
    if not existing:
        return {"error": f"no roadmap for {mid} to revise"}
    fm, _old_body = _split_frontmatter(existing)

    revisions = list(fm.get("revisions", []))
    revisions.append({
        "from_version": fm.get("version"),
        "reason": reason,
        "revised_at": date.today().isoformat(),
    })
    fm["status"] = "draft"
    fm["version"] = int(fm.get("version", 0)) + 1
    fm["milestones"] = [
        {**m, "status": m.get("status", "not_started")} for m in milestones
    ]
    fm["revisions"] = revisions
    fm.pop("approved_at", None)
    fm["drafted_at"] = date.today().isoformat()

    storage.write_file(
        path,
        _join_frontmatter(fm, draft_markdown),
        commit_msg=f"{mid}: revise roadmap v{fm['version']} — {reason[:60]}",
        author=_author(),
    )
    return {
        "status": "revised draft written",
        "mentee_id": mid,
        "version": fm["version"],
        "next": "Review, then call approve_roadmap to activate the revision.",
    }


# ═══════════════════════════════════════════════════════════════════════════
#  READ TOOLS (both roles)
# ═══════════════════════════════════════════════════════════════════════════

def _scoped_mentee_id(mentee_id: str | None) -> tuple[str | None, dict | None]:
    """Resolve + scope check. Returns (mid, None) on success, (None, error)."""
    if ROLE == "mentee":
        if mentee_id and mentee_id != MENTEE_ID_ENV:
            return None, {"error": "mentees can only read their own data"}
        return MENTEE_ID_ENV, None
    if not mentee_id:
        return None, {"error": "mentee_id required for mentor"}
    if mentee_id not in storage.list_mentees():
        return None, {"error": f"unknown mentee_id: {mentee_id}"}
    return mentee_id, None


@mcp.tool(meta={"ui": {"resourceUri": ROADMAP_RESOURCE_URI}})
def get_roadmap(mentee_id: str | None = None) -> dict:
    """
    Read a mentee's current roadmap. Mentees see only their own;
    mentors pass mentee_id to see any mentee on the roster.
    """
    mid, err = _scoped_mentee_id(mentee_id)
    if err:
        return err
    text = storage.read_file(_roadmap_path(mid))
    if not text:
        return {"status": "no roadmap yet", "mentee_id": mid}
    fm, body = _split_frontmatter(text)
    result = {
        "mentee_id": mid,
        "status": fm.get("status"),
        "version": fm.get("version"),
        "current_week": _current_week(fm) if fm.get("status") == "active" else None,
        "declared_position": fm.get("declared_position"),
        "milestones": fm.get("milestones", []),
        "body_markdown": body,
    }
    return result


@mcp.tool(meta={"ui": {"resourceUri": ROADMAP_RESOURCE_URI}})
def get_progress_summary(
    mentee_id: str | None = None,
    last_n: int = 7,
) -> dict:
    """
    Read recent progress log entries + simple drift signals. Mentees see
    their own; mentors pass mentee_id.
    """
    mid, err = _scoped_mentee_id(mentee_id)
    if err:
        return err
    roadmap_text = storage.read_file(_roadmap_path(mid))
    fm, _ = _split_frontmatter(roadmap_text) if roadmap_text else ({}, "")
    log_text = storage.read_file(_progress_path(mid))
    entries = _last_log_entries(log_text, n=last_n)

    # Drift signals
    last_log_date = None
    days_since_last_log = None
    dates = _LOG_ENTRY_RE.findall(log_text or "")
    if dates:
        last_log_date = max(dates)
        try:
            days_since_last_log = (
                date.today() - datetime.fromisoformat(last_log_date).date()
            ).days
        except ValueError:
            pass

    return {
        "mentee_id": mid,
        "roadmap_status": fm.get("status"),
        "current_week": _current_week(fm) if fm.get("status") == "active" else None,
        "last_log_date": last_log_date,
        "days_since_last_log": days_since_last_log,
        "drift_flag": (
            "inactivity" if days_since_last_log is not None and days_since_last_log >= 3
            else None
        ),
        "recent_entries": entries,
    }


# ═══════════════════════════════════════════════════════════════════════════
#  RESOURCES
# ═══════════════════════════════════════════════════════════════════════════

@mcp.resource("curriculum://index")
def resource_curriculum_index() -> str:
    """List of all curriculum page slugs."""
    from curriculum import _pages
    return json.dumps(
        [{"slug": p.slug, "title": p.title} for p in _pages], indent=2
    )


@mcp.tool()
def search_curriculum(query: str, k: int = 5) -> dict:
    """
    Full-text search the local curriculum wiki. Returns top-k pages
    with slug, title, and first 800 chars. Available to both roles —
    useful for mentor when drafting a roadmap and for mentee questions.
    """
    hits = curriculum.search(query, k=k)
    return {
        "query": query,
        "results": [
            {"slug": p.slug, "title": p.title, "excerpt": p.content[:800]}
            for p in hits
        ],
    }


@mcp.resource(
    ROADMAP_RESOURCE_URI,
    mime_type=RESOURCE_MIME_TYPE,
    name="Roadmap UI",
    description="Interactive roadmap and progress view",
)
def resource_roadmap_ui() -> str:
    if not UI_HTML_PATH.exists():
        return "<html><body>UI not built — run: cd ui && npm run build</body></html>"
    return UI_HTML_PATH.read_text(encoding="utf-8")


# ═══════════════════════════════════════════════════════════════════════════
#  Entry Point
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys

    transport = sys.argv[1] if len(sys.argv) > 1 else "stdio"

    if transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.run(
            transport="streamable-http",
            host="0.0.0.0",
            port=int(os.environ.get("PORT", 8000)),
        )
