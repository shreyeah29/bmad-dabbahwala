# Story 3.2 — SMTP Email Proxy

**Epic:** E03 Credentials & Internal Services
**Status:** done
**Created:** 2026-03-28

---

## What to build

`POST /api/internal/send-email` — sends email via SMTP. Used by n8n for report delivery and operational alerts.

## Files created / modified

- `app/routers/internal.py` — new: internal router with send-email endpoint
- `app/main.py` — added: `app.include_router(internal_router)`
- `tests/test_smtp.py` — new: 6 tests

## Acceptance Criteria

- [x] Sends email using `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD` env vars
- [x] Accepts both HTML and plain text body
- [x] Returns `{"status":"ok"}` on success
- [x] Returns 500 with error detail on SMTP failure
- [x] `REPORT_EMAIL_TO` used as default recipient if `to` not specified
- [x] All tests pass
