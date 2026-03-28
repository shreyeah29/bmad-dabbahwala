"""E21 — Chatbot"""
import logging
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.db import get_cursor
from app.services.llm_service import SONNET, call_claude

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chatbot", tags=["chatbot"])


class ChatRequest(BaseModel):
    message: str
    contact_id: Optional[int] = None
    session_id: Optional[str] = None
    history: Optional[list[dict]] = None  # [{"role": "user"|"assistant", "content": str}]


class ReindexRequest(BaseModel):
    force: bool = False


_CHATBOT_SYSTEM = """You are DabbahWala's AI assistant — friendly, knowledgeable about Indian food delivery in Atlanta.
You help customers with: menu questions, order status, pricing, delivery areas, reorder suggestions, promotions.
Keep responses concise and warm. If you don't know something, say so honestly.
Do NOT make up order statuses or delivery ETAs — direct users to contact support for real-time info."""


# ── Story 21.1: Ask & Suggest ─────────────────────────────────────────────────

@router.post("/ask")
def chatbot_ask(req: ChatRequest):
    """Answer a customer or staff question using Claude + context."""
    history = req.history or []

    # Optionally augment with contact context
    context_snippet = ""
    if req.contact_id:
        try:
            with get_cursor() as cur:
                cur.execute("""
                    SELECT name, lifecycle_segment::TEXT AS segment, order_count, last_order_at
                    FROM dabbahwala.contacts WHERE id = %s
                """, (req.contact_id,))
                row = cur.fetchone()
                if row:
                    context_snippet = (
                        f"\n\nCustomer context: Name={row['name']}, "
                        f"Segment={row['segment']}, "
                        f"Orders={row['order_count']}, "
                        f"Last order={row['last_order_at']}"
                    )
        except Exception:
            pass

    # Pull relevant menu items for context
    menu_context = ""
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT name, price, category
                FROM dabbahwala.menu_catalog
                WHERE is_available = TRUE
                ORDER BY category, name LIMIT 30
            """)
            items = cur.fetchall()
            if items:
                menu_lines = [f"- {r['name']} (${r['price'] or 'N/A'}, {r['category'] or 'General'})" for r in items]
                menu_context = "\n\nMenu highlights:\n" + "\n".join(menu_lines)
    except Exception:
        pass

    system = _CHATBOT_SYSTEM + context_snippet + menu_context

    messages = history + [{"role": "user", "content": req.message}]

    try:
        resp = call_claude(SONNET, system, messages, max_tokens=512)
        reply = next((b.text for b in resp.content if b.type == "text"), "I'm not sure how to help with that.")
        return {
            "reply": reply,
            "session_id": req.session_id,
            "contact_id": req.contact_id,
        }
    except Exception as exc:
        logger.error("Chatbot error: %s", exc)
        return JSONResponse(status_code=500, content={"detail": str(exc)})


@router.post("/suggest")
def suggest_reorder(contact_id: int):
    """Suggest items for a contact to reorder based on their history."""
    with get_cursor() as cur:
        cur.execute("""
            SELECT oi.item_name, COUNT(*) AS times_ordered
            FROM dabbahwala.order_items oi
            JOIN dabbahwala.orders o ON o.id = oi.order_id
            WHERE o.contact_id = %s
            GROUP BY oi.item_name
            ORDER BY times_ordered DESC
            LIMIT 5
        """, (contact_id,))
        past_items = [dict(r) for r in cur.fetchall()]

        cur.execute("SELECT name FROM dabbahwala.contacts WHERE id = %s", (contact_id,))
        row = cur.fetchone()
        name = row["name"] if row else "there"

    if not past_items:
        return {"suggestion": f"Hi {name}! Check out our menu — we have lots of delicious options!", "past_items": []}

    system = _CHATBOT_SYSTEM
    item_list = ", ".join(f"{i['item_name']} (x{i['times_ordered']})" for i in past_items)
    messages = [{
        "role": "user",
        "content": (
            f"Customer {name} has previously ordered: {item_list}. "
            "Write a warm 1-2 sentence reorder suggestion message personalized to them."
        )
    }]

    try:
        resp = call_claude(SONNET, system, messages, max_tokens=200)
        suggestion = next((b.text for b in resp.content if b.type == "text"), "Ready to order your favorites again?")
        return {"suggestion": suggestion, "past_items": past_items}
    except Exception as exc:
        return JSONResponse(status_code=500, content={"detail": str(exc)})


# ── Story 21.2: Reindex ───────────────────────────────────────────────────────

@router.post("/reindex")
def reindex_chatbot(req: ReindexRequest):
    """
    Refresh cached context for the chatbot (menu, playbook snippets).
    Clears the playbook hash cache so it re-fetches on next agent run.
    """
    try:
        from app.services.llm_service import _playbook_cache
        _playbook_cache.clear()
        cleared_playbook = True
    except Exception:
        cleared_playbook = False

    # Count available menu items and playbook rules to confirm data
    with get_cursor() as cur:
        cur.execute("SELECT COUNT(*) AS cnt FROM dabbahwala.menu_catalog WHERE is_available = TRUE")
        menu_count = cur.fetchone()["cnt"]
        cur.execute("SELECT COUNT(*) AS cnt FROM dabbahwala.agent_playbook WHERE is_active = TRUE")
        rule_count = cur.fetchone()["cnt"]

    return {
        "status": "ok",
        "playbook_cache_cleared": cleared_playbook,
        "menu_items": menu_count,
        "playbook_rules": rule_count,
    }
