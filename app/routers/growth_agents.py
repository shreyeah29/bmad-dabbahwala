"""E23 — Growth, Goal & Competitor Agents"""
import logging
from typing import Optional
from datetime import date, timedelta

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.db import get_cursor
from app.services.llm_service import SONNET, call_claude

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/growth", tags=["growth"])


class GoalSetRequest(BaseModel):
    goal_type: str   # "monthly_orders", "monthly_revenue", "new_contacts", "churn_rate"
    target_value: float
    period: Optional[str] = None  # ISO date of period start, default current month


class CompetitorRequest(BaseModel):
    notes: str  # Field notes about competitor activity
    competitor_name: Optional[str] = None
    source: Optional[str] = None  # "field", "social", "customer"


# ── Story 23.1: Growth Agent ──────────────────────────────────────────────────

@router.get("/analysis")
def growth_analysis():
    """AI growth analysis: trends, opportunities, recommended actions."""
    today = date.today()
    month_start = str(today.replace(day=1))
    last_month_start = str((today.replace(day=1) - timedelta(days=1)).replace(day=1))
    last_month_end = str(today.replace(day=1))

    with get_cursor() as cur:
        cur.execute("""
            SELECT COUNT(*) AS new_contacts
            FROM dabbahwala.contacts WHERE created_at >= %s
        """, (month_start,))
        new_contacts = cur.fetchone()["new_contacts"]

        cur.execute("""
            SELECT COUNT(*) AS orders, COALESCE(SUM(total_amount), 0) AS revenue
            FROM dabbahwala.orders WHERE created_at >= %s
        """, (month_start,))
        this_month = cur.fetchone()

        cur.execute("""
            SELECT COUNT(*) AS orders, COALESCE(SUM(total_amount), 0) AS revenue
            FROM dabbahwala.orders WHERE created_at >= %s AND created_at < %s
        """, (last_month_start, last_month_end))
        last_month = cur.fetchone()

        cur.execute("""
            SELECT lifecycle_segment::TEXT AS segment, COUNT(*) AS count
            FROM dabbahwala.contacts WHERE opted_out = FALSE
            GROUP BY lifecycle_segment
        """)
        segments = {r["segment"]: r["count"] for r in cur.fetchall()}

    order_growth = (
        round((this_month["orders"] - last_month["orders"]) / max(last_month["orders"], 1) * 100, 1)
        if last_month["orders"] > 0 else 0
    )

    system = (
        "You are the growth strategist for DabbahWala, an Indian food delivery service in Atlanta. "
        "Analyze the metrics and provide 3-5 actionable growth recommendations. Be specific and data-driven."
    )
    messages = [{
        "role": "user",
        "content": (
            f"Current month metrics ({month_start} to today):\n"
            f"- New contacts: {new_contacts}\n"
            f"- Orders this month: {this_month['orders']} (${this_month['revenue']:.2f})\n"
            f"- Orders last month: {last_month['orders']} (${last_month['revenue']:.2f})\n"
            f"- Order growth: {order_growth}%\n"
            f"- Segment breakdown: {segments}\n\n"
            "Provide growth recommendations."
        )
    }]

    try:
        resp = call_claude(SONNET, system, messages, max_tokens=800)
        analysis = next((b.text for b in resp.content if b.type == "text"), "")
    except Exception as exc:
        return JSONResponse(status_code=500, content={"detail": str(exc)})

    return {
        "period": month_start,
        "metrics": {
            "new_contacts": new_contacts,
            "orders_this_month": this_month["orders"],
            "revenue_this_month": float(this_month["revenue"]),
            "order_growth_pct": order_growth,
            "segments": segments,
        },
        "analysis": analysis,
    }


# ── Story 23.2: Goal Agent ────────────────────────────────────────────────────

@router.post("/goals")
def set_goal(req: GoalSetRequest):
    period = req.period or str(date.today().replace(day=1))
    with get_cursor(commit=True) as cur:
        cur.execute("""
            INSERT INTO dabbahwala.growth_goals (goal_type, target_value, period)
            VALUES (%s, %s, %s)
            ON CONFLICT (goal_type, period) DO UPDATE SET target_value = EXCLUDED.target_value
            RETURNING id
        """, (req.goal_type, req.target_value, period))
        goal_id = cur.fetchone()["id"]
    return {"status": "ok", "goal_id": goal_id, "goal_type": req.goal_type, "period": period}


@router.get("/goals")
def list_goals(period: Optional[str] = None):
    with get_cursor() as cur:
        if period:
            cur.execute("""
                SELECT * FROM dabbahwala.growth_goals WHERE period = %s ORDER BY goal_type
            """, (period,))
        else:
            cur.execute("SELECT * FROM dabbahwala.growth_goals ORDER BY period DESC, goal_type")
        return {"goals": [dict(r) for r in cur.fetchall()]}


@router.get("/goals/progress")
def goal_progress():
    """Compare current metrics against active goals for the current month."""
    month_start = str(date.today().replace(day=1))

    with get_cursor() as cur:
        cur.execute("""
            SELECT * FROM dabbahwala.growth_goals WHERE period = %s
        """, (month_start,))
        goals = {r["goal_type"]: r for r in cur.fetchall()}

        cur.execute("""
            SELECT COUNT(*) AS new_contacts FROM dabbahwala.contacts WHERE created_at >= %s
        """, (month_start,))
        new_contacts = cur.fetchone()["new_contacts"]

        cur.execute("""
            SELECT COUNT(*) AS orders, COALESCE(SUM(total_amount), 0) AS revenue
            FROM dabbahwala.orders WHERE created_at >= %s
        """, (month_start,))
        orders_row = cur.fetchone()

    actuals = {
        "new_contacts": new_contacts,
        "monthly_orders": orders_row["orders"],
        "monthly_revenue": float(orders_row["revenue"]),
    }

    progress = []
    for goal_type, goal in goals.items():
        actual = actuals.get(goal_type, 0)
        target = float(goal["target_value"])
        pct = round(actual / target * 100, 1) if target > 0 else 0
        progress.append({
            "goal_type": goal_type,
            "target": target,
            "actual": actual,
            "progress_pct": pct,
            "on_track": pct >= 50,
        })

    return {"period": month_start, "progress": progress, "actuals": actuals}


# ── Story 23.3: Competitor Agent ──────────────────────────────────────────────

@router.post("/competitor-notes")
def log_competitor_note(req: CompetitorRequest):
    with get_cursor(commit=True) as cur:
        cur.execute("""
            INSERT INTO dabbahwala.competitor_notes (competitor_name, notes, source)
            VALUES (%s, %s, %s)
            RETURNING id
        """, (req.competitor_name or "Unknown", req.notes, req.source or "field"))
        note_id = cur.fetchone()["id"]
    return {"status": "ok", "note_id": note_id}


@router.get("/competitor-notes")
def list_competitor_notes(days: int = 30):
    with get_cursor() as cur:
        cur.execute("""
            SELECT * FROM dabbahwala.competitor_notes
            WHERE created_at >= NOW() - INTERVAL '1 day' * %s
            ORDER BY created_at DESC
        """, (days,))
        return {"notes": [dict(r) for r in cur.fetchall()]}


@router.post("/competitor-analysis")
def competitor_analysis():
    """AI analysis of competitor notes to generate strategic responses."""
    with get_cursor() as cur:
        cur.execute("""
            SELECT competitor_name, notes, source, created_at
            FROM dabbahwala.competitor_notes
            WHERE created_at >= NOW() - INTERVAL '30 days'
            ORDER BY created_at DESC LIMIT 20
        """)
        notes = [dict(r) for r in cur.fetchall()]

    if not notes:
        return {"analysis": "No competitor notes available in the last 30 days.", "notes": []}

    system = (
        "You are the competitive intelligence analyst for DabbahWala, Indian food delivery in Atlanta. "
        "Analyze these field notes about competitors and suggest 3-4 strategic responses. "
        "Focus on differentiation and retention tactics."
    )
    notes_text = "\n".join(
        f"[{n['created_at']}] {n['competitor_name']}: {n['notes']}" for n in notes
    )
    messages = [{"role": "user", "content": f"Competitor notes:\n{notes_text}\n\nStrategic recommendations:"}]

    try:
        resp = call_claude(SONNET, system, messages, max_tokens=700)
        analysis = next((b.text for b in resp.content if b.type == "text"), "")
        return {"analysis": analysis, "notes_analyzed": len(notes)}
    except Exception as exc:
        return JSONResponse(status_code=500, content={"detail": str(exc)})
