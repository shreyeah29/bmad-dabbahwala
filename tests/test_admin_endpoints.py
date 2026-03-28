import os
import pytest
from contextlib import contextmanager
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
SECRET = "test-secret"


def _cursor_ctx(cursor=None, rows=None):
    @contextmanager
    def _ctx(commit=False):
        cur = cursor or MagicMock()
        if rows is not None:
            cur.fetchall.return_value = rows
        yield cur
    return _ctx


# ── /admin/migrate/{n} ────────────────────────────────────────────────────────

def test_migrate_wrong_secret_returns_403():
    response = client.post("/admin/migrate/1?secret=wrong")
    assert response.status_code == 403


def test_migrate_missing_secret_returns_403():
    response = client.post("/admin/migrate/1")
    assert response.status_code == 403


def test_migrate_file_not_found(tmp_path, monkeypatch):
    monkeypatch.setenv("ADMIN_SECRET", SECRET)
    with patch("glob.glob", return_value=[]):
        response = client.post(f"/admin/migrate/99?secret={SECRET}")
    assert response.status_code == 200
    assert "error" in response.json()
    assert "099" in response.json()["error"]


def test_migrate_runs_file(tmp_path, monkeypatch):
    monkeypatch.setenv("ADMIN_SECRET", SECRET)
    sql_file = tmp_path / "001_test.sql"
    sql_file.write_text("CREATE TABLE t (id INT);")
    cursor = MagicMock()

    with patch("glob.glob", return_value=[str(sql_file)]), \
         patch("app.db.get_cursor", side_effect=_cursor_ctx(cursor)):
        response = client.post(f"/admin/migrate/1?secret={SECRET}")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["executed"] is True
    cursor.execute.assert_called_once_with("CREATE TABLE t (id INT);")


# ── /admin/query ──────────────────────────────────────────────────────────────

def test_query_wrong_secret_returns_403(monkeypatch):
    monkeypatch.setenv("ADMIN_SECRET", SECRET)
    response = client.post("/admin/query?secret=bad&sql=SELECT+1")
    assert response.status_code == 403


def test_query_empty_sql_returns_error(monkeypatch):
    monkeypatch.setenv("ADMIN_SECRET", SECRET)
    response = client.post(f"/admin/query?secret={SECRET}&sql=")
    assert response.status_code == 200
    assert response.json()["error"] == "No SQL provided"


def test_query_via_query_param(monkeypatch):
    monkeypatch.setenv("ADMIN_SECRET", SECRET)
    rows = [{"id": 1}, {"id": 2}]
    with patch("app.db.get_cursor", side_effect=_cursor_ctx(rows=rows)):
        response = client.post(f"/admin/query?secret={SECRET}&sql=SELECT+id+FROM+t")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["count"] == 2
    assert body["rows"] == rows


def test_query_via_json_body(monkeypatch):
    monkeypatch.setenv("ADMIN_SECRET", SECRET)
    rows = [{"n": 42}]
    with patch("app.db.get_cursor", side_effect=_cursor_ctx(rows=rows)):
        response = client.post(
            "/admin/query",
            json={"secret": SECRET, "sql": "SELECT 42 AS n"},
        )

    assert response.status_code == 200
    assert response.json()["count"] == 1


def test_query_uses_read_only_cursor(monkeypatch):
    monkeypatch.setenv("ADMIN_SECRET", SECRET)
    commit_values = []

    @contextmanager
    def capturing(commit=False):
        commit_values.append(commit)
        cur = MagicMock()
        cur.fetchall.return_value = []
        yield cur

    with patch("app.db.get_cursor", side_effect=capturing):
        client.post(f"/admin/query?secret={SECRET}&sql=SELECT+1")

    assert commit_values == [False]


# ── /admin/exec ───────────────────────────────────────────────────────────────

def test_exec_wrong_secret_returns_403(monkeypatch):
    monkeypatch.setenv("ADMIN_SECRET", SECRET)
    response = client.post("/admin/exec?secret=bad&sql=DROP+TABLE+t")
    assert response.status_code == 403


def test_exec_empty_sql_returns_error(monkeypatch):
    monkeypatch.setenv("ADMIN_SECRET", SECRET)
    response = client.post(f"/admin/exec?secret={SECRET}&sql=")
    assert response.json()["error"] == "No SQL provided"


def test_exec_via_query_param(monkeypatch):
    monkeypatch.setenv("ADMIN_SECRET", SECRET)
    cursor = MagicMock()
    with patch("app.db.get_cursor", side_effect=_cursor_ctx(cursor)):
        response = client.post(
            f"/admin/exec?secret={SECRET}&sql=CREATE+TABLE+x+(id+INT)"
        )

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "executed": True}


def test_exec_via_json_body(monkeypatch):
    monkeypatch.setenv("ADMIN_SECRET", SECRET)
    cursor = MagicMock()
    with patch("app.db.get_cursor", side_effect=_cursor_ctx(cursor)):
        response = client.post(
            "/admin/exec",
            json={"secret": SECRET, "sql": "DROP TABLE IF EXISTS tmp"},
        )

    assert response.status_code == 200
    assert response.json()["executed"] is True


def test_exec_uses_commit_cursor(monkeypatch):
    monkeypatch.setenv("ADMIN_SECRET", SECRET)
    commit_values = []

    @contextmanager
    def capturing(commit=False):
        commit_values.append(commit)
        yield MagicMock()

    with patch("app.db.get_cursor", side_effect=capturing):
        client.post(f"/admin/exec?secret={SECRET}&sql=SELECT+1")

    assert commit_values == [True]
