import logging
import os
import time
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

# ---------------------------------------------------------------------------
# Structured logging — INFO by default, DEBUG when LOG_LEVEL=DEBUG
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)
logger.info("DabbahWala API starting — log_level=%s", os.environ.get("LOG_LEVEL", "INFO"))


async def startup_ensure_schema():
    """Apply critical idempotent schema patches before migrations run."""
    from app.db import get_cursor
    try:
        with get_cursor(commit=True) as cur:
            cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS delivery_date DATE")
            cur.execute(
                "UPDATE orders SET delivery_date = order_date WHERE delivery_date IS NULL"
            )
            cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS notes TEXT")
        logger.info("startup_ensure_schema — orders.delivery_date and notes present")
    except Exception as e:
        logger.error("startup_ensure_schema failed: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await startup_ensure_schema()
    await startup_run_migrations()
    yield


app = FastAPI(
    title="DabbahWala Marketing System",
    description="Lifecycle-driven marketing orchestration API",
    version="1.0.0",
    lifespan=lifespan,
)

from app.auth import router as auth_router  # noqa: E402
app.include_router(auth_router)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log every request: method, path, status code, duration ms, client IP."""
    start = time.time()
    response = await call_next(request)
    ms = int((time.time() - start) * 1000)
    logger.info(
        "HTTP %s %s → %d (%dms) client=%s",
        request.method,
        request.url.path,
        response.status_code,
        ms,
        request.client.host if request.client else "unknown",
    )
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(
        "Unhandled exception %s %s: %s [%s]",
        request.method,
        request.url.path,
        exc,
        type(exc).__name__,
        exc_info=True,
    )
    traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc), "type": type(exc).__name__},
    )


async def startup_run_migrations():
    """Apply all pending SQL migrations from migrations/ on startup."""
    import glob as _glob
    import psycopg2.errors as _pgerr
    from app.db import get_cursor

    migrations_dir = os.path.join(os.path.dirname(__file__), "..", "migrations")
    files = sorted(_glob.glob(os.path.join(migrations_dir, "*.sql")))

    if not files:
        logger.warning("startup_run_migrations — no migration files found at %s", migrations_dir)
        return

    # Ensure tracker table exists
    try:
        with get_cursor(commit=True) as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS dabbahwala.schema_migrations (
                    filename   TEXT PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
    except Exception as e:
        logger.error("startup_run_migrations — could not create schema_migrations: %s", e)
        return

    applied = skipped = failed = 0

    for path in files:
        filename = os.path.basename(path)

        # Check if already applied
        try:
            with get_cursor(commit=False) as cur:
                cur.execute(
                    "SELECT 1 FROM dabbahwala.schema_migrations WHERE filename = %s",
                    (filename,),
                )
                already = cur.fetchone()
        except Exception as e:
            logger.error("startup_run_migrations — could not check %s: %s", filename, e)
            failed += 1
            continue

        if already:
            skipped += 1
            continue

        # Apply migration
        try:
            with open(path) as f:
                sql = f.read()
            with get_cursor(commit=True) as cur:
                cur.execute(sql)
                cur.execute(
                    "INSERT INTO dabbahwala.schema_migrations (filename) VALUES (%s)"
                    " ON CONFLICT DO NOTHING",
                    (filename,),
                )
            logger.info("startup_run_migrations — APPLIED %s", filename)
            applied += 1
        except Exception as e:
            _already_exists = isinstance(
                e, (_pgerr.DuplicateTable, _pgerr.DuplicateObject, _pgerr.UniqueViolation)
            )
            if _already_exists:
                # Migration ran before tracker existed — backfill
                try:
                    with get_cursor(commit=True) as cur:
                        cur.execute(
                            "INSERT INTO dabbahwala.schema_migrations (filename) VALUES (%s)"
                            " ON CONFLICT DO NOTHING",
                            (filename,),
                        )
                except Exception:
                    pass
                logger.info("startup_run_migrations — BACKFILLED %s (already applied)", filename)
                skipped += 1
            else:
                logger.error("startup_run_migrations — FAILED %s: %s", filename, e)
                failed += 1

    logger.info(
        "startup_run_migrations — done: applied=%d skipped=%d failed=%d",
        applied, skipped, failed,
    )


@app.get("/health")
def health():
    logger.debug("Health check requested")
    try:
        from app.db import get_cursor
        with get_cursor(commit=False) as cur:
            cur.execute("SELECT 1")
        logger.debug("Health check OK — DB connected")
        return {"status": "ok", "db": "connected"}
    except Exception as e:
        logger.error("Health check FAILED — DB unreachable: %s", e)
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "db": str(e)},
        )


# ---------------------------------------------------------------------------
# Admin endpoints — protected by ADMIN_SECRET
# ---------------------------------------------------------------------------

def _check_admin_secret(secret: str) -> bool:
    admin_secret = os.environ.get("ADMIN_SECRET", "")
    return bool(admin_secret and secret == admin_secret)


@app.post("/admin/migrate/{migration_number}")
def run_migration(migration_number: int, secret: str = ""):
    """Run a specific migration file by number. Requires ADMIN_SECRET."""
    import glob
    from fastapi import HTTPException
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Forbidden")

    matches = glob.glob(f"migrations/{migration_number:03d}_*.sql")
    if not matches:
        return {"error": f"No migration file found for {migration_number:03d}"}

    migration_file = matches[0]
    logger.info("Admin migrate: running %s", migration_file)
    with open(migration_file) as f:
        sql = f.read()

    from app.db import get_cursor
    with get_cursor(commit=True) as cur:
        cur.execute(sql)

    return {"status": "ok", "migration": migration_file, "executed": True}


@app.post("/admin/query")
async def run_query(request: Request, secret: str = "", sql: str = ""):
    """Run a read-only SQL query. Accepts SQL via query param or JSON body."""
    from fastapi import HTTPException
    if not secret or not sql:
        try:
            body = await request.json()
            secret = body.get("secret", secret)
            sql = body.get("sql", sql)
        except Exception:
            pass

    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Forbidden")

    if not sql.strip():
        return {"error": "No SQL provided"}

    logger.info("Admin query: %.120s", sql.strip())
    from app.db import get_cursor
    with get_cursor(commit=False) as cur:
        cur.execute(sql)
        try:
            rows = cur.fetchall()
            return {"status": "ok", "rows": rows, "count": len(rows)}
        except Exception:
            return {"status": "ok", "rows": [], "count": 0}


@app.post("/admin/exec")
async def run_exec(request: Request, secret: str = "", sql: str = ""):
    """Run a DDL/DML SQL statement. Accepts SQL via query param or JSON body."""
    from fastapi import HTTPException
    if not secret or not sql:
        try:
            body = await request.json()
            secret = body.get("secret", secret)
            sql = body.get("sql", sql)
        except Exception:
            pass

    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Forbidden")

    if not sql.strip():
        return {"error": "No SQL provided"}

    logger.info("Admin exec: %.120s", sql.strip())
    from app.db import get_cursor
    with get_cursor(commit=True) as cur:
        cur.execute(sql)

    return {"status": "ok", "executed": True}
