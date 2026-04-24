# MedianMirror Roadmap MCP

A local MCP server for a mentor-mentee learning program. Mentor drafts a
personalised roadmap per mentee, mentee logs progress daily, mentee asks
roadmap-aware curriculum questions. Everything is markdown files in a
git repo — the mentor reads it on GitHub, the mentee reads it through
Claude.

Forked from `100x-roadmap-mcp` (v1) and extended for a 2-week pilot with
one mentor and up to five mentees.

## Architecture

- **One Python MCP server** (`server.py`) — local stdio, role-gated by
  env vars.
- **One pilot-data git repo** (separate, local clone at `PILOT_REPO_PATH`)
  holding all mentee state + a snapshot of the Zeno curriculum wiki.
- **One cron script** (`cron.py`) — runs once/day, emits emails via
  Resend on milestones + drift.
- **Four conversation patterns** in Claude Desktop — mentee onboarding,
  mentee daily log, mentee curriculum question, mentor review.

```
Claude Desktop (mentor)          Claude Desktop (mentee)
        │                                │
        │    stdio                       │    stdio
        ▼                                ▼
     server.py  ──────────────────────────→  pilot-data/
     (ROLE=mentor)              (ROLE=mentee, MENTEE_ID=arjun)
                    git commits on every write
                              ↑
                              │
                       cron.py (daily)
                              │
                              ▼
                         Resend → mentor email
```

## The nine tools

| Tool | Role | Effect |
|---|---|---|
| `declare_position` | mentee | Seed roadmap frontmatter with goal/background/hours |
| `generate_roadmap` | mentor | Write a draft roadmap for a mentee |
| `approve_roadmap` | mentor | Flip draft → active (gate #1) |
| `log_progress` | mentee | Append dated entry to progress log; optional milestone completion |
| `query_curriculum` | mentee | Return roadmap-anchored context pack for host Claude to compose an answer |
| `give_feedback` | mentor | Append to feedback log (gate #2) |
| `revise_roadmap` | mentor | Produce a new draft; old preserved in git history |
| `get_roadmap` | both (scoped) | Read current roadmap |
| `get_progress_summary` | both (scoped) | Recent logs + drift signals |

Plus `search_curriculum` as a shared helper for mentors drafting roadmaps.

## Pilot data repo layout

```
medianmirror-pilot/
├── mentees/<id>/
│   ├── roadmap.md          # YAML frontmatter + prose body
│   ├── progress-log.md     # append-only, dated
│   └── feedback-log.md     # mentor-written
├── mentor/roster.md
├── curriculum/             # snapshot of Zeno wiki (96 markdown pages)
│   ├── concepts/  entities/  sources/  synthesis/  index.md
└── shared/cohort-context.md
```

Every write from the MCP is a git commit authored as `role:id` (e.g.
`mentor-mentor` or `mentee-arjun`). The mentor can read all of it in
plain GitHub; the mentee can too, but usually works through Claude.

## Setup

```bash
# 1. Clone both repos side-by-side
git clone https://github.com/Siddhant-Goswami/100x-roadmap-mcp.git
git clone https://github.com/Siddhant-Goswami/medianmirror-pilot.git

# 2. Install Python deps
cd 100x-roadmap-mcp && uv sync

# 3. (Optional) Build the UI
cd ui && npm install && npm run build && cd ..
```

## Claude Desktop config

Add two entries to
`~/Library/Application Support/Claude/claude_desktop_config.json` —
one for the mentor, one for each mentee you're testing.

```json
{
  "mcpServers": {
    "medianmirror-mentor": {
      "command": "/Users/you/.local/bin/uv",
      "args": ["run", "--directory", "/path/to/100x-roadmap-mcp", "server.py", "stdio"],
      "env": {
        "ROLE": "mentor",
        "PILOT_REPO_PATH": "/path/to/medianmirror-pilot"
      }
    },
    "medianmirror-mentee-arjun": {
      "command": "/Users/you/.local/bin/uv",
      "args": ["run", "--directory", "/path/to/100x-roadmap-mcp", "server.py", "stdio"],
      "env": {
        "ROLE": "mentee",
        "MENTEE_ID": "arjun",
        "PILOT_REPO_PATH": "/path/to/medianmirror-pilot"
      }
    }
  }
}
```

In practice, each mentee runs the MCP on their own laptop with their own
`MENTEE_ID`, so there's no collision.

## Running the cron

```bash
MENTOR_EMAIL=you@example.com \
RESEND_API_KEY=re_... \
PILOT_REPO_PATH=/path/to/medianmirror-pilot \
REPO_LINK_BASE=https://github.com/you/medianmirror-pilot/blob/main \
  uv run python cron.py
```

If `RESEND_API_KEY` or `MENTOR_EMAIL` is unset, events print to stdout —
useful for dev. Schedule with `launchd` on macOS (daily at 06:00 IST is
the spec default).

Three rules, no LLM calls:
1. **milestone** — any milestone with `completed_at == today`
2. **inactivity** — ≥ `INACTIVITY_DAYS` (default 3) since last log
3. **pace** — any non-completed milestone `target_week` is more than
   `PACE_SLACK_WEEKS` (default 1) behind the mentee's current week

## The four conversation patterns

**A. Mentee onboarding (one-time)**

> Mentee: "I'm Arjun. 3 years backend, no ML. I want to ship an AI agent
> at work in 12 weeks. 10 hours/week."
> Claude → `declare_position`.

**B. Mentee daily log (ritual)**

> Mentee: "Log today: 1.5h on RAG chunking, confidence 3, stuck on
> semantic vs lexical."
> Claude → `log_progress`, then offers `query_curriculum`.

**C. Mentee curriculum question (ad-hoc)**

> Mentee: "When should I use semantic vs lexical chunking?"
> Claude → `query_curriculum` → composes answer anchored to Week X and
> mentee's goal, using only the returned curriculum pages.

**D. Mentor review (on milestone or drift email)**

> Mentor: "Draft feedback for Arjun on m1 — praise the ship, flag
> chunking confusion, tell him to hold on tool-calling."
> Claude → `get_roadmap` + `get_progress_summary` → drafts → mentor
> edits → `give_feedback`.

## Storage model

- **Source of truth**: the `medianmirror-pilot` git repo.
- **Read cache**: in-memory dict in `storage.py`, invalidated on write.
- **Writes**: file modify + `git add && git commit` (no automatic push;
  push is manual or cron-scheduled).
- **Curriculum**: read-only from the MCP; re-seed by re-cloning Zeno.
- **Curriculum search**: BM25 over ~90 markdown pages, built once at
  server startup.

## What's deliberately not in the MVP

- Topic mastery graphs, weekly summaries, adaptation history as their
  own tools — v1 had these; they're noise for five mentees.
- OAuth. Role comes from an env var at launch.
- Auto-push to GitHub. The mentor runs `git push` (or a cron does).
- The MCP itself calling Claude API. `query_curriculum` returns a
  context pack; the host Claude composes the final answer. One LLM
  call per mentee question, not two.

## Repo layout

```
.
├── server.py          # FastMCP server, 9 tools + 1 helper
├── storage.py         # git-backed read/write/append
├── curriculum.py      # BM25 index over pilot-data/curriculum/
├── cron.py            # daily drift + milestone checker
├── ui/                # MCP Apps HTML UI (React + Vite)
└── pyproject.toml
```
