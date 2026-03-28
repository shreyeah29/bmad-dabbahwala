# Epic 1: Platform Bootstrap

**Layer:** 0 — Foundation
**FRs:** FR-PLAT-01 to FR-PLAT-09
**Depends on:** Nothing — this is the base
**Status:** backlog

## Goal
Set up the FastAPI application skeleton with structured logging, startup hooks, DB connection pool, global error handling, and admin SQL endpoints. Everything else builds on top of this.

---

## Stories

### Story 1.1: FastAPI App Skeleton with Structured Logging
Set up `app/main.py` with the FastAPI instance, request logging middleware (method, path, status, duration, client IP), and global exception handler returning `{"detail": ..., "type": ...}` on 500.

**Acceptance Criteria:**
- `uvicorn app.main:app` starts without errors
- Every request logs: method, path, status code, duration in ms, client IP
- Uncaught exceptions return JSON 500 with detail and type fields
- `LOG_LEVEL` env var controls verbosity (default INFO)

---

### Story 1.2: Database Connection Pool
Create `app/db.py` with `psycopg2` `SimpleConnectionPool` (min 1, max 10), `get_cursor(commit=bool)` context manager using `RealDictCursor`, and `search_path = dabbahwala` set at connect time.

**Acceptance Criteria:**
- `get_cursor()` returns a dict-style cursor
- `commit=True` commits on exit; `commit=False` rolls back on exception
- `search_path` is always `dabbahwala`
- Pool reuses connections across requests

---

### Story 1.3: Health Endpoint
Implement `GET /health` — executes `SELECT 1` against DB; returns `{"status":"ok","db":"connected"}` on success or 503 `{"status":"degraded","db":"<error>"}` on failure.

**Acceptance Criteria:**
- Returns 200 when DB is up
- Returns 503 when DB is unreachable
- No auth required

---

### Story 1.4: Startup Migration Runner
On startup, create `schema_migrations` table if not exists, then iterate all `migrations/*.sql` files in order; skip already-applied filenames; log applied/skipped/failed counts. Handle already-exists errors by backfilling the tracker.

**Acceptance Criteria:**
- `schema_migrations (filename TEXT PRIMARY KEY, applied_at TIMESTAMPTZ)` created if absent
- Each migration file applied exactly once
- Re-running on redeploy is safe (idempotent)
- Counts logged at startup: `applied=N skipped=N failed=N`

---

### Story 1.5: Startup Schema Patches
On startup, apply critical one-off schema patches idempotently (e.g. `ALTER TABLE orders ADD COLUMN IF NOT EXISTS delivery_date DATE`). Run before migration runner so base schema is always correct.

**Acceptance Criteria:**
- Patches use `ADD COLUMN IF NOT EXISTS` — safe to re-run
- Logged as `startup_ensure_schema — <table>.<col> present`
- Failure is logged but does not crash startup

---

### Story 1.6: Admin SQL Endpoints
Implement `POST /admin/migrate/{n}`, `POST /admin/query`, `POST /admin/exec` — all protected by `ADMIN_SECRET` env var. `query` is read-only; `exec` commits. Both accept SQL via query param or JSON body.

**Acceptance Criteria:**
- All three return 403 if `ADMIN_SECRET` missing or wrong
- `/migrate/{n}` finds and runs `migrations/{n:03d}_*.sql`
- `/query` returns `{"status":"ok","rows":[...],"count":N}`
- `/exec` returns `{"status":"ok","executed":true}`
- SQL logged at INFO (truncated to 120 chars)

---

### Story 1.7: App Configuration
Create `app/config.py` — loads all env vars with defaults, validates required vars on startup, exposes a `settings` object used across the app.

**Acceptance Criteria:**
- Missing required vars logged as ERROR on startup
- All env var names documented with purpose
- `settings.database_url`, `settings.admin_secret`, etc. accessible throughout app

---
