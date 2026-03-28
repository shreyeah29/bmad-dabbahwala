"""E24 — n8n Schedule Management & Test Harness"""
import logging
from typing import Optional

import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/n8n", tags=["n8n"])

_N8N_BASE = "https://digitalworker.dataskate.io"
_N8N_HEADERS = {"X-N8N-API-KEY": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJkMmFmN2JlMi1hMTYwLTRlZmUtYjFhOC0wMjlmM2U3OWZmMDkiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwiaWF0IjoxNzcxNTQ3NzAzfQ.lOtKLp-YEdulBGSOD62uKCPTJBHOl_-0rDy2qa79FqE"}


class WorkflowTriggerRequest(BaseModel):
    workflow_id: str
    payload: Optional[dict] = None


class ScheduleUpdateRequest(BaseModel):
    workflow_id: str
    cron_expression: Optional[str] = None
    active: Optional[bool] = None


# ── Story 24.1: n8n Workflow Management ───────────────────────────────────────

@router.get("/workflows")
async def list_workflows():
    """List all n8n workflows with their status."""
    async with httpx.AsyncClient(timeout=30) as http:
        resp = await http.get(f"{_N8N_BASE}/api/v1/workflows", headers=_N8N_HEADERS)
        if resp.status_code != 200:
            return JSONResponse(status_code=502, content={"detail": "n8n API error", "body": resp.text[:200]})
        data = resp.json()
        workflows = data.get("data", [])
        return {
            "count": len(workflows),
            "workflows": [
                {
                    "id": w["id"],
                    "name": w["name"],
                    "active": w.get("active", False),
                    "updatedAt": w.get("updatedAt"),
                }
                for w in workflows
            ]
        }


@router.get("/workflows/{workflow_id}")
async def get_workflow(workflow_id: str):
    async with httpx.AsyncClient(timeout=30) as http:
        resp = await http.get(f"{_N8N_BASE}/api/v1/workflows/{workflow_id}", headers=_N8N_HEADERS)
        if resp.status_code != 200:
            return JSONResponse(status_code=resp.status_code, content={"detail": resp.text[:200]})
        return resp.json()


@router.post("/workflows/{workflow_id}/activate")
async def activate_workflow(workflow_id: str):
    async with httpx.AsyncClient(timeout=30) as http:
        resp = await http.post(f"{_N8N_BASE}/api/v1/workflows/{workflow_id}/activate", headers=_N8N_HEADERS)
        if resp.status_code not in (200, 204):
            return JSONResponse(status_code=502, content={"detail": resp.text[:200]})
        return {"status": "ok", "workflow_id": workflow_id, "active": True}


@router.post("/workflows/{workflow_id}/deactivate")
async def deactivate_workflow(workflow_id: str):
    async with httpx.AsyncClient(timeout=30) as http:
        resp = await http.post(f"{_N8N_BASE}/api/v1/workflows/{workflow_id}/deactivate", headers=_N8N_HEADERS)
        if resp.status_code not in (200, 204):
            return JSONResponse(status_code=502, content={"detail": resp.text[:200]})
        return {"status": "ok", "workflow_id": workflow_id, "active": False}


# ── Story 24.2: Execution history & test harness ──────────────────────────────

@router.get("/executions")
async def list_executions(workflow_id: Optional[str] = None, limit: int = 20):
    """List recent n8n workflow executions."""
    params: dict = {"limit": limit}
    if workflow_id:
        params["workflowId"] = workflow_id

    async with httpx.AsyncClient(timeout=30) as http:
        resp = await http.get(f"{_N8N_BASE}/api/v1/executions", headers=_N8N_HEADERS, params=params)
        if resp.status_code != 200:
            return JSONResponse(status_code=502, content={"detail": resp.text[:200]})
        data = resp.json()
        executions = data.get("data", [])
        return {
            "count": len(executions),
            "executions": [
                {
                    "id": e["id"],
                    "workflowId": e.get("workflowId"),
                    "status": e.get("status"),
                    "startedAt": e.get("startedAt"),
                    "stoppedAt": e.get("stoppedAt"),
                    "mode": e.get("mode"),
                }
                for e in executions
            ]
        }


@router.get("/executions/{execution_id}")
async def get_execution(execution_id: str):
    async with httpx.AsyncClient(timeout=30) as http:
        resp = await http.get(f"{_N8N_BASE}/api/v1/executions/{execution_id}", headers=_N8N_HEADERS)
        if resp.status_code != 200:
            return JSONResponse(status_code=resp.status_code, content={"detail": resp.text[:200]})
        return resp.json()


@router.post("/test/trigger-pipeline")
async def test_trigger_pipeline(contact_id: int):
    """Test harness: trigger the full agent pipeline for a single contact via n8n."""
    async with httpx.AsyncClient(timeout=60) as http:
        resp = await http.post(
            f"http://localhost:8000/api/agents/cycle/run-for-contact",
            params={"contact_id": contact_id},
        )
        if resp.status_code != 200:
            return JSONResponse(status_code=resp.status_code, content=resp.json())
        return {"status": "ok", "contact_id": contact_id, "pipeline_result": resp.json()}


@router.get("/test/health")
async def n8n_health():
    """Check n8n instance health."""
    try:
        async with httpx.AsyncClient(timeout=10) as http:
            resp = await http.get(f"{_N8N_BASE}/healthz", headers=_N8N_HEADERS)
            return {"status": "ok" if resp.status_code == 200 else "degraded", "code": resp.status_code}
    except Exception as exc:
        return {"status": "unreachable", "error": str(exc)}
