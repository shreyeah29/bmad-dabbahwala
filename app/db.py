import os
import logging
from contextlib import contextmanager

import psycopg2
import psycopg2.pool
import psycopg2.extras

logger = logging.getLogger(__name__)

_pool: psycopg2.pool.SimpleConnectionPool | None = None


def _get_pool() -> psycopg2.pool.SimpleConnectionPool:
    global _pool
    if _pool is None:
        database_url = os.environ["DATABASE_URL"]
        # Append search_path so every connection lands in the dabbahwala schema
        if "?" in database_url:
            database_url += "&options=-csearch_path%3Ddabbahwala"
        else:
            database_url += "?options=-csearch_path%3Ddabbahwala"
        _pool = psycopg2.pool.SimpleConnectionPool(1, 10, dsn=database_url)
        logger.info("DB connection pool created (min=1 max=10)")
    return _pool


@contextmanager
def get_cursor(commit: bool = False):
    """
    Yield a RealDictCursor borrowed from the connection pool.

    - commit=True  → commits on clean exit
    - commit=False → never commits (read-only queries)
    - Any exception → rollback + re-raise
    - Connection always returned to pool in finally
    """
    pool = _get_pool()
    conn = pool.getconn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            yield cur
        if commit:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)
