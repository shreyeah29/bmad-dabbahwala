from unittest.mock import MagicMock, call, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _mock_cursor(cycle_result=None, segments=None):
    if cycle_result is None:
        cycle_result = {"updated": 3, "cycle_ran_at": "2026-03-28T10:00:00+00:00"}
    if segments is None:
        segments = [
            {"segment": "cold", "count": 10},
            {"segment": "active_customer", "count": 5},
        ]

    mock_cur = MagicMock()
    mock_cur.fetchone.return_value = {"result": cycle_result}
    mock_cur.fetchall.return_value = segments

    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=mock_cur)
    mock_ctx.__exit__ = MagicMock(return_value=False)
    return mock_ctx


# ── POST /api/lifecycle/run ───────────────────────────────────────────────────

def test_lifecycle_run_returns_200():
    with patch("app.routers.lifecycle.get_cursor", return_value=_mock_cursor()):
        resp = client.post("/api/lifecycle/run")
        assert resp.status_code == 200


def test_lifecycle_run_returns_transitions():
    with patch("app.routers.lifecycle.get_cursor", return_value=_mock_cursor({"updated": 7, "cycle_ran_at": "2026-03-28T10:00:00"})):
        resp = client.post("/api/lifecycle/run")
        assert resp.json()["transitions"] == 7


def test_lifecycle_run_returns_segments():
    segs = [{"segment": "cold", "count": 20}, {"segment": "lapsed_customer", "count": 4}]
    with patch("app.routers.lifecycle.get_cursor", return_value=_mock_cursor(segments=segs)):
        resp = client.post("/api/lifecycle/run")
        data = resp.json()
        assert data["segments"]["cold"] == 20
        assert data["segments"]["lapsed_customer"] == 4


def test_lifecycle_run_returns_duration_ms():
    with patch("app.routers.lifecycle.get_cursor", return_value=_mock_cursor()):
        resp = client.post("/api/lifecycle/run")
        assert "duration_ms" in resp.json()
        assert isinstance(resp.json()["duration_ms"], int)


def test_lifecycle_run_returns_cycle_ran_at():
    with patch("app.routers.lifecycle.get_cursor", return_value=_mock_cursor({"updated": 0, "cycle_ran_at": "2026-03-28T10:00:00"})):
        resp = client.post("/api/lifecycle/run")
        assert resp.json()["cycle_ran_at"] == "2026-03-28T10:00:00"


def test_lifecycle_run_uses_commit_cursor():
    mock_ctx = _mock_cursor()
    with patch("app.routers.lifecycle.get_cursor", return_value=mock_ctx) as mock_get:
        client.post("/api/lifecycle/run")
        mock_get.assert_called_once_with(commit=True)


def test_lifecycle_run_calls_stored_function():
    mock_ctx = _mock_cursor()
    with patch("app.routers.lifecycle.get_cursor", return_value=mock_ctx):
        client.post("/api/lifecycle/run")
        sql = mock_ctx.__enter__().execute.call_args_list[0][0][0]
        assert "run_lifecycle_cycle" in sql


def test_lifecycle_run_db_error_returns_500():
    with patch("app.routers.lifecycle.get_cursor", side_effect=Exception("DB down")):
        resp = client.post("/api/lifecycle/run")
        assert resp.status_code == 500
        assert "DB down" in resp.json()["detail"]
