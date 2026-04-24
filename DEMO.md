# MedianMirror — Demo Script

A 10-minute end-to-end walkthrough. Two Claude Desktop chats, side by
side: one as **mentor**, one as **mentee Arjun**. Every tool exercised,
every artifact visible on GitHub by the end.

## Prereqs (one-time)

1. Both repos cloned:
   - `100x-roadmap-mcp` (this repo)
   - `medianmirror-pilot` (sibling, at `PILOT_REPO_PATH`)
2. `uv sync` inside `100x-roadmap-mcp`.
3. Two entries in `~/Library/Application Support/Claude/claude_desktop_config.json`:
   - `medianmirror-mentor` → `ROLE=mentor`
   - `medianmirror-mentee-arjun` → `ROLE=mentee`, `MENTEE_ID=arjun`
4. Quit and relaunch Claude Desktop. Open two chats, enable the mentor
   server in one and the mentee server in the other.

Keep a third window open on
`github.com/Siddhant-Goswami/medianmirror-pilot/tree/main/mentees/arjun`
— refresh after each step to show the commits landing.

---

## Act 1 — Mentee onboards

**Mentee chat**:
> I'm Arjun. 3 years backend, no ML. I want to ship an AI agent at work
> in 12 weeks. I can put in 10 hours a week.

Claude calls `declare_position`. New commit on GitHub:
`arjun: declare position`. `roadmap.md` now has frontmatter
`status: awaiting_draft` and the declared position captured.

**Teaching beat**: point out that nothing has been generated yet. The
mentee declares; the mentor authors. Two human gates.

---

## Act 2 — Mentor drafts and approves

**Mentor chat**:
> Read Arjun's current state and search the curriculum for AI agent
> foundations. Then draft a 12-week roadmap hitting his goal, with
> milestones at weeks 4, 8, and 12. Submit it for my review before
> approving.

Claude calls `get_roadmap("arjun")`, then `search_curriculum("AI agent
foundations retrieval tools")`, composes the draft, calls
`generate_roadmap(mentee_id="arjun", draft_markdown=..., milestones=[...])`.

Show the draft. Mentor eyeballs.

> Looks good, approve it.

Claude calls `approve_roadmap("arjun")`. Two new commits on GitHub:
`arjun: draft roadmap v1` and `arjun: approve roadmap v1`. `status:`
flips to `active`, `approved_at` stamped.

**Teaching beats**:
- Mentor tool refuses to draft before declare (`declared_position` must
  exist in frontmatter).
- `search_curriculum` returned real Zeno page slugs — the roadmap body
  links to them via relative paths that render as clickable on GitHub.
- Approval is gate #1. Nothing the mentee sees changes until this.

---

## Act 3 — Mentee logs daily

**Mentee chat**:
> Log today: worked 90 minutes on RAG basics and chunking strategies.
> Confidence 3 out of 5. Stuck on when to use semantic vs lexical
> chunking.

Claude calls `log_progress(...)`. New commit: `arjun: log 2026-04-24`.
Response includes `hint` nudging toward `query_curriculum` because
blockers were flagged.

**Teaching beat**: the ritual is one sentence. The MCP turns it into a
dated markdown block in git.

---

## Act 4 — Mentee asks a curriculum question

**Mentee chat** (same thread):
> Yes, answer the chunking question.

Claude calls `query_curriculum("semantic vs lexical chunking")`. The
tool returns:
- `roadmap_context`: current week, mentee's goal, the Week 1-2 section
  verbatim
- `recent_progress_log`: the 90-min entry just written
- `curriculum_pages`: top 3 BM25 hits from the Zeno snapshot (e.g.
  `concepts/retrieval-augmented-generation`)
- `prompt_guidance`: the §4.3 rules (anchor to current week, cite real
  pages, 100-300 words, don't leak future weeks)

Claude composes the answer per those rules.

**Teaching beats** — this is the central product bet:
- The answer is roadmap-aware: opens with "You're in Week 1…"
- Cites a real curriculum page from Arjun's own repo.
- Doesn't advance past Week 1-2, even if Arjun asks about multi-agent
  eval (try it and show the deferral).

---

## Act 5 — Milestone + mentor feedback

**Mentee chat**, some days later (or now, for demo speed):
> Log today: 2 hours, shipped my v0 RAG chatbot. Confidence 4. This is
> milestone m1.

Claude calls `log_progress(..., completed_milestone_id="m1")`. Two
commits: `arjun: log ...` and `arjun: milestone m1 completed`. Roadmap
frontmatter now shows `m1.status: completed` and `m1.completed_at: today`.

Now run the cron manually to show the email:

```bash
uv run python cron.py
```

Output includes: `[MedianMirror] arjun: shipped m1`. With
`RESEND_API_KEY`+`MENTOR_EMAIL` set, it'd land in the mentor's inbox.

**Mentor chat**:
> Check Arjun's recent progress, then draft me a feedback note on his
> milestone — praise the ship, address the chunking confusion from his
> earlier log, tell him to hold on tool-calling and spend a week on
> retrieval edge cases.

Claude calls `get_progress_summary("arjun")`, drafts. Mentor edits.

> Record it.

Claude calls `give_feedback(mentee_id="arjun", subject="On milestone m1", body=...)`.
New commit: `arjun: feedback — On milestone m1`. Gate #2 closes the
milestone loop.

---

## Act 6 — Drift + revision

Simulate drift for teaching purposes (or wait 3 days):

```bash
# backdate approved_at by 5 weeks so m2/m3 look overdue and suppress logs
uv run python cron.py
```

Output: `[MedianMirror] arjun: milestone m2 is 3w overdue` and/or
`[MedianMirror] arjun: 4d since last log`.

**Mentor chat**:
> Arjun's drifting. Let's revise — his team needs a data pipeline agent
> now, not a chatbot. Rewrite weeks 3 onward toward that, keeping the
> retrieval + evals work he's already done. Reason: scope change from
> his manager.

Claude calls `revise_roadmap(mentee_id="arjun", reason="scope change: pipeline not chatbot", draft_markdown=..., milestones=[...])`.

> Approve it.

Claude calls `approve_roadmap("arjun")`. Two new commits: `arjun: revise
roadmap v2 — scope change...` and `arjun: approve roadmap v2`. On
GitHub, click the history on `roadmap.md` to show v1 is preserved — we
didn't lose progress, we rerouted.

**Teaching beat**: revision is not deletion. The mentor can always see
what Arjun was on before, which matters when reviewing progress logs
from the pre-revision weeks.

---

## Act 7 — Scoping and role safety (30 seconds)

**Mentee chat (as Arjun)**:
> Show me Priya's roadmap.

→ `{"error": "mentees can only read their own data"}`.

> Give feedback to Priya on her last milestone.

→ `{"error": "this tool requires ROLE=mentor, current ROLE=mentee"}`.

Two different guards: one enforces role, one enforces scope.

---

## What you just demonstrated

| Act | Tool | Artifact |
|---|---|---|
| 1 | `declare_position` | frontmatter captured |
| 2 | `search_curriculum`, `generate_roadmap`, `approve_roadmap` | draft → active, 2 commits |
| 3 | `log_progress` | daily log entry |
| 4 | `query_curriculum` | roadmap-aware answer, real citations |
| 5 | `log_progress` (with milestone), `cron.py`, `get_progress_summary`, `give_feedback` | milestone email + mentor feedback |
| 6 | `cron.py` (drift), `revise_roadmap`, `approve_roadmap` | v2 draft, v1 preserved in git |
| 7 | role + scope guards | error responses |

All 9 MVP tools + the cron. Every state change is a git commit on
`medianmirror-pilot` authored as `mentor:` or `mentee:<id>`.

---

## Reset between demos

```bash
cd /path/to/medianmirror-pilot
git reset --hard <commit-before-demo>   # or reset to the seed commit
```

Don't delete files by hand — let git do it so the MCP's read cache
stays consistent on the next boot.

## Common gotchas

- **"tool requires ROLE=mentor"** on a mentor action → you're in the
  wrong chat. Each chat is bound to one MCP server (one role) at launch.
- **Tool params look like `args`/`kwargs` generic strings** → you're on
  an old build. Pull latest, relaunch Claude Desktop.
- **`query_curriculum` refuses** → roadmap is still `draft` or
  `awaiting_draft`. Approve it first.
- **Cron prints `[would email]`** → `RESEND_API_KEY` or `MENTOR_EMAIL`
  unset. That's fine for demo; set them for live pilot.
