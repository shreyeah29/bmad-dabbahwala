"""Tests for E09 — Telnyx SMS & Call Tracking"""
from unittest.mock import MagicMock, patch

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


# ── Story 9.1: Message storage ────────────────────────────────────────────────

def test_store_outbound_message():
    cur = _mock_cursor(fetchone_val={"id": 42})
    with patch("app.db.get_cursor", return_value=cur):
        resp = client.post("/api/telnyx/message", json={
            "from_number": "+18444322224",
            "to_number": "+14045551234",
            "body": "Hello from DabbahWala!",
            "direction": "outbound",
            "contact_id": 1,
        })
    assert resp.status_code == 200
    assert resp.json()["msg_id"] == 42


def test_store_inbound_message_auto_create_contact():
    """Inbound from unknown number — should create contact and trigger agent cycle."""
    cur = MagicMock()
    cur.__enter__ = lambda s: s
    cur.__exit__ = MagicMock(return_value=False)
    # First fetchone → None (no existing contact), second → new contact, third → msg insert
    cur.fetchone.side_effect = [None, {"id": 99}, {"id": 7}]

    with patch("app.db.get_cursor", return_value=cur), \
         patch("httpx.AsyncClient") as mock_http:
        mock_http.return_value.__aenter__ = MagicMock(return_value=MagicMock(
            post=MagicMock(return_value=MagicMock())
        ))
        mock_http.return_value.__aexit__ = MagicMock(return_value=False)
        resp = client.post("/api/telnyx/message", json={
            "from_number": "+14045559999",
            "to_number": "+18444322224",
            "body": "I want to order food",
            "direction": "inbound",
        })
    assert resp.status_code == 200


def test_list_templates():
    cur = _mock_cursor(rows=[{"id": 1, "name": "welcome", "body": "Hi!", "segment": None, "is_active": True}])
    with patch("app.db.get_cursor", return_value=cur):
        resp = client.get("/api/telnyx/templates")
    assert resp.status_code == 200
    assert len(resp.json()["templates"]) == 1


def test_create_template():
    cur = _mock_cursor(fetchone_val={"id": 5})
    with patch("app.db.get_cursor", return_value=cur):
        resp = client.post("/api/telnyx/templates", json={
            "name": "reorder_nudge",
            "body": "Time to reorder your dabbah!",
        })
    assert resp.status_code == 200
    assert resp.json()["template_id"] == 5


# ── Story 9.2: Call tracking ──────────────────────────────────────────────────

def test_store_call():
    cur = MagicMock()
    cur.__enter__ = lambda s: s
    cur.__exit__ = MagicMock(return_value=False)
    cur.fetchone.side_effect = [{"id": 3}, {"id": 10}]
    with patch("app.db.get_cursor", return_value=cur):
        resp = client.post("/api/telnyx/call", json={
            "from_number": "+14045551234",
            "to_number": "+18444322224",
            "direction": "inbound",
            "duration_sec": 45,
            "telnyx_call_id": "call-abc-123",
        })
    assert resp.status_code == 200


# ── Story 9.3: Field agent SMS ────────────────────────────────────────────────

def test_field_agent_message():
    cur = MagicMock()
    cur.__enter__ = lambda s: s
    cur.__exit__ = MagicMock(return_value=False)
    cur.fetchone.side_effect = [{"phone": "+14045551234"}, {"id": 20}]
    with patch("app.db.get_cursor", return_value=cur):
        resp = client.post("/api/telnyx/field-agent-message", json={
            "contact_id": 1,
            "body": "Your order is ready!",
            "agent_name": "Priya",
        })
    assert resp.status_code == 200
    assert resp.json()["agent_name"] == "Priya"


def test_field_agent_message_contact_not_found():
    cur = _mock_cursor(fetchone_val=None)
    with patch("app.db.get_cursor", return_value=cur):
        resp = client.post("/api/telnyx/field-agent-message", json={
            "contact_id": 999,
            "body": "Hi",
            "agent_name": "Raj",
        })
    assert resp.status_code == 404
