"""Tests for E12 — Daily CSV Order Processing"""
import io
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.routers.daily_orders import _normalize_phone

client = TestClient(app)


def test_normalize_phone_10_digits():
    assert _normalize_phone("4045551234") == "+14045551234"


def test_normalize_phone_11_digits():
    assert _normalize_phone("14045551234") == "+14045551234"


def test_normalize_phone_india():
    assert _normalize_phone("914045551234") == "+914045551234"


def test_normalize_phone_empty():
    assert _normalize_phone("") is None


def _make_csv(rows: list[dict]) -> bytes:
    if not rows:
        return b"email,phone,name,order_ref,total_amount,item_name,quantity,notes\n"
    header = ",".join(rows[0].keys())
    lines = [header] + [",".join(str(v) for v in r.values()) for r in rows]
    return "\n".join(lines).encode()


def test_upload_csv_not_csv():
    resp = client.post(
        "/api/daily-orders/",
        files={"file": ("orders.txt", b"not csv", "text/plain")},
    )
    assert resp.status_code == 422


def test_upload_csv_success():
    csv_bytes = _make_csv([{
        "email": "alice@example.com",
        "phone": "4045551234",
        "name": "Alice",
        "order_ref": "ORD-001",
        "total_amount": "25.50",
        "item_name": "Dal Makhani",
        "quantity": "2",
        "notes": "",
    }])

    cur = MagicMock()
    cur.__enter__ = lambda s: s
    cur.__exit__ = MagicMock(return_value=False)
    cur.fetchone.return_value = {"id": 1, "is_new": True}
    cur.rowcount = 1

    with patch("app.db.get_cursor", return_value=cur):
        resp = client.post(
            "/api/daily-orders/",
            files={"file": ("orders.csv", csv_bytes, "text/csv")},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["errors"] == 0


def test_upload_csv_missing_email_and_phone():
    csv_bytes = _make_csv([{
        "email": "",
        "phone": "",
        "name": "Bob",
        "order_ref": "ORD-002",
        "total_amount": "10.00",
        "item_name": "Rice",
        "quantity": "1",
        "notes": "",
    }])
    cur = MagicMock()
    cur.__enter__ = lambda s: s
    cur.__exit__ = MagicMock(return_value=False)
    with patch("app.db.get_cursor", return_value=cur):
        resp = client.post(
            "/api/daily-orders/",
            files={"file": ("orders.csv", csv_bytes, "text/csv")},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["errors"] == 1
    assert "Missing email and phone" in data["error_details"][0]["error"]
