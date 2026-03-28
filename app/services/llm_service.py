"""
LLM Service Foundation — shared Anthropic client, model constants,
prompt caching, and playbook RAG injection.
"""
import hashlib
import logging
from typing import Any, Dict, List, Optional

import anthropic

from app.config import settings

logger = logging.getLogger(__name__)

# ── Model constants ────────────────────────────────────────────────────────────
HAIKU = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-4-6"

# ── Client (lazy) ─────────────────────────────────────────────────────────────
_client: Optional[anthropic.Anthropic] = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    return _client


# ── Playbook cache ────────────────────────────────────────────────────────────
_playbook_cache: Dict[str, Any] = {}  # key: frozenset(categories), value: {hash, text}


def _fetch_playbook_rules(categories: List[str], cursor=None) -> str:
    """
    Query agent_playbook for given categories.
    Cache result by SHA-256 hash — re-queries only when content changes.
    """
    if cursor is None:
        from app.db import get_cursor as _gc
        with _gc() as cur:
            return _fetch_playbook_rules(categories, cursor=cur)

    cache_key = frozenset(categories)

    cursor.execute("""
        SELECT title, content
        FROM dabbahwala.agent_playbook
        WHERE (segment::TEXT = ANY(%s) OR segment IS NULL)
          AND is_active = TRUE
        ORDER BY id
    """, (list(categories),))
    rows = cursor.fetchall()

    if not rows:
        return ""

    combined = "\n\n".join(f"## {r['title']}\n{r['content']}" for r in rows)
    content_hash = hashlib.sha256(combined.encode()).hexdigest()

    cached = _playbook_cache.get(cache_key)
    if cached and cached["hash"] == content_hash:
        return cached["text"]

    _playbook_cache[cache_key] = {"hash": content_hash, "text": combined}
    logger.debug("Playbook cache updated for categories=%s hash=%s", list(categories), content_hash[:8])
    return combined


# ── Cache-control helper ──────────────────────────────────────────────────────

def system_block(text: str) -> Dict:
    """Wrap a system prompt in a cache_control ephemeral block."""
    return {
        "type": "text",
        "text": text,
        "cache_control": {"type": "ephemeral"},
    }


# ── Main call entry point ──────────────────────────────────────────────────────

def call_claude(
    model: str,
    system: str,
    messages: List[Dict],
    tools: Optional[List[Dict]] = None,
    max_tokens: int = 1024,
) -> anthropic.types.Message:
    """
    Single entry point for all Claude calls.
    System prompt is always wrapped in ephemeral cache_control block.
    """
    client = _get_client()

    kwargs: Dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "system": [system_block(system)],
        "messages": messages,
    }
    if tools:
        kwargs["tools"] = tools

    logger.debug("Calling Claude model=%s messages=%d", model, len(messages))
    response = client.messages.create(**kwargs)
    return response


def extract_tool_input(response: anthropic.types.Message, tool_name: str) -> Optional[Dict]:
    """Extract input dict from a tool_use block by name."""
    for block in response.content:
        if block.type == "tool_use" and block.name == tool_name:
            return block.input
    return None
