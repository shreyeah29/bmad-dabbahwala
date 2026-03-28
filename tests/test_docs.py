from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers.internal import _extract_doc_text

client = TestClient(app)

_SAMPLE_DOC = {
    "body": {
        "content": [
            {"paragraph": {"elements": [{"textRun": {"content": "Hello "}}]}},
            {"paragraph": {"elements": [{"textRun": {"content": "World\n"}}]}},
        ]
    }
}


def _mock_docs_token(monkeypatch):
    monkeypatch.setattr("app.routers.internal.settings.google_client_id", "cid")
    monkeypatch.setattr("app.routers.internal.settings.google_client_secret", "csec")
    monkeypatch.setattr("app.routers.internal.settings.google_docs_refresh_token", "rtoken")


# ── _extract_doc_text unit tests ──────────────────────────────────────────────

def test_extract_doc_text_basic():
    text = _extract_doc_text(_SAMPLE_DOC)
    assert text == "Hello World\n"


def test_extract_doc_text_empty_doc():
    assert _extract_doc_text({}) == ""


def test_extract_doc_text_skips_non_paragraph():
    doc = {"body": {"content": [{"sectionBreak": {}}, {"paragraph": {"elements": [{"textRun": {"content": "Hi"}}]}}]}}
    assert _extract_doc_text(doc) == "Hi"


# ── GET /api/internal/docs/{doc_id} ──────────────────────────────────────────

def test_read_doc_ok(monkeypatch):
    _mock_docs_token(monkeypatch)
    with patch("app.routers.internal._get_docs_token", AsyncMock(return_value="tok")):
        with patch("app.routers.internal.httpx.AsyncClient") as MockClient:
            mock_http = AsyncMock()
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            doc_resp = MagicMock(status_code=200)
            doc_resp.json.return_value = _SAMPLE_DOC
            mock_http.get = AsyncMock(return_value=doc_resp)

            resp = client.get("/api/internal/docs/doc123")
            assert resp.status_code == 200
            assert resp.json()["doc_id"] == "doc123"
            assert resp.json()["content"] == "Hello World\n"


def test_read_doc_not_found_returns_404(monkeypatch):
    _mock_docs_token(monkeypatch)
    with patch("app.routers.internal._get_docs_token", AsyncMock(return_value="tok")):
        with patch("app.routers.internal.httpx.AsyncClient") as MockClient:
            mock_http = AsyncMock()
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            not_found_resp = MagicMock(status_code=404)
            not_found_resp.text = "Not Found"
            mock_http.get = AsyncMock(return_value=not_found_resp)

            resp = client.get("/api/internal/docs/nonexistent")
            assert resp.status_code == 404
            assert "not found" in resp.json()["detail"].lower()


def test_read_doc_token_failure_returns_500(monkeypatch):
    _mock_docs_token(monkeypatch)
    with patch("app.routers.internal._get_docs_token", AsyncMock(side_effect=Exception("no token"))):
        resp = client.get("/api/internal/docs/doc123")
        assert resp.status_code == 500
        assert "Auth failed" in resp.json()["detail"]


def test_read_doc_api_error_returns_500(monkeypatch):
    _mock_docs_token(monkeypatch)
    with patch("app.routers.internal._get_docs_token", AsyncMock(return_value="tok")):
        with patch("app.routers.internal.httpx.AsyncClient") as MockClient:
            mock_http = AsyncMock()
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            err_resp = MagicMock(status_code=500)
            err_resp.text = "Internal error"
            mock_http.get = AsyncMock(return_value=err_resp)

            resp = client.get("/api/internal/docs/doc123")
            assert resp.status_code == 500
