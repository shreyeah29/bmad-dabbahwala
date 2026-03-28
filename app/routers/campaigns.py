"""E13 — Instantly Campaigns"""
import json
import logging
from typing import Optional

import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.config import settings
from app.db import get_cursor
from app.services.llm_service import SONNET, call_claude

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])


class PushLeadRequest(BaseModel):
    contact_id: int
    campaign_id: Optional[str] = None


class LogPushRequest(BaseModel):
    contact_id: int
    campaign_name: Optional[str] = None
    lifecycle_segment: Optional[str] = None
    instantly_lead_id: Optional[str] = None
    status: str = "success"
    error_msg: Optional[str] = None


class TemplateUpdateRequest(BaseModel):
    body: str
    segment: Optional[str] = None


# ── Story 13.1 ────────────────────────────────────────────────────────────────

@router.post("/push-lead")
def push_lead(req: PushLeadRequest):
    with get_cursor(commit=True) as cur:
        cur.execute("""
            SELECT c.email, cr.instantly_campaign_id, cr.instantly_campaign_name
            FROM dabbahwala.contacts c
            JOIN dabbahwala.campaign_routing cr ON cr.lifecycle_segment = c.lifecycle_segment
            WHERE c.id = %s
        """, (req.contact_id,))
        row = cur.fetchone()
        if not row:
            return JSONResponse(status_code=404, content={"detail": "Contact or campaign routing not found"})

        campaign_id = req.campaign_id or row["instantly_campaign_id"]
        cur.execute("""
            INSERT INTO dabbahwala.action_queue (contact_id, action_type, payload, status)
            VALUES (%s, 'move_campaign', %s, 'pending')
            RETURNING id
        """, (req.contact_id, json.dumps({"campaign_id": campaign_id, "email": row["email"]})))
        queue_id = cur.fetchone()["id"]

    return {"status": "queued", "queue_id": queue_id, "campaign_id": campaign_id}


@router.get("/pending")
def pending_pushes():
    with get_cursor() as cur:
        cur.execute("""
            SELECT aq.id, aq.contact_id, c.email, aq.payload, aq.created_at
            FROM dabbahwala.action_queue aq
            JOIN dabbahwala.contacts c ON c.id = aq.contact_id
            WHERE aq.action_type = 'move_campaign' AND aq.status = 'pending'
            ORDER BY aq.created_at ASC LIMIT 200
        """)
        return {"pending": [dict(r) for r in cur.fetchall()]}


# ── Story 13.2 ────────────────────────────────────────────────────────────────

@router.get("/active-contacts")
def active_contacts(limit: int = 500):
    with get_cursor() as cur:
        cur.execute("""
            SELECT c.id, c.email, c.name, c.lifecycle_segment::TEXT AS segment,
                   cr.instantly_campaign_id, cr.instantly_campaign_name
            FROM dabbahwala.contacts c
            JOIN dabbahwala.campaign_routing cr ON cr.lifecycle_segment = c.lifecycle_segment
            WHERE c.opted_out = FALSE
              AND c.lifecycle_segment NOT IN ('optout', 'cooling')
              AND (c.cooling_until IS NULL OR c.cooling_until < NOW())
              AND cr.is_active = TRUE
            ORDER BY c.updated_at DESC
            LIMIT %s
        """, (limit,))
        return {"contacts": [dict(r) for r in cur.fetchall()]}


@router.get("/active-contacts-stats")
def active_contacts_stats():
    with get_cursor() as cur:
        cur.execute("""
            SELECT c.lifecycle_segment::TEXT AS segment, COUNT(*) AS count
            FROM dabbahwala.contacts c
            JOIN dabbahwala.campaign_routing cr ON cr.lifecycle_segment = c.lifecycle_segment
            WHERE c.opted_out = FALSE AND cr.is_active = TRUE
            GROUP BY c.lifecycle_segment
        """)
        return {"stats": [dict(r) for r in cur.fetchall()]}


# ── Story 13.3 ────────────────────────────────────────────────────────────────

@router.post("/log-push")
def log_push(req: LogPushRequest):
    with get_cursor(commit=True) as cur:
        cur.execute("""
            INSERT INTO dabbahwala.campaign_push_log
                (contact_id, campaign_name, lifecycle_segment, instantly_lead_id, status, error_msg)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (req.contact_id, req.campaign_name, req.lifecycle_segment,
               req.instantly_lead_id, req.status, req.error_msg))
        log_id = cur.fetchone()["id"]
    return {"status": "ok", "log_id": log_id}


@router.get("/push-log")
def push_log(status_filter: Optional[str] = None, limit: int = 100):
    with get_cursor() as cur:
        q = "SELECT * FROM dabbahwala.campaign_push_log"
        params = []
        if status_filter:
            q += " WHERE status = %s"
            params.append(status_filter)
        q += " ORDER BY pushed_at DESC LIMIT %s"
        params.append(limit)
        cur.execute(q, params)
        return {"logs": [dict(r) for r in cur.fetchall()]}


# ── Story 13.4 ────────────────────────────────────────────────────────────────

@router.get("/analytics")
def campaign_analytics():
    with get_cursor() as cur:
        cur.execute("SELECT dabbahwala.get_campaign_performance() AS perf")
        return {"analytics": cur.fetchone()["perf"]}


@router.get("/templates/{name}")
def get_template(name: str):
    with get_cursor() as cur:
        cur.execute("SELECT * FROM dabbahwala.sms_templates WHERE name = %s", (name,))
        row = cur.fetchone()
        if not row:
            return JSONResponse(status_code=404, content={"detail": "Template not found"})
        return dict(row)


@router.put("/templates/{name}")
def update_template(name: str, req: TemplateUpdateRequest):
    with get_cursor(commit=True) as cur:
        cur.execute("""
            INSERT INTO dabbahwala.sms_templates (name, body, segment)
            VALUES (%s, %s, %s)
            ON CONFLICT (name) DO UPDATE SET body = EXCLUDED.body, segment = EXCLUDED.segment
            RETURNING id
        """, (name, req.body, req.segment))
        return {"status": "ok", "template_id": cur.fetchone()["id"]}


@router.post("/templates/{name}/rewrite")
def rewrite_template(name: str):
    with get_cursor() as cur:
        cur.execute("SELECT body, segment FROM dabbahwala.sms_templates WHERE name = %s", (name,))
        row = cur.fetchone()
        if not row:
            return JSONResponse(status_code=404, content={"detail": "Template not found"})

    system = "You are a marketing copywriter for DabbahWala, an Indian food delivery service. Rewrite the SMS template to be more engaging."
    messages = [{"role": "user", "content": f"Rewrite this SMS template:\n\n{row['body']}\n\nSegment: {row.get('segment', 'general')}\n\nReturn only the rewritten SMS text."}]

    try:
        resp = call_claude(SONNET, system, messages)
        new_body = next((b.text for b in resp.content if b.type == "text"), row["body"])
        with get_cursor(commit=True) as cur:
            cur.execute("UPDATE dabbahwala.sms_templates SET body = %s WHERE name = %s", (new_body, name))
        return {"status": "ok", "original": row["body"], "rewritten": new_body}
    except Exception as exc:
        return JSONResponse(status_code=500, content={"detail": str(exc)})


@router.post("/setup-instantly")
async def setup_instantly():
    if not settings.instantly_api_key:
        return JSONResponse(status_code=503, content={"detail": "INSTANTLY_API_KEY not configured"})
    return {"status": "ok", "message": "Instantly setup — use /api/webhooks/sync-campaigns to sync campaigns"}
