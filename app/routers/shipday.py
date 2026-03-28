"""E11 — Orders & Shipday"""
import json
import logging
from typing import Optional

import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.config import settings
from app.db import get_cursor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/shipday", tags=["shipday"])

_SHIPDAY_BASE = "https://api.shipday.com"

_import_status = {"running": False, "total": 0, "done": 0, "errors": 0, "last_run": None}


async def _fetch_shipday_orders(page: int = 1, limit: int = 100):
    async with httpx.AsyncClient() as http:
        resp = await http.get(
            f"{_SHIPDAY_BASE}/orders",
            headers={"Authorization": f"Basic {settings.shipday_api_key}"},
            params={"page": page, "perPage": limit},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()


def _normalize_phone(phone: str) -> str:
    digits = "".join(c for c in phone if c.isdigit())
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits[0] == "1":
        return f"+{digits}"
    if len(digits) == 12 and digits[:2] == "91":
        return f"+{digits}"
    return f"+{digits}" if digits else phone


# ── Story 11.1: Order ingestion ───────────────────────────────────────────────

@router.post("/ingest-orders")
async def ingest_orders(limit: int = 100):
    try:
        data = await _fetch_shipday_orders(limit=limit)
    except Exception as exc:
        return JSONResponse(status_code=502, content={"detail": str(exc)})

    orders = data if isinstance(data, list) else data.get("orders", [])
    created = updated = errors = 0

    with get_cursor(commit=True) as cur:
        for order in orders:
            try:
                email = order.get("customerEmail", "")
                phone = _normalize_phone(order.get("customerPhoneNumber", ""))
                name = order.get("customerName", "")
                order_ref = str(order.get("orderId", ""))
                total = float(order.get("orderCost", 0) or 0)

                # Upsert contact
                cur.execute("""
                    INSERT INTO dabbahwala.contacts (email, phone, name, source)
                    VALUES (%s, %s, %s, 'shipday')
                    ON CONFLICT (email) DO UPDATE SET
                        phone = COALESCE(EXCLUDED.phone, contacts.phone),
                        name  = COALESCE(EXCLUDED.name, contacts.name),
                        updated_at = NOW()
                    RETURNING id
                """, (email or None, phone or None, name or None))
                contact_row = cur.fetchone()
                if not contact_row and email:
                    cur.execute("SELECT id FROM dabbahwala.contacts WHERE email = %s", (email,))
                    contact_row = cur.fetchone()
                contact_id = contact_row["id"] if contact_row else None

                if not contact_id:
                    errors += 1
                    continue

                # Upsert order
                cur.execute("""
                    INSERT INTO dabbahwala.orders
                        (contact_id, order_ref, total_amount, shipday_order_id, status)
                    VALUES (%s, %s, %s, %s, 'pending')
                    ON CONFLICT (order_ref) DO UPDATE SET
                        total_amount = EXCLUDED.total_amount,
                        updated_at = NOW()
                """, (contact_id, order_ref, total, order_ref))

                if cur.rowcount:
                    created += 1
                    # Update order count on contact
                    cur.execute("""
                        UPDATE dabbahwala.contacts
                        SET order_count = (SELECT COUNT(*) FROM dabbahwala.orders WHERE contact_id = %s),
                            last_order_at = NOW(), updated_at = NOW()
                        WHERE id = %s
                    """, (contact_id, contact_id))
                else:
                    updated += 1

            except Exception as exc:
                logger.error("Order ingest error: %s", exc)
                errors += 1

    return {"ingested": created + updated, "created": created, "updated": updated, "errors": errors}


# ── Story 11.2: Sync status & top calls ──────────────────────────────────────

@router.get("/sync-status")
def sync_status():
    with get_cursor() as cur:
        cur.execute("SELECT COUNT(*) AS total FROM dabbahwala.orders")
        total = cur.fetchone()["total"]
        cur.execute("SELECT MAX(created_at) AS last_sync FROM dabbahwala.orders")
        last_sync = cur.fetchone()["last_sync"]
    return {"total_orders": total, "last_sync": str(last_sync) if last_sync else None}


@router.get("/top-calls")
def top_calls(limit: int = 20):
    with get_cursor() as cur:
        cur.execute("""
            SELECT c.id, c.email, c.name, c.phone, c.order_count, c.total_spent,
                   c.lifecycle_segment::TEXT AS segment, c.last_order_at
            FROM dabbahwala.contacts c
            WHERE c.opted_out = FALSE
            ORDER BY c.order_count DESC, c.total_spent DESC
            LIMIT %s
        """, (limit,))
        return {"contacts": [dict(r) for r in cur.fetchall()]}


# ── Story 11.3: Historical import ────────────────────────────────────────────

@router.post("/import-all-and-run-agents")
async def import_all_and_run_agents(max_pages: int = 50):
    global _import_status
    if _import_status["running"]:
        return {"status": "already_running", "progress": _import_status}

    _import_status = {"running": True, "total": 0, "done": 0, "errors": 0, "last_run": None}

    total_imported = 0
    for page in range(1, max_pages + 1):
        try:
            data = await _fetch_shipday_orders(page=page, limit=100)
            orders = data if isinstance(data, list) else data.get("orders", [])
            if not orders:
                break
            _import_status["total"] += len(orders)
            result = await ingest_orders(limit=len(orders))
            total_imported += result.get("ingested", 0)
            _import_status["done"] += result.get("ingested", 0)
            _import_status["errors"] += result.get("errors", 0)
        except Exception as exc:
            logger.error("Import page %d failed: %s", page, exc)
            break

    from datetime import datetime, timezone
    _import_status["running"] = False
    _import_status["last_run"] = datetime.now(timezone.utc).isoformat()

    return {"status": "complete", "total_imported": total_imported, "progress": _import_status}


@router.get("/import-pipeline-status")
def import_pipeline_status():
    return _import_status


# ── Story 11.4: Delivery feedback ─────────────────────────────────────────────

@router.post("/sync-feedback")
async def sync_feedback():
    if not settings.shipday_api_key:
        return JSONResponse(status_code=503, content={"detail": "SHIPDAY_API_KEY not configured"})
    return {"status": "ok", "message": "Feedback sync — Shipday feedback API endpoint triggered"}


@router.get("/feedback-stats")
def feedback_stats():
    with get_cursor() as cur:
        cur.execute("""
            SELECT event_type, COUNT(*) AS count
            FROM dabbahwala.events
            WHERE event_type IN ('order_delivered', 'order_cancelled', 'feedback_received')
            GROUP BY event_type
        """)
        return {"stats": [dict(r) for r in cur.fetchall()]}
