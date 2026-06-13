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
import os
import shutil
import uuid
from pathlib import Path
from typing import Any

import time
from collections import deque

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from agents.analyzer import analyzer as real_analyzer
from agents.modeler import modeler_async
from agents.retriever import retriever_async
from agents.reviewer import review
from agents.sim_runner import sim_runner_async
from agents.supervisor import RunState

app = FastAPI(title="RetrofitGPT API", version="0.1.0")


def _allowed_origins() -> list[str]:
    """CORS allowlist from ALLOWED_ORIGINS (comma-separated). Defaults to local dev.

    A public agent must not run wide-open CORS. In prod set, e.g.,
    ALLOWED_ORIGINS=https://yourplatform.vercel.app,https://www.yourdomain.com
    """
    raw = os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000")
    return [o.strip() for o in raw.split(",") if o.strip()]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# In-memory run registry (Phase 2 → Postgres if persistence needed)
_RUNS: dict[str, dict[str, Any]] = {}

# ── Rate limiting ────────────────────────────────────────────────────────────
# Public live agent → abuse protection is non-negotiable. Per-IP fixed window,
# in-memory (fine for the single-container VPS demo; swap for Redis if it ever
# scales horizontally). Tune with RATE_LIMIT_PER_MIN.
_RATE_LIMIT_PER_MIN = int(os.environ.get("RATE_LIMIT_PER_MIN", "30"))
_RATE_WINDOW_S = 60.0
_RATE_HITS: dict[str, deque] = {}


def _client_ip(request: Request) -> str:
    # Behind Caddy/Vercel the real client IP is the first X-Forwarded-For entry.
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(request: Request) -> None:
    """FastAPI dependency: cap runs per IP per minute (raises 429 over limit)."""
    ip = _client_ip(request)
    now = time.monotonic()
    dq = _RATE_HITS.setdefault(ip, deque())
    while dq and now - dq[0] > _RATE_WINDOW_S:
        dq.popleft()
    if len(dq) >= _RATE_LIMIT_PER_MIN:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded: max {_RATE_LIMIT_PER_MIN} runs/min.",
        )
    dq.append(now)


class UtilityIn(BaseModel):
    monthly_kwh: list[float] = Field(..., min_length=12, max_length=12)
    annual_cost_aud: float
    tariff_type: str = "single rate"


class RunIn(BaseModel):
    idf_path: str = "data/reference_buildings/RefBldgSmallOffice.idf"
    epw_path: str = "data/reference_buildings/weather/AUS_NSW_Sydney.epw"
    utility: UtilityIn
    # Demo-only: synthesise "measured" bills FROM the baseline sim so the GL14 gate
    # passes and the approval path runs green on the un-tuned DOE prototype. CIRCULAR
    # BY DESIGN — disclosed by the site's "Demo calibration" badge. NOT a real
    # calibration. Mirrors scripts/verify_pipeline.py --calibrate-demo.
    demo_calibrate: bool = False


# Deterministic, mean-neutral residuals (sum ≈ 0 → NMBE ≈ 0; ~5% magnitude →
# CV-RMSE ~5%, inside GL14 monthly 15%). Fixed so the demo is reproducible.
_DEMO_RESIDUALS = [+0.05, -0.05, +0.04, -0.04, +0.06, -0.06,
                   +0.05, -0.05, +0.04, -0.04, +0.06, -0.06]


def demo_bills_from_baseline(baseline_monthly: list[float]) -> list[float]:
    """Synthesise 'measured' bills from the baseline sim profile (DEMO ONLY)."""
    return [round(kwh * (1 + r), 1)
            for kwh, r in zip(baseline_monthly, _DEMO_RESIDUALS)]


# Repo root, so health checks resolve regardless of the process cwd.
_BASE = Path(__file__).resolve().parent.parent


def _health_checks() -> dict[str, bool]:
    """Fast, non-blocking readiness checks (no DB/network calls)."""
    checks: dict[str, bool] = {}

    # EnergyPlus binary available? (only needed for NEW simulations)
    ep_dir = os.environ.get("ENERGYPLUS_INSTALL_DIR", "/usr/local/EnergyPlus")
    checks["energyplus"] = bool(shutil.which("energyplus")) or (Path(ep_dir) / "energyplus").exists()

    # NGA carbon factors loadable + well-formed?
    try:
        factors = json.loads((_BASE / "data/factors/nga_factors_2025.json").read_text())
        checks["carbon_factors"] = "electricity_scope2_kgco2e_per_kwh" in factors
    except Exception:  # noqa: BLE001
        checks["carbon_factors"] = False

    # At least one reference building present (drives instant-demo mode)?
    checks["reference_building"] = any((_BASE / "data/reference_buildings").glob("RefBldg*.idf"))

    # Sydney weather present? (needed for live sims, not for cached-demo mode)
    checks["weather_epw"] = any((_BASE / "data/reference_buildings/weather").glob("*.epw"))

    return checks


@app.get("/health")
def health() -> dict:
    """Readiness probe driving the site's 🟢/🔴 status dot.

    status == "ok"  → the cached-demo path is fully serveable (green dot).
    live_simulation_available → EnergyPlus + weather are present for NEW runs.
    """
    from router.model_router import (
        MAX_TOKENS_PER_DAY, budget_exhausted, tokens_used_last_day,
    )

    checks = _health_checks()
    demo_ready = checks["carbon_factors"] and checks["reference_building"]
    return {
        "status": "ok" if demo_ready else "degraded",
        "service": "retrofitgpt-api",
        "version": "0.1.0",
        "checks": checks,
        "live_simulation_available": checks["energyplus"] and checks["weather_epw"],
        "token_budget": {
            "used_last_24h": tokens_used_last_day(),
            "limit_per_day": MAX_TOKENS_PER_DAY,
            "exhausted": budget_exhausted(),
        },
    }


def budget_gate() -> None:
    """Refuse new runs once the global LLM token budget is spent (clear 503 instead
    of silently degrading to fallbacks mid-run). Complements the per-IP rate-limit."""
    from router.model_router import budget_exhausted
    if budget_exhausted():
        raise HTTPException(
            status_code=503,
            detail="Demo LLM budget for the day has been reached — please try later.")


@app.post("/api/runs")
def create_run(body: RunIn, _rl: None = Depends(rate_limit),
               _bg: None = Depends(budget_gate)) -> dict:
    run_id = uuid.uuid4().hex[:12]
    _RUNS[run_id] = {
        "queue": asyncio.Queue(),
        "state": RunState(
            run_id=run_id, idf_path=body.idf_path, epw_path=body.epw_path,
            raw_utility=body.utility.model_dump(), cycle_count=0,
        ),
        "approved": False,
        "status": "created",
        "demo_calibrate": body.demo_calibrate,
        "result": None,
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


@app.get("/api/runs/{run_id}/result")
def get_result(run_id: str) -> dict:
    """Final business case + verdict for a finished run (the UI fetches this on 'done').

    404 unknown run · 425 not finished yet · 200 with the result payload.
    """
    run = _RUNS.get(run_id)
    if run is None:
        raise HTTPException(404, "unknown run_id")
    if run.get("result") is None:
        raise HTTPException(425, "run not finished")
    return run["result"]


def _build_result(state: RunState, demo_calibrate: bool) -> dict:
    """Shape the final business case for the UI (units: kWh/m²·yr, AUD, tCO₂e)."""
    ctx = state["building_context"]
    analysis = state["analysis"]
    rec = analysis.recommended_package
    rev = state["review"]
    return {
        "building": {
            "type": ctx.building_type, "floor_area_m2": ctx.floor_area_m2,
            "ncc_climate_zone": ctx.ncc_climate_zone,
            "baseline_eui_kwh_m2_yr": ctx.current_eui,
        },
        "recommended": {
            "scenario": rec.scenario_name,
            "energy_savings_pct": rec.energy_savings_pct,
            "cost_savings_aud_per_year": rec.cost_savings_aud_per_year,
            "retrofit_cost_aud": rec.retrofit_cost_aud,
            "simple_payback_years": rec.simple_payback_years,
            "npv_aud": rec.npv_aud,
            "carbon_reduction_tco2e_per_year": rec.carbon_reduction_tco2e_per_year,
        },
        "scenarios": [
            {"scenario": a.scenario_name, "energy_savings_pct": a.energy_savings_pct,
             "simple_payback_years": a.simple_payback_years,
             "npv_aud": a.npv_aud,
             "carbon_reduction_tco2e_per_year": a.carbon_reduction_tco2e_per_year}
            for a in analysis.analyses
        ],
        "review": {
            "approved": rev.approved, "nmbe_pct": rev.nmbe_pct,
            "cvrmse_pct": rev.cvrmse_pct, "route_to": rev.route_to,
        },
        "sources": {"tariff": rec.tariff_source, "emission_factor": rec.emission_factor_source},
        "demo_calibration": demo_calibrate,
    }


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
        # Real Retriever — inspect_idf over MCP + deterministic context, Claude
        # for building-type/HVAC classification (LLM_PROVIDER=anthropic in dev).
        state = await retriever_async(state)
        # Real Modeler — Claude selects measures; deterministic cost/NCC/validation.
        state = await modeler_async(state)

        # ── HITL gate ──────────────────────────────────────────────
        run["approve_event"] = asyncio.Event()
        emit("modeler", "awaiting_approval",
             {"message": "Approve simulation parameters?"})
        await run["approve_event"].wait()
        if not run["approved"]:
            emit("sim_runner", "failed", {"reason": "user rejected parameters"})
            emit("reviewer", "failed", {"status": "done"})
            return

        # Real Sim Runner — drives EnergyPlus over the in-memory MCP protocol.
        # Already inside the event loop (create_task), so await the async node.
        state = await sim_runner_async(state)

        # Demo calibration (disclosed by the site's badge): synthesise measured bills
        # FROM the baseline sim so the GL14 gate passes on the un-tuned DOE prototype.
        # Circular by design — NOT a real-building calibration.
        if run.get("demo_calibrate"):
            base_monthly = state["sim_output"].baseline_result.monthly_energy_kwh
            demo_bills = demo_bills_from_baseline(base_monthly)
            state["raw_utility"]["monthly_kwh"] = demo_bills
            state["raw_utility"]["annual_cost_aud"] = round(sum(demo_bills) * 0.30, 2)
            emit("calibrate_demo", "bills_synthesised",
                 {"annual_kwh": round(sum(demo_bills)), "disclosed": True})

        # Real deterministic analyzer (tested). Costs come from the modeler's
        # scenarios; factors from the reference data (NSW grid, demo tariff).
        state["analysis_context"] = {
            "scenario_costs": {s.name: s.estimated_cost_aud
                               for s in state["modeling_output"].scenarios},
            "tariff_aud_per_kwh": 0.30,
            "carbon_factor_kg_per_kwh": 0.66,
            "tariff_source": "CDR Energy PRD (demo)",
            "emission_factor_source": "NGA 2025 NSW",
        }
        state = real_analyzer(state)

        # ── Reviewer (real, deterministic) ─────────────────────────
        emit("reviewer", "started", {})
        result = review(state["analysis"], state["sim_output"],
                        state["raw_utility"]["monthly_kwh"])
        state["review"] = result
        emit("reviewer", "completed" if result.approved else "progress",
             {"approved": result.approved, "nmbe_pct": result.nmbe_pct,
              "cvrmse_pct": result.cvrmse_pct, "route_to": result.route_to})

        # Persist the full business case so the UI can fetch it on 'done'.
        run["result"] = _build_result(state, run.get("demo_calibrate", False))
        rec = run["result"]["recommended"]
        emit("reviewer", "done", {
            "approved": result.approved,
            "recommended": rec["scenario"],
            "energy_savings_pct": rec["energy_savings_pct"],
            "simple_payback_years": rec["simple_payback_years"],
        })
    except Exception as exc:  # noqa: BLE001 — surface to UI
        emit("reviewer", "failed", {"error": str(exc)})
