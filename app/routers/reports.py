"""E19 — Daily Reports API"""
import logging
from typing import Optional
from datetime import date, timedelta

from fastapi import APIRouter
from fastapi.responses import JSONResponse, HTMLResponse

from app.db import get_cursor
from app.services.llm_service import SONNET, call_claude

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reports", tags=["reports"])


# ── Story 19: Daily Reports ───────────────────────────────────────────────────

@router.get("/daily-summary")
def daily_summary(report_date: Optional[str] = None):
    """Return key metrics for a given date (default: today)."""
    target = report_date or str(date.today())
    next_day = str(date.fromisoformat(target) + timedelta(days=1))

    with get_cursor() as cur:
        cur.execute("""
            SELECT COUNT(*) AS new_contacts
            FROM dabbahwala.contacts
            WHERE created_at >= %s AND created_at < %s
        """, (target, next_day))
        new_contacts = cur.fetchone()["new_contacts"]

        cur.execute("""
            SELECT COUNT(*) AS orders, COALESCE(SUM(total_amount), 0) AS revenue
            FROM dabbahwala.orders
            WHERE created_at >= %s AND created_at < %s
        """, (target, next_day))
        order_row = cur.fetchone()

        cur.execute("""
            SELECT COUNT(*) AS messages_sent
            FROM dabbahwala.telnyx_messages
            WHERE direction = 'outbound' AND created_at >= %s AND created_at < %s
        """, (target, next_day))
        messages = cur.fetchone()["messages_sent"]

        cur.execute("""
            SELECT lifecycle_segment::TEXT AS segment, COUNT(*) AS count
            FROM dabbahwala.contacts
            WHERE opted_out = FALSE
            GROUP BY lifecycle_segment
        """)
        segment_breakdown = [dict(r) for r in cur.fetchall()]

        cur.execute("""
            SELECT COUNT(*) AS opted_out_today
            FROM dabbahwala.contacts
            WHERE opted_out = TRUE AND updated_at >= %s AND updated_at < %s
        """, (target, next_day))
        opted_out = cur.fetchone()["opted_out_today"]

    return {
        "date": target,
        "new_contacts": new_contacts,
        "orders": order_row["orders"],
        "revenue": float(order_row["revenue"]),
        "messages_sent": messages,
        "opted_out_today": opted_out,
        "segment_breakdown": segment_breakdown,
    }


@router.get("/weekly-summary")
def weekly_summary():
    """Return metrics for the last 7 days."""
    today = date.today()
    week_ago = str(today - timedelta(days=7))
    tomorrow = str(today + timedelta(days=1))

    with get_cursor() as cur:
        cur.execute("""
            SELECT COUNT(*) AS new_contacts
            FROM dabbahwala.contacts WHERE created_at >= %s
        """, (week_ago,))
        new_contacts = cur.fetchone()["new_contacts"]

        cur.execute("""
            SELECT COUNT(*) AS orders, COALESCE(SUM(total_amount), 0) AS revenue
            FROM dabbahwala.orders WHERE created_at >= %s
        """, (week_ago,))
        order_row = cur.fetchone()

        cur.execute("""
            SELECT COUNT(*) AS actions
            FROM dabbahwala.action_queue WHERE created_at >= %s
        """, (week_ago,))
        actions = cur.fetchone()["actions"]

        cur.execute("""
            SELECT event_type, COUNT(*) AS count
            FROM dabbahwala.events WHERE created_at >= %s
            GROUP BY event_type ORDER BY count DESC LIMIT 10
        """, (week_ago,))
        top_events = [dict(r) for r in cur.fetchall()]

    return {
        "period_start": week_ago,
        "period_end": str(today),
        "new_contacts": new_contacts,
        "orders": order_row["orders"],
        "revenue": float(order_row["revenue"]),
        "actions_queued": actions,
        "top_events": top_events,
    }


@router.post("/ai-narrative")
def ai_narrative_report(report_date: Optional[str] = None):
    """Generate an AI narrative summary of today's marketing activity."""
    summary = daily_summary(report_date)

    system = (
        "You are the marketing operations analyst for DabbahWala, an Indian food delivery service in Atlanta. "
        "Write a concise daily report (3-4 sentences) summarizing the marketing metrics provided. "
        "Be direct and highlight key wins or concerns."
    )
    messages = [{
        "role": "user",
        "content": (
            f"Here are today's metrics for {summary['date']}:\n"
            f"- New contacts: {summary['new_contacts']}\n"
            f"- Orders: {summary['orders']} (Revenue: ${summary['revenue']:.2f})\n"
            f"- SMS sent: {summary['messages_sent']}\n"
            f"- Opted out today: {summary['opted_out_today']}\n"
            f"- Segment breakdown: {summary['segment_breakdown']}\n\n"
            "Write a brief executive summary."
        )
    }]

    try:
        resp = call_claude(SONNET, system, messages, max_tokens=512)
        narrative = next((b.text for b in resp.content if b.type == "text"), "")
        return {"date": summary["date"], "metrics": summary, "narrative": narrative}
    except Exception as exc:
        return JSONResponse(status_code=500, content={"detail": str(exc)})


@router.get("/campaign-performance")
def campaign_performance():
    with get_cursor() as cur:
        cur.execute("SELECT dabbahwala.get_campaign_performance() AS perf")
        return {"performance": cur.fetchone()["perf"]}


@router.get("/agent-activity")
def agent_activity(days: int = 7):
    since = str(date.today() - timedelta(days=days))
    with get_cursor() as cur:
        cur.execute("""
            SELECT
                COUNT(*) AS total_runs,
                COUNT(DISTINCT contact_id) AS unique_contacts,
                SUM(CASE WHEN action_taken != 'none' THEN 1 ELSE 0 END) AS actions_taken
            FROM dabbahwala.orchestrator_log
            WHERE created_at >= %s
        """, (since,))
        stats = dict(cur.fetchone())

        cur.execute("""
            SELECT action_taken, COUNT(*) AS count
            FROM dabbahwala.orchestrator_log
            WHERE created_at >= %s AND action_taken != 'none'
            GROUP BY action_taken
            ORDER BY count DESC
        """, (since,))
        breakdown = [dict(r) for r in cur.fetchall()]

    return {"since": since, "stats": stats, "action_breakdown": breakdown}
