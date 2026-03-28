import pytest
import logging
from contextlib import contextmanager
from unittest.mock import MagicMock, patch, call


async def _run_ensure_schema():
    from app.main import startup_ensure_schema
    await startup_ensure_schema()


def _cursor_ctx(cursor):
    @contextmanager
    def _ctx(commit=False):
        yield cursor
    return _ctx


def _failing_ctx(exc):
    @contextmanager
    def _ctx(commit=False):
        raise exc
    return _ctx


@pytest.mark.asyncio
async def test_schema_patches_execute_all_statements():
    """All three SQL statements are executed."""
    cursor = MagicMock()
    with patch("app.db.get_cursor", side_effect=_cursor_ctx(cursor)):
        await _run_ensure_schema()

    executed = [c.args[0] for c in cursor.execute.call_args_list]
    assert any("delivery_date" in s and "ADD COLUMN" in s for s in executed)
    assert any("delivery_date = order_date" in s for s in executed)
    assert any("notes" in s and "ADD COLUMN" in s for s in executed)


@pytest.mark.asyncio
async def test_schema_patches_use_commit_true():
    """Patches must commit — uses get_cursor(commit=True)."""
    commit_values = []

    @contextmanager
    def capturing_ctx(commit=False):
        commit_values.append(commit)
        yield MagicMock()

    with patch("app.db.get_cursor", side_effect=capturing_ctx):
        await _run_ensure_schema()

    assert all(v is True for v in commit_values)


@pytest.mark.asyncio
async def test_schema_patch_success_logged(caplog):
    """Successful patch run logged at INFO."""
    cursor = MagicMock()
    with patch("app.db.get_cursor", side_effect=_cursor_ctx(cursor)), \
         caplog.at_level(logging.INFO, logger="app.main"):
        await _run_ensure_schema()

    assert any("startup_ensure_schema" in r.message for r in caplog.records)
    assert any("present" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_schema_patch_failure_logged_does_not_raise(caplog):
    """DB error is logged at ERROR; startup_ensure_schema does not raise."""
    with patch("app.db.get_cursor", side_effect=_failing_ctx(Exception("db down"))), \
         caplog.at_level(logging.ERROR, logger="app.main"):
        await _run_ensure_schema()   # must not raise

    assert any("startup_ensure_schema failed" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_ensure_schema_runs_before_migrations():
    """lifespan calls ensure_schema then run_migrations in order."""
    call_order = []

    async def fake_ensure(_=None):
        call_order.append("ensure")

    async def fake_migrations(_=None):
        call_order.append("migrations")

    with patch("app.main.startup_ensure_schema", side_effect=fake_ensure), \
         patch("app.main.startup_run_migrations", side_effect=fake_migrations):
        from app.main import lifespan, app as _app
        async with lifespan(_app):
            pass

    assert call_order == ["ensure", "migrations"]
