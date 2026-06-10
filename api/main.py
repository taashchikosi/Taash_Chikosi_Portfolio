"""FastAPI backend — REST + SSE bridge between the agent pipeline and the Next.js UI.

Endpoints (project plan §8):
    POST /api/runs                 → start a run (IDF + 12-month utility JSON)
    GET  /api/runs/{id}/events     → SSE stream of AgentEvent
    POST /api/runs/{id}/approve    → HITL approve / modify gate
    GET  /api/metrics              → dashboard data (stub until Langfuse export)
    GET  /health

Phase 2 swaps the stub agents for real ones — the event contract stays identical.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from agents import stubs
from agents.reviewer import review
from agents.supervisor import RunState

app = FastAPI(title="RetrofitGPT API", version="0.1.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

# In-memory run registry (Phase 2 → Postgres if persistence needed)
_RUNS: dict[str, dict[str, Any]] = {}


class UtilityIn(BaseModel):
    monthly_kwh: list[float] = Field(..., min_length=12, max_length=12)
    annual_cost_aud: float
    tariff_type: str = "single rate"


class RunIn(BaseModel):
    idf_path: str = "data/reference_buildings/RefBldgSmallOffice.idf"
    epw_path: str = "data/reference_buildings/weather/AUS_NSW_Sydney.epw"
    utility: UtilityIn


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "retrofitgpt-api", "version": "0.1.0"}


@app.post("/api/runs")
def create_run(body: RunIn) -> dict:
    run_id = uuid.uuid4().hex[:12]
    _RUNS[run_id] = {
        "queue": asyncio.Queue(),
        "state": RunState(
            run_id=run_id, idf_path=body.idf_path, epw_path=body.epw_path,
            raw_utility=body.utility.model_dump(), cycle_count=0,
        ),
        "approved": False,
        "status": "created",
    }
    return {"run_id": run_id, "status": "created"}


@app.get("/api/runs/{run_id}/events")
async def stream_events(run_id: str):
    run = _RUNS.get(run_id)
    if run is None:
        raise HTTPException(404, "unknown run_id")

    queue: asyncio.Queue = run["queue"]

    def emit(agent: str, status: str, payload: dict) -> None:
        queue.put_nowait({"agent": agent, "status": status, "payload": payload})

    run["state"]["emit"] = emit

    async def event_generator():
        # Drive the pipeline in the background, streaming events as they fire
        asyncio.create_task(_drive_pipeline(run))
        while True:
            event = await queue.get()
            yield {"data": json.dumps(event)}
            if event.get("status") in ("done", "failed", "human_review"):
                break

    return EventSourceResponse(event_generator())


@app.post("/api/runs/{run_id}/approve")
def approve(run_id: str, decision: dict) -> dict:
    run = _RUNS.get(run_id)
    if run is None:
        raise HTTPException(404, "unknown run_id")
    run["approved"] = decision.get("action", "approve") == "approve"
    event = run.get("approve_event")
    if event is not None:
        event.set()
    return {"run_id": run_id, "approved": run["approved"]}


@app.get("/api/metrics")
def metrics() -> dict:
    """Dashboard data. Stub until the Langfuse export is wired (Phase 3)."""
    return {
        "cost_per_run_aud": None, "p95_latency_ms": None,
        "eval_pass_rate": None, "guardrail_triggers": None,
        "router_breakdown": {"flash": 0.90, "pro": 0.08, "sonnet": 0.02},
        "note": "live metrics arrive in Phase 3 (Langfuse export)",
    }


async def _drive_pipeline(run: dict) -> None:
    """Run agents in order, pausing at the HITL gate before sim_runner."""
    state: RunState = run["state"]
    emit = state["emit"]
    try:
        state = stubs.retriever(state)
        state = stubs.modeler(state)

        # ── HITL gate ──────────────────────────────────────────────
        run["approve_event"] = asyncio.Event()
        emit("modeler", "awaiting_approval",
             {"message": "Approve simulation parameters?"})
        await run["approve_event"].wait()
        if not run["approved"]:
            emit("sim_runner", "failed", {"reason": "user rejected parameters"})
            emit("reviewer", "failed", {"status": "done"})
            return

        state = stubs.sim_runner(state)
        state = stubs.analyzer(state)

        # ── Reviewer (real, deterministic) ─────────────────────────
        emit("reviewer", "started", {})
        result = review(state["analysis"], state["sim_output"],
                        state["raw_utility"]["monthly_kwh"])
        state["review"] = result
        emit("reviewer", "completed" if result.approved else "progress",
             {"approved": result.approved, "nmbe_pct": result.nmbe_pct,
              "cvrmse_pct": result.cvrmse_pct, "route_to": result.route_to})
        emit("reviewer", "done", {"approved": result.approved})
    except Exception as exc:  # noqa: BLE001 — surface to UI
        emit("reviewer", "failed", {"error": str(exc)})
