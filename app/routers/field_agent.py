"""E20 — Field Agent"""
import logging
from typing import Optional
from datetime import date

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.db import get_cursor
from app.services.llm_service import HAIKU, SONNET, call_claude

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/field-agent", tags=["field-agent"])


class OutcomeLogRequest(BaseModel):
    contact_id: int
    agent_name: str
    outcome: str  # "order_placed", "not_interested", "callback", "left_voicemail", "no_answer"
    notes: Optional[str] = None
    order_ref: Optional[str] = None


class ScorecardRequest(BaseModel):
    agent_name: str
    period_days: int = 30


# ── Story 20.1: Daily Brief ───────────────────────────────────────────────────

@router.get("/daily-brief")
def daily_brief(limit: int = 20):
    """
    Generate today's call list: top contacts by order count who haven't been
    called recently and are not opted out.
    """
    with get_cursor() as cur:
        cur.execute("""
            SELECT c.id, c.name, c.phone, c.email,
                   c.lifecycle_segment::TEXT AS segment,
                   c.order_count, c.total_spent, c.last_order_at,
                   MAX(fc.created_at) AS last_call_at
            FROM dabbahwala.contacts c
            LEFT JOIN dabbahwala.field_calls fc ON fc.contact_id = c.id
            WHERE c.opted_out = FALSE
              AND c.phone IS NOT NULL
              AND c.lifecycle_segment NOT IN ('optout', 'cooling')
            GROUP BY c.id, c.name, c.phone, c.email, c.lifecycle_segment,
                     c.order_count, c.total_spent, c.last_order_at
            ORDER BY c.order_count DESC, last_call_at ASC NULLS FIRST
            LIMIT %s
        """, (limit,))
        contacts = [dict(r) for r in cur.fetchall()]

    # Build AI talking points for each contact (batch using HAIKU for speed)
    brief_items = []
    for c in contacts:
        brief_items.append({
            **c,
            "talking_points": _generate_talking_points(c),
        })

    return {
        "date": str(date.today()),
        "call_count": len(brief_items),
        "brief": brief_items,
    }


def _generate_talking_points(contact: dict) -> str:
    """Quick HAIKU call to generate personalized talking points."""
    system = (
        "You are a field sales agent assistant for DabbahWala, Indian food delivery in Atlanta. "
        "Generate 2-3 brief talking points for a phone call with this customer. Be warm, personal, specific."
    )
    msgs = [{"role": "user", "content": (
        f"Customer: {contact.get('name', 'Unknown')}, "
        f"Segment: {contact.get('segment', 'unknown')}, "
        f"Orders: {contact.get('order_count', 0)}, "
        f"Last order: {contact.get('last_order_at', 'never')}. "
        "Talking points:"
    )}]
    try:
        resp = call_claude(HAIKU, system, msgs, max_tokens=200)
        return next((b.text for b in resp.content if b.type == "text"), "")
    except Exception:
        return ""


@router.get("/call-list")
def call_list(segment: Optional[str] = None, limit: int = 50):
    """Filtered call list by segment."""
    with get_cursor() as cur:
        conditions = ["opted_out = FALSE", "phone IS NOT NULL"]
        params = []
        if segment:
            conditions.append("lifecycle_segment = %s::dabbahwala.lifecycle_segment_type")
            params.append(segment)
        where = "WHERE " + " AND ".join(conditions)
        params.append(limit)
        cur.execute(f"""
            SELECT id, name, phone, email, lifecycle_segment::TEXT AS segment,
                   order_count, total_spent, last_order_at
            FROM dabbahwala.contacts
            {where}
            ORDER BY order_count DESC
            LIMIT %s
        """, params)
        return {"contacts": [dict(r) for r in cur.fetchall()]}


# ── Story 20.2: Outcome logging ───────────────────────────────────────────────

@router.post("/log-outcome")
def log_outcome(req: OutcomeLogRequest):
    with get_cursor(commit=True) as cur:
        cur.execute("""
            INSERT INTO dabbahwala.field_calls
                (contact_id, agent_name, outcome, notes, order_ref)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        """, (req.contact_id, req.agent_name, req.outcome, req.notes, req.order_ref))
        call_id = cur.fetchone()["id"]

        # If order placed, update lifecycle segment
        if req.outcome == "order_placed":
            cur.execute("""
                UPDATE dabbahwala.contacts
                SET lifecycle_segment = 'active'::dabbahwala.lifecycle_segment_type,
                    updated_at = NOW()
                WHERE id = %s AND lifecycle_segment NOT IN ('active', 'champion')
            """, (req.contact_id,))

        # Log as event
        import json
        cur.execute(
            "SELECT dabbahwala.ingest_event(%s, %s, %s)",
            (req.contact_id, "field_call", json.dumps({
                "agent": req.agent_name,
                "outcome": req.outcome,
                "notes": req.notes,
            }))
        )

    return {"status": "ok", "call_id": call_id}


@router.get("/outcomes")
def list_outcomes(agent_name: Optional[str] = None, days: int = 30, limit: int = 100):
    with get_cursor() as cur:
        conditions = [f"created_at >= NOW() - INTERVAL '{days} days'"]
        params = []
        if agent_name:
            conditions.append("agent_name = %s")
            params.append(agent_name)
        where = "WHERE " + " AND ".join(conditions)
        params.append(limit)
        cur.execute(f"""
            SELECT fc.id, fc.contact_id, c.name AS contact_name, c.phone,
                   fc.agent_name, fc.outcome, fc.notes, fc.order_ref, fc.created_at
            FROM dabbahwala.field_calls fc
            JOIN dabbahwala.contacts c ON c.id = fc.contact_id
            {where}
            ORDER BY fc.created_at DESC
            LIMIT %s
        """, params)
        return {"outcomes": [dict(r) for r in cur.fetchall()]}


# ── Story 20.3: Scorecard ─────────────────────────────────────────────────────

@router.post("/scorecard")
def agent_scorecard(req: ScorecardRequest):
    with get_cursor() as cur:
        cur.execute("""
            SELECT
                outcome,
                COUNT(*) AS count
            FROM dabbahwala.field_calls
            WHERE agent_name = %s
              AND created_at >= NOW() - INTERVAL '1 day' * %s
            GROUP BY outcome
            ORDER BY count DESC
        """, (req.agent_name, req.period_days))
        breakdown = [dict(r) for r in cur.fetchall()]

        total_calls = sum(r["count"] for r in breakdown)
        orders = next((r["count"] for r in breakdown if r["outcome"] == "order_placed"), 0)
        conversion_rate = round(orders / total_calls * 100, 1) if total_calls > 0 else 0.0

    return {
        "agent_name": req.agent_name,
        "period_days": req.period_days,
        "total_calls": total_calls,
        "orders_placed": orders,
        "conversion_rate_pct": conversion_rate,
        "outcome_breakdown": breakdown,
    }


@router.get("/team-scorecard")
def team_scorecard(days: int = 30):
    with get_cursor() as cur:
        cur.execute("""
            SELECT
                agent_name,
                COUNT(*) AS total_calls,
                SUM(CASE WHEN outcome = 'order_placed' THEN 1 ELSE 0 END) AS orders,
                ROUND(100.0 * SUM(CASE WHEN outcome = 'order_placed' THEN 1 ELSE 0 END) / COUNT(*), 1)
                    AS conversion_pct
            FROM dabbahwala.field_calls
            WHERE created_at >= NOW() - INTERVAL '1 day' * %s
            GROUP BY agent_name
            ORDER BY orders DESC
        """, (days,))
        return {"period_days": days, "agents": [dict(r) for r in cur.fetchall()]}
