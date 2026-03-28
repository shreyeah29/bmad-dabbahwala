"""E15 — Broadcasts"""
import logging
from typing import Optional

import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.config import settings
from app.db import get_cursor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/broadcasts", tags=["broadcasts"])


class BroadcastCreateRequest(BaseModel):
    name: str
    message_body: str
    segment: Optional[str] = None
    scheduled_at: Optional[str] = None


class BroadcastDispatchRequest(BaseModel):
    broadcast_id: int
    dry_run: bool = False


# ── Story 15.1: Job management ────────────────────────────────────────────────

@router.post("/")
def create_broadcast(req: BroadcastCreateRequest):
    with get_cursor(commit=True) as cur:
        cur.execute("""
            INSERT INTO dabbahwala.broadcasts
                (name, message_body, segment, scheduled_at, status)
            VALUES (%s, %s, %s, %s, 'draft')
            RETURNING id
        """, (req.name, req.message_body, req.segment, req.scheduled_at))
        broadcast_id = cur.fetchone()["id"]
    return {"status": "ok", "broadcast_id": broadcast_id}


@router.get("/")
def list_broadcasts(status: Optional[str] = None):
    with get_cursor() as cur:
        q = "SELECT * FROM dabbahwala.broadcasts"
        params = []
        if status:
            q += " WHERE status = %s"
            params.append(status)
        q += " ORDER BY created_at DESC LIMIT 100"
        cur.execute(q, params)
        return {"broadcasts": [dict(r) for r in cur.fetchall()]}


@router.get("/{broadcast_id}")
def get_broadcast(broadcast_id: int):
    with get_cursor() as cur:
        cur.execute("SELECT * FROM dabbahwala.broadcasts WHERE id = %s", (broadcast_id,))
        row = cur.fetchone()
        if not row:
            return JSONResponse(status_code=404, content={"detail": "Broadcast not found"})
        return dict(row)


@router.delete("/{broadcast_id}")
def cancel_broadcast(broadcast_id: int):
    with get_cursor(commit=True) as cur:
        cur.execute("""
            UPDATE dabbahwala.broadcasts SET status = 'cancelled', updated_at = NOW()
            WHERE id = %s AND status IN ('draft', 'scheduled')
        """, (broadcast_id,))
        if cur.rowcount == 0:
            return JSONResponse(
                status_code=409,
                content={"detail": "Broadcast not found or already sent/cancelled"}
            )
    return {"status": "ok", "broadcast_id": broadcast_id, "new_status": "cancelled"}


# ── Story 15.2: Recipient preview & dispatch ──────────────────────────────────

@router.get("/{broadcast_id}/preview")
def preview_recipients(broadcast_id: int):
    with get_cursor() as cur:
        cur.execute("SELECT * FROM dabbahwala.broadcasts WHERE id = %s", (broadcast_id,))
        bcast = cur.fetchone()
        if not bcast:
            return JSONResponse(status_code=404, content={"detail": "Broadcast not found"})

        conditions = ["opted_out = FALSE"]
        params: list = []
        if bcast.get("segment"):
            conditions.append("lifecycle_segment = %s::dabbahwala.lifecycle_segment_type")
            params.append(bcast["segment"])

        where = "WHERE " + " AND ".join(conditions)
        cur.execute(f"""
            SELECT id, email, phone, name, lifecycle_segment::TEXT AS segment
            FROM dabbahwala.contacts
            {where}
            ORDER BY id
            LIMIT 500
        """, params)
        recipients = [dict(r) for r in cur.fetchall()]

    return {
        "broadcast_id": broadcast_id,
        "recipient_count": len(recipients),
        "sample": recipients[:10],
    }


@router.post("/{broadcast_id}/dispatch")
async def dispatch_broadcast(broadcast_id: int, dry_run: bool = False):
    """
    Dispatch a broadcast — send SMS via Telnyx to all matching contacts.
    Set dry_run=true to preview without sending.
    """
    with get_cursor(commit=True) as cur:
        cur.execute("SELECT * FROM dabbahwala.broadcasts WHERE id = %s", (broadcast_id,))
        bcast = cur.fetchone()
        if not bcast:
            return JSONResponse(status_code=404, content={"detail": "Broadcast not found"})
        if bcast["status"] not in ("draft", "scheduled"):
            return JSONResponse(
                status_code=409,
                content={"detail": f"Cannot dispatch broadcast with status '{bcast['status']}'"}
            )

        conditions = ["opted_out = FALSE", "phone IS NOT NULL"]
        params: list = []
        if bcast.get("segment"):
            conditions.append("lifecycle_segment = %s::dabbahwala.lifecycle_segment_type")
            params.append(bcast["segment"])

        where = "WHERE " + " AND ".join(conditions)
        cur.execute(f"""
            SELECT id, phone FROM dabbahwala.contacts
            {where}
        """, params)
        recipients = cur.fetchall()

        if dry_run:
            return {
                "dry_run": True,
                "broadcast_id": broadcast_id,
                "would_send_to": len(recipients),
            }

        # Mark as sending
        cur.execute("""
            UPDATE dabbahwala.broadcasts SET status = 'sending', updated_at = NOW()
            WHERE id = %s
        """, (broadcast_id,))

    sent = failed = 0
    from_number = settings.telnyx_from_number if hasattr(settings, "telnyx_from_number") else "+18444322224"

    async with httpx.AsyncClient(timeout=10) as http:
        for contact in recipients:
            try:
                await http.post(
                    "http://localhost:8000/api/telnyx/message",
                    json={
                        "from_number": from_number,
                        "to_number": contact["phone"],
                        "body": bcast["message_body"],
                        "direction": "outbound",
                        "contact_id": contact["id"],
                    },
                )
                sent += 1
            except Exception as exc:
                logger.error("Broadcast %d send failed to contact %d: %s", broadcast_id, contact["id"], exc)
                failed += 1

    with get_cursor(commit=True) as cur:
        cur.execute("""
            UPDATE dabbahwala.broadcasts
            SET status = 'sent', sent_count = %s, failed_count = %s, updated_at = NOW()
            WHERE id = %s
        """, (sent, failed, broadcast_id))

    return {
        "status": "ok",
        "broadcast_id": broadcast_id,
        "sent": sent,
        "failed": failed,
    }
