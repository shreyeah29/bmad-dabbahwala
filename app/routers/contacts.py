"""E14 — Prospects & Contacts"""
import csv
import io
import logging
import re
from typing import Optional

from fastapi import APIRouter, UploadFile, File
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.db import get_cursor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/contacts", tags=["contacts"])


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


class ContactUpdateRequest(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    lifecycle_segment: Optional[str] = None
    opted_out: Optional[bool] = None
    notes: Optional[str] = None
    tags: Optional[str] = None


class BulkSegmentRequest(BaseModel):
    contact_ids: list[int]
    lifecycle_segment: str


# ── Story 14.1: CSV Import ────────────────────────────────────────────────────

@router.post("/import")
async def import_contacts(file: UploadFile = File(...)):
    """
    Accept CSV with columns: email, phone, name, source, lifecycle_segment, tags, notes
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
                source = (row.get("source") or "import").strip()
                segment = (row.get("lifecycle_segment") or "cold").strip()
                tags = (row.get("tags") or "").strip() or None
                notes = (row.get("notes") or "").strip() or None

                if not email and not phone:
                    error_rows.append({"row": i, "error": "Missing email and phone"})
                    errors += 1
                    continue

                if email:
                    cur.execute("""
                        INSERT INTO dabbahwala.contacts
                            (email, phone, name, source, lifecycle_segment, tags, notes)
                        VALUES (%s, %s, %s, %s, %s::dabbahwala.lifecycle_segment_type, %s, %s)
                        ON CONFLICT (email) DO UPDATE SET
                            phone = COALESCE(EXCLUDED.phone, contacts.phone),
                            name  = COALESCE(EXCLUDED.name, contacts.name),
                            tags  = COALESCE(EXCLUDED.tags, contacts.tags),
                            notes = COALESCE(EXCLUDED.notes, contacts.notes),
                            updated_at = NOW()
                        RETURNING id, (xmax = 0) AS is_new
                    """, (email, phone, name, source, segment, tags, notes))
                else:
                    cur.execute("""
                        INSERT INTO dabbahwala.contacts (phone, name, source, lifecycle_segment, tags, notes)
                        VALUES (%s, %s, %s, %s::dabbahwala.lifecycle_segment_type, %s, %s)
                        ON CONFLICT DO NOTHING RETURNING id, TRUE AS is_new
                    """, (phone, name, source, segment, tags, notes))

                contact_row = cur.fetchone()
                if not contact_row:
                    cur.execute(
                        "SELECT id, FALSE AS is_new FROM dabbahwala.contacts WHERE email = %s OR phone = %s",
                        (email, phone)
                    )
                    contact_row = cur.fetchone()

                if contact_row.get("is_new"):
                    created += 1
                else:
                    updated += 1

            except Exception as exc:
                logger.error("CSV import row %d error: %s", i, exc)
                error_rows.append({"row": i, "error": str(exc)})
                errors += 1

    return {
        "status": "ok",
        "created": created,
        "updated": updated,
        "errors": errors,
        "error_details": error_rows[:20],
    }


# ── Story 14.2: Bulk update ───────────────────────────────────────────────────

@router.post("/bulk-segment")
def bulk_update_segment(req: BulkSegmentRequest):
    """Reassign a list of contact IDs to a new lifecycle segment."""
    if not req.contact_ids:
        return JSONResponse(status_code=422, content={"detail": "contact_ids is empty"})

    with get_cursor(commit=True) as cur:
        cur.execute("""
            UPDATE dabbahwala.contacts
            SET lifecycle_segment = %s::dabbahwala.lifecycle_segment_type,
                updated_at = NOW()
            WHERE id = ANY(%s)
        """, (req.lifecycle_segment, req.contact_ids))
        updated = cur.rowcount

    return {"status": "ok", "updated": updated, "segment": req.lifecycle_segment}


@router.post("/bulk-optout")
def bulk_optout(req: BulkSegmentRequest):
    """Opt out a list of contact IDs."""
    with get_cursor(commit=True) as cur:
        cur.execute("""
            UPDATE dabbahwala.contacts
            SET opted_out = TRUE, lifecycle_segment = 'optout'::dabbahwala.lifecycle_segment_type,
                updated_at = NOW()
            WHERE id = ANY(%s)
        """, (req.contact_ids,))
        updated = cur.rowcount
    return {"status": "ok", "opted_out": updated}


# ── Story 14.3: Single contact ops ───────────────────────────────────────────

@router.get("/")
def list_contacts(
    segment: Optional[str] = None,
    opted_out: Optional[bool] = None,
    limit: int = 100,
    offset: int = 0,
):
    with get_cursor() as cur:
        conditions = []
        params: list = []
        if segment:
            conditions.append("lifecycle_segment = %s::dabbahwala.lifecycle_segment_type")
            params.append(segment)
        if opted_out is not None:
            conditions.append("opted_out = %s")
            params.append(opted_out)
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        params += [limit, offset]
        cur.execute(f"""
            SELECT id, email, phone, name, lifecycle_segment::TEXT AS segment,
                   opted_out, order_count, total_spent, last_order_at, tags, notes, created_at
            FROM dabbahwala.contacts
            {where}
            ORDER BY updated_at DESC
            LIMIT %s OFFSET %s
        """, params)
        return {"contacts": [dict(r) for r in cur.fetchall()]}


@router.get("/{contact_id}")
def get_contact(contact_id: int):
    with get_cursor() as cur:
        cur.execute("""
            SELECT id, email, phone, name, lifecycle_segment::TEXT AS segment,
                   opted_out, order_count, total_spent, last_order_at, tags, notes,
                   cooling_until, created_at, updated_at
            FROM dabbahwala.contacts WHERE id = %s
        """, (contact_id,))
        row = cur.fetchone()
        if not row:
            return JSONResponse(status_code=404, content={"detail": "Contact not found"})
        return dict(row)


@router.patch("/{contact_id}")
def update_contact(contact_id: int, req: ContactUpdateRequest):
    fields = []
    params = []
    if req.name is not None:
        fields.append("name = %s"); params.append(req.name)
    if req.phone is not None:
        fields.append("phone = %s"); params.append(_normalize_phone(req.phone) or req.phone)
    if req.email is not None:
        fields.append("email = %s"); params.append(req.email.lower())
    if req.lifecycle_segment is not None:
        fields.append("lifecycle_segment = %s::dabbahwala.lifecycle_segment_type")
        params.append(req.lifecycle_segment)
    if req.opted_out is not None:
        fields.append("opted_out = %s"); params.append(req.opted_out)
    if req.notes is not None:
        fields.append("notes = %s"); params.append(req.notes)
    if req.tags is not None:
        fields.append("tags = %s"); params.append(req.tags)

    if not fields:
        return JSONResponse(status_code=422, content={"detail": "No fields to update"})

    fields.append("updated_at = NOW()")
    params.append(contact_id)

    with get_cursor(commit=True) as cur:
        cur.execute(
            f"UPDATE dabbahwala.contacts SET {', '.join(fields)} WHERE id = %s",
            params
        )
        if cur.rowcount == 0:
            return JSONResponse(status_code=404, content={"detail": "Contact not found"})

    return {"status": "ok", "contact_id": contact_id}


@router.delete("/{contact_id}")
def delete_contact(contact_id: int):
    with get_cursor(commit=True) as cur:
        cur.execute("DELETE FROM dabbahwala.contacts WHERE id = %s", (contact_id,))
        if cur.rowcount == 0:
            return JSONResponse(status_code=404, content={"detail": "Contact not found"})
    return {"status": "ok", "deleted": contact_id}


@router.get("/{contact_id}/history")
def contact_history(contact_id: int):
    with get_cursor() as cur:
        cur.execute("""
            SELECT id, event_type, payload, created_at
            FROM dabbahwala.events
            WHERE contact_id = %s
            ORDER BY created_at DESC
            LIMIT 50
        """, (contact_id,))
        events = [dict(r) for r in cur.fetchall()]

        cur.execute("""
            SELECT id, direction, body, status, created_at
            FROM dabbahwala.telnyx_messages
            WHERE contact_id = %s
            ORDER BY created_at DESC
            LIMIT 20
        """, (contact_id,))
        messages = [dict(r) for r in cur.fetchall()]

    return {"events": events, "messages": messages}
