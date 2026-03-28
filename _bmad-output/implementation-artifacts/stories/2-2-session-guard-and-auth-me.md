# Story 2.2 — Session Guard & Auth Me

**Epic:** E02 Auth & Dashboard
**Status:** done
**Created:** 2026-03-28

---

## What to build

- `get_current_user(request)` — returns session dict or None (already in app/auth.py from 2.1)
- `GET /auth/me` — returns `{"email": ..., "name": ...}` for authenticated users, 401 otherwise

## Files modified

- `app/auth.py` — added `GET /auth/me` endpoint
- `tests/test_session_guard.py` — new: 7 tests

## Acceptance Criteria

- [x] `get_current_user()` returns user dict or None
- [x] `GET /auth/me` returns `{"email": ..., "name": ...}` for authenticated users
- [x] Returns 401 for unauthenticated requests
- [x] Domain restriction configurable via `ALLOWED_DOMAIN` env var (default `dabbahwala.com`)
- [x] All tests pass
