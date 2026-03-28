import importlib
import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

_SECRET = "test-admin-secret"


def _with_secret(monkeypatch):
    monkeypatch.setattr("app.routers.credentials.settings.admin_secret", _SECRET)


# ── Auth guard ────────────────────────────────────────────────────────────────

def test_credentials_missing_header_returns_403():
    resp = client.get("/api/credentials/")
    assert resp.status_code == 403


def test_credentials_wrong_header_returns_403(monkeypatch):
    _with_secret(monkeypatch)
    resp = client.get("/api/credentials/", headers={"X-Admin-Secret": "wrong"})
    assert resp.status_code == 403


def test_credentials_correct_header_returns_200(monkeypatch):
    _with_secret(monkeypatch)
    resp = client.get("/api/credentials/", headers={"X-Admin-Secret": _SECRET})
    assert resp.status_code == 200


# ── Response shape ────────────────────────────────────────────────────────────

def test_credentials_returns_all_keys(monkeypatch):
    _with_secret(monkeypatch)
    monkeypatch.setattr("app.routers.credentials.settings.anthropic_api_key", "sk-test")
    monkeypatch.setattr("app.routers.credentials.settings.telnyx_api_key", "telnyx-test")

    resp = client.get("/api/credentials/", headers={"X-Admin-Secret": _SECRET})
    data = resp.json()

    expected_keys = {
        "database_url", "anthropic_api_key", "telnyx_api_key",
        "airtable_api_key", "airtable_base_id", "shipday_api_key",
        "instantly_api_key", "n8n_api_key", "smtp_host", "smtp_user",
        "smtp_password", "report_email_to", "allowed_domain",
        "google_client_id", "google_client_secret", "google_redirect_uri",
    }
    assert expected_keys.issubset(data.keys())


def test_credentials_returns_live_values(monkeypatch):
    _with_secret(monkeypatch)
    monkeypatch.setattr("app.routers.credentials.settings.anthropic_api_key", "sk-live-test")
    resp = client.get("/api/credentials/", headers={"X-Admin-Secret": _SECRET})
    assert resp.json()["anthropic_api_key"] == "sk-live-test"


def test_credentials_read_at_request_time(monkeypatch):
    """Values must reflect settings at request time, not import time."""
    _with_secret(monkeypatch)
    monkeypatch.setattr("app.routers.credentials.settings.n8n_api_key", "first")
    resp1 = client.get("/api/credentials/", headers={"X-Admin-Secret": _SECRET})
    assert resp1.json()["n8n_api_key"] == "first"

    monkeypatch.setattr("app.routers.credentials.settings.n8n_api_key", "second")
    resp2 = client.get("/api/credentials/", headers={"X-Admin-Secret": _SECRET})
    assert resp2.json()["n8n_api_key"] == "second"


# ── Logging ───────────────────────────────────────────────────────────────────

def test_credentials_logs_info_on_call(monkeypatch, caplog):
    import logging
    _with_secret(monkeypatch)
    with caplog.at_level(logging.INFO, logger="app.routers.credentials"):
        client.get("/api/credentials/", headers={"X-Admin-Secret": _SECRET})
    assert any("Credentials fetched" in r.message for r in caplog.records)
