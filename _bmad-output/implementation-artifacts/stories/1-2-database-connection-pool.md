# Story 1.2 — Database Connection Pool

**Epic:** E01 Platform Bootstrap
**Status:** done
**Created:** 2026-03-28

---

## What to build

Create `app/db.py` — the single database access layer used by every router and service.

Requirements:
1. `psycopg2.pool.SimpleConnectionPool` — min 1, max 10 connections
2. Connection string from `DATABASE_URL` env var
3. `search_path = dabbahwala` applied on every connection via `options` param
4. `get_cursor(commit=True/False)` — context manager that:
   - Borrows a connection from the pool
   - Returns a `RealDictCursor` (rows as dicts, not tuples)
   - On clean exit: commits if `commit=True`
   - On exception: always rolls back, then re-raises
   - Always returns connection to pool in `finally`

## Files to create

- `app/db.py`

## Files to update

- `tests/test_main.py` — no changes needed
- `tests/test_db.py` — new test file

## Tech constraints

- `psycopg2-binary` (already in requirements.txt)
- Pool is a module-level singleton, initialised lazily on first use
- No real DB in tests — mock `psycopg2.pool.SimpleConnectionPool`

## Acceptance Criteria

- [ ] `get_cursor()` returns a `RealDictCursor`
- [ ] `commit=True` calls `connection.commit()` on clean exit
- [ ] Any exception triggers `connection.rollback()` before re-raise
- [ ] Connection always returned to pool (even on error)
- [ ] `search_path=dabbahwala` in connection options
- [ ] All tests pass with mocked pool

## Tests to write

`tests/test_db.py`:
- `get_cursor(commit=True)` commits on clean exit
- `get_cursor(commit=False)` does not commit
- Exception inside `with get_cursor()` triggers rollback and re-raises
- Connection is always returned to pool
