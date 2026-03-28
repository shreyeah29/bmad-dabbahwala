import logging
import time
from typing import Any, Dict, List

import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.config import settings
from app.db import get_cursor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/intelligence", tags=["intelligence"])

# ── Signal detectors (SQL) ────────────────────────────────────────────────────

_SIGNALS = [
    {
        "signal_type": "engaged_no_order",
        "action": "send_sms",
        "confidence": 0.7,
        "sql": """
            SELECT c.id AS contact_id FROM dabbahwala.contacts c
            WHERE c.lifecycle_segment = 'engaged'
              AND c.opted_out = FALSE
              AND (c.cooling_until IS NULL OR c.cooling_until < NOW())
              AND (c.last_order_at IS NULL OR c.last_order_at < NOW() - INTERVAL '14 days')
              AND c.id = ANY(%s)
        """,
    },
    {
        "signal_type": "new_customer_no_repeat",
        "action": "send_sms",
        "confidence": 0.75,
        "sql": """
            SELECT c.id AS contact_id FROM dabbahwala.contacts c
            WHERE c.lifecycle_segment = 'new_customer'
              AND c.opted_out = FALSE
              AND c.order_count = 1
              AND (c.last_order_at IS NULL OR c.last_order_at < NOW() - INTERVAL '7 days')
              AND c.id = ANY(%s)
        """,
    },
    {
        "signal_type": "lapsed_reengaged",
        "action": "send_sms",
        "confidence": 0.8,
        "sql": """
            SELECT DISTINCT e.contact_id FROM dabbahwala.events e
            JOIN dabbahwala.contacts c ON c.id = e.contact_id
            WHERE e.event_type IN ('email_opened', 'email_clicked')
              AND e.created_at >= NOW() - INTERVAL '7 days'
              AND c.lifecycle_segment = 'lapsed_customer'
              AND c.opted_out = FALSE
              AND c.id = ANY(%s)
        """,
    },
    {
        "signal_type": "reorder_intent",
        "action": "send_sms",
        "confidence": 0.65,
        "sql": """
            SELECT c.id AS contact_id FROM dabbahwala.contacts c
            JOIN dabbahwala.engagement_rollups er ON er.contact_id = c.id
            WHERE c.lifecycle_segment = 'active_customer'
              AND c.opted_out = FALSE
              AND er.orders_7d = 0
              AND er.orders_30d >= 2
              AND c.id = ANY(%s)
        """,
    },
    {
        "signal_type": "subscription_candidates",
        "action": "send_email",
        "confidence": 0.6,
        "sql": """
            SELECT c.id AS contact_id FROM dabbahwala.contacts c
            WHERE c.order_count >= 5
              AND c.opted_out = FALSE
              AND c.lifecycle_segment IN ('active_customer', 'new_customer')
              AND c.id = ANY(%s)
        """,
    },
    {
        "signal_type": "high_value_at_risk",
        "action": "field_sales_call",
        "confidence": 0.85,
        "sql": """
            SELECT c.id AS contact_id FROM dabbahwala.contacts c
            JOIN dabbahwala.engagement_rollups er ON er.contact_id = c.id
            WHERE c.total_spent >= (
                SELECT PERCENTILE_CONT(0.8) WITHIN GROUP (ORDER BY total_spent)
                FROM dabbahwala.contacts WHERE opted_out = FALSE
            )
              AND er.orders_30d = 0
              AND c.lifecycle_segment NOT IN ('optout', 'cooling')
              AND c.opted_out = FALSE
              AND c.id = ANY(%s)
        """,
    },
    {
        "signal_type": "app_customers_for_conversion",
        "action": "field_sales_call",
        "confidence": 0.7,
        "sql": """
            SELECT c.id AS contact_id FROM dabbahwala.contacts c
            WHERE c.source = 'app'
              AND c.opted_out = FALSE
              AND c.lifecycle_segment NOT IN ('optout', 'cooling')
              AND (c.last_order_at IS NULL OR c.last_order_at < NOW() - INTERVAL '30 days')
              AND c.id = ANY(%s)
        """,
    },
]

# Priority map for ROUTE phase
_SIGNAL_PRIORITY = {
    "high_value_at_risk": 1,
    "lapsed_reengaged": 2,
    "new_customer_no_repeat": 3,
    "reorder_intent": 4,
    "engaged_no_order": 5,
    "app_customers_for_conversion": 6,
    "subscription_candidates": 7,
}


# ── Phase implementations ─────────────────────────────────────────────────────

def _phase_collect(cur) -> List[int]:
    """Return IDs of contacts eligible for signal detection."""
    cur.execute("""
        SELECT c.id FROM dabbahwala.contacts c
        WHERE c.opted_out = FALSE
          AND (c.cooling_until IS NULL OR c.cooling_until < NOW())
          AND c.lifecycle_segment != 'optout'
        ORDER BY c.updated_at DESC
        LIMIT 5000
    """)
    return [row["id"] for row in cur.fetchall()]


def _phase_profile(cur, contact_ids: List[int]) -> int:
    """Refresh engagement rollups for all collected contacts."""
    if not contact_ids:
        return 0
    for cid in contact_ids:
        cur.execute("SELECT dabbahwala.refresh_engagement_rollups(%s)", (cid,))
    return len(contact_ids)


def _phase_signal(cur, contact_ids: List[int]) -> int:
    """Run all signal detectors, create opportunities."""
    if not contact_ids:
        return 0
    total = 0
    for sig in _SIGNALS:
        try:
            cur.execute(sig["sql"], (contact_ids,))
            hits = cur.fetchall()
            for row in hits:
                cid = row["contact_id"] if "contact_id" in row else row[0]
                cur.execute(
                    "SELECT dabbahwala.create_opportunity(%s, %s, %s, %s) AS opp_id",
                    (cid, sig["signal_type"], sig["confidence"], sig["action"]),
                )
                opp_id = cur.fetchone()["opp_id"]
                if opp_id:
                    total += 1
        except Exception as exc:
            logger.warning("Signal '%s' failed: %s", sig["signal_type"], exc)
    return total


def _phase_route(cur) -> int:
    """Assign priority to pending opportunities based on signal type."""
    routed = 0
    for signal_type, priority in _SIGNAL_PRIORITY.items():
        cur.execute("""
            UPDATE dabbahwala.opportunities
            SET notes = COALESCE(notes, '') || ' priority=' || %s
            WHERE signal_type = %s AND status = 'pending'
        """, (str(priority), signal_type))
        routed += cur.rowcount
    return routed


def _phase_dispatch(cur) -> int:
    """Queue immediate automated actions for high-priority pending opportunities."""
    cur.execute("""
        INSERT INTO dabbahwala.action_queue (contact_id, action_type, payload, status)
        SELECT
            o.contact_id,
            o.recommended_action,
            jsonb_build_object(
                'opportunity_id', o.id,
                'signal_type', o.signal_type,
                'confidence', o.confidence
            ),
            'pending'
        FROM dabbahwala.opportunities o
        WHERE o.status = 'pending'
          AND o.recommended_action IN ('send_sms', 'send_email')
          AND o.created_at >= NOW() - INTERVAL '1 hour'
          AND NOT EXISTS (
              SELECT 1 FROM dabbahwala.action_queue aq
              WHERE aq.contact_id = o.contact_id
                AND aq.status = 'pending'
                AND aq.payload->>'opportunity_id' = o.id::TEXT
          )
    """)
    return cur.rowcount


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/run-cycle")
def run_cycle():
    start = time.time()
    phases: Dict[str, Any] = {}
    opportunities_created = 0

    try:
        with get_cursor(commit=True) as cur:
            # COLLECT
            try:
                contact_ids = _phase_collect(cur)
                phases["collect"] = {"contacts": len(contact_ids), "status": "ok"}
                logger.info("COLLECT phase: %d contacts eligible", len(contact_ids))
            except Exception as exc:
                logger.error("COLLECT phase failed: %s", exc)
                phases["collect"] = {"status": "error", "detail": str(exc)}
                contact_ids = []

            # PROFILE
            try:
                profiled = _phase_profile(cur, contact_ids)
                phases["profile"] = {"updated": profiled, "status": "ok"}
                logger.info("PROFILE phase: %d rollups updated", profiled)
            except Exception as exc:
                logger.error("PROFILE phase failed: %s", exc)
                phases["profile"] = {"status": "error", "detail": str(exc)}

            # SIGNAL
            try:
                opportunities_created = _phase_signal(cur, contact_ids)
                phases["signal"] = {"opportunities_created": opportunities_created, "status": "ok"}
                logger.info("SIGNAL phase: %d opportunities created", opportunities_created)
            except Exception as exc:
                logger.error("SIGNAL phase failed: %s", exc)
                phases["signal"] = {"status": "error", "detail": str(exc)}

            # ROUTE
            try:
                routed = _phase_route(cur)
                phases["route"] = {"routed": routed, "status": "ok"}
                logger.info("ROUTE phase: %d opportunities routed", routed)
            except Exception as exc:
                logger.error("ROUTE phase failed: %s", exc)
                phases["route"] = {"status": "error", "detail": str(exc)}

            # DISPATCH
            try:
                dispatched = _phase_dispatch(cur)
                phases["dispatch"] = {"dispatched": dispatched, "status": "ok"}
                logger.info("DISPATCH phase: %d actions queued", dispatched)
            except Exception as exc:
                logger.error("DISPATCH phase failed: %s", exc)
                phases["dispatch"] = {"status": "error", "detail": str(exc)}

    except Exception as exc:
        logger.error("Intelligence cycle DB error: %s", exc)
        return JSONResponse(status_code=500, content={"detail": str(exc)})

    duration_ms = int((time.time() - start) * 1000)
    logger.info("Intelligence cycle complete duration_ms=%d opportunities=%d", duration_ms, opportunities_created)

    return {
        "phases": phases,
        "opportunities_created": opportunities_created,
        "duration_ms": duration_ms,
    }


@router.get("/pending-actions")
def pending_actions():
    with get_cursor() as cur:
        cur.execute("""
            SELECT o.id, o.contact_id, c.email, c.name,
                   o.signal_type, o.recommended_action::TEXT AS action,
                   o.confidence, o.created_at
            FROM dabbahwala.opportunities o
            JOIN dabbahwala.contacts c ON c.id = o.contact_id
            WHERE o.status = 'pending'
            ORDER BY o.created_at DESC
            LIMIT 200
        """)
        rows = [dict(r) for r in cur.fetchall()]
    return {"pending": rows, "count": len(rows)}


@router.post("/ingest-instantly-events")
async def ingest_instantly_events():
    if not settings.instantly_api_key:
        return JSONResponse(status_code=503, content={"detail": "INSTANTLY_API_KEY not configured"})

    ingested = 0
    skipped = 0

    async with httpx.AsyncClient() as http:
        resp = await http.get(
            "https://api.instantly.ai/api/v1/analytics/campaign/summary",
            headers={"Authorization": f"Bearer {settings.instantly_api_key}"},
            params={"limit": 100},
        )
        if resp.status_code != 200:
            logger.error("Instantly API error: %s", resp.text[:200])
            return JSONResponse(status_code=502, content={"detail": "Instantly API error"})

        events = resp.json().get("data", [])

    import json as _json
    with get_cursor(commit=True) as cur:
        for evt in events:
            email = evt.get("email", "")
            event_type = evt.get("event_type", "")

            _INSTANTLY_MAP = {
                "email_opened": "email_opened",
                "email_clicked": "email_clicked",
                "email_replied": "sms_received",
            }
            mapped = _INSTANTLY_MAP.get(event_type)
            if not mapped or not email:
                skipped += 1
                continue

            cur.execute("SELECT id FROM dabbahwala.contacts WHERE email = %s", (email,))
            row = cur.fetchone()
            if not row:
                skipped += 1
                continue

            cur.execute(
                "SELECT dabbahwala.ingest_event(%s, %s, %s)",
                (row["id"], mapped, _json.dumps({"source": "instantly", "raw": evt})),
            )
            ingested += 1

    logger.info("Instantly events ingested=%d skipped=%d", ingested, skipped)
    return {"ingested": ingested, "skipped": skipped}


# ── Opportunities CRUD ────────────────────────────────────────────────────────

class CreateOpportunityRequest(BaseModel):
    contact_id: int
    signal_type: str
    confidence: float = 0.5
    recommended_action: str = "no_action"
    notes: str = ""


@router.post("/opportunities")
def create_opportunity(req: CreateOpportunityRequest):
    with get_cursor(commit=True) as cur:
        cur.execute(
            "SELECT dabbahwala.create_opportunity(%s, %s, %s, %s, %s) AS opp_id",
            (req.contact_id, req.signal_type, req.confidence, req.recommended_action, req.notes or None),
        )
        opp_id = cur.fetchone()["opp_id"]
    if opp_id is None:
        return {"status": "duplicate", "opp_id": None}
    return {"status": "created", "opp_id": opp_id}


@router.get("/opportunities/pending")
def get_pending_opportunities():
    with get_cursor() as cur:
        cur.execute("""
            SELECT o.id, o.contact_id, c.email, c.name,
                   o.signal_type, o.recommended_action::TEXT AS action,
                   o.confidence, o.status, o.created_at
            FROM dabbahwala.opportunities o
            JOIN dabbahwala.contacts c ON c.id = o.contact_id
            WHERE o.status = 'pending'
            ORDER BY o.created_at DESC
            LIMIT 500
        """)
        rows = [dict(r) for r in cur.fetchall()]
    return {"opportunities": rows, "count": len(rows)}


@router.post("/opportunities/{opp_id}/dispatched")
def mark_dispatched(opp_id: int):
    with get_cursor(commit=True) as cur:
        cur.execute("""
            UPDATE dabbahwala.opportunities
            SET status = 'actioned', actioned_at = NOW()
            WHERE id = %s AND status = 'pending'
        """, (opp_id,))
        if cur.rowcount == 0:
            return JSONResponse(status_code=404, content={"detail": "Opportunity not found or not pending"})
    return {"status": "ok", "opp_id": opp_id}


@router.post("/opportunities/{opp_id}/outcome")
def record_outcome(opp_id: int, outcome: str = "converted"):
    valid = {"converted", "declined", "expired"}
    if outcome not in valid:
        return JSONResponse(status_code=422, content={"detail": f"outcome must be one of {sorted(valid)}"})

    status_map = {"converted": "actioned", "declined": "dismissed", "expired": "expired"}
    with get_cursor(commit=True) as cur:
        cur.execute("""
            UPDATE dabbahwala.opportunities
            SET status = %s, actioned_at = NOW(),
                notes = COALESCE(notes, '') || ' outcome=' || %s
            WHERE id = %s
        """, (status_map[outcome], outcome, opp_id))
        if cur.rowcount == 0:
            return JSONResponse(status_code=404, content={"detail": "Opportunity not found"})
    return {"status": "ok", "opp_id": opp_id, "outcome": outcome}
