import logging
import time

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.db import get_cursor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/lifecycle", tags=["lifecycle"])


@router.post("/run")
def run_lifecycle():
    start = time.time()
    try:
        with get_cursor(commit=True) as cur:
            cur.execute("SELECT dabbahwala.run_lifecycle_cycle() AS result")
            result = cur.fetchone()["result"]

            cur.execute("""
                SELECT lifecycle_segment::TEXT AS segment, COUNT(*) AS count
                FROM dabbahwala.contacts
                WHERE opted_out = FALSE
                GROUP BY lifecycle_segment
            """)
            segments = {row["segment"]: row["count"] for row in cur.fetchall()}

    except Exception as exc:
        logger.error("Lifecycle cycle failed: %s", exc)
        return JSONResponse(status_code=500, content={"detail": str(exc)})

    duration_ms = int((time.time() - start) * 1000)
    transitions = result.get("updated", 0) if isinstance(result, dict) else 0

    logger.info(
        "Lifecycle cycle complete transitions=%s duration_ms=%s",
        transitions, duration_ms,
    )

    return {
        "transitions": transitions,
        "duration_ms": duration_ms,
        "segments": segments,
        "cycle_ran_at": result.get("cycle_ran_at") if isinstance(result, dict) else None,
    }
