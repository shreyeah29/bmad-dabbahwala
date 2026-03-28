# Story 3.1 — Credentials Bootstrap Endpoint

**Epic:** E03 Credentials & Internal Services
**Status:** done
**Created:** 2026-03-28

---

## What to build

`GET /api/credentials/` — returns all runtime API keys as JSON. Used by n8n workflows to fetch keys at startup without hardcoding secrets.

Auth: `X-Admin-Secret` header compared to `ADMIN_SECRET` env var. Returns 403 if missing or wrong.

## Files created / modified

- `app/routers/__init__.py` — new: empty package init
- `app/routers/credentials.py` — new: credentials router
- `app/main.py` — added: `app.include_router(credentials_router)`
- `tests/test_credentials.py` — new: 7 tests

## Acceptance Criteria

- [x] Returns 403 if `X-Admin-Secret` header missing or wrong
- [x] Returns JSON object with all configured API keys
- [x] Values read from settings at request time (not cached)
- [x] Logged at INFO on each call (redacted — shows set/unset only)
- [x] All tests pass
