"""Tests for E11 — Orders & Shipday"""
from unittest.mock import MagicMock, patch, AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _mock_cursor(rows=None, fetchone_val=None, rowcount=1):
    cur = MagicMock()
    cur.__enter__ = lambda s: s
    cur.__exit__ = MagicMock(return_value=False)
    cur.fetchone.return_value = fetchone_val
    cur.fetchall.return_value = rows or []
    cur.rowcount = rowcount
    return cur


def test_sync_status():
    cur = MagicMock()
    cur.__enter__ = lambda s: s
    cur.__exit__ = MagicMock(return_value=False)
    cur.fetchone.side_effect = [{"total": 42}, {"last_sync": None}]
    with patch("app.db.get_cursor", return_value=cur):
        resp = client.get("/api/shipday/sync-status")
    assert resp.status_code == 200
    assert resp.json()["total_orders"] == 42


def test_top_calls():
    cur = _mock_cursor(rows=[
        {"id": 1, "email": "a@b.com", "name": "Alice", "phone": "+14045551234",
         "order_count": 5, "total_spent": 120.0, "segment": "warm", "last_order_at": None}
    ])
    with patch("app.db.get_cursor", return_value=cur):
        resp = client.get("/api/shipday/top-calls")
    assert resp.status_code == 200
    assert len(resp.json()["contacts"]) == 1


def test_ingest_orders_success():
    mock_orders = [
        {"customerEmail": "joe@example.com", "customerPhoneNumber": "4045551234",
         "customerName": "Joe", "orderId": "101", "orderCost": 15.99}
    ]
    cur = MagicMock()
    cur.__enter__ = lambda s: s
    cur.__exit__ = MagicMock(return_value=False)
    cur.fetchone.return_value = {"id": 1}
    cur.rowcount = 1

    with patch("app.routers.shipday._fetch_shipday_orders", return_value=mock_orders), \
         patch("app.db.get_cursor", return_value=cur):
        resp = client.post("/api/shipday/ingest-orders?limit=10")
    assert resp.status_code == 200
    data = resp.json()
    assert data["errors"] == 0


def test_ingest_orders_api_error():
    with patch("app.routers.shipday._fetch_shipday_orders",
               side_effect=Exception("Connection refused")):
        resp = client.post("/api/shipday/ingest-orders")
    assert resp.status_code == 502


def test_feedback_stats():
    cur = _mock_cursor(rows=[
        {"event_type": "order_delivered", "count": 10},
        {"event_type": "order_cancelled", "count": 2},
    ])
    with patch("app.db.get_cursor", return_value=cur):
        resp = client.get("/api/shipday/feedback-stats")
    assert resp.status_code == 200
    assert len(resp.json()["stats"]) == 2


def test_import_pipeline_status():
    resp = client.get("/api/shipday/import-pipeline-status")
    assert resp.status_code == 200
    assert "running" in resp.json()
