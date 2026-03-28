# Story 1.3 — Health Endpoint

**Epic:** E01 Platform Bootstrap
**Status:** done
**Created:** 2026-03-28

---

## What to build

Add `GET /health` to `app/main.py`.

- Executes `SELECT 1` via `get_cursor()`
- Returns 200 `{"status": "ok", "db": "connected"}` when DB is up
- Returns 503 `{"status": "degraded", "db": "<error message>"}` when DB fails
- No authentication required
- Logs DB check at DEBUG level (not INFO — health checks are noisy)

## Files to update

- `app/main.py` — add the `/health` route

## Files to create

- `tests/test_health.py`

## Acceptance Criteria

- [ ] Returns 200 + `{"status":"ok","db":"connected"}` when DB reachable
- [ ] Returns 503 + `{"status":"degraded","db":"..."}` when DB unreachable
- [ ] No auth required
- [ ] DB check logged at DEBUG level
