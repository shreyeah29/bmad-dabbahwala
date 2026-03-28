import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.auth import _sessions, get_current_user

client = TestClient(app, follow_redirects=False)


# ── get_current_user helper ───────────────────────────────────────────────────

def test_get_current_user_returns_none_when_no_cookie():
    from starlette.requests import Request
    from starlette.datastructures import Headers
    scope = {"type": "http", "headers": [], "method": "GET", "path": "/"}
    request = Request(scope)
    assert get_current_user(request) is None


def test_get_current_user_returns_none_for_unknown_session():
    from starlette.requests import Request
    scope = {
        "type": "http",
        "headers": [(b"cookie", b"session_id=does-not-exist")],
        "method": "GET",
        "path": "/",
    }
    request = Request(scope)
    assert get_current_user(request) is None


def test_get_current_user_returns_user_for_valid_session():
    from starlette.requests import Request
    _sessions["test-valid-session"] = {"email": "u@dabbahwala.com", "name": "User"}
    scope = {
        "type": "http",
        "headers": [(b"cookie", b"session_id=test-valid-session")],
        "method": "GET",
        "path": "/",
    }
    request = Request(scope)
    user = get_current_user(request)
    assert user is not None
    assert user["email"] == "u@dabbahwala.com"
    assert user["name"] == "User"
    del _sessions["test-valid-session"]


# ── GET /auth/me ──────────────────────────────────────────────────────────────

def test_auth_me_unauthenticated_returns_401():
    resp = client.get("/auth/me")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Not authenticated"


def test_auth_me_authenticated_returns_user():
    _sessions["me-session"] = {"email": "ops@dabbahwala.com", "name": "Ops"}
    c = TestClient(app, follow_redirects=False, cookies={"session_id": "me-session"})
    resp = c.get("/auth/me")
    assert resp.status_code == 200
    assert resp.json() == {"email": "ops@dabbahwala.com", "name": "Ops"}
    del _sessions["me-session"]


def test_auth_me_expired_session_returns_401():
    # Session was deleted (e.g. logout), cookie still sent
    resp = client.get("/auth/me", cookies={"session_id": "stale-session-xyz"})
    assert resp.status_code == 401


def test_auth_me_returns_only_email_and_name():
    _sessions["fields-session"] = {"email": "a@dabbahwala.com", "name": "A", "extra": "should-not-appear"}
    c = TestClient(app, follow_redirects=False, cookies={"session_id": "fields-session"})
    resp = c.get("/auth/me")
    assert resp.status_code == 200
    data = resp.json()
    assert set(data.keys()) == {"email", "name"}
    del _sessions["fields-session"]
