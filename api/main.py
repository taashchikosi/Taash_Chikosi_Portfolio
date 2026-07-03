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
from agents.supervisor import RunState, build_graph
from agents.tracing import get_tracer
from verification.cohort_benchmark import city_from_epw, load_cohort
from verification.pydantic_schemas import ModelInputs

app = FastAPI(title="RetrofitGPT API", version="0.1.0")

# Repo root, so file lookups resolve regardless of the process cwd.
_BASE_DIR = Path(__file__).resolve().parent.parent
_CATALOG_PATH = _BASE_DIR / "data/reference_buildings/catalog.json"
_NGA_PATH = _BASE_DIR / "data/factors/nga_factors_2025.json"


def _state_from_epw(epw_path: str) -> str:
    """AUS_<STATE>_City.epw → STATE. The weather file IS the site, so the grid
    carbon factor follows it deterministically (Perth→WA, Brisbane→QLD, …)."""
    try:
        parts = Path(epw_path).stem.split("_")
        if len(parts) >= 2 and parts[0].upper() == "AUS":
            return parts[1].upper()
    except Exception:  # noqa: BLE001
        pass
    return "NSW"  # documented Sydney fallback


def carbon_factor_for_state(state: str) -> tuple[float, str]:
    """(kg CO₂e/kWh, source label) for a state's grid, from the NGA 2025 factors.
    Never LLM-authored; fails closed to the national factor if a state is missing."""
    try:
        factors = json.loads(_NGA_PATH.read_text())["electricity_scope2_kgco2e_per_kwh"]
    except Exception:  # noqa: BLE001
        return 0.62, "NGA 2025 NATIONAL"
    value = factors.get(state.upper(), factors.get("NATIONAL", 0.62))
    return float(value), f"NGA 2025 {state.upper()}"


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
    # Default = the Medium office (the verified demo path: ~4,982 m² authoritative
    # area, benchmarked against the real Sydney CBD cohort). The frontend sends an
    # explicit IDF/EPW per building+city selection; this default is for direct API
    # calls and keeps parity with scripts/verify_pipeline.py.
    idf_path: str = "data/reference_buildings/RefBldgMediumOffice.idf"
    epw_path: str = "data/reference_buildings/weather/AUS_NSW_Sydney.epw"
    utility: UtilityIn
    # "Run without validation": when False the Reviewer skips the realistic-range
    # (CBD cohort) gate and the run is left explicitly unvalidated — an honest-
    # failure path, never a fabricated pass. Default True = enforce the realism gate.
    # (Named validate_realism, not `validate`, to avoid shadowing BaseModel.validate.)
    validate_realism: bool = True
    # The six editable model inputs (spec §3). Each field is None unless the user
    # moved it off its calibrated default; set values drive the baseline EUI
    # through real EnergyPlus. Editing an input off-default moves the simulated
    # baseline EUI, which can push it outside the CBD cohort range → Reviewer withholds.
    model_inputs: ModelInputs | None = None


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
        MAX_TOKENS_PER_DAY, budget_exhausted, cost_used_last_day, tokens_used_last_day,
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
            # real rolling 24h USD spend (per-provider priced); the demo deltas this
            # across a run for an accurate per-run cost (not tokens×blended-rate).
            "cost_used_last_24h": cost_used_last_day(),
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
            model_inputs=body.model_inputs or ModelInputs(),
            validate=body.validate_realism,
        ),
        "approved": False,
        "status": "created",
        "validate": body.validate_realism,
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
        # Drive the pipeline EXACTLY ONCE per run. A reconnecting EventSource (e.g. a
        # transient network blip, or the browser auto-reconnecting after the
        # awaiting_approval pause) must RESUME streaming the same queue — not restart
        # the agents. Re-driving would replay the approval gate and re-run EnergyPlus,
        # which previously surfaced as "the gate reappears after I approved".
        if not run.get("driving"):
            run["driving"] = True
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
    # The operator picks ONE measure at the gate (keeps the live run to 2 EnergyPlus
    # sims). `measure` is the chosen scenario key, e.g. "double_glazing".
    run["chosen_measure"] = decision.get("measure")
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


def _build_result(state: RunState) -> dict:
    """Shape the final business case for the UI (units: kWh/m²·yr, AUD, tCO₂e)."""
    ctx = state["building_context"]
    analysis = state["analysis"]
    rec = analysis.recommended_package
    rev = state["review"]
    # Headline baseline EUI = the SIMULATED baseline (EnergyPlus), not the
    # input-derived current_eui. After the Bug #12 reconciliation both are on the
    # true area, but the demo's claim is "this is what the physics produced", so
    # report the sim value and fall back to current_eui only if the sim is absent.
    sim = state.get("sim_output")
    baseline_eui = (sim.baseline_result.annual_eui
                    if sim is not None else ctx.current_eui)
    return {
        "building": {
            "type": ctx.building_type, "floor_area_m2": ctx.floor_area_m2,
            "ncc_climate_zone": ctx.ncc_climate_zone,
            "baseline_eui_kwh_m2_yr": baseline_eui,
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
            "approved": rev.approved, "realistic": rev.realistic,
            "within_cohort": rev.within_cohort,
            "cohort_validated": rev.cohort_validated,
            "baseline_eui": rev.baseline_eui,
            "cohort_p25": rev.cohort_p25, "cohort_p75": rev.cohort_p75,
            "cohort_median": rev.cohort_median, "cohort_n": rev.cohort_n,
            "floor_area_realistic": rev.floor_area_realistic,
            "route_to": rev.route_to,
        },
        "sources": {"tariff": rec.tariff_source, "emission_factor": rec.emission_factor_source},
        "cohort_validated": rev.cohort_validated,
    }


@app.get("/api/metrics")
def metrics() -> dict:
    """Dashboard data. Null until the Langfuse export is wired (Phase 3).

    No fabricated numbers: fields are null rather than placeholder percentages, so
    a public endpoint never advertises invented figures. (Removed the fake
    router_breakdown {flash:0.90, pro:0.08, sonnet:0.02} — it was unused and not
    measured.)
    """
    return {
        "cost_per_run_aud": None, "p95_latency_ms": None,
        "eval_pass_rate": None, "guardrail_triggers": None,
        "router_breakdown": None,
        "note": "live metrics arrive in Phase 3 (Langfuse export)",
    }


def _graph_nodes(run: dict, trace) -> dict:
    """Build the LangGraph node callables for one run.

    Each wrapper (1) injects the run's `emit` callback into the state the agent
    sees, (2) strips it from the returned state so checkpoints stay serializable,
    and (3) records a Langfuse span with the node's timing + key outputs. Agent
    functions are resolved late (module globals) so tests can monkeypatch them.
    """
    emit = run["state"]["emit"]

    def _with_emit(state: RunState) -> RunState:
        s = dict(state)
        s["emit"] = emit
        return s

    def _clean(state: RunState) -> RunState:
        out = dict(state)
        out.pop("emit", None)
        return out

    async def n_retriever(state: RunState) -> RunState:
        sp = trace.span("retriever.classify")
        out = await retriever_async(_with_emit(state))
        ctx = out.get("building_context")
        sp.end(output={"building_type": getattr(ctx, "building_type", None),
                       "ncc_zone": getattr(ctx, "ncc_climate_zone", None)})
        return _clean(out)

    async def n_modeler(state: RunState) -> RunState:
        sp = trace.span("modeler.select_measures")
        out = await modeler_async(_with_emit(state))
        mo = out.get("modeling_output")
        sp.end(output={"scenarios": [s.name for s in mo.scenarios] if mo else None})
        return _clean(out)

    async def n_sim_runner(state: RunState) -> RunState:
        sp = trace.span("sim_runner.energyplus")
        out = await sim_runner_async(_with_emit(state))
        sim = out.get("sim_output")
        sp.end(output={
            "scenarios": {
                r.scenario_name: {"eui": r.annual_eui, "status": r.simulation_status}
                for r in sim.results
            } if sim else None,
        })
        return _clean(out)

    def n_analyzer(state: RunState) -> RunState:
        sp = trace.span("analyzer.compute")
        s = _with_emit(state)
        # Deterministic analysis context. The emission factor follows the SELECTED
        # CITY's grid (derived from the weather file's state — Perth→WA 0.50,
        # Brisbane→QLD 0.67, Melbourne→VIC 0.78, Sydney→NSW 0.64), never hardcoded.
        grid_state = _state_from_epw(s.get("epw_path") or "")
        carbon_factor, emission_source = carbon_factor_for_state(grid_state)
        s["analysis_context"] = {
            "scenario_costs": {sc.name: sc.estimated_cost_aud
                               for sc in s["modeling_output"].scenarios},
            "tariff_aud_per_kwh": 0.30,
            "carbon_factor_kg_per_kwh": carbon_factor,
            "tariff_source": "CDR Energy PRD (demo)",
            "emission_factor_source": emission_source,
        }
        out = real_analyzer(s)
        sp.end(output={"emission_factor": emission_source})
        return _clean(out)

    def n_reviewer(state: RunState) -> RunState:
        # Real, deterministic gate. Loads the REAL CBD cohort for this city +
        # building size; rejects a baseline EUI outside its p25–p75. None where no
        # cohort was built (illustrative combo) → left unvalidated, never faked.
        sp = trace.span("reviewer.cohort_gate")
        s = _with_emit(state)
        emit("reviewer", "started", {})
        ctx = s["building_context"]
        cohort = load_cohort(city_from_epw(s.get("epw_path") or ""),
                             ctx.building_type)
        result = review(s["analysis"], s["sim_output"], ctx,
                        cohort=cohort, validate=s.get("validate", True))
        s["review"] = result
        s["cycle_count"] = s.get("cycle_count", 0) + 1
        emit("reviewer", "completed" if result.approved else "progress",
             {"approved": result.approved, "within_cohort": result.within_cohort,
              "baseline_eui": result.baseline_eui,
              "cohort_p25": result.cohort_p25, "cohort_p75": result.cohort_p75,
              "cohort_validated": result.cohort_validated,
              "route_to": result.route_to})
        sp.end(output={"approved": result.approved,
                       "baseline_eui": result.baseline_eui,
                       "within_cohort": result.within_cohort,
                       "route_to": result.route_to})
        return _clean(s)

    return {"retriever": n_retriever, "modeler": n_modeler,
            "sim_runner": n_sim_runner, "analyzer": n_analyzer,
            "reviewer": n_reviewer}


async def _drive_pipeline(run: dict) -> None:
    """Drive the compiled LangGraph StateGraph for one run.

    The graph (agents/supervisor.build_graph) interrupts BEFORE sim_runner —
    the genuine HITL gate. We stream to the interrupt, surface the measure
    choices, block on the human approval, apply the pick via `update_state`,
    and resume the same checkpointed thread to the end. SSE event contract is
    unchanged from the pre-graph driver.
    """
    state: RunState = run["state"]
    emit = state["emit"]
    tracer = get_tracer()
    trace = tracer.start_run("aem.run", trace_id=None,
                             metadata={"run_id": state.get("run_id")})
    try:
        graph = build_graph(_graph_nodes(run, trace))
        config = {"configurable": {"thread_id": state["run_id"]}}
        seed = {k: v for k, v in state.items() if k != "emit"}

        # Leg 1 — retriever → modeler, then the graph interrupts before sim_runner.
        async for _ in graph.astream(seed, config, stream_mode="updates"):
            pass

        # ── HITL gate — operator picks ONE measure to simulate ─────────
        # The Modeler proposed the full applicable set (baseline + up to 3). We
        # surface those as choices; the operator picks one, and we simulate
        # baseline + that one only (2 real EnergyPlus sims — nothing faked).
        snap = graph.get_state(config)
        mo = snap.values["modeling_output"]
        baseline_name = mo.baseline_scenario.name
        retrofits = [s for s in mo.scenarios if s.name != baseline_name]
        candidates = [
            {"key": s.name, "description": s.description,
             "est_cost_aud": s.estimated_cost_aud}
            for s in retrofits
        ]
        run["approve_event"] = asyncio.Event()
        gate_sp = trace.span("hitl.await_approval")
        emit("modeler", "awaiting_approval",
             {"message": "Pick one measure to simulate, then approve.",
              "measures": candidates})
        await run["approve_event"].wait()
        if not run["approved"]:
            gate_sp.end(output={"approved": False})
            trace.end(metadata={"outcome": "rejected_at_gate"})
            tracer.flush()
            emit("sim_runner", "failed", {"reason": "user rejected parameters"})
            emit("reviewer", "failed", {"status": "done"})
            return

        # Keep baseline + the single chosen measure (default: first offered).
        chosen = next((s for s in retrofits
                       if s.name == run.get("chosen_measure")), None)
        if chosen is None:
            chosen = retrofits[0]
        graph.update_state(config, {
            "modeling_output": mo.model_copy(
                update={"scenarios": [mo.baseline_scenario, chosen]}),
            "approved": True,
        })
        gate_sp.end(output={"approved": True, "measure": chosen.name})
        emit("modeler", "measure_selected", {"key": chosen.name})

        # Leg 2 — resume the SAME thread: sim_runner → analyzer → reviewer → END.
        async for _ in graph.astream(None, config, stream_mode="updates"):
            pass

        final: RunState = graph.get_state(config).values
        result = final["review"]

        # Persist the full business case so the UI can fetch it on 'done'.
        run["result"] = _build_result(final)
        rec = run["result"]["recommended"]
        trace.end(metadata={"outcome": "approved" if result.approved else "withheld",
                            "baseline_eui": result.baseline_eui})
        tracer.flush()
        emit("reviewer", "done", {
            "approved": result.approved,
            "recommended": rec["scenario"],
            "energy_savings_pct": rec["energy_savings_pct"],
            "simple_payback_years": rec["simple_payback_years"],
        })
    except Exception as exc:  # noqa: BLE001 — surface to UI
        # A pipeline exception is an INFRA/engine failure, not a Reviewer verdict.
        # Preserve the real error string so the frontend can show it, and flag it as
        # a pipeline error (kind="pipeline_error") so the UI never renders it as an
        # "adjust your inputs" cohort rejection. The terminal `status:"failed"` is
        # what the SSE loop breaks on; the payload carries the honest cause.
        trace.end(metadata={"outcome": "pipeline_error", "error": str(exc)})
        tracer.flush()
        emit("reviewer", "failed",
             {"error": str(exc), "kind": "pipeline_error",
              "message": "The run failed before a verified result could be produced "
                         "(engine/infrastructure error, not a model-input problem)."})
