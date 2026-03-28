from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app, raise_server_exceptions=False)


def test_app_boots():
    """App starts and returns 404 for unknown routes (no routes registered yet)."""
    response = client.get("/")
    assert response.status_code == 404


def test_global_exception_handler():
    """Unhandled exceptions return JSON with detail and type fields."""
    from fastapi import APIRouter
    from app.main import app

    router = APIRouter()

    @router.get("/__test_crash__")
    def crash():
        raise ValueError("intentional test crash")

    app.include_router(router)

    response = client.get("/__test_crash__")
    assert response.status_code == 500
    body = response.json()
    assert "detail" in body
    assert "type" in body
    assert body["type"] == "ValueError"
    assert "intentional test crash" in body["detail"]


def test_request_logging_middleware_does_not_crash():
    """Middleware runs without error on a normal request."""
    response = client.get("/some-path-that-does-not-exist")
    assert response.status_code == 404
