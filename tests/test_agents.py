import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _cursor_ctx(fetchall=None, fetchone=None, rowcount=1):
    cur = MagicMock()
    cur.fetchall.return_value = fetchall or []
    cur.fetchone.return_value = fetchone or {}
    cur.rowcount = rowcount
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=cur)
    ctx.__exit__ = MagicMock(return_value=False)
    return ctx, cur


_MOCK_CONTACT = {
    "id": 1, "email": "test@dabbahwala.com", "name": "Test User",
    "lifecycle_segment": "active_customer", "order_count": 3,
    "total_spent": 150.0, "opted_out": False, "cooling_until": None,
}

_MOCK_PIPELINE_RESULT = {
    "contact_id": 1,
    "chosen_action": "send_sms",
    "duration_ms": 1200,
    "layer1": {
        "sentiment": {"sentiment": "positive", "confidence": 0.8, "summary": ""},
        "intent": {"intent": "ready_to_order", "signals": [], "confidence": 0.7},
        "engagement": {"engagement_score": 0.75, "trend": "rising", "last_touch_hours_ago": 24},
        "menu_signal": {"top_picks": ["Butter Chicken"], "bridge_item": "", "avoid": []},
    },
    "layer2": {
        "stage": {"recommended_stage": "active_customer", "confidence": 0.9, "reason": ""},
        "channel": {"recommended_channel": "sms", "channel_timing": "immediate", "reason": ""},
        "offer": {"offer_type": "reminder", "suggested_copy": "Try our Butter Chicken!", "reason": ""},
        "escalation": {"should_escalate": False, "urgency": "none", "reason": ""},
    },
    "orchestrator": {
        "chosen_action": "send_sms",
        "reasoning": "High intent, sms recommended",
        "sms_copy": "Hi! Try our Butter Chicken today.",
        "guardrail_blocked": False,
    },
}


# ── POST /api/agents/cycle/run ────────────────────────────────────────────────

def test_cycle_run_contact_not_found():
    ctx, cur = _cursor_ctx(fetchone=None)
    cur.fetchone.return_value = None
    with patch("app.routers.agents.get_cursor", return_value=ctx):
        resp = client.post("/api/agents/cycle/run?contact_id=999")
        assert resp.status_code == 404


def test_cycle_run_ok():
    ctx, cur = _cursor_ctx(fetchone=_MOCK_CONTACT)
    with patch("app.routers.agents.get_cursor", return_value=ctx):
        with patch("app.routers.agents.run_full_pipeline", new=AsyncMock(return_value=_MOCK_PIPELINE_RESULT)):
            resp = client.post("/api/agents/cycle/run?contact_id=1")
            assert resp.status_code == 200
            data = resp.json()
            assert data["chosen_action"] == "send_sms"
            assert "layer1_summary" in data
            assert "layer2_summary" in data


def test_cycle_run_returns_reasoning():
    ctx, cur = _cursor_ctx(fetchone=_MOCK_CONTACT)
    with patch("app.routers.agents.get_cursor", return_value=ctx):
        with patch("app.routers.agents.run_full_pipeline", new=AsyncMock(return_value=_MOCK_PIPELINE_RESULT)):
            resp = client.post("/api/agents/cycle/run?contact_id=1")
            assert "reasoning" in resp.json()


# ── POST /api/agents/cycle/run-all ────────────────────────────────────────────

def test_cycle_run_all_returns_summary():
    ctx, cur = _cursor_ctx(fetchall=[{"id": 1}, {"id": 2}])
    with patch("app.routers.agents.get_cursor", return_value=ctx):
        with patch("app.routers.agents.run_full_pipeline", new=AsyncMock(return_value=_MOCK_PIPELINE_RESULT)):
            with patch("app.routers.agents._post_process_batch", new=AsyncMock()):
                resp = client.post("/api/agents/cycle/run-all?max_contacts=10")
                assert resp.status_code == 200
                data = resp.json()
                assert "processed" in data
                assert "summary" in data


def test_cycle_run_all_summary_keys():
    ctx, cur = _cursor_ctx(fetchall=[])
    with patch("app.routers.agents.get_cursor", return_value=ctx):
        with patch("app.routers.agents._post_process_batch", new=AsyncMock()):
            resp = client.post("/api/agents/cycle/run-all")
            data = resp.json()
            assert "send_sms" in data["summary"]
            assert "move_campaign" in data["summary"]
            assert "escalate_airtable" in data["summary"]


# ── GET /api/agents/action-queue/pending ──────────────────────────────────────

def test_get_pending_actions_ok():
    ctx, cur = _cursor_ctx(fetchall=[
        {"id": 1, "contact_id": 1, "email": "a@dabbahwala.com",
         "action_type": "send_sms", "payload": {}, "status": "pending",
         "created_at": "2026-03-28", "scheduled_for": None},
    ])
    with patch("app.routers.agents.get_cursor", return_value=ctx):
        resp = client.get("/api/agents/action-queue/pending")
        assert resp.status_code == 200
        assert resp.json()["count"] == 1


# ── POST /api/agents/action-queue/{id}/done ───────────────────────────────────

def test_mark_action_done_ok():
    ctx, cur = _cursor_ctx(rowcount=1)
    with patch("app.routers.agents.get_cursor", return_value=ctx):
        resp = client.post("/api/agents/action-queue/1/done")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


def test_mark_action_done_not_found():
    ctx, cur = _cursor_ctx(rowcount=0)
    with patch("app.routers.agents.get_cursor", return_value=ctx):
        resp = client.post("/api/agents/action-queue/999/done")
        assert resp.status_code == 404


# ── POST /api/agents/goals ────────────────────────────────────────────────────

def test_upsert_goal_ok():
    ctx, cur = _cursor_ctx(rowcount=1)
    with patch("app.routers.agents.get_cursor", return_value=ctx):
        resp = client.post("/api/agents/goals", json={
            "contact_id": 1,
            "goal_type": "retain",
            "goal_data": {"target": "monthly_order"},
        })
        assert resp.status_code == 200
        assert resp.json()["goal_type"] == "retain"


def test_upsert_goal_invalid_type():
    resp = client.post("/api/agents/goals", json={
        "contact_id": 1,
        "goal_type": "invalid_goal",
    })
    assert resp.status_code == 422


def test_upsert_goal_valid_types():
    ctx, cur = _cursor_ctx(rowcount=1)
    for goal_type in ("convert_to_order", "retain", "reactivate"):
        with patch("app.routers.agents.get_cursor", return_value=ctx):
            resp = client.post("/api/agents/goals", json={
                "contact_id": 1,
                "goal_type": goal_type,
            })
            assert resp.status_code == 200, f"Failed for goal_type={goal_type}"


# ── Report agents ─────────────────────────────────────────────────────────────

def test_activity_report_ok():
    ctx, cur = _cursor_ctx(fetchone={"report": {"date": "2026-03-28", "orders": 5}})
    with patch("app.routers.agents.get_cursor", return_value=ctx):
        mock_resp = MagicMock()
        mock_text = MagicMock()
        mock_text.type = "text"
        mock_text.text = "<h1>Activity Report</h1>"
        mock_resp.content = [mock_text]
        with patch("app.services.llm_service.call_claude", return_value=mock_resp):
            resp = client.post("/api/agents/report/activity")
            assert resp.status_code == 200
            assert "<h1>" in resp.json()["html"]


def test_outcome_report_ok():
    ctx, cur = _cursor_ctx(
        fetchall=[{"action_type": "send_sms", "count": 10, "done": 8}],
        fetchone={"converted": 3},
    )
    cur.fetchone.side_effect = [{"converted": 3}]
    cur.fetchall.return_value = [{"action_type": "send_sms", "count": 10, "done": 8}]
    with patch("app.routers.agents.get_cursor", return_value=ctx):
        mock_resp = MagicMock()
        mock_text = MagicMock()
        mock_text.type = "text"
        mock_text.text = "<h1>Outcome Report</h1>"
        mock_resp.content = [mock_text]
        with patch("app.services.llm_service.call_claude", return_value=mock_resp):
            resp = client.post("/api/agents/report/outcome")
            assert resp.status_code == 200
            assert "html" in resp.json()
