# Story 1.5 — Startup Schema Patches

**Epic:** E01 Platform Bootstrap
**Status:** done
**Created:** 2026-03-28

---

## What to build

A `startup_ensure_schema()` function called from `lifespan` **before** `startup_run_migrations()`.

Applies critical idempotent schema patches that fix gaps migrations may silently skip:
- `ALTER TABLE orders ADD COLUMN IF NOT EXISTS delivery_date DATE`
- `UPDATE orders SET delivery_date = order_date WHERE delivery_date IS NULL`
- `ALTER TABLE orders ADD COLUMN IF NOT EXISTS notes TEXT`

Rules:
- All patches use `IF NOT EXISTS` — always safe to re-run
- Each successful patch logged at INFO: `startup_ensure_schema — orders.delivery_date present`
- Failure logged at ERROR but must NOT raise — startup continues

## Files to update

- `app/main.py` — add `startup_ensure_schema()`, call it first in `lifespan`

## Files to create

- `tests/test_startup_schema_patches.py`

## Acceptance Criteria

- [ ] `startup_ensure_schema` runs before `startup_run_migrations` in lifespan
- [ ] All three SQL statements executed via `get_cursor(commit=True)`
- [ ] Success logged at INFO per patch
- [ ] Exception caught, logged at ERROR, startup continues (no raise)
- [ ] All tests pass with mocked DB
