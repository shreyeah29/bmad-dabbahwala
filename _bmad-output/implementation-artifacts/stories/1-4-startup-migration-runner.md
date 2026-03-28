# Story 1.4 — Startup Migration Runner

**Epic:** E01 Platform Bootstrap
**Status:** done
**Created:** 2026-03-28

---

## What to build

A FastAPI startup event that auto-applies SQL migrations from `migrations/*.sql` on every deploy.

Logic:
1. Create `dabbahwala.schema_migrations (filename TEXT PRIMARY KEY, applied_at TIMESTAMPTZ)` if not exists
2. Glob `migrations/*.sql` sorted ascending (001_ before 002_)
3. For each file: check `schema_migrations` — skip if already applied
4. Apply file SQL; on success insert filename into `schema_migrations`
5. On `DuplicateTable / DuplicateObject / UniqueViolation` error: backfill tracker (migration ran before tracker existed) — count as skipped
6. On any other error: log ERROR, count as failed, continue to next file (don't abort)
7. Log final summary: `applied=N skipped=N failed=N`

## Files to update

- `app/main.py` — add `startup_run_migrations` event handler
- `migrations/` — create directory (empty for now; real SQL added in E04)

## Files to create

- `tests/test_startup_migrations.py`
- `migrations/.gitkeep`

## Acceptance Criteria

- [ ] `schema_migrations` table created if absent
- [ ] Files applied in sorted order (001 before 002)
- [ ] Already-applied files skipped without error
- [ ] SQL applied and filename recorded atomically
- [ ] DuplicateTable/Object/UniqueViolation → backfill + skip (not fail)
- [ ] Any other error → logged, counted as failed, next file continues
- [ ] Final log: `applied=N skipped=N failed=N`
- [ ] No migration files → warning logged, graceful return
- [ ] All tests pass with mocked DB

## Tests to write

`tests/test_startup_migrations.py`:
- No migration files → warning, no DB calls
- Already-applied file → skipped
- New file → applied and recorded
- DuplicateTable error → backfilled, counted as skipped
- Unknown error → logged as failed, continues to next file
- Files applied in sorted order
