import os
import pytest
from unittest.mock import patch, MagicMock, call
from contextlib import contextmanager


# ── helpers ──────────────────────────────────────────────────────────────────

def _cursor_ctx(cursor):
    """Wrap a mock cursor in a context manager."""
    @contextmanager
    def _ctx(commit=False):
        yield cursor
    return _ctx


def _failing_ctx(exc):
    """Context manager that raises on enter."""
    @contextmanager
    def _ctx(commit=False):
        raise exc
        yield  # noqa: unreachable
    return _ctx


async def _run_migrations():
    """Import and call the startup handler directly."""
    from app.main import startup_run_migrations
    await startup_run_migrations()


# ── tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_no_migration_files_logs_warning_and_returns(tmp_path, caplog):
    """No .sql files → warning logged, no DB calls."""
    import logging
    cursor = MagicMock()
    with patch("app.db.get_cursor", side_effect=_cursor_ctx(cursor)), \
         patch("glob.glob", return_value=[]), \
         caplog.at_level(logging.WARNING, logger="app.main"):
        await _run_migrations()

    assert any("no migration files found" in r.message for r in caplog.records)
    cursor.execute.assert_not_called()


@pytest.mark.asyncio
async def test_already_applied_file_is_skipped(tmp_path):
    """File already in schema_migrations → skipped, not re-executed."""
    sql_file = tmp_path / "001_test.sql"
    sql_file.write_text("CREATE TABLE t (id INT);")

    call_count = 0

    @contextmanager
    def smart_cursor(commit=False):
        nonlocal call_count
        cur = MagicMock()
        call_count += 1
        if call_count == 1:
            # CREATE TABLE schema_migrations
            pass
        elif call_count == 2:
            # SELECT 1 FROM schema_migrations — return a row (already applied)
            cur.fetchone.return_value = {"filename": "001_test.sql"}
        yield cur

    with patch("app.db.get_cursor", side_effect=smart_cursor), \
         patch("glob.glob", return_value=[str(sql_file)]):
        await _run_migrations()

    # SQL file content must NOT be executed
    # (call_count == 2 means only tracker create + check happened)
    assert call_count == 2


@pytest.mark.asyncio
async def test_new_file_is_applied_and_recorded(tmp_path, caplog):
    """New migration file → SQL executed, filename inserted into tracker."""
    import logging
    sql_file = tmp_path / "001_init.sql"
    sql_file.write_text("CREATE TABLE foo (id INT);")

    executions = []

    @contextmanager
    def smart_cursor(commit=False):
        cur = MagicMock()
        cur.fetchone.return_value = None  # not yet applied
        cur.execute.side_effect = lambda sql, *a: executions.append(sql.strip())
        yield cur

    with patch("app.db.get_cursor", side_effect=smart_cursor), \
         patch("glob.glob", return_value=[str(sql_file)]), \
         caplog.at_level(logging.INFO, logger="app.main"):
        await _run_migrations()

    # The file SQL was executed
    assert any("CREATE TABLE foo" in s for s in executions), "migration SQL not executed"
    # The tracker INSERT was executed
    assert any("INSERT INTO dabbahwala.schema_migrations" in s for s in executions)
    assert any("APPLIED 001_init.sql" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_duplicate_table_error_backfills_and_skips(tmp_path, caplog):
    """DuplicateTable on apply → backfill tracker, count as skipped not failed."""
    import logging
    import psycopg2.errors as pgerr

    sql_file = tmp_path / "001_dup.sql"
    sql_file.write_text("CREATE TABLE already_exists (id INT);")

    call_n = 0

    @contextmanager
    def smart_cursor(commit=False):
        nonlocal call_n
        call_n += 1
        cur = MagicMock()
        if call_n == 1:
            # schema_migrations create — ok
            pass
        elif call_n == 2:
            # check applied — not yet
            cur.fetchone.return_value = None
        elif call_n == 3:
            # apply migration — raise DuplicateTable
            cur.execute.side_effect = pgerr.DuplicateTable("table exists")
        elif call_n == 4:
            # backfill insert — ok
            pass
        yield cur

    with patch("app.db.get_cursor", side_effect=smart_cursor), \
         patch("glob.glob", return_value=[str(sql_file)]), \
         caplog.at_level(logging.INFO, logger="app.main"):
        await _run_migrations()

    assert any("BACKFILLED" in r.message for r in caplog.records)
    assert not any("FAILED" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_unknown_error_logged_as_failed_continues(tmp_path, caplog):
    """Unknown error on apply → logged as FAILED, next file still processed."""
    import logging

    file1 = tmp_path / "001_bad.sql"
    file1.write_text("BAD SQL;")
    file2 = tmp_path / "002_good.sql"
    file2.write_text("CREATE TABLE good (id INT);")

    call_n = 0

    @contextmanager
    def smart_cursor(commit=False):
        nonlocal call_n
        call_n += 1
        cur = MagicMock()
        cur.fetchone.return_value = None
        if call_n == 3:
            cur.execute.side_effect = Exception("syntax error")
        yield cur

    with patch("app.db.get_cursor", side_effect=smart_cursor), \
         patch("glob.glob", return_value=[str(file1), str(file2)]), \
         caplog.at_level(logging.ERROR, logger="app.main"):
        await _run_migrations()

    assert any("FAILED 001_bad.sql" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_files_applied_in_sorted_order(tmp_path):
    """Migrations must run in ascending filename order."""
    f1 = tmp_path / "003_c.sql"
    f2 = tmp_path / "001_a.sql"
    f3 = tmp_path / "002_b.sql"
    for f in (f1, f2, f3):
        f.write_text("SELECT 1;")

    applied_order = []

    @contextmanager
    def smart_cursor(commit=False):
        cur = MagicMock()
        cur.fetchone.return_value = None
        def capture(sql, *args):
            if "INSERT INTO dabbahwala.schema_migrations" in sql and args:
                applied_order.append(args[0][0])
        cur.execute.side_effect = capture
        yield cur

    glob_result = [str(f1), str(f2), str(f3)]  # intentionally unsorted

    with patch("app.db.get_cursor", side_effect=smart_cursor), \
         patch("glob.glob", return_value=glob_result):
        await _run_migrations()

    assert applied_order == ["001_a.sql", "002_b.sql", "003_c.sql"]
