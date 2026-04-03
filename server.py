"""
Learning Coach MCP Server — Personalised AI Learning Assistant
==============================================================

An MCP server for Claude Desktop that generates hyper-personalised
learning roadmaps by combining:
  1. Claude's native User Memory (read via a user-provided context prompt)
  2. A local knowledge graph that tracks learning goals, weekly progress,
     topics mastered, and roadmap state — without touching User Memory.

Architecture:
  - Claude's User Memory stays untouched. The user shares relevant context
    via the "get_learning_context" prompt, and Claude injects it naturally.
  - This server maintains a SEPARATE local knowledge graph (JSON-backed)
    for learning-specific state: goals, roadmap, weekly logs, topic mastery.
  - All persistence is local — no external DB, no cloud calls.

Run:  uv run server.py
Test: npx @modelcontextprotocol/inspector  →  http://localhost:8000/mcp

MCP Python SDK v1.26.0 | March 2026
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP, Context
from mcp.types import CallToolResult, TextContent

# ─── MCP Apps UI ────────────────────────────────────────────────────────────
RESOURCE_MIME_TYPE = "text/html;profile=mcp-app"
ROADMAP_RESOURCE_URI = "ui://learning-coach/mcp-app.html"
UI_HTML_PATH = Path(__file__).parent / "ui" / "dist" / "mcp-app.html"

# ─── Configuration ──────────────────────────────────────────────────────────

DATA_DIR = Path(os.environ.get(
    "LEARNING_COACH_DATA",
    os.path.expanduser("~/.learning-coach")
))
DATA_DIR.mkdir(parents=True, exist_ok=True)

LEARNER_FILE = DATA_DIR / "learner_profile.json"
ROADMAP_FILE = DATA_DIR / "roadmap.json"
PROGRESS_FILE = DATA_DIR / "progress_log.json"
TOPICS_FILE = DATA_DIR / "topic_graph.json"

# ─── Persistence Helpers ────────────────────────────────────────────────────

def _load(path: Path, default: Any = None) -> Any:
    if default is None:
        default = {}
    if path.exists():
        return json.loads(path.read_text())
    return default


def _save(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, default=str))


# ─── Server ─────────────────────────────────────────────────────────────────

mcp = FastMCP(
    "Learning Coach",
    json_response=True,
)


# ═══════════════════════════════════════════════════════════════════════════
#  TOOLS — Functions the LLM can call
# ═══════════════════════════════════════════════════════════════════════════

# ─── Learner Profile ────────────────────────────────────────────────────

@mcp.tool()
def set_learning_goal(
    goal: str,
    target_role: str = "",
    experience_level: str = "beginner",
    weekly_hours: int = 10,
    deadline_weeks: int = 12,
) -> dict:
    """
    Set or update the learner's primary learning goal.
    This stores the goal locally — it does NOT write to Claude's User Memory.

    Args:
        goal: What the learner wants to achieve (e.g. "Become proficient in MLOps")
        target_role: The role they're aiming for (e.g. "ML Engineer")
        experience_level: Current level — beginner, intermediate, or advanced
        weekly_hours: Hours per week available for learning
        deadline_weeks: Target number of weeks to complete the roadmap
    """
    profile = _load(LEARNER_FILE)
    profile.update({
        "goal": goal,
        "target_role": target_role,
        "experience_level": experience_level,
        "weekly_hours": weekly_hours,
        "deadline_weeks": deadline_weeks,
        "created_at": profile.get("created_at", datetime.now().isoformat()),
        "updated_at": datetime.now().isoformat(),
    })
    _save(LEARNER_FILE, profile)
    return {
        "status": "Goal saved",
        "profile": profile,
        "note": "This is stored locally in the Learning Coach — Claude's User Memory is not modified."
    }


@mcp.tool()
def get_learner_profile() -> dict:
    """
    Retrieve the current learner profile and goal from local storage.
    Returns the goal, experience level, weekly hours, and deadline.
    """
    profile = _load(LEARNER_FILE)
    if not profile:
        return {
            "status": "No profile set yet",
            "hint": "Use set_learning_goal to create your profile."
        }
    return profile


# ─── Roadmap Generation ────────────────────────────────────────────────

@mcp.tool()
def generate_roadmap(
    user_context: str,
    focus_areas: list[str] | None = None,
    prerequisites_known: list[str] | None = None,
) -> dict:
    """
    Generate a personalised learning roadmap.

    IMPORTANT: The 'user_context' parameter should contain relevant details
    from your Claude memory about the user — their background, skills, interests,
    past projects, etc. Claude should gather this from its own memory and pass it
    in. This way we personalise WITHOUT writing to or reading from Claude's
    memory system directly.

    Args:
        user_context: A summary of the user's background, skills, and interests
                      (Claude should populate this from its own User Memory)
        focus_areas: Optional list of specific areas to focus on
        prerequisites_known: Optional list of topics the user already knows
    """
    profile = _load(LEARNER_FILE)
    if not profile.get("goal"):
        return {
            "error": "No learning goal set. Use set_learning_goal first."
        }

    total_weeks = profile.get("deadline_weeks", 12)
    hours_per_week = profile.get("weekly_hours", 10)
    level = profile.get("experience_level", "beginner")

    # Build the roadmap scaffold
    # In production, you'd call an LLM here. For the MCP server,
    # we return a structured template that Claude will enrich.
    roadmap = {
        "id": str(uuid.uuid4())[:8],
        "created_at": datetime.now().isoformat(),
        "goal": profile["goal"],
        "target_role": profile.get("target_role", ""),
        "total_weeks": total_weeks,
        "hours_per_week": hours_per_week,
        "experience_level": level,
        "user_context_summary": user_context[:500],  # Store summary, not full memory
        "focus_areas": focus_areas or [],
        "prerequisites_known": prerequisites_known or [],
        "phases": [],
        "status": "draft",
    }

    # Create phase structure based on weeks
    if total_weeks <= 4:
        phase_names = ["Foundation", "Deep Dive", "Build & Ship"]
        phase_weeks = _distribute_weeks(total_weeks, 3)
    elif total_weeks <= 8:
        phase_names = ["Foundation", "Core Skills", "Advanced Topics", "Build & Ship"]
        phase_weeks = _distribute_weeks(total_weeks, 4)
    else:
        phase_names = [
            "Foundation & Setup",
            "Core Concepts",
            "Intermediate Practice",
            "Advanced Topics",
            "Capstone Project",
        ]
        phase_weeks = _distribute_weeks(total_weeks, 5)

    week_counter = 1
    for name, num_weeks in zip(phase_names, phase_weeks):
        phase = {
            "name": name,
            "start_week": week_counter,
            "end_week": week_counter + num_weeks - 1,
            "weeks": num_weeks,
            "status": "not_started",
            "topics": [],  # Claude will fill these based on user_context
            "milestones": [],
        }
        roadmap["phases"].append(phase)
        week_counter += num_weeks

    _save(ROADMAP_FILE, roadmap)

    return {
        "status": "Roadmap scaffold created",
        "roadmap": roadmap,
        "instruction_to_claude": (
            "Now personalise this roadmap by filling in specific topics, "
            "resources, and milestones for each phase. Use the user_context "
            "provided and the learner's goal to make it deeply relevant. "
            "Then call update_roadmap_phase for each phase with the details."
        ),
    }


@mcp.tool()
def update_roadmap_phase(
    phase_name: str,
    topics: list[str],
    milestones: list[str],
    resources: list[str] | None = None,
    projects: list[str] | None = None,
) -> dict:
    """
    Update a specific phase of the roadmap with personalised content.
    Claude should call this after generate_roadmap to fill in the details.

    Args:
        phase_name: Name of the phase to update (e.g. "Foundation & Setup")
        topics: List of topics to cover in this phase
        milestones: List of checkpoints/milestones for this phase
        resources: Optional list of recommended resources (courses, docs, etc.)
        projects: Optional list of hands-on projects for this phase
    """
    roadmap = _load(ROADMAP_FILE)
    if not roadmap:
        return {"error": "No roadmap exists. Generate one first."}

    for phase in roadmap.get("phases", []):
        if phase["name"].lower() == phase_name.lower():
            phase["topics"] = topics
            phase["milestones"] = milestones
            phase["resources"] = resources or []
            phase["projects"] = projects or []
            _save(ROADMAP_FILE, roadmap)
            return {"status": f"Phase '{phase_name}' updated", "phase": phase}

    return {"error": f"Phase '{phase_name}' not found in roadmap."}


@mcp.tool(
    meta={"ui": {"resourceUri": ROADMAP_RESOURCE_URI}},
)
def get_roadmap() -> dict:
    """
    Get the full current roadmap with all phases, topics, and progress.
    Renders an interactive roadmap.sh-style visualization in supporting hosts.
    """
    roadmap = _load(ROADMAP_FILE)
    if not roadmap:
        msg = "No roadmap exists yet. Use generate_roadmap to create one."
        return CallToolResult(
            content=[TextContent(type="text", text=msg)],
            structuredContent={"status": msg},
        )

    progress = _load(PROGRESS_FILE, default=[])
    topics = _load(TOPICS_FILE)
    roadmap["total_sessions_logged"] = len(progress)
    current_week = _calculate_current_week(roadmap)
    roadmap["current_week"] = current_week

    structured = {
        "roadmap": roadmap,
        "topics": topics,
        "current_week": current_week,
    }
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(structured, default=str))],
        structuredContent=structured,
    )


# ─── Progress Tracking ──────────────────────────────────────────────────

@mcp.tool()
def log_learning_session(
    topic: str,
    duration_minutes: int,
    summary: str,
    confidence_level: int = 3,
    blockers: str = "",
    resources_used: list[str] | None = None,
) -> dict:
    """
    Log a learning session. This is the primary way to track progress.
    Call this at the end of a study session or learning conversation.

    Args:
        topic: What was studied (e.g. "Python decorators", "Transformer architecture")
        duration_minutes: How long the session lasted
        summary: Brief summary of what was learned / accomplished
        confidence_level: Self-assessed confidence 1-5 (1=lost, 3=okay, 5=solid)
        blockers: Any blockers or confusion points
        resources_used: List of resources used during this session
    """
    progress = _load(PROGRESS_FILE, default=[])

    entry = {
        "id": str(uuid.uuid4())[:8],
        "date": date.today().isoformat(),
        "week": _get_current_roadmap_week(),
        "topic": topic,
        "duration_minutes": duration_minutes,
        "summary": summary,
        "confidence_level": confidence_level,
        "blockers": blockers,
        "resources_used": resources_used or [],
        "logged_at": datetime.now().isoformat(),
    }

    progress.append(entry)
    _save(PROGRESS_FILE, progress)

    # Update topic graph
    _update_topic_mastery(topic, confidence_level, duration_minutes)

    return {
        "status": "Session logged",
        "entry": entry,
        "streak": _calculate_streak(progress),
    }


@mcp.tool()
def get_weekly_summary(week_number: int | None = None) -> dict:
    """
    Get a summary of learning activity for a specific week.
    If no week number is given, returns the current week's summary.

    Args:
        week_number: The roadmap week to summarise (default: current week)
    """
    progress = _load(PROGRESS_FILE, default=[])
    target_week = week_number or _get_current_roadmap_week()

    week_entries = [e for e in progress if e.get("week") == target_week]

    if not week_entries:
        return {
            "week": target_week,
            "status": "No sessions logged for this week",
            "hint": "Use log_learning_session to track your study sessions."
        }

    total_minutes = sum(e.get("duration_minutes", 0) for e in week_entries)
    topics_covered = list({e["topic"] for e in week_entries})
    avg_confidence = (
        sum(e.get("confidence_level", 3) for e in week_entries) / len(week_entries)
    )
    blockers = [
        e["blockers"] for e in week_entries
        if e.get("blockers")
    ]

    return {
        "week": target_week,
        "sessions_count": len(week_entries),
        "total_minutes": total_minutes,
        "total_hours": round(total_minutes / 60, 1),
        "topics_covered": topics_covered,
        "average_confidence": round(avg_confidence, 1),
        "blockers": blockers,
        "entries": week_entries,
    }


@mcp.tool(
    meta={"ui": {"resourceUri": ROADMAP_RESOURCE_URI}},
)
def get_progress_dashboard() -> dict:
    """
    Get a comprehensive dashboard of overall learning progress.
    Shows streaks, topic mastery, phase completion, and recommendations.
    Renders an interactive progress dashboard in supporting hosts.
    """
    profile = _load(LEARNER_FILE)
    roadmap = _load(ROADMAP_FILE)
    progress = _load(PROGRESS_FILE, default=[])
    topics = _load(TOPICS_FILE)

    if not profile.get("goal"):
        msg = "Set a learning goal first with set_learning_goal."
        return CallToolResult(
            content=[TextContent(type="text", text=msg)],
            structuredContent={"status": msg},
        )

    total_minutes = sum(e.get("duration_minutes", 0) for e in progress)
    current_week = _get_current_roadmap_week()

    # Identify weak areas (confidence < 3)
    weak_topics = [
        {"topic": name, "confidence": data["confidence"], "sessions": data["sessions"]}
        for name, data in topics.items()
        if data.get("confidence", 0) < 3
    ]

    # Identify strong areas (confidence >= 4)
    strong_topics = [
        {"topic": name, "confidence": data["confidence"], "sessions": data["sessions"]}
        for name, data in topics.items()
        if data.get("confidence", 0) >= 4
    ]

    # Current phase
    current_phase = None
    if roadmap.get("phases"):
        for phase in roadmap["phases"]:
            if phase["start_week"] <= current_week <= phase["end_week"]:
                current_phase = phase["name"]
                break

    target_hours = profile.get("weekly_hours", 10)
    weeks_active = max(1, current_week)
    expected_total_hours = target_hours * weeks_active
    actual_total_hours = round(total_minutes / 60, 1)

    result = {
        "goal": profile.get("goal"),
        "current_week": current_week,
        "total_weeks": roadmap.get("total_weeks", "?"),
        "current_phase": current_phase,
        "total_sessions": len(progress),
        "total_hours": actual_total_hours,
        "expected_hours": expected_total_hours,
        "pace": "on_track" if actual_total_hours >= expected_total_hours * 0.8 else "behind",
        "streak_days": _calculate_streak(progress),
        "topics_explored": len(topics),
        "strong_topics": strong_topics[:5],
        "weak_topics": weak_topics[:5],
        "recommendation": _generate_recommendation(
            weak_topics, strong_topics, current_phase, actual_total_hours, expected_total_hours
        ),
    }
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(result, default=str))],
        structuredContent=result,
    )


@mcp.tool()
def get_topic_mastery() -> dict:
    """
    Get the full topic mastery graph — all topics studied with
    confidence levels, time invested, and last studied date.
    """
    topics = _load(TOPICS_FILE)
    if not topics:
        return {"status": "No topics tracked yet. Log some sessions first."}

    # Sort by confidence (ascending — show weakest first)
    sorted_topics = dict(
        sorted(topics.items(), key=lambda x: x[1].get("confidence", 0))
    )
    return {
        "total_topics": len(sorted_topics),
        "topics": sorted_topics,
    }


@mcp.tool()
def adapt_roadmap(
    reason: str,
    adjustments: str,
) -> dict:
    """
    Record an adaptation to the roadmap based on progress or changing needs.
    This preserves the history of changes for reflection.

    Args:
        reason: Why the roadmap is being adapted (e.g. "Struggling with calculus prerequisites")
        adjustments: Description of changes to make
    """
    roadmap = _load(ROADMAP_FILE)
    if not roadmap:
        return {"error": "No roadmap exists."}

    if "adaptations" not in roadmap:
        roadmap["adaptations"] = []

    adaptation = {
        "date": date.today().isoformat(),
        "week": _get_current_roadmap_week(),
        "reason": reason,
        "adjustments": adjustments,
    }
    roadmap["adaptations"].append(adaptation)
    _save(ROADMAP_FILE, roadmap)

    return {
        "status": "Adaptation recorded",
        "adaptation": adaptation,
        "total_adaptations": len(roadmap["adaptations"]),
        "instruction_to_claude": (
            "Now review the current roadmap phases and update them "
            "based on this adaptation using update_roadmap_phase."
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════
#  RESOURCES — Data the LLM can read
# ═══════════════════════════════════════════════════════════════════════════

@mcp.resource("learning://profile")
def resource_profile() -> str:
    """The learner's current profile and goal."""
    profile = _load(LEARNER_FILE)
    return json.dumps(profile, indent=2) if profile else "No profile set."


@mcp.resource("learning://roadmap")
def resource_roadmap() -> str:
    """The full learning roadmap."""
    roadmap = _load(ROADMAP_FILE)
    return json.dumps(roadmap, indent=2) if roadmap else "No roadmap generated."


@mcp.resource("learning://progress")
def resource_progress() -> str:
    """All learning session logs."""
    progress = _load(PROGRESS_FILE, default=[])
    return json.dumps(progress, indent=2)


@mcp.resource("learning://topics")
def resource_topics() -> str:
    """The topic mastery graph."""
    topics = _load(TOPICS_FILE)
    return json.dumps(topics, indent=2) if topics else "No topics tracked."


@mcp.resource(
    ROADMAP_RESOURCE_URI,
    mime_type=RESOURCE_MIME_TYPE,
    name="Learning Coach UI",
    description="Interactive roadmap and progress dashboard",
)
def resource_roadmap_ui() -> str:
    """MCP Apps HTML resource for the interactive roadmap visualization."""
    if not UI_HTML_PATH.exists():
        return "<html><body>UI not built — run: cd ui && npm run build</body></html>"
    return UI_HTML_PATH.read_text(encoding="utf-8")


@mcp.resource("learning://this-week")
def resource_this_week() -> str:
    """Quick summary of the current week's activity."""
    progress = _load(PROGRESS_FILE, default=[])
    current_week = _get_current_roadmap_week()
    week_entries = [e for e in progress if e.get("week") == current_week]

    if not week_entries:
        return f"Week {current_week}: No sessions logged yet."

    total_mins = sum(e.get("duration_minutes", 0) for e in week_entries)
    topics = list({e["topic"] for e in week_entries})
    return (
        f"Week {current_week}: {len(week_entries)} sessions, "
        f"{round(total_mins/60, 1)} hours, "
        f"Topics: {', '.join(topics)}"
    )


# ═══════════════════════════════════════════════════════════════════════════
#  PROMPTS — Reusable templates for LLM interactions
# ═══════════════════════════════════════════════════════════════════════════

@mcp.prompt()
def get_learning_context() -> str:
    """
    Prompt for Claude to gather and inject the user's context.
    Claude uses its OWN User Memory to fill this in — the MCP server
    never reads or writes to Claude's memory directly.
    """
    return (
        "Before generating or updating the learning roadmap, gather the user's "
        "relevant context from your memory. Include:\n\n"
        "1. Their professional background and current role\n"
        "2. Technical skills they already have\n"
        "3. Past projects or experience relevant to their learning goal\n"
        "4. Their learning style preferences (if known)\n"
        "5. Any constraints (time, budget, location)\n\n"
        "Summarise this context in 2-3 paragraphs. This summary will be passed "
        "to the Learning Coach tools to personalise the roadmap.\n\n"
        "IMPORTANT: Do NOT share sensitive personal information. Only include "
        "professionally relevant details that help personalise the learning path."
    )


@mcp.prompt()
def weekly_checkin() -> str:
    """
    Weekly check-in prompt. Use at the start of each week to review
    progress and plan the upcoming week.
    """
    return (
        "Let's do a weekly learning check-in. Please:\n\n"
        "1. Call get_weekly_summary for last week's data\n"
        "2. Call get_progress_dashboard for the overall picture\n"
        "3. Call get_roadmap to see where we are in the plan\n\n"
        "Then provide:\n"
        "- A brief review of last week (what went well, what didn't)\n"
        "- Whether we're on track with the roadmap\n"
        "- Specific focus areas for this coming week\n"
        "- If any roadmap adaptation is needed, suggest it\n\n"
        "Keep the tone encouraging but honest about progress."
    )


@mcp.prompt()
def end_of_session_log(topic: str = "", duration: str = "30") -> str:
    """
    Quick prompt for logging a learning session.
    Use after any study/learning conversation.

    Args:
        topic: The topic studied (optional, can be inferred)
        duration: Approximate duration in minutes
    """
    return (
        f"Please log this learning session using log_learning_session.\n\n"
        f"Topic: {topic or '(infer from our conversation)'}\n"
        f"Duration: ~{duration} minutes\n\n"
        "Based on our conversation, fill in:\n"
        "- A concise summary of what was learned\n"
        "- A confidence level (1-5) based on how well the user understood\n"
        "- Any blockers or confusion points that came up\n"
        "- Resources we discussed or used"
    )


@mcp.prompt()
def personalise_roadmap() -> str:
    """
    Full roadmap personalisation flow. Use this to kick off
    the entire roadmap generation process.
    """
    return (
        "Let's create a personalised learning roadmap. Follow these steps:\n\n"
        "STEP 1: Check if a learning goal exists (call get_learner_profile).\n"
        "  - If not, ask the user about their goal and call set_learning_goal.\n\n"
        "STEP 2: Gather context from your memory about this user.\n"
        "  - Their background, skills, interests, past work.\n"
        "  - Summarise it in 2-3 paragraphs (do NOT share raw memory data).\n\n"
        "STEP 3: Generate the roadmap scaffold.\n"
        "  - Call generate_roadmap with the user context summary.\n\n"
        "STEP 4: Personalise each phase.\n"
        "  - For each phase, call update_roadmap_phase with:\n"
        "    - Specific, actionable topics tailored to their level\n"
        "    - Concrete milestones (not vague checkpoints)\n"
        "    - Real resources (courses, docs, tutorials)\n"
        "    - Hands-on projects that match their interests\n\n"
        "STEP 5: Present the complete roadmap to the user.\n"
        "  - Show it week-by-week with clear deliverables.\n"
        "  - Highlight how it connects to their background.\n"
        "  - Ask if any adjustments are needed."
    )


# ═══════════════════════════════════════════════════════════════════════════
#  Internal Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _distribute_weeks(total: int, phases: int) -> list[int]:
    """Distribute weeks across phases as evenly as possible."""
    base = total // phases
    remainder = total % phases
    return [base + (1 if i < remainder else 0) for i in range(phases)]


def _calculate_current_week(roadmap: dict) -> int:
    """Calculate the current week based on roadmap creation date."""
    created = roadmap.get("created_at", "")
    if not created:
        return 1
    try:
        created_date = datetime.fromisoformat(created).date()
        days_elapsed = (date.today() - created_date).days
        return max(1, (days_elapsed // 7) + 1)
    except (ValueError, TypeError):
        return 1


def _get_current_roadmap_week() -> int:
    """Get the current roadmap week number."""
    roadmap = _load(ROADMAP_FILE)
    if not roadmap:
        return 1
    return _calculate_current_week(roadmap)


def _update_topic_mastery(topic: str, confidence: int, duration: int) -> None:
    """Update the topic mastery graph with a new data point."""
    topics = _load(TOPICS_FILE)
    key = topic.lower().strip()

    if key not in topics:
        topics[key] = {
            "name": topic,
            "confidence": confidence,
            "total_minutes": duration,
            "sessions": 1,
            "first_studied": date.today().isoformat(),
            "last_studied": date.today().isoformat(),
        }
    else:
        entry = topics[key]
        # Weighted average for confidence — recent sessions matter more
        old_conf = entry.get("confidence", 3)
        entry["confidence"] = round((old_conf * 0.4) + (confidence * 0.6), 1)
        entry["total_minutes"] = entry.get("total_minutes", 0) + duration
        entry["sessions"] = entry.get("sessions", 0) + 1
        entry["last_studied"] = date.today().isoformat()

    _save(TOPICS_FILE, topics)


def _calculate_streak(progress: list[dict]) -> int:
    """Calculate the current daily learning streak."""
    if not progress:
        return 0

    dates = sorted({e.get("date", "") for e in progress if e.get("date")}, reverse=True)
    if not dates:
        return 0

    streak = 0
    check_date = date.today()

    for d in dates:
        try:
            log_date = date.fromisoformat(d)
        except ValueError:
            continue

        if log_date == check_date:
            streak += 1
            check_date -= timedelta(days=1)
        elif log_date < check_date:
            break

    return streak


def _generate_recommendation(
    weak: list, strong: list, phase: str | None,
    actual_hours: float, expected_hours: float,
) -> str:
    """Generate a contextual recommendation based on current state."""
    parts = []

    if actual_hours < expected_hours * 0.5:
        parts.append(
            "You're significantly behind on study hours. "
            "Consider shorter, more frequent sessions to build momentum."
        )
    elif actual_hours < expected_hours * 0.8:
        parts.append(
            "You're slightly behind on hours. "
            "One or two extra sessions this week would get you back on track."
        )
    else:
        parts.append("Great pace — you're keeping up with your target hours.")

    if weak:
        weak_names = [w["topic"] for w in weak[:3]]
        parts.append(
            f"Topics needing more attention: {', '.join(weak_names)}. "
            "Consider revisiting these with practice exercises."
        )

    if strong:
        strong_names = [s["topic"] for s in strong[:2]]
        parts.append(
            f"Strong in: {', '.join(strong_names)}. "
            "You could use these as foundations for more advanced topics."
        )

    if phase:
        parts.append(f"Currently in phase: {phase}.")

    return " ".join(parts)


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
