# Story 2.1 — Google OAuth2 Login Flow

**Epic:** E02 Auth & Dashboard
**Status:** done
**Created:** 2026-03-28

---

## What to build

Google OAuth2 login restricted to `@dabbahwala.com` accounts.

- `GET /login` — HTML login page with "Sign in with Google" button
- `GET /auth/google` — redirect to Google OAuth consent screen
- `GET /auth/callback` — exchange code for token, verify domain, store session cookie
- `GET /auth/logout` — clear session and redirect to `/login`

Session stored in-memory dict (`_sessions`); session ID in httponly cookie.

## Files created / modified

- `app/auth.py` — new: APIRouter with all 4 routes + `get_current_user()` helper
- `app/config.py` — added: `google_client_id`, `google_client_secret`, `google_redirect_uri`
- `app/main.py` — added: `app.include_router(auth_router)`
- `tests/test_auth.py` — new: 13 tests

## Acceptance Criteria

- [x] `/login` renders HTML login page
- [x] `/auth/google` redirects to Google OAuth consent screen
- [x] `/auth/callback` exchanges code for token; stores session
- [x] `/auth/logout` clears session and redirects to `/login`
- [x] Only `@dabbahwala.com` accounts allowed; others get 403
- [x] All tests pass without real credentials
