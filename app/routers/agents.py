"""
Agent cycle endpoints — orchestrate the full AI pipeline.
Stories 7.14 (cycle endpoints), 7.15 (action queue + goals),
        7.16 (batch post-processing), 7.17 (report agents)
"""
import asyncio
import json
import logging
import time
from typing import Optional

import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.config import settings
from app.db import get_cursor
from app.services.agent_pipeline import run_full_pipeline

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agents", tags=["agents"])

MAX_BATCH = 200  # max contacts per batch run


# ── Context loader ────────────────────────────────────────────────────────────

def _load_contact_context(cur, contact_id: int) -> dict:
    cur.execute("SELECT * FROM dabbahwala.contacts WHERE id = %s", (contact_id,))
    contact = dict(cur.fetchone() or {})

    cur.execute("""
        SELECT * FROM dabbahwala.orders
        WHERE contact_id = %s ORDER BY created_at DESC LIMIT 10
    """, (contact_id,))
    past_orders = [dict(r) for r in cur.fetchall()]

    cur.execute("""
        SELECT * FROM dabbahwala.events
        WHERE contact_id = %s ORDER BY created_at DESC LIMIT 30
    """, (contact_id,))
    recent_events = [dict(r) for r in cur.fetchall()]

    cur.execute("""
        SELECT * FROM dabbahwala.telnyx_messages
        WHERE contact_id = %s ORDER BY created_at DESC LIMIT 20
    """, (contact_id,))
    comm_history = [dict(r) for r in cur.fetchall()]

    cur.execute("""
        SELECT * FROM dabbahwala.engagement_rollups WHERE contact_id = %s
    """, (contact_id,))
    rollup_row = cur.fetchone()
    rollup = dict(rollup_row) if rollup_row else {}

    cur.execute("""
        SELECT * FROM dabbahwala.menu_catalog
        WHERE is_available = TRUE AND discarded_date IS NULL
        LIMIT 30
    """)
    menu_items = [dict(r) for r in cur.fetchall()]

    cur.execute("""
        SELECT * FROM dabbahwala.action_queue
        WHERE contact_id = %s ORDER BY created_at DESC LIMIT 10
    """, (contact_id,))
    action_history = [dict(r) for r in cur.fetchall()]

    delivery_events = [e for e in recent_events if e.get("event_type") in
                       ("order_placed", "order_delivered", "order_cancelled")]

    return {
        "contact": contact,
        "past_orders": past_orders,
        "recent_events": recent_events,
        "comm_history": comm_history,
        "rollup": rollup,
        "menu_items": menu_items,
        "action_history": action_history,
        "delivery_events": delivery_events,
    }


def _store_pipeline_result(cur, contact_id: int, result: dict):
    layer1 = result.get("layer1", {})
    layer2 = result.get("layer2", {})
    orch = result.get("orchestrator", {})

    cur.execute("""
        INSERT INTO dabbahwala.contact_observations
            (contact_id, menu_signal, sentiment, intent, engagement_lvl, raw_outputs)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (
        contact_id,
        layer1.get("menu_signal", {}).get("top_picks", [""])[0] if layer1.get("menu_signal", {}).get("top_picks") else None,
        layer1.get("sentiment", {}).get("sentiment"),
        layer1.get("intent", {}).get("intent"),
        str(layer1.get("engagement", {}).get("engagement_score", 0)),
        json.dumps(layer1),
    ))

    cur.execute("""
        INSERT INTO dabbahwala.action_plans
            (contact_id, stage_signal, channel, offer, escalation_flag, raw_outputs)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (
        contact_id,
        layer2.get("stage", {}).get("recommended_stage"),
        layer2.get("channel", {}).get("recommended_channel"),
        layer2.get("offer", {}).get("suggested_copy"),
        layer2.get("escalation", {}).get("should_escalate", False),
        json.dumps(layer2),
    ))

    cur.execute("""
        INSERT INTO dabbahwala.orchestrator_log
            (contact_id, decision, reasoning, actions)
        VALUES (%s, %s, %s, %s)
    """, (
        contact_id,
        orch.get("chosen_action"),
        orch.get("reasoning"),
        json.dumps([orch.get("chosen_action")]),
    ))

    chosen_action = orch.get("chosen_action", "none")
    if chosen_action != "none":
        cur.execute("""
            INSERT INTO dabbahwala.action_queue
                (contact_id, action_type, payload, status)
            VALUES (%s, %s, %s, 'pending')
        """, (
            contact_id,
            chosen_action,
            json.dumps({"sms_copy": orch.get("sms_copy", ""), "reasoning": orch.get("reasoning", "")}),
        ))


# ── Story 7.14 — Cycle endpoints ──────────────────────────────────────────────

@router.post("/cycle/run")
async def run_cycle_single(contact_id: int):
    start = time.time()
    with get_cursor(commit=True) as cur:
        ctx = _load_contact_context(cur, contact_id)
        if not ctx["contact"]:
            return JSONResponse(status_code=404, content={"detail": "Contact not found"})

        result = await run_full_pipeline(ctx["contact"], ctx)
        _store_pipeline_result(cur, contact_id, result)

    duration_ms = int((time.time() - start) * 1000)
    return {
        "contact_id": contact_id,
        "chosen_action": result["chosen_action"],
        "duration_ms": duration_ms,
        "layer1_summary": {
            "sentiment": result["layer1"].get("sentiment", {}).get("sentiment"),
            "intent": result["layer1"].get("intent", {}).get("intent"),
            "engagement": result["layer1"].get("engagement", {}).get("engagement_score"),
        },
        "layer2_summary": {
            "stage": result["layer2"].get("stage", {}).get("recommended_stage"),
            "channel": result["layer2"].get("channel", {}).get("recommended_channel"),
            "escalate": result["layer2"].get("escalation", {}).get("should_escalate"),
        },
        "reasoning": result["orchestrator"].get("reasoning"),
    }


@router.post("/cycle/run-for-contact")
async def run_cycle_realtime(contact_id: int):
    """Real-time path — no batch limits, triggered on inbound SMS."""
    return await run_cycle_single(contact_id)


@router.post("/cycle/run-all")
async def run_cycle_batch(max_contacts: int = MAX_BATCH, segment: Optional[str] = None):
    start = time.time()
    results = []
    errors = []

    with get_cursor(commit=True) as cur:
        q = """
            SELECT id FROM dabbahwala.contacts
            WHERE opted_out = FALSE
              AND lifecycle_segment != 'optout'
              AND (cooling_until IS NULL OR cooling_until < NOW())
        """
        params = []
        if segment:
            q += " AND lifecycle_segment = %s"
            params.append(segment)
        q += " ORDER BY updated_at ASC LIMIT %s"
        params.append(max_contacts)

        cur.execute(q, params)
        contact_ids = [r["id"] for r in cur.fetchall()]

    for cid in contact_ids:
        try:
            with get_cursor(commit=True) as cur:
                ctx = _load_contact_context(cur, cid)
                result = await run_full_pipeline(ctx["contact"], ctx)
                _store_pipeline_result(cur, cid, result)
                results.append({"contact_id": cid, "chosen_action": result["chosen_action"]})
        except Exception as exc:
            logger.error("Batch cycle failed contact_id=%s: %s", cid, exc)
            errors.append({"contact_id": cid, "error": str(exc)})

    await _post_process_batch(results)

    return {
        "processed": len(results),
        "errors": len(errors),
        "duration_ms": int((time.time() - start) * 1000),
        "summary": {
            "send_sms": sum(1 for r in results if r["chosen_action"] == "send_sms"),
            "move_campaign": sum(1 for r in results if r["chosen_action"] == "move_campaign"),
            "escalate_airtable": sum(1 for r in results if r["chosen_action"] == "escalate_airtable"),
            "none": sum(1 for r in results if r["chosen_action"] == "none"),
        },
    }


@router.post("/cycle/run-all-lapsed")
async def run_cycle_lapsed(max_contacts: int = 100):
    return await run_cycle_batch(max_contacts=max_contacts, segment="lapsed_customer")


@router.post("/cycle/run-daily-sweep")
async def run_daily_sweep():
    start = time.time()
    lifecycle_result = None
    cycle_result = None

    try:
        from app.routers.lifecycle import run_lifecycle
        lifecycle_result = run_lifecycle()
    except Exception as exc:
        logger.error("Daily sweep lifecycle failed: %s", exc)

    try:
        cycle_result = await run_cycle_batch(max_contacts=MAX_BATCH)
    except Exception as exc:
        logger.error("Daily sweep agent cycle failed: %s", exc)

    return {
        "lifecycle": lifecycle_result,
        "agent_cycle": cycle_result,
        "duration_ms": int((time.time() - start) * 1000),
    }


# ── Story 7.16 — Batch post-processing ───────────────────────────────────────

async def _post_process_batch(results: list):
    move_campaign_ids = [r["contact_id"] for r in results if r["chosen_action"] == "move_campaign"]
    escalate_ids = [r["contact_id"] for r in results if r["chosen_action"] == "escalate_airtable"]

    if move_campaign_ids:
        await _push_to_instantly(move_campaign_ids)

    if escalate_ids:
        await _create_airtable_tasks(escalate_ids)

    if move_campaign_ids:
        await _send_campaign_digest(len(move_campaign_ids))


async def _push_to_instantly(contact_ids: list):
    if not settings.instantly_api_key:
        logger.warning("Instantly API key not set — skipping campaign push")
        return

    with get_cursor() as cur:
        for cid in contact_ids:
            try:
                cur.execute("""
                    SELECT c.email, c.name, cr.instantly_campaign_id
                    FROM dabbahwala.contacts c
                    JOIN dabbahwala.campaign_routing cr ON cr.lifecycle_segment = c.lifecycle_segment
                    WHERE c.id = %s
                """, (cid,))
                row = cur.fetchone()
                if not row or not row["instantly_campaign_id"]:
                    continue

                async with httpx.AsyncClient() as http:
                    await http.post(
                        "https://api.instantly.ai/api/v1/lead/add",
                        headers={"Authorization": f"Bearer {settings.instantly_api_key}"},
                        json={
                            "api_key": settings.instantly_api_key,
                            "campaign_id": row["instantly_campaign_id"],
                            "leads": [{"email": row["email"], "first_name": (row["name"] or "").split()[0]}],
                        },
                    )
                logger.info("Pushed contact_id=%s to Instantly", cid)
            except Exception as exc:
                logger.error("Instantly push failed contact_id=%s: %s", cid, exc)


async def _create_airtable_tasks(contact_ids: list):
    if not settings.airtable_api_key:
        logger.warning("Airtable API key not set — skipping task creation")
        return

    with get_cursor() as cur:
        for cid in contact_ids:
            try:
                cur.execute("SELECT email, name, phone FROM dabbahwala.contacts WHERE id = %s", (cid,))
                row = cur.fetchone()
                if not row:
                    continue

                async with httpx.AsyncClient() as http:
                    await http.post(
                        f"https://api.airtable.com/v0/{settings.airtable_base_id}/Field%20Sales%20Tasks",
                        headers={
                            "Authorization": f"Bearer {settings.airtable_api_key}",
                            "Content-Type": "application/json",
                        },
                        json={"fields": {
                            "Contact Email": row["email"],
                            "Contact Name": row["name"] or "",
                            "Phone": row["phone"] or "",
                            "Status": "Pending",
                            "Source": "AI Escalation",
                        }},
                    )
                logger.info("Airtable task created for contact_id=%s", cid)
            except Exception as exc:
                logger.error("Airtable task failed contact_id=%s: %s", cid, exc)


async def _send_campaign_digest(count: int):
    try:
        async with httpx.AsyncClient() as http:
            await http.post(
                "http://localhost:8000/api/internal/send-email",
                json={
                    "to": f"support@{settings.allowed_domain}",
                    "subject": f"DabbahWala: {count} campaign moves queued",
                    "body_text": f"{count} contacts were moved to new campaigns in the last AI cycle.",
                },
            )
    except Exception as exc:
        logger.error("Campaign digest email failed: %s", exc)


# ── Story 7.15 — Action Queue & Goals ────────────────────────────────────────

@router.get("/action-queue/pending")
def get_pending_actions():
    with get_cursor() as cur:
        cur.execute("""
            SELECT aq.id, aq.contact_id, c.email, aq.action_type::TEXT AS action_type,
                   aq.payload, aq.status, aq.created_at, aq.scheduled_for
            FROM dabbahwala.action_queue aq
            JOIN dabbahwala.contacts c ON c.id = aq.contact_id
            WHERE aq.status = 'pending'
            ORDER BY aq.created_at ASC
            LIMIT 500
        """)
        rows = [dict(r) for r in cur.fetchall()]
    return {"actions": rows, "count": len(rows)}


@router.post("/action-queue/{action_id}/done")
def mark_action_done(action_id: int):
    with get_cursor(commit=True) as cur:
        cur.execute("""
            UPDATE dabbahwala.action_queue
            SET status = 'done', executed_at = NOW()
            WHERE id = %s AND status IN ('pending', 'executing')
        """, (action_id,))
        if cur.rowcount == 0:
            return JSONResponse(status_code=404, content={"detail": "Action not found or already completed"})
    return {"status": "ok", "action_id": action_id}


class GoalRequest(BaseModel):
    contact_id: int
    goal_type: str
    goal_data: dict = {}


@router.post("/goals")
def upsert_goal(req: GoalRequest):
    valid_goals = {"convert_to_order", "retain", "reactivate"}
    if req.goal_type not in valid_goals:
        return JSONResponse(status_code=422, content={"detail": f"goal_type must be one of {sorted(valid_goals)}"})

    with get_cursor(commit=True) as cur:
        cur.execute("""
            INSERT INTO dabbahwala.customer_goals (contact_id, goal_type, goal_data)
            VALUES (%s, %s, %s)
            ON CONFLICT DO NOTHING
        """, (req.contact_id, req.goal_type, json.dumps(req.goal_data)))
        cur.execute("""
            UPDATE dabbahwala.customer_goals
            SET goal_data = %s, updated_at = NOW()
            WHERE contact_id = %s AND goal_type = %s
        """, (json.dumps(req.goal_data), req.contact_id, req.goal_type))

    return {"status": "ok", "contact_id": req.contact_id, "goal_type": req.goal_type}


# ── Story 7.17 — Report agents ────────────────────────────────────────────────

@router.post("/report/activity")
async def generate_activity_report():
    from app.services.llm_service import SONNET, call_claude

    with get_cursor() as cur:
        cur.execute("SELECT dabbahwala.generate_daily_report() AS report")
        report_data = cur.fetchone()["report"]

    system = "You are a marketing analyst for DabbahWala. Generate a concise HTML activity report."
    messages = [{"role": "user", "content": (
        f"Generate an HTML email report for today's marketing activity:\n{json.dumps(report_data, indent=2)}\n\n"
        "Include: orders, new contacts, SMS activity, email performance. Return HTML only."
    )}]

    try:
        resp = call_claude(SONNET, system, messages, max_tokens=2048)
        html = next((b.text for b in resp.content if b.type == "text"), "<p>Report generation failed</p>")
        return {"status": "ok", "html": html, "report_data": report_data}
    except Exception as exc:
        logger.error("Activity report failed: %s", exc)
        return JSONResponse(status_code=500, content={"detail": str(exc)})


@router.post("/report/outcome")
async def generate_outcome_report():
    from app.services.llm_service import SONNET, call_claude

    with get_cursor() as cur:
        cur.execute("""
            SELECT action_type::TEXT, COUNT(*) as count, COUNT(*) FILTER (WHERE status='done') as done
            FROM dabbahwala.action_queue
            WHERE created_at >= NOW() - INTERVAL '24 hours'
            GROUP BY action_type
        """)
        action_summary = [dict(r) for r in cur.fetchall()]

        cur.execute("""
            SELECT COUNT(*) AS converted FROM dabbahwala.opportunities
            WHERE status = 'actioned' AND actioned_at >= NOW() - INTERVAL '24 hours'
        """)
        conversions = cur.fetchone()["converted"]

    system = "You are a marketing analyst for DabbahWala. Generate a concise HTML outcome report."
    messages = [{"role": "user", "content": (
        f"AI actions taken today:\n{json.dumps(action_summary, indent=2)}\n"
        f"Conversions attributed: {conversions}\n\n"
        "Generate an HTML email report covering AI actions taken and conversion attributions. Return HTML only."
    )}]

    try:
        resp = call_claude(SONNET, system, messages, max_tokens=2048)
        html = next((b.text for b in resp.content if b.type == "text"), "<p>Report generation failed</p>")
        return {"status": "ok", "html": html}
    except Exception as exc:
        logger.error("Outcome report failed: %s", exc)
        return JSONResponse(status_code=500, content={"detail": str(exc)})
