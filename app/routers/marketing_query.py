"""E22 — Marketing Query"""
import logging
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.db import get_cursor
from app.services.llm_service import SONNET, call_claude

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/query", tags=["query"])

# Named queries — pre-approved safe SQL for common marketing questions
_NAMED_QUERIES: dict[str, dict] = {
    "contacts_by_segment": {
        "description": "Count contacts per lifecycle segment",
        "sql": """
            SELECT lifecycle_segment::TEXT AS segment, COUNT(*) AS count
            FROM dabbahwala.contacts
            WHERE opted_out = FALSE
            GROUP BY lifecycle_segment ORDER BY count DESC
        """,
        "params": [],
    },
    "top_customers": {
        "description": "Top 20 customers by order count",
        "sql": """
            SELECT id, name, email, phone, order_count, total_spent,
                   lifecycle_segment::TEXT AS segment, last_order_at
            FROM dabbahwala.contacts
            WHERE opted_out = FALSE
            ORDER BY order_count DESC, total_spent DESC
            LIMIT 20
        """,
        "params": [],
    },
    "recent_orders": {
        "description": "Orders in the last 7 days",
        "sql": """
            SELECT o.id, o.order_ref, o.total_amount, o.status, o.created_at,
                   c.name, c.email
            FROM dabbahwala.orders o
            JOIN dabbahwala.contacts c ON c.id = o.contact_id
            WHERE o.created_at >= NOW() - INTERVAL '7 days'
            ORDER BY o.created_at DESC
            LIMIT 100
        """,
        "params": [],
    },
    "opted_out_contacts": {
        "description": "Contacts who have opted out",
        "sql": """
            SELECT id, name, email, phone, updated_at
            FROM dabbahwala.contacts
            WHERE opted_out = TRUE
            ORDER BY updated_at DESC LIMIT 200
        """,
        "params": [],
    },
    "lapsed_contacts": {
        "description": "Contacts with no order in 30+ days",
        "sql": """
            SELECT id, name, email, phone, lifecycle_segment::TEXT AS segment,
                   order_count, last_order_at
            FROM dabbahwala.contacts
            WHERE opted_out = FALSE
              AND order_count > 0
              AND (last_order_at IS NULL OR last_order_at < NOW() - INTERVAL '30 days')
            ORDER BY last_order_at ASC NULLS FIRST
            LIMIT 200
        """,
        "params": [],
    },
    "campaign_push_log": {
        "description": "Recent campaign push log entries",
        "sql": """
            SELECT * FROM dabbahwala.campaign_push_log
            ORDER BY pushed_at DESC LIMIT 100
        """,
        "params": [],
    },
    "event_counts": {
        "description": "Event type counts over the last 30 days",
        "sql": """
            SELECT event_type, COUNT(*) AS count
            FROM dabbahwala.events
            WHERE created_at >= NOW() - INTERVAL '30 days'
            GROUP BY event_type ORDER BY count DESC
        """,
        "params": [],
    },
    "sms_activity": {
        "description": "Inbound vs outbound SMS in the last 7 days",
        "sql": """
            SELECT direction, COUNT(*) AS count
            FROM dabbahwala.telnyx_messages
            WHERE created_at >= NOW() - INTERVAL '7 days'
            GROUP BY direction
        """,
        "params": [],
    },
}


class FreeQueryRequest(BaseModel):
    question: str
    max_rows: int = 50


# ── Story 22.1: Named queries ─────────────────────────────────────────────────

@router.get("/named")
def list_named_queries():
    return {
        "queries": [
            {"name": k, "description": v["description"]}
            for k, v in _NAMED_QUERIES.items()
        ]
    }


@router.get("/named/{query_name}")
def run_named_query(query_name: str):
    if query_name not in _NAMED_QUERIES:
        return JSONResponse(status_code=404, content={"detail": f"Unknown query: {query_name}"})
    q = _NAMED_QUERIES[query_name]
    with get_cursor() as cur:
        cur.execute(q["sql"], q["params"])
        rows = [dict(r) for r in cur.fetchall()]
    return {"query": query_name, "description": q["description"], "rows": rows, "count": len(rows)}


# ── Story 22.2: Free-form Claude query ────────────────────────────────────────

_SCHEMA_SUMMARY = """
DabbahWala PostgreSQL schema (dabbahwala schema):
- contacts(id, email, phone, name, lifecycle_segment, opted_out, order_count, total_spent, last_order_at, created_at)
- orders(id, contact_id, order_ref, total_amount, status, created_at)
- order_items(id, order_id, item_name, quantity)
- events(id, contact_id, event_type, payload, created_at)
- telnyx_messages(id, contact_id, direction, body, status, created_at)
- campaign_push_log(id, contact_id, campaign_name, lifecycle_segment, status, pushed_at)
- orchestrator_log(id, contact_id, action_taken, reasoning, created_at)
- action_queue(id, contact_id, action_type, payload, status, created_at)
- menu_catalog(id, name, category, price, is_available)
- agent_playbook(id, category, rule_text, segment, priority, is_active)
- field_calls(id, contact_id, agent_name, outcome, notes, created_at)

lifecycle_segment values: cold, warm, active, champion, lapsed, cooling, optout
All tables are in the dabbahwala schema. Use fully qualified names like dabbahwala.contacts.
Write only SELECT queries — no INSERT/UPDATE/DELETE/DROP.
"""


@router.post("/ask")
def free_form_query(req: FreeQueryRequest):
    """
    Natural language marketing query — Claude generates SQL, we execute it.
    Returns rows + the SQL used.
    """
    system = (
        "You are a PostgreSQL expert for DabbahWala marketing analytics. "
        "Given a natural language question, return a safe SELECT SQL query only — no explanation, no markdown. "
        "Never use INSERT, UPDATE, DELETE, DROP, TRUNCATE or any DDL/DML. "
        "Use dabbahwala schema prefix on all tables.\n\n"
        + _SCHEMA_SUMMARY
    )
    messages = [{"role": "user", "content": f"Question: {req.question}\n\nSQL query:"}]

    try:
        resp = call_claude(SONNET, system, messages, max_tokens=512)
        sql = next((b.text for b in resp.content if b.type == "text"), "").strip()
    except Exception as exc:
        return JSONResponse(status_code=500, content={"detail": f"Claude error: {exc}"})

    # Safety guard — block write operations
    sql_upper = sql.upper()
    for forbidden in ("INSERT", "UPDATE", "DELETE", "DROP", "TRUNCATE", "ALTER", "CREATE", "GRANT"):
        if forbidden in sql_upper:
            return JSONResponse(
                status_code=400,
                content={"detail": f"Generated SQL contains forbidden operation: {forbidden}"}
            )

    try:
        with get_cursor() as cur:
            cur.execute(sql)
            rows = [dict(r) for r in cur.fetchmany(req.max_rows)]
        return {
            "question": req.question,
            "sql": sql,
            "rows": rows,
            "count": len(rows),
        }
    except Exception as exc:
        return JSONResponse(
            status_code=422,
            content={"detail": f"SQL execution error: {exc}", "sql": sql}
        )
