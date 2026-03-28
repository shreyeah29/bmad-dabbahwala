from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app, follow_redirects=False)


# ── /login ────────────────────────────────────────────────────────────────────

def test_login_returns_html():
    resp = client.get("/login")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Sign in with Google" in resp.text


def test_login_contains_auth_link():
    resp = client.get("/login")
    assert "/auth/google" in resp.text


# ── /auth/google ──────────────────────────────────────────────────────────────

def test_auth_google_redirects_to_google():
    resp = client.get("/auth/google")
    assert resp.status_code in (302, 307)
    assert "accounts.google.com" in resp.headers["location"]


def test_auth_google_redirect_contains_oauth_params():
    resp = client.get("/auth/google")
    location = resp.headers["location"]
    assert "response_type=code" in location
    assert "scope=openid" in location


# ── /auth/callback ────────────────────────────────────────────────────────────

def test_callback_missing_code_redirects_to_login():
    resp = client.get("/auth/callback")
    assert resp.status_code in (302, 307)
    assert "/login" in resp.headers["location"]


def test_callback_token_exchange_failure_redirects_to_login():
    with patch("app.auth.httpx.AsyncClient") as MockClient:
        mock_http = AsyncMock()
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        token_resp = MagicMock()
        token_resp.status_code = 400
        token_resp.text = "invalid_grant"
        mock_http.post = AsyncMock(return_value=token_resp)

        resp = client.get("/auth/callback?code=bad-code")
        assert resp.status_code in (302, 307)
        assert "/login" in resp.headers["location"]


def test_callback_userinfo_failure_redirects_to_login():
    with patch("app.auth.httpx.AsyncClient") as MockClient:
        mock_http = AsyncMock()
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        token_resp = MagicMock()
        token_resp.status_code = 200
        token_resp.json.return_value = {"access_token": "tok"}

        userinfo_resp = MagicMock()
        userinfo_resp.status_code = 401
        userinfo_resp.text = "unauthorized"

        mock_http.post = AsyncMock(return_value=token_resp)
        mock_http.get = AsyncMock(return_value=userinfo_resp)

        resp = client.get("/auth/callback?code=some-code")
        assert resp.status_code in (302, 307)
        assert "/login" in resp.headers["location"]


def test_callback_wrong_domain_returns_403():
    with patch("app.auth.httpx.AsyncClient") as MockClient:
        mock_http = AsyncMock()
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        token_resp = MagicMock()
        token_resp.status_code = 200
        token_resp.json.return_value = {"access_token": "tok"}

        userinfo_resp = MagicMock()
        userinfo_resp.status_code = 200
        userinfo_resp.json.return_value = {"email": "attacker@gmail.com", "name": "Attacker"}

        mock_http.post = AsyncMock(return_value=token_resp)
        mock_http.get = AsyncMock(return_value=userinfo_resp)

        resp = client.get("/auth/callback?code=test-code")
        assert resp.status_code == 403
        assert "dabbahwala.com" in resp.json()["detail"]


def test_callback_valid_user_sets_session_cookie():
    with patch("app.auth.httpx.AsyncClient") as MockClient:
        mock_http = AsyncMock()
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        token_resp = MagicMock()
        token_resp.status_code = 200
        token_resp.json.return_value = {"access_token": "tok"}

        userinfo_resp = MagicMock()
        userinfo_resp.status_code = 200
        userinfo_resp.json.return_value = {"email": "ops@dabbahwala.com", "name": "Ops User"}

        mock_http.post = AsyncMock(return_value=token_resp)
        mock_http.get = AsyncMock(return_value=userinfo_resp)

        resp = client.get("/auth/callback?code=valid-code")
        assert resp.status_code in (302, 307)
        assert "/dashboard" in resp.headers["location"]
        assert "session_id" in resp.cookies


def test_callback_valid_user_session_stored():
    from app.auth import _sessions

    with patch("app.auth.httpx.AsyncClient") as MockClient:
        mock_http = AsyncMock()
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        token_resp = MagicMock()
        token_resp.status_code = 200
        token_resp.json.return_value = {"access_token": "tok"}

        userinfo_resp = MagicMock()
        userinfo_resp.status_code = 200
        userinfo_resp.json.return_value = {"email": "dev@dabbahwala.com", "name": "Dev"}

        mock_http.post = AsyncMock(return_value=token_resp)
        mock_http.get = AsyncMock(return_value=userinfo_resp)

        resp = client.get("/auth/callback?code=valid-code")
        session_id = resp.cookies.get("session_id")
        assert session_id is not None
        assert _sessions[session_id]["email"] == "dev@dabbahwala.com"
        assert _sessions[session_id]["name"] == "Dev"


# ── /auth/logout ──────────────────────────────────────────────────────────────

def test_logout_clears_session_and_redirects():
    from app.auth import _sessions
    _sessions["logout-test-session"] = {"email": "user@dabbahwala.com", "name": "User"}

    resp = client.get("/auth/logout", cookies={"session_id": "logout-test-session"})
    assert resp.status_code in (302, 307)
    assert "/login" in resp.headers["location"]
    assert "logout-test-session" not in _sessions


def test_logout_without_session_still_redirects():
    resp = client.get("/auth/logout")
    assert resp.status_code in (302, 307)
    assert "/login" in resp.headers["location"]


def test_logout_clears_cookie():
    from app.auth import _sessions
    _sessions["cookie-clear-session"] = {"email": "u@dabbahwala.com", "name": "U"}

    resp = client.get("/auth/logout", cookies={"session_id": "cookie-clear-session"})
    # Cookie should be deleted (set to empty or max-age=0)
    set_cookie = resp.headers.get("set-cookie", "")
    assert "session_id" in set_cookie
