from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

_TOKEN_RESP = {"access_token": "test-access-token"}
_FILE_ID = "1abc123XYZ"


def _mock_token(monkeypatch):
    monkeypatch.setattr("app.routers.internal.settings.google_client_id", "cid")
    monkeypatch.setattr("app.routers.internal.settings.google_client_secret", "csecret")
    monkeypatch.setattr("app.routers.internal.settings.google_drive_refresh_token", "rtoken")
    monkeypatch.setattr("app.routers.internal.settings.google_drive_folder_id", "folder123")


# ── Upload ────────────────────────────────────────────────────────────────────

def test_drive_upload_ok(monkeypatch):
    _mock_token(monkeypatch)
    with patch("app.routers.internal.httpx.AsyncClient") as MockClient:
        mock_http = AsyncMock()
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        token_resp = MagicMock(status_code=200)
        token_resp.json.return_value = _TOKEN_RESP
        token_resp.raise_for_status = MagicMock()

        upload_resp = MagicMock(status_code=200)
        upload_resp.json.return_value = {"id": _FILE_ID}

        mock_http.post = AsyncMock(side_effect=[token_resp, upload_resp])

        resp = client.post("/api/internal/drive/upload", json={
            "filename": "test.csv",
            "content": "col1,col2\n1,2",
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        assert resp.json()["file_id"] == _FILE_ID


def test_drive_upload_token_failure_returns_500(monkeypatch):
    _mock_token(monkeypatch)
    with patch("app.routers.internal._get_drive_token", AsyncMock(side_effect=Exception("auth down"))):
        resp = client.post("/api/internal/drive/upload", json={
            "filename": "test.csv",
            "content": "data",
        })
        assert resp.status_code == 500
        assert "Auth failed" in resp.json()["detail"]


def test_drive_upload_api_error_returns_500(monkeypatch):
    _mock_token(monkeypatch)
    with patch("app.routers.internal._get_drive_token", AsyncMock(return_value="tok")):
        with patch("app.routers.internal.httpx.AsyncClient") as MockClient:
            mock_http = AsyncMock()
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            bad_resp = MagicMock(status_code=403)
            bad_resp.text = "Forbidden"
            mock_http.post = AsyncMock(return_value=bad_resp)

            resp = client.post("/api/internal/drive/upload", json={
                "filename": "test.csv",
                "content": "data",
            })
            assert resp.status_code == 500


# ── List files ────────────────────────────────────────────────────────────────

def test_drive_list_files_ok(monkeypatch):
    _mock_token(monkeypatch)
    with patch("app.routers.internal._get_drive_token", AsyncMock(return_value="tok")):
        with patch("app.routers.internal.httpx.AsyncClient") as MockClient:
            mock_http = AsyncMock()
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            list_resp = MagicMock(status_code=200)
            list_resp.json.return_value = {"files": [
                {"id": "f1", "name": "report.csv", "modifiedTime": "2026-03-28T10:00:00Z"},
                {"id": "f2", "name": "menu.csv", "modifiedTime": "2026-03-27T09:00:00Z"},
            ]}
            mock_http.get = AsyncMock(return_value=list_resp)

            resp = client.get("/api/internal/drive/files")
            assert resp.status_code == 200
            files = resp.json()["files"]
            assert len(files) == 2
            assert files[0] == {"id": "f1", "name": "report.csv", "modified_at": "2026-03-28T10:00:00Z"}


def test_drive_list_files_token_failure_returns_500(monkeypatch):
    _mock_token(monkeypatch)
    with patch("app.routers.internal._get_drive_token", AsyncMock(side_effect=Exception("no token"))):
        resp = client.get("/api/internal/drive/files")
        assert resp.status_code == 500


def test_drive_list_files_api_error_returns_500(monkeypatch):
    _mock_token(monkeypatch)
    with patch("app.routers.internal._get_drive_token", AsyncMock(return_value="tok")):
        with patch("app.routers.internal.httpx.AsyncClient") as MockClient:
            mock_http = AsyncMock()
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            bad_resp = MagicMock(status_code=500)
            bad_resp.text = "Internal Server Error"
            mock_http.get = AsyncMock(return_value=bad_resp)

            resp = client.get("/api/internal/drive/files")
            assert resp.status_code == 500


def test_drive_list_files_empty(monkeypatch):
    _mock_token(monkeypatch)
    with patch("app.routers.internal._get_drive_token", AsyncMock(return_value="tok")):
        with patch("app.routers.internal.httpx.AsyncClient") as MockClient:
            mock_http = AsyncMock()
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            list_resp = MagicMock(status_code=200)
            list_resp.json.return_value = {"files": []}
            mock_http.get = AsyncMock(return_value=list_resp)

            resp = client.get("/api/internal/drive/files")
            assert resp.status_code == 200
            assert resp.json()["files"] == []
