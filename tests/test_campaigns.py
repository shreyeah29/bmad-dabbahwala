"""Tests for E13 — Instantly Campaigns"""
from unittest.mock import MagicMock, patch, AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _mock_cursor(rows=None, fetchone_val=None):
    cur = MagicMock()
    cur.__enter__ = lambda s: s
    cur.__exit__ = MagicMock(return_value=False)
    cur.fetchone.return_value = fetchone_val
    cur.fetchall.return_value = rows or []
    return cur


# ── Story 13.1: Push lead ─────────────────────────────────────────────────────

def test_push_lead_success():
    cur = MagicMock()
    cur.__enter__ = lambda s: s
    cur.__exit__ = MagicMock(return_value=False)
    cur.fetchone.side_effect = [
        {"email": "a@b.com", "instantly_campaign_id": "camp-1", "instantly_campaign_name": "Warm"},
        {"id": 7},
    ]
    with patch("app.db.get_cursor", return_value=cur):
        resp = client.post("/api/campaigns/push-lead", json={"contact_id": 1})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "queued"
    assert data["queue_id"] == 7


def test_push_lead_not_found():
    cur = _mock_cursor(fetchone_val=None)
    with patch("app.db.get_cursor", return_value=cur):
        resp = client.post("/api/campaigns/push-lead", json={"contact_id": 999})
    assert resp.status_code == 404


def test_pending_pushes():
    cur = _mock_cursor(rows=[
        {"id": 1, "contact_id": 2, "email": "a@b.com", "payload": {}, "created_at": None}
    ])
    with patch("app.db.get_cursor", return_value=cur):
        resp = client.get("/api/campaigns/pending")
    assert resp.status_code == 200
    assert len(resp.json()["pending"]) == 1


# ── Story 13.2: Active contacts ───────────────────────────────────────────────

def test_active_contacts():
    cur = _mock_cursor(rows=[
        {"id": 1, "email": "a@b.com", "name": "Alice", "segment": "warm",
         "instantly_campaign_id": "camp-1", "instantly_campaign_name": "Warm"}
    ])
    with patch("app.db.get_cursor", return_value=cur):
        resp = client.get("/api/campaigns/active-contacts")
    assert resp.status_code == 200
    assert len(resp.json()["contacts"]) == 1


def test_active_contacts_stats():
    cur = _mock_cursor(rows=[{"segment": "warm", "count": 50}])
    with patch("app.db.get_cursor", return_value=cur):
        resp = client.get("/api/campaigns/active-contacts-stats")
    assert resp.status_code == 200


# ── Story 13.3: Log push ──────────────────────────────────────────────────────

def test_log_push():
    cur = _mock_cursor(fetchone_val={"id": 10})
    with patch("app.db.get_cursor", return_value=cur):
        resp = client.post("/api/campaigns/log-push", json={
            "contact_id": 1,
            "campaign_name": "Warm",
            "lifecycle_segment": "warm",
            "instantly_lead_id": "lead-abc",
            "status": "success",
        })
    assert resp.status_code == 200
    assert resp.json()["log_id"] == 10


def test_push_log():
    cur = _mock_cursor(rows=[{"id": 1, "contact_id": 2, "status": "success"}])
    with patch("app.db.get_cursor", return_value=cur):
        resp = client.get("/api/campaigns/push-log")
    assert resp.status_code == 200


# ── Story 13.4: Templates ─────────────────────────────────────────────────────

def test_get_template():
    cur = _mock_cursor(fetchone_val={"id": 1, "name": "welcome", "body": "Hi!", "segment": None})
    with patch("app.db.get_cursor", return_value=cur):
        resp = client.get("/api/campaigns/templates/welcome")
    assert resp.status_code == 200
    assert resp.json()["name"] == "welcome"


def test_get_template_not_found():
    cur = _mock_cursor(fetchone_val=None)
    with patch("app.db.get_cursor", return_value=cur):
        resp = client.get("/api/campaigns/templates/nope")
    assert resp.status_code == 404


def test_update_template():
    cur = _mock_cursor(fetchone_val={"id": 5})
    with patch("app.db.get_cursor", return_value=cur):
        resp = client.put("/api/campaigns/templates/welcome", json={
            "body": "Welcome to DabbahWala!",
            "segment": "warm",
        })
    assert resp.status_code == 200
    assert resp.json()["template_id"] == 5


def test_rewrite_template():
    template_row = {"body": "Order now!", "segment": "warm"}
    cur = _mock_cursor(fetchone_val=template_row)

    mock_resp = MagicMock()
    mock_resp.content = [MagicMock(type="text", text="Order now and save 20%!")]

    with patch("app.db.get_cursor", return_value=cur), \
         patch("app.services.llm_service.call_claude", return_value=mock_resp):
        resp = client.post("/api/campaigns/templates/welcome/rewrite")
    assert resp.status_code == 200
    data = resp.json()
    assert "rewritten" in data
    assert data["original"] == "Order now!"
