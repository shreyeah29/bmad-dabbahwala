from unittest.mock import MagicMock, patch, call
import pytest


def _make_mock_pool():
    """Return a mock pool + mock connection wired together."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    # cursor() used as context manager
    mock_conn.cursor.return_value.__enter__ = lambda s: mock_cursor
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    mock_pool = MagicMock()
    mock_pool.getconn.return_value = mock_conn
    return mock_pool, mock_conn, mock_cursor


def test_get_cursor_commits_on_clean_exit():
    mock_pool, mock_conn, _ = _make_mock_pool()

    import app.db as db_module
    original = db_module._pool
    db_module._pool = mock_pool
    try:
        with db_module.get_cursor(commit=True):
            pass
        mock_conn.commit.assert_called_once()
        mock_conn.rollback.assert_not_called()
    finally:
        db_module._pool = original


def test_get_cursor_no_commit_when_commit_false():
    mock_pool, mock_conn, _ = _make_mock_pool()

    import app.db as db_module
    original = db_module._pool
    db_module._pool = mock_pool
    try:
        with db_module.get_cursor(commit=False):
            pass
        mock_conn.commit.assert_not_called()
        mock_conn.rollback.assert_not_called()
    finally:
        db_module._pool = original


def test_get_cursor_rollback_and_reraise_on_exception():
    mock_pool, mock_conn, _ = _make_mock_pool()

    import app.db as db_module
    original = db_module._pool
    db_module._pool = mock_pool
    try:
        with pytest.raises(ValueError, match="db error"):
            with db_module.get_cursor(commit=True):
                raise ValueError("db error")
        mock_conn.rollback.assert_called_once()
        mock_conn.commit.assert_not_called()
    finally:
        db_module._pool = original


def test_get_cursor_always_returns_connection_to_pool():
    mock_pool, mock_conn, _ = _make_mock_pool()

    import app.db as db_module
    original = db_module._pool
    db_module._pool = mock_pool
    try:
        # Clean exit
        with db_module.get_cursor():
            pass
        mock_pool.putconn.assert_called_once_with(mock_conn)
    finally:
        db_module._pool = original


def test_get_cursor_returns_connection_to_pool_even_on_error():
    mock_pool, mock_conn, _ = _make_mock_pool()

    import app.db as db_module
    original = db_module._pool
    db_module._pool = mock_pool
    try:
        with pytest.raises(RuntimeError):
            with db_module.get_cursor():
                raise RuntimeError("boom")
        mock_pool.putconn.assert_called_once_with(mock_conn)
    finally:
        db_module._pool = original


def test_get_cursor_yields_real_dict_cursor():
    mock_pool, mock_conn, mock_cursor = _make_mock_pool()

    import app.db as db_module
    original = db_module._pool
    db_module._pool = mock_pool
    try:
        with db_module.get_cursor() as cur:
            assert cur is mock_cursor
    finally:
        db_module._pool = original
