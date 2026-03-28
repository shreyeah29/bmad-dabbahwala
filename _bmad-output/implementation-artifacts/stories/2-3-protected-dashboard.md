# Story 2.3 — Protected Dashboard

**Epic:** E02 Auth & Dashboard
**Status:** done
**Created:** 2026-03-28

---

## What to build

`GET /dashboard` serves `app/dashboard.html` as HTMLResponse. Unauthenticated requests redirect to `/login`.

## Files created / modified

- `app/dashboard.html` — new: marketing ops dashboard UI with sign-out link
- `app/auth.py` — added `GET /dashboard` endpoint
- `tests/test_dashboard.py` — new: 5 tests

## Acceptance Criteria

- [x] Authenticated `@dabbahwala.com` users see the dashboard HTML
- [x] Unauthenticated requests redirect to `/login`
- [x] Stale/unknown session cookie redirects to `/login`
- [x] Dashboard HTML is served as HTMLResponse
- [x] All tests pass
