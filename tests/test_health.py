from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

# get_cursor is imported locally inside the health() function,
# so we patch it at its source: app.db.get_cursor


def _mock_cursor_ctx(cursor=None):
    """Helper: return a mock context manager yielding `cursor`."""
    mock_ctx = MagicMock()
    mock_ctx.__enter__ = lambda s: cursor or MagicMock()
    mock_ctx.__exit__ = MagicMock(return_value=False)
    return mock_ctx


def test_health_ok():
    mock_cursor = MagicMock()
    with patch("app.db.get_cursor", return_value=_mock_cursor_ctx(mock_cursor)):
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "connected"}
    mock_cursor.execute.assert_called_once_with("SELECT 1")


def test_health_degraded_when_db_unreachable():
    with patch("app.db.get_cursor", side_effect=Exception("connection refused")):
        response = client.get("/health")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert "connection refused" in body["db"]


def test_health_no_auth_required():
    """Health endpoint must be reachable without any credentials."""
    with patch("app.db.get_cursor", return_value=_mock_cursor_ctx()):
        response = client.get("/health")

    assert response.status_code != 401
    assert response.status_code != 403
