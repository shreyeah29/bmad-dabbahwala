"""E09 — Telnyx SMS & Call Tracking"""
import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

from app.config import settings
from app.db import get_cursor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/telnyx", tags=["telnyx"])


class MessageRequest(BaseModel):
    from_number: str
    to_number: str
    body: str
    direction: str = "outbound"
    telnyx_msg_id: Optional[str] = None
    contact_id: Optional[int] = None


class CallRequest(BaseModel):
    from_number: str
    to_number: str
    direction: str = "outbound"
    duration_sec: Optional[int] = None
    telnyx_call_id: Optional[str] = None
    transcript: Optional[str] = None
    summary: Optional[str] = None


class FieldMessageRequest(BaseModel):
    contact_id: int
    body: str
    agent_name: str
    template_name: Optional[str] = None


class TemplateRequest(BaseModel):
    name: str
    body: str
    segment: Optional[str] = None


# ── Story 9.1: Message storage ────────────────────────────────────────────────

@router.post("/message")
async def store_message(req: MessageRequest):
    contact_id = req.contact_id

    with get_cursor(commit=True) as cur:
        # Auto-create contact for unknown inbound numbers
        if req.direction == "inbound" and not contact_id:
            cur.execute("SELECT id FROM dabbahwala.contacts WHERE phone = %s", (req.from_number,))
            row = cur.fetchone()
            if row:
                contact_id = row["id"]
            else:
                cur.execute("""
                    INSERT INTO dabbahwala.contacts (phone, lifecycle_segment, source)
                    VALUES (%s, 'cold', 'telnyx')
                    ON CONFLICT DO NOTHING RETURNING id
                """, (req.from_number,))
                new_row = cur.fetchone()
                contact_id = new_row["id"] if new_row else None
                logger.info("Auto-created contact for inbound number=%s", req.from_number)

        cur.execute("""
            INSERT INTO dabbahwala.telnyx_messages
                (contact_id, direction, from_number, to_number, body, telnyx_msg_id, status)
            VALUES (%s, %s, %s, %s, %s, %s, 'received')
            ON CONFLICT (telnyx_msg_id) DO NOTHING RETURNING id
        """, (contact_id, req.direction, req.from_number, req.to_number, req.body, req.telnyx_msg_id))
        row = cur.fetchone()
        msg_id = row["id"] if row else None

    # Trigger agent cycle for inbound
    if req.direction == "inbound" and contact_id:
        try:
            import httpx
            async with httpx.AsyncClient() as http:
                await http.post(f"http://localhost:8000/api/agents/cycle/run-for-contact?contact_id={contact_id}")
        except Exception as exc:
            logger.warning("Agent cycle trigger failed: %s", exc)

    return {"status": "ok", "msg_id": msg_id, "contact_id": contact_id}


# Alias
router.add_api_route("/api/sms/message", store_message, methods=["POST"], tags=["telnyx"])


# ── Story 9.2: Call tracking ──────────────────────────────────────────────────

@router.post("/call")
def store_call(req: CallRequest):
    with get_cursor(commit=True) as cur:
        phone = req.from_number if req.direction == "inbound" else req.to_number
        cur.execute("SELECT id FROM dabbahwala.contacts WHERE phone = %s", (phone,))
        row = cur.fetchone()
        contact_id = row["id"] if row else None

        cur.execute("""
            INSERT INTO dabbahwala.telnyx_calls
                (contact_id, direction, from_number, to_number, duration_sec, telnyx_call_id, status)
            VALUES (%s, %s, %s, %s, %s, %s, 'completed')
            ON CONFLICT (telnyx_call_id) DO NOTHING RETURNING id
        """, (contact_id, req.direction, req.from_number, req.to_number,
               req.duration_sec, req.telnyx_call_id))
        call_row = cur.fetchone()

    logger.info("Call stored direction=%s contact_id=%s duration=%s", req.direction, contact_id, req.duration_sec)
    return {"status": "ok", "contact_id": contact_id, "call_id": call_row["id"] if call_row else None}


# ── Story 9.3: Field agent SMS & templates ────────────────────────────────────

@router.post("/field-agent-message")
def field_agent_message(req: FieldMessageRequest):
    with get_cursor(commit=True) as cur:
        cur.execute("SELECT phone FROM dabbahwala.contacts WHERE id = %s", (req.contact_id,))
        row = cur.fetchone()
        if not row:
            return JSONResponse(status_code=404, content={"detail": "Contact not found"})

        cur.execute("""
            INSERT INTO dabbahwala.telnyx_messages
                (contact_id, direction, from_number, to_number, body, status)
            VALUES (%s, 'outbound', %s, %s, %s, 'queued')
            RETURNING id
        """, (req.contact_id, f"field:{req.agent_name}", row["phone"], req.body))
        msg_id = cur.fetchone()["id"]

    return {"status": "ok", "msg_id": msg_id, "agent_name": req.agent_name}


@router.get("/templates")
def list_templates():
    with get_cursor() as cur:
        cur.execute("SELECT * FROM dabbahwala.sms_templates WHERE is_active = TRUE ORDER BY name")
        return {"templates": [dict(r) for r in cur.fetchall()]}


@router.post("/templates")
def create_template(req: TemplateRequest):
    with get_cursor(commit=True) as cur:
        cur.execute("""
            INSERT INTO dabbahwala.sms_templates (name, body, segment)
            VALUES (%s, %s, %s)
            ON CONFLICT (name) DO UPDATE SET body = EXCLUDED.body, segment = EXCLUDED.segment
            RETURNING id
        """, (req.name, req.body, req.segment))
        template_id = cur.fetchone()["id"]
    return {"status": "ok", "template_id": template_id}
