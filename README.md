# 🧠 Learning Coach MCP Server

**A personalised AI learning assistant that generates hyper-personalised roadmaps using Claude's User Memory + MCP — without compromising memory privacy.**

Built with MCP Python SDK v1.26.0 | Runs as a Claude Desktop MCP Server

---

## The Core Idea

```
┌──────────────────────────────────────────────────────────────────┐
│                        CLAUDE DESKTOP                            │
│                                                                  │
│   ┌──────────────────┐         ┌──────────────────────────────┐ │
│   │  Claude's Native │         │   Learning Coach MCP Server  │ │
│   │  User Memory     │         │                              │ │
│   │                  │         │   Tools:                     │ │
│   │  • Background    │ ──(1)──▶│   • set_learning_goal        │ │
│   │  • Skills        │  Claude │   • generate_roadmap         │ │
│   │  • Interests     │ reads & │   • log_learning_session     │ │
│   │  • Preferences   │ passes  │   • get_progress_dashboard   │ │
│   │  • Past projects │ context │   • get_weekly_summary       │ │
│   │                  │         │   • adapt_roadmap            │ │
│   │  ❌ NOT modified │         │                              │ │
│   │  by this server  │         │   Local Storage:             │ │
│   └──────────────────┘         │   ~/.learning-coach/         │ │
│                                │   ├── learner_profile.json   │ │
│                                │   ├── roadmap.json           │ │
│                                │   ├── progress_log.json      │ │
│                                │   └── topic_graph.json       │ │
│                                └──────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
```

**How memory privacy works:**
1. Claude reads its own User Memory about you (background, skills, etc.)
2. Claude summarises relevant context and passes it to the roadmap generator
3. The MCP server stores only learning-specific data in a separate local directory
4. Claude's User Memory is **never read or written to** by the MCP server

---

## Features

### 🎯 Roadmap Generation
- Multi-phase roadmaps personalised to your background
- Specific topics, milestones, resources, and projects per phase
- Adapts based on progress and changing needs

### 📊 Progress Tracking
- Log learning sessions with topic, duration, and confidence
- Weekly summaries with hours, topics, and blockers
- Daily streak tracking for motivation

### 🧬 Topic Mastery Graph
- Tracks confidence per topic over time (weighted recent sessions higher)
- Identifies weak areas needing attention
- Shows strong foundations you can build on

### 📈 Smart Dashboard
- Overall pace vs. target hours
- Current phase and week indicator
- AI-generated recommendations based on your data

### 🖥️ MCP App UI
- Interactive in-host UI for roadmap and dashboard views
- Automatically used by supporting MCP clients when calling key tools
- Host-theme aware (uses MCP Apps style tokens and safe areas)

### 🔄 Adaptive Learning
- Record roadmap adaptations with reasons
- Full history of changes for reflection
- Claude suggests adjustments during weekly check-ins

---

## Quick Start

### 1. Install

```bash
# Clone or create the project
git clone <your-repo> learning-coach-mcp
cd learning-coach-mcp

# Install dependencies
uv sync
```

### 2. Test Locally

```bash
# Run the test client (exercises all tools)
uv run test_client.py

# Or test with MCP Inspector
uv run server.py http  # Start HTTP server
# Then: npx @modelcontextprotocol/inspector
# Connect to: http://localhost:8000/mcp
```

### 2.5 Build the MCP UI (optional but recommended)

The interactive MCP App UI is served from `ui/dist/mcp-app.html`.  
If it is not built, the server falls back to a simple HTML message.

```bash
cd ui
npm install
npm run build
```

After build, the server exposes the UI resource:

- `ui://learning-coach/mcp-app.html`

### 3. Connect to Claude Desktop

Edit your Claude Desktop config:

**macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
**Linux:** `~/.config/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "learning-coach": {
      "command": "uv",
      "args": [
        "--directory", "/absolute/path/to/learning-coach-mcp",
        "run", "server.py", "stdio"
      ]
    }
  }
}
```

**Restart Claude Desktop** after editing.

---

## Usage — Conversation Flows

### 🚀 First Time Setup

> **You:** "I want to learn AI agent development. Can you create a learning roadmap for me?"
>
> **Claude:** *(reads its memory about you, calls set_learning_goal, then generate_roadmap with your context, fills in each phase with update_roadmap_phase)*
>
> "Based on your experience with Python and FastAPI, here's your 10-week roadmap..."

### 📝 After a Study Session

> **You:** "I just spent 45 minutes learning about RAG architectures"
>
> **Claude:** *(calls log_learning_session with topic, duration, summary, confidence)*
>
> "Logged! You're at 3 sessions this week. Your confidence in RAG is at 3/5 — want to dive deeper into retrieval strategies?"

### 📅 Weekly Check-in

> **You:** "Let's do a weekly check-in"
>
> **Claude:** *(calls get_weekly_summary, get_progress_dashboard, get_roadmap)*
>
> "Week 3 summary: 4 sessions, 3.5 hours. You're slightly behind your 12hr/week target. Strong on MCP fundamentals, but Tool Calling needs more practice. This week, focus on..."

### 🔄 Adapting the Plan

> **You:** "I'm finding the math prerequisites for ML harder than expected"
>
> **Claude:** *(calls adapt_roadmap, then updates affected phases)*
>
> "I've recorded this adaptation and adjusted your roadmap. I've added a 'Math Foundations' sprint to Week 4-5 before we hit the advanced ML topics..."

---

## Tools Reference

| Tool | Purpose |
|------|---------|
| `set_learning_goal` | Set/update your learning goal, target role, and schedule |
| `get_learner_profile` | Retrieve your current profile and goal |
| `generate_roadmap` | Create a personalised multi-phase roadmap |
| `update_roadmap_phase` | Fill in specific topics, milestones, resources per phase |
| `get_roadmap` | Get the full roadmap with progress |
| `log_learning_session` | Log a study session (topic, duration, confidence) |
| `get_weekly_summary` | Week-level summary of sessions and hours |
| `get_progress_dashboard` | Full dashboard with pace, streaks, recommendations |
| `get_topic_mastery` | All topics with confidence levels and time invested |
| `adapt_roadmap` | Record and apply roadmap changes |

## Resources (auto-available)

| URI | Contents |
|-----|----------|
| `learning://profile` | Learner profile and goal |
| `learning://roadmap` | Full roadmap JSON |
| `learning://progress` | All session logs |
| `learning://topics` | Topic mastery graph |
| `ui://learning-coach/mcp-app.html` | MCP App HTML (interactive roadmap/dashboard UI) |
| `learning://this-week` | Quick current week summary |

## MCP UI Rendering

The following tools are UI-enabled and render the MCP App in supporting hosts:

- `get_roadmap`
- `get_progress_dashboard`

Both return `structuredContent` plus a `ui` resource reference, allowing hosts to show a rich interactive view instead of plain text output.

## Prompts (reusable templates)

| Prompt | Use Case |
|--------|----------|
| `get_learning_context` | Guides Claude to gather user context from memory |
| `weekly_checkin` | Structured weekly review flow |
| `end_of_session_log` | Quick logging after a study conversation |
| `personalise_roadmap` | Full roadmap generation workflow |

---

## Data Storage

All data is stored locally in `~/.learning-coach/` (configurable via `LEARNING_COACH_DATA` env var):

```
~/.learning-coach/
├── learner_profile.json    # Goal, role, schedule
├── roadmap.json            # Full roadmap with phases
├── progress_log.json       # All session entries
└── topic_graph.json        # Topic mastery data
```

Data is plain JSON — you can inspect, edit, or back it up manually.

---

## Architecture Decisions

### Why NOT read Claude's memory directly?

1. **Privacy**: Claude's User Memory may contain personal details unrelated to learning
2. **Separation of concerns**: Learning state ≠ identity state
3. **No API exists**: MCP servers cannot access Claude's internal memory system
4. **Better design**: Claude acts as the *broker* — it knows the user and translates relevant context to the learning system

### Why local JSON instead of a database?

1. **Zero dependencies**: No SQLite, no Postgres, nothing to install
2. **Human-readable**: You can open and inspect your data anytime
3. **Portable**: Copy the folder to move your learning history
4. **Sufficient**: For a single-user learning assistant, JSON is plenty fast

### Why stdio transport for Claude Desktop?

Claude Desktop uses stdio to communicate with local MCP servers. The server also supports Streamable HTTP for testing with MCP Inspector or for remote deployment.

---

## Extending This

Ideas for building on top of this:

- **Spaced repetition**: Use the topic mastery graph to schedule review sessions
- **Resource scraping**: Add tools that fetch and summarise learning resources
- **Calendar integration**: Connect to Google Calendar MCP to block study time
- **LLM-powered summaries**: Call the Anthropic API from within tools for richer analysis
- **Multi-learner support**: Add user_id parameter for cohort-based deployments
- **Export to Notion/Obsidian**: Add tools that export roadmaps as markdown

---

## License

MIT
