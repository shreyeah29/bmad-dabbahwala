# Story 1.7 — App Configuration

**Epic:** E01 Platform Bootstrap
**Status:** done
**Created:** 2026-03-28

---

## What to build

`app/config.py` — a single `Settings` object that loads all env vars at import time.

- Uses `pydantic-settings` (or plain Pydantic v2 with `model_validator`) to read from env
- Required vars: `DATABASE_URL`, `ANTHROPIC_API_KEY`, `TELNYX_API_KEY`, `AIRTABLE_API_KEY`, `AIRTABLE_BASE_ID`, `SHIPDAY_API_KEY`, `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`, `ADMIN_SECRET`
- Optional vars with defaults: `INSTANTLY_API_KEY=""`, `N8N_API_KEY=""`, `REPORT_EMAIL_TO="core@dabbahwala.com"`, `LOG_LEVEL="INFO"`, `ALLOWED_DOMAIN="dabbahwala.com"`
- Missing required vars logged as WARNING (not ERROR — app still starts, fails at runtime when key is first used)
- Module-level `settings` singleton imported everywhere

## Files to create

- `app/config.py`
- `tests/test_config.py`

## Acceptance Criteria

- [ ] `from app.config import settings` works
- [ ] `settings.database_url`, `settings.admin_secret`, `settings.anthropic_api_key` etc. all accessible
- [ ] Missing required vars produce a warning (logged), not a crash
- [ ] Optional vars fall back to their defaults when not set
- [ ] `settings.log_level` defaults to `"INFO"`
- [ ] `settings.report_email_to` defaults to `"core@dabbahwala.com"`
- [ ] All tests pass without real env vars
