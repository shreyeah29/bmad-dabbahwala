from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _mock_cursor(event_id=42):
    mock_cur = MagicMock()
    mock_cur.fetchone.return_value = {"event_id": event_id}
    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=mock_cur)
    mock_ctx.__exit__ = MagicMock(return_value=False)
    return mock_ctx


# ── Valid event types ─────────────────────────────────────────────────────────

def test_ingest_event_ok():
    with patch("app.routers.events.get_cursor", return_value=_mock_cursor(42)):
        resp = client.post("/api/events/ingest", json={
            "contact_id": 1,
            "event_type": "order_placed",
            "metadata": {"order_ref": "ORD-001"},
        })
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok", "event_id": 42}


def test_ingest_event_all_valid_types():
    valid_types = [
        "order_placed", "order_delivered", "order_cancelled",
        "sms_sent", "sms_received", "email_sent", "email_opened",
        "email_clicked", "call_made", "feedback_received",
    ]
    for event_type in valid_types:
        with patch("app.routers.events.get_cursor", return_value=_mock_cursor(1)):
            resp = client.post("/api/events/ingest", json={
                "contact_id": 1,
                "event_type": event_type,
            })
            assert resp.status_code == 200, f"Failed for event_type={event_type}"


def test_ingest_event_default_empty_metadata():
    with patch("app.routers.events.get_cursor", return_value=_mock_cursor(5)):
        resp = client.post("/api/events/ingest", json={
            "contact_id": 1,
            "event_type": "sms_sent",
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


# ── Invalid event type → 422 ──────────────────────────────────────────────────

def test_ingest_event_invalid_type_returns_422():
    resp = client.post("/api/events/ingest", json={
        "contact_id": 1,
        "event_type": "not_a_real_event",
    })
    assert resp.status_code == 422
    assert "Invalid event_type" in resp.json()["detail"]


def test_ingest_event_invalid_type_lists_valid_types():
    resp = client.post("/api/events/ingest", json={
        "contact_id": 1,
        "event_type": "bad_event",
    })
    assert "order_placed" in resp.json()["detail"]


def test_ingest_event_empty_type_returns_422():
    resp = client.post("/api/events/ingest", json={
        "contact_id": 1,
        "event_type": "",
    })
    assert resp.status_code == 422


# ── DB call ───────────────────────────────────────────────────────────────────

def test_ingest_event_calls_stored_function():
    mock_ctx = _mock_cursor(99)
    with patch("app.routers.events.get_cursor", return_value=mock_ctx) as mock_get:
        client.post("/api/events/ingest", json={
            "contact_id": 7,
            "event_type": "email_opened",
            "metadata": {"campaign": "test"},
        })
        mock_get.assert_called_once_with(commit=True)
        mock_ctx.__enter__().execute.assert_called_once()
        sql = mock_ctx.__enter__().execute.call_args[0][0]
        assert "ingest_event" in sql
