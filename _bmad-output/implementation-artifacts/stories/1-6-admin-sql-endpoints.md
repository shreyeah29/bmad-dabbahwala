# Story 1.6 — Admin SQL Endpoints

**Epic:** E01 Platform Bootstrap
**Status:** done
**Created:** 2026-03-28

---

## What to build

Three admin endpoints on `app/main.py` (not a router — they live at root level):

| Endpoint | Auth | Purpose |
|----------|------|---------|
| `POST /admin/migrate/{n}` | `ADMIN_SECRET` query param | Run `migrations/{n:03d}_*.sql` |
| `POST /admin/query` | `ADMIN_SECRET` query param or JSON body | Read-only SQL, returns rows |
| `POST /admin/exec` | `ADMIN_SECRET` query param or JSON body | Write SQL (DDL/DML), commits |

Auth pattern: `secret` query param compared to `ADMIN_SECRET` env var. Return 403 if missing or wrong.

SQL accepted via query param `sql=` OR JSON body `{"secret": "...", "sql": "..."}`.

SQL logged at INFO truncated to 120 chars.

## Files to update

- `app/main.py` — add three endpoints

## Files to create

- `tests/test_admin_endpoints.py`

## Acceptance Criteria

- [ ] All three return 403 if secret wrong or missing
- [ ] `/migrate/{n}` globs `migrations/{n:03d}_*.sql`; returns 200 with migration filename or error if not found
- [ ] `/query` executes SQL read-only (commit=False); returns `{"status":"ok","rows":[...],"count":N}`
- [ ] `/exec` executes SQL with commit=True; returns `{"status":"ok","executed":true}`
- [ ] Both `/query` and `/exec` accept SQL via query param OR JSON body
- [ ] Empty SQL returns `{"error":"No SQL provided"}`
- [ ] SQL logged at INFO (truncated to 120 chars)
- [ ] All tests pass with mocked DB
