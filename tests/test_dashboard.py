import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.auth import _sessions

client = TestClient(app, follow_redirects=False)


def test_dashboard_unauthenticated_redirects_to_login():
    resp = client.get("/dashboard")
    assert resp.status_code in (302, 307)
    assert "/login" in resp.headers["location"]


def test_dashboard_authenticated_returns_200():
    _sessions["dash-session"] = {"email": "ops@dabbahwala.com", "name": "Ops"}
    c = TestClient(app, follow_redirects=False, cookies={"session_id": "dash-session"})
    resp = c.get("/dashboard")
    assert resp.status_code == 200
    del _sessions["dash-session"]


def test_dashboard_authenticated_returns_html():
    _sessions["dash-html-session"] = {"email": "ops@dabbahwala.com", "name": "Ops"}
    c = TestClient(app, follow_redirects=False, cookies={"session_id": "dash-html-session"})
    resp = c.get("/dashboard")
    assert "text/html" in resp.headers["content-type"]
    assert "DabbahWala" in resp.text
    del _sessions["dash-html-session"]


def test_dashboard_contains_logout_link():
    _sessions["dash-logout-session"] = {"email": "ops@dabbahwala.com", "name": "Ops"}
    c = TestClient(app, follow_redirects=False, cookies={"session_id": "dash-logout-session"})
    resp = c.get("/dashboard")
    assert "/auth/logout" in resp.text
    del _sessions["dash-logout-session"]


def test_dashboard_stale_cookie_redirects_to_login():
    resp = client.get("/dashboard", cookies={"session_id": "stale-session-abc"})
    assert resp.status_code in (302, 307)
    assert "/login" in resp.headers["location"]
