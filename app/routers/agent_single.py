"""
E08 — Single-Agent Router
Specialized endpoints for individual agent calls, useful for debugging and experiments.
"""
import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.db import get_cursor
from app.services.llm_service import (
    HAIKU, SONNET, call_claude, extract_tool_input, _fetch_playbook_rules
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agent", tags=["agent-single"])


class AgentRequest(BaseModel):
    contact_id: int
    extra_context: dict = {}


@router.post("/analyze")
def analyze_contact(req: AgentRequest):
    """Run a quick single-pass analysis on a contact without the full pipeline."""
    with get_cursor() as cur:
        cur.execute("SELECT * FROM dabbahwala.contacts WHERE id = %s", (req.contact_id,))
        row = cur.fetchone()
        if not row:
            return JSONResponse(status_code=404, content={"detail": "Contact not found"})
        contact = dict(row)

        cur.execute("""
            SELECT * FROM dabbahwala.events
            WHERE contact_id = %s ORDER BY created_at DESC LIMIT 20
        """, (req.contact_id,))
        events = [dict(r) for r in cur.fetchall()]

    system = (
        "You are a marketing analyst for DabbahWala. "
        "Provide a concise analysis of this contact's current status and best next action."
    )
    messages = [{"role": "user", "content": (
        f"Contact: {contact.get('name')}, email={contact.get('email')}, "
        f"segment={contact.get('lifecycle_segment')}, orders={contact.get('order_count', 0)}, "
        f"total_spent=${contact.get('total_spent', 0)}\n"
        f"Recent events: {[e.get('event_type') for e in events[:10]]}\n"
        f"Extra context: {req.extra_context}\n\n"
        "Use submit_analysis tool."
    )}]
    tools = [{
        "name": "submit_analysis",
        "description": "Submit contact analysis",
        "input_schema": {
            "type": "object",
            "properties": {
                "status_summary": {"type": "string"},
                "recommended_action": {"type": "string"},
                "priority": {"type": "string", "enum": ["high", "medium", "low"]},
                "reasoning": {"type": "string"},
            },
            "required": ["status_summary", "recommended_action", "priority", "reasoning"],
        },
    }]

    try:
        resp = call_claude(SONNET, system, messages, tools=tools)
        result = extract_tool_input(resp, "submit_analysis") or {}
        return {"contact_id": req.contact_id, "analysis": result}
    except Exception as exc:
        logger.error("Single agent analyze failed: %s", exc)
        return JSONResponse(status_code=500, content={"detail": str(exc)})


@router.post("/playbook-preview")
def playbook_preview(categories: list[str] = None):
    """Preview what playbook rules would be injected for given categories."""
    if not categories:
        categories = ["cold", "engaged", "active_customer"]

    with get_cursor() as cur:
        text = _fetch_playbook_rules(categories, cursor=cur)

    return {"categories": categories, "rules": text, "char_count": len(text)}


@router.get("/contact/{contact_id}/summary")
def contact_summary(contact_id: int):
    """Return DB summary for a single contact — for debugging agent inputs."""
    with get_cursor() as cur:
        cur.execute("SELECT dabbahwala.get_contact_detail(%s) AS detail", (contact_id,))
        row = cur.fetchone()
        if not row or not row["detail"]:
            return JSONResponse(status_code=404, content={"detail": "Contact not found"})
        return {"contact_id": contact_id, "detail": row["detail"]}
