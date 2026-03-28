"""E16 — Menu & History"""
import logging
from typing import Optional

import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.config import settings
from app.db import get_cursor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/menu", tags=["menu"])

_AIRTABLE_BASE = "https://api.airtable.com/v0"


class MenuItemRequest(BaseModel):
    name: str
    description: Optional[str] = None
    price: Optional[float] = None
    category: Optional[str] = None
    is_available: bool = True
    airtable_id: Optional[str] = None
    tags: Optional[str] = None


# ── Story 16.1: Catalog API ───────────────────────────────────────────────────

@router.get("/")
def list_menu(category: Optional[str] = None, available_only: bool = True):
    with get_cursor() as cur:
        conditions = []
        params = []
        if available_only:
            conditions.append("is_available = TRUE")
        if category:
            conditions.append("LOWER(category) = LOWER(%s)")
            params.append(category)
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        cur.execute(f"""
            SELECT id, name, description, price, category, is_available, tags, created_at
            FROM dabbahwala.menu_catalog
            {where}
            ORDER BY category, name
        """, params)
        return {"items": [dict(r) for r in cur.fetchall()]}


@router.get("/{item_id}")
def get_menu_item(item_id: int):
    with get_cursor() as cur:
        cur.execute("SELECT * FROM dabbahwala.menu_catalog WHERE id = %s", (item_id,))
        row = cur.fetchone()
        if not row:
            return JSONResponse(status_code=404, content={"detail": "Menu item not found"})
        return dict(row)


@router.post("/")
def create_menu_item(req: MenuItemRequest):
    with get_cursor(commit=True) as cur:
        cur.execute("""
            INSERT INTO dabbahwala.menu_catalog
                (name, description, price, category, is_available, airtable_id, tags)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (name) DO UPDATE SET
                description  = EXCLUDED.description,
                price        = EXCLUDED.price,
                category     = EXCLUDED.category,
                is_available = EXCLUDED.is_available,
                tags         = EXCLUDED.tags
            RETURNING id
        """, (req.name, req.description, req.price, req.category,
               req.is_available, req.airtable_id, req.tags))
        item_id = cur.fetchone()["id"]
    return {"status": "ok", "item_id": item_id}


@router.patch("/{item_id}/availability")
def toggle_availability(item_id: int, is_available: bool):
    with get_cursor(commit=True) as cur:
        cur.execute("""
            UPDATE dabbahwala.menu_catalog
            SET is_available = %s WHERE id = %s
        """, (is_available, item_id))
        if cur.rowcount == 0:
            return JSONResponse(status_code=404, content={"detail": "Menu item not found"})
    return {"status": "ok", "item_id": item_id, "is_available": is_available}


@router.get("/categories/list")
def list_categories():
    with get_cursor() as cur:
        cur.execute("""
            SELECT DISTINCT category FROM dabbahwala.menu_catalog
            WHERE category IS NOT NULL ORDER BY category
        """)
        return {"categories": [r["category"] for r in cur.fetchall()]}


# ── Story 16.2: Airtable sync ─────────────────────────────────────────────────

@router.post("/sync-airtable")
async def sync_menu_from_airtable():
    if not settings.airtable_api_key:
        return JSONResponse(status_code=503, content={"detail": "AIRTABLE_API_KEY not configured"})

    base_id = settings.airtable_base_id
    table_name = "Menu"

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
            name = f.get("Name") or f.get("name") or ""
            if not name:
                continue
            cur.execute("""
                INSERT INTO dabbahwala.menu_catalog
                    (name, description, price, category, is_available, airtable_id, tags)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (name) DO UPDATE SET
                    description  = EXCLUDED.description,
                    price        = EXCLUDED.price,
                    category     = EXCLUDED.category,
                    is_available = EXCLUDED.is_available,
                    airtable_id  = EXCLUDED.airtable_id,
                    tags         = EXCLUDED.tags
                RETURNING id, (xmax = 0) AS is_new
            """, (
                name,
                f.get("Description") or f.get("description"),
                float(f.get("Price") or f.get("price") or 0) or None,
                f.get("Category") or f.get("category"),
                bool(f.get("Available", True)),
                rec["id"],
                f.get("Tags") or f.get("tags"),
            ))
            row = cur.fetchone()
            if row and row.get("is_new"):
                created += 1
            else:
                updated += 1

    return {
        "status": "ok",
        "synced": len(records),
        "created": created,
        "updated": updated,
    }
