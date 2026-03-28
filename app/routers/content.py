"""E18 — Team Content"""
import logging
from typing import Optional

import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.config import settings
from app.db import get_cursor
from app.services.llm_service import HAIKU, call_claude

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/content", tags=["content"])

_AIRTABLE_BASE = "https://api.airtable.com/v0"


class ContentSubmitRequest(BaseModel):
    title: str
    body: str
    content_type: str  # e.g. "tip", "recipe", "promotion", "announcement"
    author: Optional[str] = None
    segment: Optional[str] = None
    tags: Optional[str] = None


class ContentSearchRequest(BaseModel):
    query: str
    content_type: Optional[str] = None
    limit: int = 10


# ── Story 18.1: Sync & Submit ─────────────────────────────────────────────────

@router.post("/submit")
def submit_content(req: ContentSubmitRequest):
    with get_cursor(commit=True) as cur:
        cur.execute("""
            INSERT INTO dabbahwala.team_content
                (title, body, content_type, author, segment, tags, status)
            VALUES (%s, %s, %s, %s, %s, %s, 'pending')
            RETURNING id
        """, (req.title, req.body, req.content_type, req.author, req.segment, req.tags))
        content_id = cur.fetchone()["id"]
    return {"status": "ok", "content_id": content_id}


@router.post("/sync-airtable")
async def sync_content_from_airtable():
    if not settings.airtable_api_key:
        return JSONResponse(status_code=503, content={"detail": "AIRTABLE_API_KEY not configured"})

    base_id = settings.airtable_base_id
    table_name = "Content"

    records = []
    offset = None

    async with httpx.AsyncClient(timeout=30) as http:
        while True:
            params = {"pageSize": 100}
            if offset:
                params["offset"] = offset
            resp = await http.get(
                f"{_AIRTABLE_BASE}/{base_id}/{table_name}",
                headers={"Authorization": f"Bearer {settings.airtable_api_key}"},
                params=params,
            )
            if resp.status_code != 200:
                return JSONResponse(
                    status_code=502,
                    content={"detail": f"Airtable error: {resp.text[:200]}"}
                )
            data = resp.json()
            records.extend(data.get("records", []))
            offset = data.get("offset")
            if not offset:
                break

    created = updated = 0
    with get_cursor(commit=True) as cur:
        for rec in records:
            f = rec.get("fields", {})
            title = f.get("Title") or f.get("title") or ""
            body = f.get("Body") or f.get("body") or f.get("Content") or ""
            if not title or not body:
                continue
            cur.execute("""
                INSERT INTO dabbahwala.team_content
                    (title, body, content_type, author, segment, tags, status, airtable_id)
                VALUES (%s, %s, %s, %s, %s, %s, 'approved', %s)
                ON CONFLICT (airtable_id) DO UPDATE SET
                    title        = EXCLUDED.title,
                    body         = EXCLUDED.body,
                    content_type = EXCLUDED.content_type,
                    author       = EXCLUDED.author,
                    segment      = EXCLUDED.segment,
                    tags         = EXCLUDED.tags
                RETURNING id, (xmax = 0) AS is_new
            """, (
                title,
                body,
                f.get("Type") or f.get("content_type") or "general",
                f.get("Author") or f.get("author"),
                f.get("Segment") or f.get("segment"),
                f.get("Tags") or f.get("tags"),
                rec["id"],
            ))
            row = cur.fetchone()
            if row and row.get("is_new"):
                created += 1
            else:
                updated += 1

    return {"status": "ok", "synced": len(records), "created": created, "updated": updated}


# ── Story 18.2: Browse & Search ───────────────────────────────────────────────

@router.get("/")
def list_content(
    content_type: Optional[str] = None,
    segment: Optional[str] = None,
    status: Optional[str] = "approved",
    limit: int = 50,
):
    with get_cursor() as cur:
        conditions = []
        params = []
        if status:
            conditions.append("status = %s")
            params.append(status)
        if content_type:
            conditions.append("content_type = %s")
            params.append(content_type)
        if segment:
            conditions.append("(segment IS NULL OR segment = %s)")
            params.append(segment)
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        params.append(limit)
        cur.execute(f"""
            SELECT id, title, body, content_type, author, segment, tags, status, created_at
            FROM dabbahwala.team_content
            {where}
            ORDER BY created_at DESC
            LIMIT %s
        """, params)
        return {"content": [dict(r) for r in cur.fetchall()]}


@router.post("/search")
def search_content(req: ContentSearchRequest):
    with get_cursor() as cur:
        conditions = ["(LOWER(title) LIKE %s OR LOWER(body) LIKE %s)"]
        params = [f"%{req.query.lower()}%", f"%{req.query.lower()}%"]
        if req.content_type:
            conditions.append("content_type = %s")
            params.append(req.content_type)
        where = "WHERE " + " AND ".join(conditions)
        params.append(req.limit)
        cur.execute(f"""
            SELECT id, title, body, content_type, author, segment, tags, status, created_at
            FROM dabbahwala.team_content
            {where}
            ORDER BY created_at DESC
            LIMIT %s
        """, params)
        return {"results": [dict(r) for r in cur.fetchall()]}


@router.get("/{content_id}")
def get_content(content_id: int):
    with get_cursor() as cur:
        cur.execute("SELECT * FROM dabbahwala.team_content WHERE id = %s", (content_id,))
        row = cur.fetchone()
        if not row:
            return JSONResponse(status_code=404, content={"detail": "Content not found"})
        return dict(row)
