"""
Test Client — Exercises all Learning Coach MCP tools via stdio.
Run: uv run test_client.py
"""
import asyncio
import json

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    server_params = StdioServerParameters(
        command="uv",
        args=["run", "server.py", "stdio"],
    )

    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            # ─── 1. Discover capabilities ─────────────────────
            print("=" * 60)
            print("LEARNING COACH MCP — Test Client")
            print("=" * 60)

            tools = await session.list_tools()
            print(f"\n📦 {len(tools.tools)} tools available:")
            for t in tools.tools:
                print(f"   • {t.name}")

            resources = await session.list_resources()
            print(f"\n📂 {len(resources.resources)} resources:")
            for r in resources.resources:
                print(f"   • {r.uri}")

            prompts = await session.list_prompts()
            print(f"\n💬 {len(prompts.prompts)} prompts:")
            for p in prompts.prompts:
                print(f"   • {p.name}: {p.description}")

            # ─── 2. Set a learning goal ───────────────────────
            print("\n" + "=" * 60)
            print("STEP 1: Setting learning goal...")
            print("=" * 60)

            result = await session.call_tool("set_learning_goal", {
                "goal": "Master AI Agent Development with Python",
                "target_role": "AI Engineer",
                "experience_level": "intermediate",
                "weekly_hours": 12,
                "deadline_weeks": 10,
            })
            print(json.dumps(json.loads(result.content[0].text), indent=2))

            # ─── 3. Generate roadmap ──────────────────────────
            print("\n" + "=" * 60)
            print("STEP 2: Generating personalised roadmap...")
            print("=" * 60)

            result = await session.call_tool("generate_roadmap", {
                "user_context": (
                    "The learner is a software developer with 3 years of Python "
                    "experience, has built REST APIs with FastAPI, understands "
                    "basic ML concepts (supervised learning, neural networks), "
                    "and has used the OpenAI API for simple chatbots. They work "
                    "at a startup and want to transition into an AI engineering "
                    "role. They learn best through building projects and prefer "
                    "documentation over video courses."
                ),
                "focus_areas": ["MCP", "Tool Calling", "RAG", "Multi-Agent Systems"],
                "prerequisites_known": ["Python", "FastAPI", "Basic ML", "OpenAI API"],
            })
            roadmap = json.loads(result.content[0].text)
            print(f"Roadmap created with {len(roadmap['roadmap']['phases'])} phases")

            # ─── 4. Fill in a phase ───────────────────────────
            print("\n" + "=" * 60)
            print("STEP 3: Updating phase with specific content...")
            print("=" * 60)

            result = await session.call_tool("update_roadmap_phase", {
                "phase_name": "Foundation & Setup",
                "topics": [
                    "MCP Protocol Fundamentals",
                    "FastMCP Server Development",
                    "Tool Calling Architecture",
                    "Prompt Engineering for Agents",
                ],
                "milestones": [
                    "Build and test a basic MCP server with 3+ tools",
                    "Connect server to Claude Desktop successfully",
                    "Understand JSON-RPC and transport layers",
                ],
                "resources": [
                    "MCP Python SDK docs: github.com/modelcontextprotocol/python-sdk",
                    "Anthropic's Building Effective Agents guide",
                    "MCP Specification: modelcontextprotocol.io",
                ],
                "projects": [
                    "Personal Knowledge Base MCP Server",
                    "Weather + News Aggregator MCP Server",
                ],
            })
            print(json.dumps(json.loads(result.content[0].text), indent=2))

            # ─── 5. Log some learning sessions ────────────────
            print("\n" + "=" * 60)
            print("STEP 4: Logging learning sessions...")
            print("=" * 60)

            sessions_to_log = [
                {
                    "topic": "MCP Protocol Fundamentals",
                    "duration_minutes": 45,
                    "summary": "Learned about MCP architecture: hosts, clients, servers. Understood the three primitives (tools, resources, prompts) and how JSON-RPC works under the hood.",
                    "confidence_level": 4,
                    "resources_used": ["MCP Specification", "Python SDK README"],
                },
                {
                    "topic": "FastMCP Server Development",
                    "duration_minutes": 60,
                    "summary": "Built a basic MCP server with FastMCP. Created tools with type hints, added resources with URI templates. Tested with MCP Inspector.",
                    "confidence_level": 4,
                    "resources_used": ["Python SDK examples"],
                },
                {
                    "topic": "Tool Calling Architecture",
                    "duration_minutes": 30,
                    "summary": "Studied how Claude processes tool calls. Understood the request/response cycle and how tool results feed back into the conversation.",
                    "confidence_level": 3,
                    "blockers": "Still unclear on how structured output validation works with outputSchema.",
                    "resources_used": ["Anthropic docs"],
                },
            ]

            for s in sessions_to_log:
                result = await session.call_tool("log_learning_session", s)
                parsed = json.loads(result.content[0].text)
                print(f"  ✓ Logged: {s['topic']} ({s['duration_minutes']}min, confidence: {s['confidence_level']}/5)")

            # ─── 6. Check dashboard ───────────────────────────
            print("\n" + "=" * 60)
            print("STEP 5: Progress Dashboard")
            print("=" * 60)

            result = await session.call_tool("get_progress_dashboard", {})
            dashboard = json.loads(result.content[0].text)
            print(f"  Goal: {dashboard.get('goal')}")
            print(f"  Current week: {dashboard.get('current_week')} / {dashboard.get('total_weeks')}")
            print(f"  Total hours: {dashboard.get('total_hours')}")
            print(f"  Sessions: {dashboard.get('total_sessions')}")
            print(f"  Streak: {dashboard.get('streak_days')} days")
            print(f"  Pace: {dashboard.get('pace')}")
            print(f"  Topics explored: {dashboard.get('topics_explored')}")
            if dashboard.get("weak_topics"):
                print(f"  Needs attention: {[t['topic'] for t in dashboard['weak_topics']]}")
            print(f"\n  💡 {dashboard.get('recommendation')}")

            # ─── 7. Topic mastery ─────────────────────────────
            print("\n" + "=" * 60)
            print("STEP 6: Topic Mastery Graph")
            print("=" * 60)

            result = await session.call_tool("get_topic_mastery", {})
            mastery = json.loads(result.content[0].text)
            for name, data in mastery.get("topics", {}).items():
                bar = "█" * int(data["confidence"]) + "░" * (5 - int(data["confidence"]))
                print(f"  {bar} {data['confidence']}/5  {data['name']} ({data['sessions']} sessions, {data['total_minutes']}min)")

            # ─── 8. Read resources ────────────────────────────
            print("\n" + "=" * 60)
            print("STEP 7: Reading 'this-week' resource")
            print("=" * 60)

            result = await session.read_resource("learning://this-week")
            print(f"  {result.contents[0].text}")

            # ─── 9. Get a prompt ──────────────────────────────
            print("\n" + "=" * 60)
            print("STEP 8: Getting 'weekly_checkin' prompt")
            print("=" * 60)

            result = await session.get_prompt("weekly_checkin", {})
            print(f"  {result.messages[0].content.text[:200]}...")

            print("\n" + "=" * 60)
            print("✅ All tests passed! Learning Coach MCP is working.")
            print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
