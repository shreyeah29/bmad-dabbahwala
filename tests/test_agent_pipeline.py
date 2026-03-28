"""Tests for agent pipeline — all agents mocked at the Claude call level."""
import asyncio
from unittest.mock import MagicMock, patch

import pytest

from app.services.agent_pipeline import (
    run_menu_agent, run_sentiment_agent, run_intent_agent,
    run_engagement_agent, run_orchestrator, _delivery_guardrail,
    run_layer1_parallel, run_layer2_parallel,
)

_CONTACT = {
    "id": 1, "name": "Test", "email": "t@dabbahwala.com",
    "lifecycle_segment": "active_customer", "order_count": 3,
    "total_spent": 120.0, "opted_out": False, "cooling_until": None,
}


def _mock_claude(tool_name: str, tool_input: dict):
    block = MagicMock()
    block.type = "tool_use"
    block.name = tool_name
    block.input = tool_input
    resp = MagicMock()
    resp.content = [block]
    return resp


# ── Menu agent ────────────────────────────────────────────────────────────────

def test_menu_agent_returns_picks():
    with patch("app.services.agent_pipeline.call_claude",
               return_value=_mock_claude("submit_menu_picks", {
                   "top_picks": ["Butter Chicken", "Dal Makhani"],
                   "bridge_item": "Palak Paneer",
                   "avoid": [],
               })):
        result = run_menu_agent(_CONTACT, [], [])
        assert result["top_picks"] == ["Butter Chicken", "Dal Makhani"]
        assert result["bridge_item"] == "Palak Paneer"


def test_menu_agent_error_returns_defaults():
    with patch("app.services.agent_pipeline.call_claude", side_effect=Exception("API down")):
        result = run_menu_agent(_CONTACT, [], [])
        assert result["top_picks"] == []
        assert "error" in result


# ── Sentiment agent ───────────────────────────────────────────────────────────

def test_sentiment_agent_returns_sentiment():
    with patch("app.services.agent_pipeline.call_claude",
               return_value=_mock_claude("submit_sentiment", {
                   "sentiment": "positive", "confidence": 0.85, "summary": "Loves the food",
               })):
        result = run_sentiment_agent(_CONTACT, [], [])
        assert result["sentiment"] == "positive"
        assert result["confidence"] == 0.85


def test_sentiment_agent_error_defaults_neutral():
    with patch("app.services.agent_pipeline.call_claude", side_effect=Exception("error")):
        result = run_sentiment_agent(_CONTACT, [], [])
        assert result["sentiment"] == "neutral"


# ── Intent agent ──────────────────────────────────────────────────────────────

def test_intent_agent_returns_intent():
    with patch("app.services.agent_pipeline.call_claude",
               return_value=_mock_claude("submit_intent", {
                   "intent": "ready_to_order", "signals": ["viewed_menu"], "confidence": 0.9,
               })):
        result = run_intent_agent(_CONTACT, [], {})
        assert result["intent"] == "ready_to_order"


def test_intent_agent_error_defaults_unknown():
    with patch("app.services.agent_pipeline.call_claude", side_effect=Exception("error")):
        result = run_intent_agent(_CONTACT, [], {})
        assert result["intent"] == "unknown"


# ── Engagement agent ──────────────────────────────────────────────────────────

def test_engagement_agent_returns_score():
    with patch("app.services.agent_pipeline.call_claude",
               return_value=_mock_claude("submit_engagement", {
                   "engagement_score": 0.75, "trend": "rising", "last_touch_hours_ago": 12,
               })):
        result = run_engagement_agent(_CONTACT, {}, [])
        assert result["engagement_score"] == 0.75
        assert result["trend"] == "rising"


# ── Delivery guardrail ────────────────────────────────────────────────────────

def test_delivery_guardrail_blocks_on_active_order():
    events = [{"event_type": "order_placed"}]
    reason = _delivery_guardrail(_CONTACT, events)
    assert reason is not None
    assert "delivery" in reason.lower()


def test_delivery_guardrail_passes_with_no_orders():
    reason = _delivery_guardrail(_CONTACT, [])
    assert reason is None


# ── Orchestrator ──────────────────────────────────────────────────────────────

def test_orchestrator_blocks_opted_out():
    contact = {**_CONTACT, "opted_out": True}
    result = run_orchestrator(contact, {}, {}, [], [])
    assert result["chosen_action"] == "none"
    assert result["guardrail_blocked"] is True


def test_orchestrator_blocks_cooling():
    contact = {**_CONTACT, "cooling_until": "2099-01-01"}
    result = run_orchestrator(contact, {}, {}, [], [])
    assert result["chosen_action"] == "none"
    assert result["guardrail_blocked"] is True


def test_orchestrator_returns_chosen_action():
    with patch("app.services.agent_pipeline.call_claude",
               return_value=_mock_claude("submit_action", {
                   "chosen_action": "send_sms",
                   "reasoning": "High intent detected",
                   "sms_copy": "Hey, order today!",
               })):
        result = run_orchestrator(_CONTACT, {
            "sentiment": {"sentiment": "positive", "confidence": 0.8},
            "intent": {"intent": "ready_to_order", "confidence": 0.9},
            "engagement": {"engagement_score": 0.8, "trend": "rising"},
            "menu_signal": {"top_picks": []},
        }, {
            "stage": {"recommended_stage": "active_customer"},
            "channel": {"recommended_channel": "sms", "channel_timing": "immediate"},
            "offer": {"offer_type": "reminder", "suggested_copy": "Try us!"},
            "escalation": {"should_escalate": False, "urgency": "none"},
        }, [], [])
        assert result["chosen_action"] == "send_sms"
        assert result["guardrail_blocked"] is False


# ── Layer 1 parallel ──────────────────────────────────────────────────────────

def test_layer1_parallel_returns_all_keys():
    def _fake_claude(model, system, messages, tools=None, max_tokens=1024):
        tool_name = tools[0]["name"] if tools else "unknown"
        defaults = {
            "submit_menu_picks": {"top_picks": [], "bridge_item": "", "avoid": []},
            "submit_sentiment": {"sentiment": "neutral", "confidence": 0.5, "summary": ""},
            "submit_intent": {"intent": "unknown", "signals": [], "confidence": 0.5},
            "submit_engagement": {"engagement_score": 0.5, "trend": "flat", "last_touch_hours_ago": 48},
        }
        return _mock_claude(tool_name, defaults.get(tool_name, {}))

    with patch("app.services.agent_pipeline.call_claude", side_effect=_fake_claude):
        result = asyncio.get_event_loop().run_until_complete(
            run_layer1_parallel(_CONTACT, {"menu_items": [], "past_orders": [], "recent_events": [], "rollup": {}})
        )
        assert "menu_signal" in result
        assert "sentiment" in result
        assert "intent" in result
        assert "engagement" in result


def test_layer1_parallel_agent_failure_does_not_abort():
    """If one agent fails, others still complete."""
    call_count = [0]

    def _flaky_claude(model, system, messages, tools=None, max_tokens=1024):
        call_count[0] += 1
        if call_count[0] == 1:
            raise Exception("First call fails")
        tool_name = tools[0]["name"] if tools else "unknown"
        return _mock_claude(tool_name, {})

    with patch("app.services.agent_pipeline.call_claude", side_effect=_flaky_claude):
        result = asyncio.get_event_loop().run_until_complete(
            run_layer1_parallel(_CONTACT, {"menu_items": [], "past_orders": [], "recent_events": [], "rollup": {}})
        )
        # Should still return all keys even with partial failure
        assert "menu_signal" in result
        assert "sentiment" in result
