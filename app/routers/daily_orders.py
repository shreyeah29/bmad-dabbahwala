"""E12 — Daily CSV Order Processing"""
import csv
import io
import logging
import re
from typing import Optional

from fastapi import APIRouter, UploadFile, File
from fastapi.responses import JSONResponse

from app.db import get_cursor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/daily-orders", tags=["daily-orders"])


def _normalize_phone(phone: str) -> Optional[str]:
    if not phone:
        return None
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits[0] == "1":
        return f"+{digits}"
    if len(digits) == 12 and digits[:2] == "91":
        return f"+{digits}"
    return f"+{digits}" if len(digits) >= 7 else None


def _match_menu_item(cur, name: str) -> Optional[int]:
    # Exact match first
    cur.execute("""
        SELECT id FROM dabbahwala.menu_catalog
        WHERE LOWER(name) = LOWER(%s) AND is_available = TRUE
        LIMIT 1
    """, (name,))
    row = cur.fetchone()
    if row:
        return row["id"]

    # Partial match (fuzzy)
    cur.execute("""
        SELECT id FROM dabbahwala.menu_catalog
        WHERE LOWER(name) LIKE LOWER(%s) AND is_available = TRUE
        LIMIT 1
    """, (f"%{name}%",))
    row = cur.fetchone()
    return row["id"] if row else None


@router.post("/")
async def process_daily_orders(file: UploadFile = File(...)):
    """
    Accept daily CSV upload with columns:
    email, phone, name, order_ref, total_amount, item_name, quantity, notes
    """
    if not file.filename.endswith(".csv"):
        return JSONResponse(status_code=422, content={"detail": "File must be a .csv"})

    content = await file.read()
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))

    created = updated = errors = 0
    error_rows = []

    with get_cursor(commit=True) as cur:
        for i, row in enumerate(reader, start=2):
            try:
                email = (row.get("email") or "").strip().lower() or None
                phone = _normalize_phone((row.get("phone") or "").strip())
                name = (row.get("name") or "").strip() or None
                order_ref = (row.get("order_ref") or "").strip() or None
                total = float(row.get("total_amount") or 0)
                item_name = (row.get("item_name") or "").strip()
                quantity = int(row.get("quantity") or 1)
                notes = (row.get("notes") or "").strip() or None

                if not email and not phone:
                    error_rows.append({"row": i, "error": "Missing email and phone"})
                    errors += 1
                    continue

                # Upsert contact
                if email:
                    cur.execute("""
                        INSERT INTO dabbahwala.contacts (email, phone, name, source)
                        VALUES (%s, %s, %s, 'csv')
                        ON CONFLICT (email) DO UPDATE SET
                            phone = COALESCE(EXCLUDED.phone, contacts.phone),
                            name  = COALESCE(EXCLUDED.name, contacts.name),
                            updated_at = NOW()
                        RETURNING id, (xmax = 0) AS is_new
                    """, (email, phone, name))
                else:
                    cur.execute("""
                        INSERT INTO dabbahwala.contacts (phone, name, source)
                        VALUES (%s, %s, 'csv')
                        ON CONFLICT DO NOTHING RETURNING id, TRUE AS is_new
                    """, (phone, name))

                contact_row = cur.fetchone()
                if not contact_row:
                    cur.execute("SELECT id FROM dabbahwala.contacts WHERE email = %s OR phone = %s", (email, phone))
                    contact_row = cur.fetchone()

                contact_id = contact_row["id"]
                is_new = contact_row.get("is_new", False)

                # Upsert order
                if order_ref:
                    cur.execute("""
                        INSERT INTO dabbahwala.orders
                            (contact_id, order_ref, total_amount, notes, status)
                        VALUES (%s, %s, %s, %s, 'pending')
                        ON CONFLICT (order_ref) DO UPDATE SET
                            total_amount = EXCLUDED.total_amount,
                            notes = EXCLUDED.notes
                        RETURNING id
                    """, (contact_id, order_ref, total, notes))
                    order_row = cur.fetchone()
                    order_id = order_row["id"]

                    # Add order item
                    if item_name and order_id:
                        menu_id = _match_menu_item(cur, item_name)
                        cur.execute("""
                            INSERT INTO dabbahwala.order_items (order_id, item_name, quantity)
                            VALUES (%s, %s, %s)
                            ON CONFLICT DO NOTHING
                        """, (order_id, item_name, quantity))

                    # Update contact order count
                    cur.execute("""
                        UPDATE dabbahwala.contacts SET
                            order_count = (SELECT COUNT(*) FROM dabbahwala.orders WHERE contact_id = %s),
                            last_order_at = NOW(), updated_at = NOW()
                        WHERE id = %s
                    """, (contact_id, contact_id))

                if is_new:
                    created += 1
                else:
                    updated += 1

            except Exception as exc:
                logger.error("CSV row %d error: %s", i, exc)
                error_rows.append({"row": i, "error": str(exc)})
                errors += 1

    return {
        "status": "ok",
        "created": created,
        "updated": updated,
        "errors": errors,
        "error_details": error_rows[:20],
    }
