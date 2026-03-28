# Epic 2: Auth & Dashboard

**Layer:** 0 — Foundation
**FRs:** FR-AUTH-01 to FR-AUTH-04
**Depends on:** E01
**Status:** backlog

## Goal
Google OAuth2 login restricted to `@dabbahwala.com` accounts. Serve a protected HTML marketing dashboard.

---

## Stories

### Story 2.1: Google OAuth2 Login Flow
Implement `GET /login` (HTML form), `GET /auth/google` (redirect to Google), `GET /auth/callback` (token exchange + session cookie), `GET /auth/logout`.

**Acceptance Criteria:**
- `/login` renders HTML login page
- `/auth/google` redirects to Google OAuth consent screen
- `/auth/callback` exchanges code for token; stores session
- `/auth/logout` clears session and redirects to `/login`
- Only `@dabbahwala.com` accounts allowed; others get 403

---

### Story 2.2: Session Guard & Auth Me
Implement `get_current_user(request)` helper used as auth guard; `GET /auth/me` returns current user info.

**Acceptance Criteria:**
- `get_current_user()` returns user dict or None
- `GET /auth/me` returns `{"email": ..., "name": ...}` for authenticated users
- Returns 401 for unauthenticated requests
- Domain restriction configurable via env var (default `dabbahwala.com`)

---

### Story 2.3: Protected Dashboard
`GET /dashboard` serves `app/dashboard.html`; redirects to `/login` if not authenticated.

**Acceptance Criteria:**
- Authenticated `@dabbahwala.com` users see the dashboard HTML
- Unauthenticated requests redirect to `/login`
- Dashboard HTML is served as HTMLResponse

---
