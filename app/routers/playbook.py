"""E17 — Playbook Rules"""
import logging
from typing import Optional

import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.config import settings
from app.db import get_cursor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/playbook", tags=["playbook"])

_AIRTABLE_BASE = "https://api.airtable.com/v0"


class PlaybookRuleRequest(BaseModel):
    category: str
    rule_text: str
    segment: Optional[str] = None
    priority: int = 50
    is_active: bool = True
    airtable_id: Optional[str] = None


# ── Story 17.1: Rules API ─────────────────────────────────────────────────────

@router.get("/")
def list_rules(category: Optional[str] = None, segment: Optional[str] = None, active_only: bool = True):
    with get_cursor() as cur:
        conditions = []
        params = []
        if active_only:
            conditions.append("is_active = TRUE")
        if category:
            conditions.append("LOWER(category) = LOWER(%s)")
            params.append(category)
        if segment:
            conditions.append("(segment IS NULL OR segment = %s)")
            params.append(segment)
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        cur.execute(f"""
            SELECT id, category, rule_text, segment, priority, is_active, airtable_id, created_at
            FROM dabbahwala.agent_playbook
            {where}
            ORDER BY priority DESC, category
        """, params)
        return {"rules": [dict(r) for r in cur.fetchall()]}


@router.get("/{rule_id}")
def get_rule(rule_id: int):
    with get_cursor() as cur:
        cur.execute("SELECT * FROM dabbahwala.agent_playbook WHERE id = %s", (rule_id,))
        row = cur.fetchone()
        if not row:
            return JSONResponse(status_code=404, content={"detail": "Rule not found"})
        return dict(row)


@router.post("/")
def create_rule(req: PlaybookRuleRequest):
    with get_cursor(commit=True) as cur:
        cur.execute("""
            INSERT INTO dabbahwala.agent_playbook
                (category, rule_text, segment, priority, is_active, airtable_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (req.category, req.rule_text, req.segment, req.priority,
               req.is_active, req.airtable_id))
        rule_id = cur.fetchone()["id"]
    return {"status": "ok", "rule_id": rule_id}


@router.put("/{rule_id}")
def update_rule(rule_id: int, req: PlaybookRuleRequest):
    with get_cursor(commit=True) as cur:
        cur.execute("""
            UPDATE dabbahwala.agent_playbook
            SET category = %s, rule_text = %s, segment = %s,
                priority = %s, is_active = %s
            WHERE id = %s
        """, (req.category, req.rule_text, req.segment,
               req.priority, req.is_active, rule_id))
        if cur.rowcount == 0:
            return JSONResponse(status_code=404, content={"detail": "Rule not found"})
    return {"status": "ok", "rule_id": rule_id}


@router.delete("/{rule_id}")
def delete_rule(rule_id: int):
    with get_cursor(commit=True) as cur:
        cur.execute("DELETE FROM dabbahwala.agent_playbook WHERE id = %s", (rule_id,))
        if cur.rowcount == 0:
            return JSONResponse(status_code=404, content={"detail": "Rule not found"})
    return {"status": "ok", "deleted": rule_id}


@router.get("/categories/list")
def list_categories():
    with get_cursor() as cur:
        cur.execute("""
            SELECT DISTINCT category FROM dabbahwala.agent_playbook
            WHERE is_active = TRUE ORDER BY category
        """)
        return {"categories": [r["category"] for r in cur.fetchall()]}


# ── Story 17.2: Airtable sync ─────────────────────────────────────────────────

@router.post("/sync-airtable")
async def sync_playbook_from_airtable():
    if not settings.airtable_api_key:
        return JSONResponse(status_code=503, content={"detail": "AIRTABLE_API_KEY not configured"})

    base_id = settings.airtable_base_id
    table_name = "Playbook"

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
            rule_text = f.get("Rule") or f.get("rule_text") or ""
            category = f.get("Category") or f.get("category") or "general"
            if not rule_text:
                continue
            cur.execute("""
                INSERT INTO dabbahwala.agent_playbook
                    (category, rule_text, segment, priority, is_active, airtable_id)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (airtable_id) DO UPDATE SET
                    category  = EXCLUDED.category,
                    rule_text = EXCLUDED.rule_text,
                    segment   = EXCLUDED.segment,
                    priority  = EXCLUDED.priority,
                    is_active = EXCLUDED.is_active
                RETURNING id, (xmax = 0) AS is_new
            """, (
                category,
                rule_text,
                f.get("Segment") or f.get("segment"),
                int(f.get("Priority") or 50),
                bool(f.get("Active", True)),
                rec["id"],
            ))
            row = cur.fetchone()
            if row and row.get("is_new"):
                created += 1
            else:
                updated += 1

    # Invalidate playbook hash cache so agents re-fetch
    try:
        from app.services.llm_service import _playbook_cache
        _playbook_cache.clear()
    except Exception:
        pass

    return {
        "status": "ok",
        "synced": len(records),
        "created": created,
        "updated": updated,
    }
