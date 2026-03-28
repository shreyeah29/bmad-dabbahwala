"""Tests for E10 — Webhooks & Delivery"""
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


# ── Story 10.1: Instantly webhook ─────────────────────────────────────────────

def test_instantly_webhook_email_opened():
    cur = MagicMock()
    cur.__enter__ = lambda s: s
    cur.__exit__ = MagicMock(return_value=False)
    cur.fetchone.return_value = {"id": 1}
    with patch("app.db.get_cursor", return_value=cur):
        resp = client.post("/api/webhooks/instantly", json={
            "email": "test@example.com",
            "event_type": "email_opened",
        })
    assert resp.status_code == 200
    assert resp.json()["ingested"] == 1


def test_instantly_webhook_unknown_event_skipped():
    cur = _mock_cursor()
    with patch("app.db.get_cursor", return_value=cur):
        resp = client.post("/api/webhooks/instantly", json={
            "email": "test@example.com",
            "event_type": "unknown_event",
        })
    assert resp.status_code == 200
    assert resp.json()["skipped"] == 1


def test_instantly_webhook_unknown_email_skipped():
    cur = _mock_cursor(fetchone_val=None)
    with patch("app.db.get_cursor", return_value=cur):
        resp = client.post("/api/webhooks/instantly", json={
            "email": "nobody@unknown.com",
            "event_type": "email_opened",
        })
    assert resp.status_code == 200
    assert resp.json()["skipped"] == 1


# ── Story 10.2: Telnyx webhook ────────────────────────────────────────────────

def test_telnyx_webhook_non_message_event():
    resp = client.post("/api/webhooks/telnyx", json={
        "data": {"event_type": "call.initiated"}
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ── Story 10.3: Shipday webhook ───────────────────────────────────────────────

def test_shipday_webhook_get():
    resp = client.get("/api/webhooks/shipday")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_shipday_webhook_order_delivered():
    cur = MagicMock()
    cur.__enter__ = lambda s: s
    cur.__exit__ = MagicMock(return_value=False)
    cur.fetchone.return_value = {"id": 5, "contact_id": 2}
    with patch("app.db.get_cursor", return_value=cur), \
         patch("threading.Thread") as mock_thread:
        mock_thread.return_value.start = MagicMock()
        resp = client.post("/api/webhooks/shipday", json={
            "status": "OrderDelivered",
            "orderId": "ORD-001",
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["event_type"] == "order_delivered"


def test_shipday_webhook_order_not_found():
    cur = _mock_cursor(fetchone_val=None)
    with patch("app.db.get_cursor", return_value=cur):
        resp = client.post("/api/webhooks/shipday", json={
            "status": "OrderDelivered",
            "orderId": "UNKNOWN-999",
        })
    assert resp.status_code == 200
    assert resp.json()["status"] == "skipped"


# ── Story 10.4: Campaign sync ─────────────────────────────────────────────────

def test_list_campaigns():
    cur = _mock_cursor(rows=[
        {"lifecycle_segment": "warm", "instantly_campaign_id": "camp-1", "is_active": True}
    ])
    with patch("app.db.get_cursor", return_value=cur):
        resp = client.get("/api/webhooks/campaigns")
    assert resp.status_code == 200
    assert len(resp.json()["campaigns"]) == 1
