from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _cursor_ctx(fetchall=None, fetchone=None, rowcount=0):
    cur = MagicMock()
    cur.fetchall.return_value = fetchall or []
    cur.fetchone.return_value = fetchone or {"opp_id": 1}
    cur.rowcount = rowcount
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=cur)
    ctx.__exit__ = MagicMock(return_value=False)
    return ctx, cur


# ── POST /api/intelligence/run-cycle ─────────────────────────────────────────

def test_run_cycle_returns_200():
    ctx, cur = _cursor_ctx(fetchall=[], fetchone={"opp_id": None})
    with patch("app.routers.intelligence.get_cursor", return_value=ctx):
        resp = client.post("/api/intelligence/run-cycle")
        assert resp.status_code == 200


def test_run_cycle_returns_phases():
    ctx, cur = _cursor_ctx(fetchall=[], fetchone={"opp_id": None})
    with patch("app.routers.intelligence.get_cursor", return_value=ctx):
        resp = client.post("/api/intelligence/run-cycle")
        data = resp.json()
        assert "phases" in data
        assert "opportunities_created" in data
        assert "duration_ms" in data


def test_run_cycle_has_all_five_phases():
    ctx, cur = _cursor_ctx(fetchall=[], fetchone={"opp_id": None})
    with patch("app.routers.intelligence.get_cursor", return_value=ctx):
        resp = client.post("/api/intelligence/run-cycle")
        phases = resp.json()["phases"]
        for phase in ("collect", "profile", "signal", "route", "dispatch"):
            assert phase in phases, f"Missing phase: {phase}"


def test_run_cycle_db_error_returns_500():
    with patch("app.routers.intelligence.get_cursor", side_effect=Exception("DB down")):
        resp = client.post("/api/intelligence/run-cycle")
        assert resp.status_code == 500


def test_run_cycle_collect_returns_contact_count():
    ctx, cur = _cursor_ctx(
        fetchall=[{"id": 1}, {"id": 2}, {"id": 3}],
        fetchone={"opp_id": None},
    )
    with patch("app.routers.intelligence.get_cursor", return_value=ctx):
        resp = client.post("/api/intelligence/run-cycle")
        assert resp.json()["phases"]["collect"]["contacts"] == 3


# ── GET /api/intelligence/pending-actions ─────────────────────────────────────

def test_pending_actions_returns_list():
    ctx, cur = _cursor_ctx(fetchall=[
        {"id": 1, "contact_id": 10, "email": "a@dabbahwala.com", "name": "A",
         "signal_type": "engaged_no_order", "action": "send_sms",
         "confidence": 0.7, "created_at": "2026-03-28"},
    ])
    with patch("app.routers.intelligence.get_cursor", return_value=ctx):
        resp = client.get("/api/intelligence/pending-actions")
        assert resp.status_code == 200
        assert resp.json()["count"] == 1


def test_pending_actions_empty():
    ctx, cur = _cursor_ctx(fetchall=[])
    with patch("app.routers.intelligence.get_cursor", return_value=ctx):
        resp = client.get("/api/intelligence/pending-actions")
        assert resp.json()["pending"] == []


# ── POST /api/intelligence/opportunities ──────────────────────────────────────

def test_create_opportunity_ok():
    ctx, cur = _cursor_ctx(fetchone={"opp_id": 42})
    with patch("app.routers.intelligence.get_cursor", return_value=ctx):
        resp = client.post("/api/intelligence/opportunities", json={
            "contact_id": 1,
            "signal_type": "engaged_no_order",
            "confidence": 0.7,
            "recommended_action": "send_sms",
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "created"
        assert resp.json()["opp_id"] == 42


def test_create_opportunity_duplicate_returns_duplicate_status():
    ctx, cur = _cursor_ctx(fetchone={"opp_id": None})
    with patch("app.routers.intelligence.get_cursor", return_value=ctx):
        resp = client.post("/api/intelligence/opportunities", json={
            "contact_id": 1,
            "signal_type": "engaged_no_order",
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "duplicate"


# ── GET /api/intelligence/opportunities/pending ───────────────────────────────

def test_get_pending_opportunities_ok():
    ctx, cur = _cursor_ctx(fetchall=[
        {"id": 1, "contact_id": 5, "email": "b@dabbahwala.com", "name": "B",
         "signal_type": "reorder_intent", "action": "send_sms",
         "confidence": 0.65, "status": "pending", "created_at": "2026-03-28"},
    ])
    with patch("app.routers.intelligence.get_cursor", return_value=ctx):
        resp = client.get("/api/intelligence/opportunities/pending")
        assert resp.status_code == 200
        assert resp.json()["count"] == 1


# ── POST /api/intelligence/opportunities/{id}/dispatched ──────────────────────

def test_mark_dispatched_ok():
    ctx, cur = _cursor_ctx(rowcount=1)
    with patch("app.routers.intelligence.get_cursor", return_value=ctx):
        resp = client.post("/api/intelligence/opportunities/1/dispatched")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


def test_mark_dispatched_not_found_returns_404():
    ctx, cur = _cursor_ctx(rowcount=0)
    with patch("app.routers.intelligence.get_cursor", return_value=ctx):
        resp = client.post("/api/intelligence/opportunities/999/dispatched")
        assert resp.status_code == 404


# ── POST /api/intelligence/opportunities/{id}/outcome ────────────────────────

def test_record_outcome_converted():
    ctx, cur = _cursor_ctx(rowcount=1)
    with patch("app.routers.intelligence.get_cursor", return_value=ctx):
        resp = client.post("/api/intelligence/opportunities/1/outcome?outcome=converted")
        assert resp.status_code == 200
        assert resp.json()["outcome"] == "converted"


def test_record_outcome_invalid_returns_422():
    resp = client.post("/api/intelligence/opportunities/1/outcome?outcome=invalid")
    assert resp.status_code == 422


def test_record_outcome_not_found_returns_404():
    ctx, cur = _cursor_ctx(rowcount=0)
    with patch("app.routers.intelligence.get_cursor", return_value=ctx):
        resp = client.post("/api/intelligence/opportunities/999/outcome?outcome=expired")
        assert resp.status_code == 404


# ── POST /api/intelligence/ingest-instantly-events ────────────────────────────

def test_ingest_instantly_no_api_key(monkeypatch):
    monkeypatch.setattr("app.routers.intelligence.settings.instantly_api_key", "")
    resp = client.post("/api/intelligence/ingest-instantly-events")
    assert resp.status_code == 503


def test_ingest_instantly_api_error(monkeypatch):
    monkeypatch.setattr("app.routers.intelligence.settings.instantly_api_key", "key123")
    with patch("app.routers.intelligence.httpx.AsyncClient") as MockClient:
        mock_http = AsyncMock()
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
        bad_resp = MagicMock(status_code=401)
        bad_resp.text = "Unauthorized"
        mock_http.get = AsyncMock(return_value=bad_resp)

        resp = client.post("/api/intelligence/ingest-instantly-events")
        assert resp.status_code == 502


def test_ingest_instantly_ok(monkeypatch):
    monkeypatch.setattr("app.routers.intelligence.settings.instantly_api_key", "key123")
    with patch("app.routers.intelligence.httpx.AsyncClient") as MockClient:
        mock_http = AsyncMock()
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        api_resp = MagicMock(status_code=200)
        api_resp.json.return_value = {"data": [
            {"email": "user@dabbahwala.com", "event_type": "email_opened"},
            {"email": "unknown@gmail.com", "event_type": "email_opened"},
        ]}
        mock_http.get = AsyncMock(return_value=api_resp)

        ctx, cur = _cursor_ctx(fetchone={"id": 1})
        # First call: contact lookup found; second: not found
        cur.fetchone.side_effect = [{"id": 1}, None]
        cur.fetchall.return_value = []

        with patch("app.routers.intelligence.get_cursor", return_value=ctx):
            resp = client.post("/api/intelligence/ingest-instantly-events")
            assert resp.status_code == 200
            data = resp.json()
            assert "ingested" in data
            assert "skipped" in data
