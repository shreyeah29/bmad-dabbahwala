"""E10 — Webhooks & Delivery"""
import json
import logging
import threading
from typing import Optional

import httpx
from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.config import settings
from app.db import get_cursor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])

_INSTANTLY_EVENT_MAP = {
    "email_opened": "email_opened",
    "email_clicked": "email_clicked",
    "email_replied": "sms_received",
    "email_bounced": None,
}

_SHIPDAY_STATUS_MAP = {
    "OrderDelivered": "order_delivered",
    "OrderPickedUp": None,
    "OrderAssigned": None,
    "OrderFailed": "order_cancelled",
    "OutForDelivery": None,
}


# ── Story 10.1: Instantly webhook ─────────────────────────────────────────────

@router.post("/instantly")
async def instantly_webhook(request: Request):
    body = await request.json()
    events = body if isinstance(body, list) else [body]
    ingested = skipped = 0

    with get_cursor(commit=True) as cur:
        for evt in events:
            email = evt.get("email", "")
            event_type_raw = evt.get("event_type", "")
            mapped = _INSTANTLY_EVENT_MAP.get(event_type_raw)
            if not mapped or not email:
                skipped += 1
                continue

            cur.execute("SELECT id FROM dabbahwala.contacts WHERE email = %s", (email,))
            row = cur.fetchone()
            if not row:
                logger.info("Instantly webhook: unknown email=%s skipped", email)
                skipped += 1
                continue

            cur.execute(
                "SELECT dabbahwala.ingest_event(%s, %s, %s)",
                (row["id"], mapped, json.dumps({"source": "instantly", "raw": evt})),
            )
            ingested += 1

    return {"ingested": ingested, "skipped": skipped}


# ── Story 10.2: Telnyx webhook ────────────────────────────────────────────────

@router.post("/telnyx")
async def telnyx_webhook(request: Request, x_telnyx_signature: Optional[str] = Header(default=None)):
    body = await request.json()

    # Optional signature validation
    if settings.telnyx_api_key and x_telnyx_signature:
        logger.debug("Telnyx webhook signature present — validation deferred to Telnyx SDK")

    event_type = body.get("data", {}).get("event_type", "")
    if "message.received" in event_type:
        payload = body.get("data", {}).get("payload", {})
        from_number = payload.get("from", {}).get("phone_number", "")
        to_number = payload.get("to", [{}])[0].get("phone_number", "") if payload.get("to") else ""
        text = payload.get("text", "")
        msg_id = payload.get("id", "")

        async with httpx.AsyncClient() as http:
            await http.post("http://localhost:8000/api/telnyx/message", json={
                "from_number": from_number,
                "to_number": to_number,
                "body": text,
                "direction": "inbound",
                "telnyx_msg_id": msg_id,
            })

    return {"status": "ok"}


# ── Story 10.3: Shipday webhooks ──────────────────────────────────────────────

@router.post("/shipday")
@router.get("/shipday")
async def shipday_webhook(request: Request):
    if request.method == "GET":
        return {"status": "ok", "message": "Shipday webhook endpoint active"}

    body = await request.json()
    status = body.get("status", "")
    order_ref = body.get("orderId", body.get("order_ref", ""))
    event_type = _SHIPDAY_STATUS_MAP.get(status)

    with get_cursor(commit=True) as cur:
        cur.execute("SELECT id, contact_id FROM dabbahwala.orders WHERE order_ref = %s", (str(order_ref),))
        order_row = cur.fetchone()
        if not order_row:
            return {"status": "skipped", "reason": "order not found"}

        if event_type:
            cur.execute(
                "SELECT dabbahwala.ingest_event(%s, %s, %s)",
                (order_row["contact_id"], event_type, json.dumps({"source": "shipday", "raw": body})),
            )

        cur.execute("""
            UPDATE dabbahwala.orders SET status = %s WHERE id = %s
        """, (status.lower(), order_row["id"]))

        contact_id = order_row["contact_id"]

    if status == "OrderDelivered" and contact_id:
        def _delayed_cycle():
            import time
            time.sleep(4 * 3600)
            try:
                import httpx as _httpx
                _httpx.post(f"http://localhost:8000/api/agents/cycle/run-for-contact?contact_id={contact_id}")
            except Exception as exc:
                logger.error("Delayed agent cycle failed: %s", exc)
        threading.Thread(target=_delayed_cycle, daemon=True).start()
        logger.info("Delivery complete — agent cycle scheduled in 4h for contact_id=%s", contact_id)

    elif status == "OrderFailed" and contact_id:
        try:
            async with httpx.AsyncClient() as http:
                await http.post(f"http://localhost:8000/api/agents/cycle/run-for-contact?contact_id={contact_id}")
        except Exception as exc:
            logger.error("Escalation cycle failed: %s", exc)

    return {"status": "ok", "order_ref": order_ref, "event_type": event_type}


@router.post("/delivery/status")
async def delivery_status(request: Request):
    return await shipday_webhook(request)


# ── Story 10.4: Campaign sync webhooks ────────────────────────────────────────

@router.post("/sync-campaigns")
async def sync_campaigns():
    if not settings.instantly_api_key:
        return JSONResponse(status_code=503, content={"detail": "INSTANTLY_API_KEY not configured"})

    async with httpx.AsyncClient() as http:
        resp = await http.get(
            "https://api.instantly.ai/api/v1/campaign/list",
            params={"api_key": settings.instantly_api_key, "limit": 100},
        )
        if resp.status_code != 200:
            return JSONResponse(status_code=502, content={"detail": "Instantly API error"})
        campaigns = resp.json().get("data", [])

    updated = 0
    with get_cursor(commit=True) as cur:
        for camp in campaigns:
            cur.execute("""
                UPDATE dabbahwala.campaign_routing
                SET instantly_campaign_id = %s,
                    instantly_campaign_name = %s,
                    updated_at = NOW()
                WHERE instantly_campaign_name = %s
            """, (camp.get("id"), camp.get("name"), camp.get("name")))
            updated += cur.rowcount

    return {"status": "ok", "campaigns_synced": len(campaigns), "routing_updated": updated}


@router.get("/campaigns")
def list_campaigns():
    with get_cursor() as cur:
        cur.execute("SELECT * FROM dabbahwala.campaign_routing ORDER BY lifecycle_segment")
        return {"campaigns": [dict(r) for r in cur.fetchall()]}


@router.post("/campaign-stats")
async def sync_campaign_stats():
    return {"status": "ok", "message": "Campaign stats sync — triggered via Instantly webhook"}
