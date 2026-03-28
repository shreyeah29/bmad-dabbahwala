import smtplib
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

_SMTP_SETTINGS = {
    "smtp_host": "smtp.example.com",
    "smtp_user": "user@example.com",
    "smtp_password": "secret",
    "report_email_to": "core@dabbahwala.com",
}


def _patch_settings(monkeypatch):
    for k, v in _SMTP_SETTINGS.items():
        monkeypatch.setattr(f"app.routers.internal.settings.{k}", v)


# ── Happy path ────────────────────────────────────────────────────────────────

def test_send_email_ok(monkeypatch):
    _patch_settings(monkeypatch)
    with patch("app.routers.internal.smtplib.SMTP") as MockSMTP:
        mock_server = MagicMock()
        MockSMTP.return_value.__enter__ = MagicMock(return_value=mock_server)
        MockSMTP.return_value.__exit__ = MagicMock(return_value=False)

        resp = client.post("/api/internal/send-email", json={
            "to": "ops@dabbahwala.com",
            "subject": "Test",
            "body_text": "Hello",
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


def test_send_email_calls_starttls_and_login(monkeypatch):
    _patch_settings(monkeypatch)
    with patch("app.routers.internal.smtplib.SMTP") as MockSMTP:
        mock_server = MagicMock()
        MockSMTP.return_value.__enter__ = MagicMock(return_value=mock_server)
        MockSMTP.return_value.__exit__ = MagicMock(return_value=False)

        client.post("/api/internal/send-email", json={
            "subject": "Test",
            "body_text": "Hello",
        })
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("user@example.com", "secret")


def test_send_email_uses_default_recipient_when_to_omitted(monkeypatch):
    _patch_settings(monkeypatch)
    with patch("app.routers.internal.smtplib.SMTP") as MockSMTP:
        mock_server = MagicMock()
        MockSMTP.return_value.__enter__ = MagicMock(return_value=mock_server)
        MockSMTP.return_value.__exit__ = MagicMock(return_value=False)

        client.post("/api/internal/send-email", json={
            "subject": "Report",
            "body_text": "Daily report",
        })
        args = mock_server.sendmail.call_args
        assert args[0][1] == "core@dabbahwala.com"


def test_send_email_sends_html_body(monkeypatch):
    _patch_settings(monkeypatch)
    with patch("app.routers.internal.smtplib.SMTP") as MockSMTP:
        mock_server = MagicMock()
        MockSMTP.return_value.__enter__ = MagicMock(return_value=mock_server)
        MockSMTP.return_value.__exit__ = MagicMock(return_value=False)

        client.post("/api/internal/send-email", json={
            "to": "ops@dabbahwala.com",
            "subject": "HTML Test",
            "body_html": "<h1>Hello</h1>",
        })
        mock_server.sendmail.assert_called_once()
        sent_body = mock_server.sendmail.call_args[0][2]
        assert "Hello" in sent_body


def test_send_email_connects_to_configured_host(monkeypatch):
    _patch_settings(monkeypatch)
    with patch("app.routers.internal.smtplib.SMTP") as MockSMTP:
        mock_server = MagicMock()
        MockSMTP.return_value.__enter__ = MagicMock(return_value=mock_server)
        MockSMTP.return_value.__exit__ = MagicMock(return_value=False)

        client.post("/api/internal/send-email", json={
            "subject": "Test",
            "body_text": "Hello",
        })
        MockSMTP.assert_called_once_with("smtp.example.com", 587)


# ── Error path ────────────────────────────────────────────────────────────────

def test_send_email_smtp_error_returns_500(monkeypatch):
    _patch_settings(monkeypatch)
    with patch("app.routers.internal.smtplib.SMTP") as MockSMTP:
        MockSMTP.side_effect = smtplib.SMTPException("connection refused")

        resp = client.post("/api/internal/send-email", json={
            "subject": "Test",
            "body_text": "Hello",
        })
        assert resp.status_code == 500
        assert resp.json()["status"] == "error"
        assert "connection refused" in resp.json()["detail"]
