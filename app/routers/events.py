import logging
from typing import Any, Dict

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.db import get_cursor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/events", tags=["events"])

VALID_EVENT_TYPES = {
    "order_placed",
    "order_delivered",
    "order_cancelled",
    "sms_sent",
    "sms_received",
    "email_sent",
    "email_opened",
    "email_clicked",
    "call_made",
    "feedback_received",
}


class IngestEventRequest(BaseModel):
    contact_id: int
    event_type: str
    metadata: Dict[str, Any] = {}


@router.post("/ingest")
def ingest_event(req: IngestEventRequest):
    if req.event_type not in VALID_EVENT_TYPES:
        return JSONResponse(
            status_code=422,
            content={
                "detail": f"Invalid event_type '{req.event_type}'. "
                          f"Must be one of: {sorted(VALID_EVENT_TYPES)}"
            },
        )

    import json as _json
    with get_cursor(commit=True) as cur:
        cur.execute(
            "SELECT dabbahwala.ingest_event(%s, %s, %s) AS event_id",
            (req.contact_id, req.event_type, _json.dumps(req.metadata)),
        )
        row = cur.fetchone()
        event_id = row["event_id"]

    logger.debug(
        "Event ingested contact_id=%s event_type=%s event_id=%s",
        req.contact_id, req.event_type, event_id,
    )
    return {"status": "ok", "event_id": event_id}
