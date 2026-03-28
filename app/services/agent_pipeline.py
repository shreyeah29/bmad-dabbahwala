"""
AI Agent Pipeline — 8 Claude calls per contact.
Layer 1 (Observer): Menu, Sentiment, Intent, Engagement — parallel
Layer 2 (Advisor):  Stage, Channel, Offer, Escalation — parallel
Layer 3 (Orchestrator): Final action decision
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.services.llm_service import (
    HAIKU, SONNET, call_claude, extract_tool_input, _fetch_playbook_rules
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 1 — Observer Agents
# ═══════════════════════════════════════════════════════════════════════════════

def run_menu_agent(contact: Dict, menu_items: List[Dict], past_orders: List[Dict]) -> Dict:
    menu_text = "\n".join(f"- {m['name']} (${m.get('price', '?')}): {m.get('description', '')}" for m in menu_items[:20])
    order_text = "\n".join(f"- {o.get('notes', 'order')} on {o.get('delivery_date', '?')}" for o in past_orders[:10])

    system = (
        "You are a menu analyst for DabbahWala, an Indian food delivery service. "
        "Given a contact's order history and this week's menu, identify the best picks."
    )
    messages = [{"role": "user", "content": (
        f"Contact: {contact.get('name', 'Customer')} (segment: {contact.get('lifecycle_segment', 'unknown')})\n"
        f"Past orders:\n{order_text or 'No orders yet'}\n\n"
        f"This week's menu:\n{menu_text or 'Menu not available'}\n\n"
        "Use the submit_menu_picks tool to respond."
    )}]
    tools = [{
        "name": "submit_menu_picks",
        "description": "Submit menu recommendations for this contact",
        "input_schema": {
            "type": "object",
            "properties": {
                "top_picks": {"type": "array", "items": {"type": "string"}, "description": "Top 3 menu items"},
                "bridge_item": {"type": "string", "description": "Item to introduce new flavours"},
                "avoid": {"type": "array", "items": {"type": "string"}, "description": "Items to avoid"},
            },
            "required": ["top_picks", "bridge_item", "avoid"],
        },
    }]
    try:
        resp = call_claude(HAIKU, system, messages, tools=tools)
        result = extract_tool_input(resp, "submit_menu_picks") or {}
        return {"top_picks": result.get("top_picks", []), "bridge_item": result.get("bridge_item", ""), "avoid": result.get("avoid", [])}
    except Exception as exc:
        logger.error("Menu agent failed: %s", exc)
        return {"top_picks": [], "bridge_item": "", "avoid": [], "error": str(exc)}


def run_sentiment_agent(contact: Dict, comm_history: List[Dict], recent_events: List[Dict]) -> Dict:
    sms_text = "\n".join(f"- [{m.get('direction', '?')}] {m.get('body', '')}" for m in comm_history[:20])
    events_text = "\n".join(f"- {e.get('event_type', '?')}" for e in recent_events[:15])

    system = (
        "You are a sentiment analyst for DabbahWala marketing. "
        "Analyse customer communication and events to determine sentiment."
    )
    messages = [{"role": "user", "content": (
        f"Contact: {contact.get('name', 'Customer')}\n"
        f"Recent SMS:\n{sms_text or 'No SMS history'}\n\n"
        f"Recent events:\n{events_text or 'No recent events'}\n\n"
        "Use submit_sentiment tool to respond."
    )}]
    tools = [{
        "name": "submit_sentiment",
        "description": "Submit sentiment analysis",
        "input_schema": {
            "type": "object",
            "properties": {
                "sentiment": {"type": "string", "enum": ["positive", "neutral", "negative"]},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "summary": {"type": "string"},
            },
            "required": ["sentiment", "confidence", "summary"],
        },
    }]
    try:
        resp = call_claude(HAIKU, system, messages, tools=tools)
        result = extract_tool_input(resp, "submit_sentiment") or {}
        return {"sentiment": result.get("sentiment", "neutral"), "confidence": result.get("confidence", 0.5), "summary": result.get("summary", "")}
    except Exception as exc:
        logger.error("Sentiment agent failed: %s", exc)
        return {"sentiment": "neutral", "confidence": 0.0, "summary": "", "error": str(exc)}


def run_intent_agent(contact: Dict, recent_events: List[Dict], menu_picks: Dict) -> Dict:
    events_text = "\n".join(f"- {e.get('event_type', '?')} at {e.get('created_at', '?')}" for e in recent_events[:20])
    picks_text = ", ".join(menu_picks.get("top_picks", [])) or "none"

    system = (
        "You are an intent classifier for DabbahWala. "
        "Classify the contact's current buying intent based on their behaviour."
    )
    messages = [{"role": "user", "content": (
        f"Contact: {contact.get('name', 'Customer')}, segment={contact.get('lifecycle_segment', '?')}, "
        f"orders={contact.get('order_count', 0)}\n"
        f"Menu top picks: {picks_text}\n"
        f"Recent events:\n{events_text or 'None'}\n\n"
        "Use submit_intent tool to respond."
    )}]
    tools = [{
        "name": "submit_intent",
        "description": "Submit intent classification",
        "input_schema": {
            "type": "object",
            "properties": {
                "intent": {"type": "string", "enum": ["ready_to_order", "needs_info", "price_sensitive", "not_interested", "unknown"]},
                "signals": {"type": "array", "items": {"type": "string"}},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            },
            "required": ["intent", "signals", "confidence"],
        },
    }]
    try:
        resp = call_claude(SONNET, system, messages, tools=tools)
        result = extract_tool_input(resp, "submit_intent") or {}
        return {"intent": result.get("intent", "unknown"), "signals": result.get("signals", []), "confidence": result.get("confidence", 0.5)}
    except Exception as exc:
        logger.error("Intent agent failed: %s", exc)
        return {"intent": "unknown", "signals": [], "confidence": 0.0, "error": str(exc)}


def run_engagement_agent(contact: Dict, rollup: Optional[Dict], recent_events: List[Dict]) -> Dict:
    rollup = rollup or {}
    system = (
        "You are an engagement analyst for DabbahWala. "
        "Score contact engagement from 0 (completely disengaged) to 1 (highly engaged)."
    )
    messages = [{"role": "user", "content": (
        f"Contact: {contact.get('name', 'Customer')}, segment={contact.get('lifecycle_segment', '?')}\n"
        f"7-day orders: {rollup.get('orders_7d', 0)}, 30-day orders: {rollup.get('orders_30d', 0)}\n"
        f"7-day SMS sent: {rollup.get('sms_sent_7d', 0)}, received: {rollup.get('sms_recv_7d', 0)}\n"
        f"Email opens 7d: {rollup.get('email_opens_7d', 0)}\n"
        f"Recent event count: {len(recent_events)}\n\n"
        "Use submit_engagement tool to respond."
    )}]
    tools = [{
        "name": "submit_engagement",
        "description": "Submit engagement assessment",
        "input_schema": {
            "type": "object",
            "properties": {
                "engagement_score": {"type": "number", "minimum": 0, "maximum": 1},
                "trend": {"type": "string", "enum": ["rising", "flat", "falling"]},
                "last_touch_hours_ago": {"type": "number"},
            },
            "required": ["engagement_score", "trend", "last_touch_hours_ago"],
        },
    }]
    try:
        resp = call_claude(HAIKU, system, messages, tools=tools)
        result = extract_tool_input(resp, "submit_engagement") or {}
        return {"engagement_score": result.get("engagement_score", 0.0), "trend": result.get("trend", "flat"), "last_touch_hours_ago": result.get("last_touch_hours_ago", 999)}
    except Exception as exc:
        logger.error("Engagement agent failed: %s", exc)
        return {"engagement_score": 0.0, "trend": "flat", "last_touch_hours_ago": 999, "error": str(exc)}


async def run_layer1_parallel(contact: Dict, context: Dict) -> Dict:
    """Run all 4 Layer 1 agents concurrently."""
    loop = asyncio.get_event_loop()

    menu_task = loop.run_in_executor(None, run_menu_agent,
        contact, context.get("menu_items", []), context.get("past_orders", []))
    sentiment_task = loop.run_in_executor(None, run_sentiment_agent,
        contact, context.get("comm_history", []), context.get("recent_events", []))
    # Intent and engagement depend on nothing else from L1 at call time
    intent_placeholder = loop.run_in_executor(None, run_intent_agent,
        contact, context.get("recent_events", []), {})
    engagement_task = loop.run_in_executor(None, run_engagement_agent,
        contact, context.get("rollup"), context.get("recent_events", []))

    menu, sentiment, intent_base, engagement = await asyncio.gather(
        menu_task, sentiment_task, intent_placeholder, engagement_task,
        return_exceptions=True,
    )

    # If any task returned an exception, convert to error dict
    def _safe(result, default):
        if isinstance(result, Exception):
            logger.error("Layer 1 agent exception: %s", result)
            return {**default, "error": str(result)}
        return result

    menu = _safe(menu, {"top_picks": [], "bridge_item": "", "avoid": []})
    sentiment = _safe(sentiment, {"sentiment": "neutral", "confidence": 0.0, "summary": ""})
    engagement = _safe(engagement, {"engagement_score": 0.0, "trend": "flat", "last_touch_hours_ago": 999})

    # Re-run intent with actual menu picks
    try:
        intent = await loop.run_in_executor(None, run_intent_agent,
            contact, context.get("recent_events", []), menu)
    except Exception as exc:
        logger.error("Intent agent exception: %s", exc)
        intent = {"intent": "unknown", "signals": [], "confidence": 0.0, "error": str(exc)}

    return {
        "menu_signal": menu,
        "sentiment": sentiment,
        "intent": intent,
        "engagement": engagement,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 2 — Advisor Agents
# ═══════════════════════════════════════════════════════════════════════════════

def run_stage_agent(contact: Dict, layer1: Dict) -> Dict:
    system = "You are a lifecycle stage advisor for DabbahWala. Recommend the best lifecycle stage for this contact."
    messages = [{"role": "user", "content": (
        f"Contact segment: {contact.get('lifecycle_segment')}, orders: {contact.get('order_count', 0)}\n"
        f"Sentiment: {layer1.get('sentiment', {}).get('sentiment')}\n"
        f"Intent: {layer1.get('intent', {}).get('intent')}\n"
        f"Engagement score: {layer1.get('engagement', {}).get('engagement_score')}\n"
        "Use submit_stage tool."
    )}]
    tools = [{"name": "submit_stage", "description": "Submit stage recommendation",
        "input_schema": {"type": "object", "properties": {
            "recommended_stage": {"type": "string"},
            "confidence": {"type": "number"},
            "reason": {"type": "string"},
        }, "required": ["recommended_stage", "confidence", "reason"]}}]
    try:
        resp = call_claude(HAIKU, system, messages, tools=tools)
        return extract_tool_input(resp, "submit_stage") or {"recommended_stage": contact.get("lifecycle_segment"), "confidence": 0.5, "reason": ""}
    except Exception as exc:
        logger.error("Stage agent failed: %s", exc)
        return {"recommended_stage": contact.get("lifecycle_segment"), "confidence": 0.0, "reason": "", "error": str(exc)}


def run_channel_agent(contact: Dict, layer1: Dict) -> Dict:
    system = "You are a channel selection advisor for DabbahWala. Choose the best communication channel."
    messages = [{"role": "user", "content": (
        f"Contact: opted_out={contact.get('opted_out')}, segment={contact.get('lifecycle_segment')}\n"
        f"Engagement: {layer1.get('engagement', {})}\n"
        f"Sentiment: {layer1.get('sentiment', {}).get('sentiment')}\n"
        "Use submit_channel tool."
    )}]
    tools = [{"name": "submit_channel", "description": "Submit channel recommendation",
        "input_schema": {"type": "object", "properties": {
            "recommended_channel": {"type": "string", "enum": ["sms", "email", "call", "none"]},
            "channel_timing": {"type": "string", "enum": ["immediate", "tomorrow", "3days", "none"]},
            "reason": {"type": "string"},
        }, "required": ["recommended_channel", "channel_timing", "reason"]}}]
    try:
        resp = call_claude(HAIKU, system, messages, tools=tools)
        return extract_tool_input(resp, "submit_channel") or {"recommended_channel": "none", "channel_timing": "none", "reason": ""}
    except Exception as exc:
        logger.error("Channel agent failed: %s", exc)
        return {"recommended_channel": "none", "channel_timing": "none", "reason": "", "error": str(exc)}


def run_offer_agent(contact: Dict, layer1: Dict) -> Dict:
    top_picks = layer1.get("menu_signal", {}).get("top_picks", [])
    picks_text = ", ".join(top_picks) if top_picks else "no specific picks"
    system = "You are an offer strategist for DabbahWala. Craft the most compelling offer for this contact."
    messages = [{"role": "user", "content": (
        f"Contact value: total_spent=${contact.get('total_spent', 0)}, orders={contact.get('order_count', 0)}\n"
        f"Intent: {layer1.get('intent', {}).get('intent')}\n"
        f"Top menu picks: {picks_text}\n"
        "Use submit_offer tool. Reference specific menu items in suggested_copy."
    )}]
    tools = [{"name": "submit_offer", "description": "Submit offer recommendation",
        "input_schema": {"type": "object", "properties": {
            "offer_type": {"type": "string", "enum": ["discount", "reminder", "social_proof", "none"]},
            "suggested_copy": {"type": "string"},
            "reason": {"type": "string"},
        }, "required": ["offer_type", "suggested_copy", "reason"]}}]
    try:
        resp = call_claude(SONNET, system, messages, tools=tools)
        return extract_tool_input(resp, "submit_offer") or {"offer_type": "none", "suggested_copy": "", "reason": ""}
    except Exception as exc:
        logger.error("Offer agent failed: %s", exc)
        return {"offer_type": "none", "suggested_copy": "", "reason": "", "error": str(exc)}


def run_escalation_agent(contact: Dict, layer1: Dict, delivery_events: List[Dict]) -> Dict:
    failed_deliveries = [e for e in delivery_events if e.get("event_type") in ("order_cancelled",)]
    system = "You are an escalation advisor for DabbahWala. Decide if this contact needs human intervention."
    messages = [{"role": "user", "content": (
        f"Contact: {contact.get('name')}, segment={contact.get('lifecycle_segment')}\n"
        f"Sentiment: {layer1.get('sentiment', {}).get('sentiment')}\n"
        f"Failed/cancelled deliveries (recent): {len(failed_deliveries)}\n"
        f"Delivery events: {[e.get('event_type') for e in delivery_events[:5]]}\n"
        "Use submit_escalation tool."
    )}]
    tools = [{"name": "submit_escalation", "description": "Submit escalation decision",
        "input_schema": {"type": "object", "properties": {
            "should_escalate": {"type": "boolean"},
            "urgency": {"type": "string", "enum": ["high", "medium", "none"]},
            "reason": {"type": "string"},
        }, "required": ["should_escalate", "urgency", "reason"]}}]
    try:
        # Auto-escalate on delivery failures regardless of Claude
        if len(failed_deliveries) >= 2:
            return {"should_escalate": True, "urgency": "high", "reason": "Multiple delivery failures detected"}
        resp = call_claude(SONNET, system, messages, tools=tools)
        return extract_tool_input(resp, "submit_escalation") or {"should_escalate": False, "urgency": "none", "reason": ""}
    except Exception as exc:
        logger.error("Escalation agent failed: %s", exc)
        return {"should_escalate": False, "urgency": "none", "reason": "", "error": str(exc)}


async def run_layer2_parallel(contact: Dict, layer1: Dict, delivery_events: List[Dict]) -> Dict:
    loop = asyncio.get_event_loop()
    stage_t = loop.run_in_executor(None, run_stage_agent, contact, layer1)
    channel_t = loop.run_in_executor(None, run_channel_agent, contact, layer1)
    offer_t = loop.run_in_executor(None, run_offer_agent, contact, layer1)
    escalation_t = loop.run_in_executor(None, run_escalation_agent, contact, layer1, delivery_events)

    stage, channel, offer, escalation = await asyncio.gather(
        stage_t, channel_t, offer_t, escalation_t, return_exceptions=True,
    )

    def _safe(result, default):
        if isinstance(result, Exception):
            logger.error("Layer 2 agent exception: %s", result)
            return {**default, "error": str(result)}
        return result

    return {
        "stage": _safe(stage, {"recommended_stage": contact.get("lifecycle_segment"), "confidence": 0.0, "reason": ""}),
        "channel": _safe(channel, {"recommended_channel": "none", "channel_timing": "none", "reason": ""}),
        "offer": _safe(offer, {"offer_type": "none", "suggested_copy": "", "reason": ""}),
        "escalation": _safe(escalation, {"should_escalate": False, "urgency": "none", "reason": ""}),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 3 — Orchestrator
# ═══════════════════════════════════════════════════════════════════════════════

_DELIVERY_GUARDRAIL_HOURS = 2   # no outreach within 2h of active delivery
_MAX_DAILY_SMS = 1               # max SMS per contact per day


def _delivery_guardrail(contact: Dict, delivery_events: List[Dict]) -> Optional[str]:
    """Return block reason if contact is mid-delivery, else None."""
    for evt in delivery_events:
        if evt.get("event_type") == "order_placed":
            # Simplified: if order placed within last 2h, block
            return "Active delivery in progress — outreach blocked"
    return None


def run_orchestrator(
    contact: Dict,
    layer1: Dict,
    layer2: Dict,
    delivery_events: List[Dict],
    action_history: List[Dict],
) -> Dict:
    # ── Delivery guardrail ──
    block_reason = _delivery_guardrail(contact, delivery_events)
    if block_reason:
        return {"chosen_action": "none", "reasoning": block_reason, "guardrail_blocked": True}

    # ── General guardrails ──
    if contact.get("opted_out"):
        return {"chosen_action": "none", "reasoning": "Contact opted out", "guardrail_blocked": True}
    if contact.get("cooling_until"):
        return {"chosen_action": "none", "reasoning": "Contact in cooling period", "guardrail_blocked": True}

    escalation = layer2.get("escalation", {})
    channel = layer2.get("channel", {})
    offer = layer2.get("offer", {})

    system = (
        "You are the master orchestrator for DabbahWala's AI marketing system. "
        "Given all agent outputs, choose ONE action for this contact right now."
    )
    messages = [{"role": "user", "content": (
        f"Contact: {contact.get('name')}, segment={contact.get('lifecycle_segment')}, "
        f"orders={contact.get('order_count', 0)}\n\n"
        f"Layer 1 Summary:\n"
        f"  Sentiment: {layer1.get('sentiment', {}).get('sentiment')} ({layer1.get('sentiment', {}).get('confidence', 0):.2f})\n"
        f"  Intent: {layer1.get('intent', {}).get('intent')} ({layer1.get('intent', {}).get('confidence', 0):.2f})\n"
        f"  Engagement: {layer1.get('engagement', {}).get('engagement_score', 0):.2f} ({layer1.get('engagement', {}).get('trend')})\n"
        f"  Top menu picks: {layer1.get('menu_signal', {}).get('top_picks', [])}\n\n"
        f"Layer 2 Summary:\n"
        f"  Recommended stage: {layer2.get('stage', {}).get('recommended_stage')}\n"
        f"  Channel: {channel.get('recommended_channel')} ({channel.get('channel_timing')})\n"
        f"  Offer: {offer.get('offer_type')} — {offer.get('suggested_copy', '')[:100]}\n"
        f"  Escalation: should_escalate={escalation.get('should_escalate')}, urgency={escalation.get('urgency')}\n\n"
        f"Recent actions taken: {len(action_history)}\n"
        "Choose ONE action. Use submit_action tool."
    )}]
    tools = [{"name": "submit_action", "description": "Submit the chosen action",
        "input_schema": {"type": "object", "properties": {
            "chosen_action": {"type": "string", "enum": ["send_sms", "move_campaign", "escalate_airtable", "none"]},
            "reasoning": {"type": "string"},
            "sms_copy": {"type": "string", "description": "SMS text if chosen_action=send_sms"},
        }, "required": ["chosen_action", "reasoning"]}}]

    try:
        resp = call_claude(SONNET, system, messages, tools=tools)
        result = extract_tool_input(resp, "submit_action") or {"chosen_action": "none", "reasoning": "No tool call returned"}
        return {**result, "guardrail_blocked": False}
    except Exception as exc:
        logger.error("Orchestrator failed: %s", exc)
        return {"chosen_action": "none", "reasoning": str(exc), "guardrail_blocked": False, "error": str(exc)}


# ═══════════════════════════════════════════════════════════════════════════════
# FULL PIPELINE
# ═══════════════════════════════════════════════════════════════════════════════

async def run_full_pipeline(contact: Dict, context: Dict) -> Dict:
    """
    Runs Layer 1 → Layer 2 → Layer 3 for a single contact.
    Returns full pipeline output including chosen_action.
    """
    import time
    start = time.time()

    layer1 = await run_layer1_parallel(contact, context)
    logger.info("Layer 1 complete contact_id=%s", contact.get("id"))

    layer2 = await run_layer2_parallel(
        contact, layer1, context.get("delivery_events", [])
    )
    logger.info("Layer 2 complete contact_id=%s", contact.get("id"))

    orchestrator_result = run_orchestrator(
        contact, layer1, layer2,
        context.get("delivery_events", []),
        context.get("action_history", []),
    )
    logger.info(
        "Layer 3 complete contact_id=%s chosen_action=%s",
        contact.get("id"), orchestrator_result.get("chosen_action"),
    )

    return {
        "contact_id": contact.get("id"),
        "layer1": layer1,
        "layer2": layer2,
        "orchestrator": orchestrator_result,
        "chosen_action": orchestrator_result.get("chosen_action", "none"),
        "duration_ms": int((time.time() - start) * 1000),
    }
