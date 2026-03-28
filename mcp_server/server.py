"""E25 — DabbahWala MCP Server
Exposes PostgreSQL marketing data to Claude Desktop via the MCP protocol.
Tool groups: contacts, analytics, communications, recommendations, opportunities, agents.
"""
import json
import logging
import os
import sys

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

logger = logging.getLogger(__name__)

# Base URL for the FastAPI app — override with DABBAHWALA_API_URL env var
_API_BASE = os.environ.get("DABBAHWALA_API_URL", "http://localhost:8000")

app = Server("dabbahwala")


async def _get(path: str, params: dict = None) -> dict:
    async with httpx.AsyncClient(timeout=30) as http:
        resp = await http.get(f"{_API_BASE}{path}", params=params or {})
        resp.raise_for_status()
        return resp.json()


async def _post(path: str, json_body: dict = None, params: dict = None) -> dict:
    async with httpx.AsyncClient(timeout=30) as http:
        resp = await http.post(f"{_API_BASE}{path}", json=json_body or {}, params=params or {})
        resp.raise_for_status()
        return resp.json()


# ── Story 25.1: Server setup ──────────────────────────────────────────────────

@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        # ── Contacts ──────────────────────────────────────────────────────────
        Tool(
            name="get_contact",
            description="Get full details for a contact by ID",
            inputSchema={
                "type": "object",
                "properties": {
                    "contact_id": {"type": "integer", "description": "Contact ID"}
                },
                "required": ["contact_id"],
            },
        ),
        Tool(
            name="search_contacts",
            description="List contacts filtered by segment, opted_out status, with pagination",
            inputSchema={
                "type": "object",
                "properties": {
                    "segment": {"type": "string", "description": "Lifecycle segment (e.g. warm, active, lapsed)"},
                    "opted_out": {"type": "boolean"},
                    "limit": {"type": "integer", "default": 20},
                    "offset": {"type": "integer", "default": 0},
                },
            },
        ),
        Tool(
            name="get_contact_history",
            description="Get events and SMS messages for a contact",
            inputSchema={
                "type": "object",
                "properties": {
                    "contact_id": {"type": "integer"}
                },
                "required": ["contact_id"],
            },
        ),

        # ── Analytics ─────────────────────────────────────────────────────────
        Tool(
            name="daily_summary",
            description="Get key marketing metrics for a date (default today)",
            inputSchema={
                "type": "object",
                "properties": {
                    "report_date": {"type": "string", "description": "ISO date (YYYY-MM-DD)"}
                },
            },
        ),
        Tool(
            name="weekly_summary",
            description="Get aggregated metrics for the last 7 days",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="segments_breakdown",
            description="Count contacts by lifecycle segment",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="top_customers",
            description="Top customers by order count",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 20}
                },
            },
        ),
        Tool(
            name="run_named_query",
            description=(
                "Run a pre-approved named SQL query. Available: contacts_by_segment, top_customers, "
                "recent_orders, opted_out_contacts, lapsed_contacts, campaign_push_log, event_counts, sms_activity"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query_name": {"type": "string"}
                },
                "required": ["query_name"],
            },
        ),

        # ── Communications ────────────────────────────────────────────────────
        Tool(
            name="get_sms_messages",
            description="Get recent SMS messages for a contact",
            inputSchema={
                "type": "object",
                "properties": {
                    "contact_id": {"type": "integer"},
                    "limit": {"type": "integer", "default": 20},
                },
                "required": ["contact_id"],
            },
        ),
        Tool(
            name="send_field_agent_sms",
            description="Send an SMS from a field agent to a contact",
            inputSchema={
                "type": "object",
                "properties": {
                    "contact_id": {"type": "integer"},
                    "body": {"type": "string"},
                    "agent_name": {"type": "string"},
                },
                "required": ["contact_id", "body", "agent_name"],
            },
        ),

        # ── Recommendations ───────────────────────────────────────────────────
        Tool(
            name="get_reorder_suggestion",
            description="Get AI-powered reorder suggestions for a contact based on their history",
            inputSchema={
                "type": "object",
                "properties": {
                    "contact_id": {"type": "integer"}
                },
                "required": ["contact_id"],
            },
        ),
        Tool(
            name="chatbot_ask",
            description="Ask DabbahWala's AI assistant a question (optionally with contact context)",
            inputSchema={
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                    "contact_id": {"type": "integer"},
                },
                "required": ["message"],
            },
        ),

        # ── Opportunities ─────────────────────────────────────────────────────
        Tool(
            name="list_opportunities",
            description="List open sales/retention opportunities",
            inputSchema={
                "type": "object",
                "properties": {
                    "status": {"type": "string", "default": "open"},
                    "limit": {"type": "integer", "default": 20},
                },
            },
        ),
        Tool(
            name="get_pending_actions",
            description="Get pending agent action queue items",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 20}
                },
            },
        ),

        # ── Agents ────────────────────────────────────────────────────────────
        Tool(
            name="run_agent_cycle",
            description="Run the full AI agent pipeline for a specific contact",
            inputSchema={
                "type": "object",
                "properties": {
                    "contact_id": {"type": "integer"}
                },
                "required": ["contact_id"],
            },
        ),
        Tool(
            name="growth_analysis",
            description="Get AI growth analysis with recommendations for DabbahWala",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="goal_progress",
            description="Check current month goal progress vs targets",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


# ── Story 25.2: Contact & analytics tools ─────────────────────────────────────
# ── Story 25.3: Communication & action tools ──────────────────────────────────

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        result = await _dispatch_tool(name, arguments)
        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]
    except httpx.HTTPStatusError as exc:
        error = {"error": str(exc), "status_code": exc.response.status_code}
        return [TextContent(type="text", text=json.dumps(error))]
    except Exception as exc:
        logger.error("MCP tool %s failed: %s", name, exc)
        return [TextContent(type="text", text=json.dumps({"error": str(exc)}))]


async def _dispatch_tool(name: str, args: dict) -> dict:
    if name == "get_contact":
        return await _get(f"/api/contacts/{args['contact_id']}")

    if name == "search_contacts":
        params = {k: v for k, v in args.items() if v is not None}
        return await _get("/api/contacts/", params)

    if name == "get_contact_history":
        return await _get(f"/api/contacts/{args['contact_id']}/history")

    if name == "daily_summary":
        params = {}
        if args.get("report_date"):
            params["report_date"] = args["report_date"]
        return await _get("/api/reports/daily-summary", params)

    if name == "weekly_summary":
        return await _get("/api/reports/weekly-summary")

    if name == "segments_breakdown":
        return await _get("/api/query/named/contacts_by_segment")

    if name == "top_customers":
        return await _get("/api/shipday/top-calls", {"limit": args.get("limit", 20)})

    if name == "run_named_query":
        return await _get(f"/api/query/named/{args['query_name']}")

    if name == "get_sms_messages":
        history = await _get(f"/api/contacts/{args['contact_id']}/history")
        return {"messages": history.get("messages", [])[:args.get("limit", 20)]}

    if name == "send_field_agent_sms":
        return await _post("/api/telnyx/field-agent-message", {
            "contact_id": args["contact_id"],
            "body": args["body"],
            "agent_name": args["agent_name"],
        })

    if name == "get_reorder_suggestion":
        return await _post(f"/api/chatbot/suggest?contact_id={args['contact_id']}")

    if name == "chatbot_ask":
        payload = {"message": args["message"]}
        if args.get("contact_id"):
            payload["contact_id"] = args["contact_id"]
        return await _post("/api/chatbot/ask", payload)

    if name == "list_opportunities":
        params = {"status_filter": args.get("status", "open"), "limit": args.get("limit", 20)}
        return await _get("/api/intelligence/opportunities", params)

    if name == "get_pending_actions":
        return await _get("/api/agents/action-queue/pending", {"limit": args.get("limit", 20)})

    if name == "run_agent_cycle":
        return await _post(
            "/api/agents/cycle/run-for-contact",
            params={"contact_id": args["contact_id"]}
        )

    if name == "growth_analysis":
        return await _get("/api/growth/analysis")

    if name == "goal_progress":
        return await _get("/api/growth/goals/progress")

    return {"error": f"Unknown tool: {name}"}


def main():
    """Entry point for MCP server — runs via stdio."""
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    import asyncio
    asyncio.run(stdio_server(app))


if __name__ == "__main__":
    main()
