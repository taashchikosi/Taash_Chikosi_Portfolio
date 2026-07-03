"""Agent 3: Sim Runner — drives EnergyPlus over the real MCP protocol (plan §2).

Unlike the Analyzer/Reviewer (pure-Python deterministic agents), this agent is
the one that *exercises the MCP layer*: it talks to the in-process FastMCP server
through an in-memory client (no subprocess, no network) and calls the same 9
EnergyPlus tools an external MCP client would. That is the project's core hiring
signal — physics-in-the-loop **via MCP**, not MCP-as-decoration.

Per scenario from the Modeler (baseline + each retrofit):
    1. clone_idf             → working copy (never mutate the original)
    2. modify_idf_component  → apply each IDFModification   [baseline has none]
    3. run_simulation        → async EnergyPlus job_id
    4. get_simulation_status → POLL until success | failed | timeout
    5. get_annual_energy / get_monthly_energy / get_eui / get_energy_end_uses
       → assemble one SimulationResult
→ SimRunnerOutput(results=[...], baseline_result=...)  (contract unchanged)

The tool caller is injectable so the orchestration is unit-tested with a fake
client (no EnergyPlus, no Docker, no fastmcp needed in CI). The live FastMCP
client is imported lazily inside FastMCPCaller for the same reason.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Awaitable, Callable, Optional

from agents.model_inputs import apply_model_inputs
from agents.retrofit_catalog import CATALOG
from agents.supervisor import RunState
from verification.cohort_benchmark import office_band_for_area
from verification.pydantic_schemas import (
    ModelingOutput, ModelInputs, SimRunnerOutput, SimulationResult,
)

# An async tool caller: (tool_name, **kwargs) -> the tool's *unwrapped* data dict.
ToolCaller = Callable[..., Awaitable[dict[str, Any]]]

POLL_INTERVAL_S = 3.0      # how often to poll a running EnergyPlus job
POLL_TIMEOUT_S = 2000.0    # just over the tool's own 1800s subprocess cap
DEFAULT_EPW = "data/reference_buildings/weather/AUS_NSW_Sydney.epw"
DEFAULT_FLOOR_AREA_M2 = 511.0   # DOE small office, matches the retriever


# ── Envelope handling ──────────────────────────────────────────────────────
def _unwrap(raw: Any) -> dict[str, Any]:
    """Strip BOTH envelopes → the tool's payload dict.

    1) MCP transport: FastMCP `Client.call_tool(...)` returns a CallToolResult.
       Prefer `.data` (fully deserialized), then `.structured_content`, then the
       text of the first content block.
    2) Our ToolResponse envelope: every tool returns `wrap(name, data)` =
       {schema_version, tool_name, timestamp, data:{...}} — so peel off `data`.
    """
    payload: Any = raw
    if not isinstance(raw, dict):
        for attr in ("data", "structured_content"):
            val = getattr(raw, attr, None)
            if isinstance(val, dict):
                payload = val
                break
        else:
            content = getattr(raw, "content", None)
            if content:
                text = getattr(content[0], "text", None)
                if isinstance(text, str):
                    try:
                        payload = json.loads(text)
                    except json.JSONDecodeError:
                        payload = {"value": text}
    # Some client versions nest a bare return under "result".
    if isinstance(payload, dict) and set(payload) == {"result"} and isinstance(payload["result"], dict):
        payload = payload["result"]
    # Peel the ToolResponse envelope.
    if isinstance(payload, dict) and "tool_name" in payload and isinstance(payload.get("data"), dict):
        payload = payload["data"]
    return payload if isinstance(payload, dict) else {"value": payload}


class FastMCPCaller:
    """Calls tools on the in-process FastMCP server over the real MCP protocol,
    using FastMCP's in-memory transport (one session reused for the whole run).

    Used as an async context manager:
        async with FastMCPCaller() as call:
            await call("clone_idf", idf_path=..., scenario_name=...)
    """

    def __init__(self, server: Any = None) -> None:
        self._server = server
        self._client = None

    async def __aenter__(self) -> "FastMCPCaller":
        from fastmcp import Client  # lazy: keeps tests / CI fastmcp-free
        if self._server is None:
            from mcp_server.server import mcp as server
            self._server = server
        self._client = Client(self._server)
        await self._client.__aenter__()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if self._client is not None:
            await self._client.__aexit__(*exc)

    async def __call__(self, name: str, **kwargs: Any) -> dict[str, Any]:
        raw = await self._client.call_tool(name, kwargs)  # type: ignore[union-attr]
        return _unwrap(raw)


# ── Orchestration ──────────────────────────────────────────────────────────
def _failed(name: str, reason: str, emit, runtime: float = 0.0) -> SimulationResult:
    """A schema-valid SimulationResult marking a scenario that did not complete.

    Zeros (not faked monthly values) so the Reviewer's realism gate + the LLM06
    guardrail can't be fooled by a sim that never produced a real profile.
    """
    if emit:
        emit("sim_runner", "progress",
             {"scenario": name, "status": "failed", "reason": reason})
    return SimulationResult(
        scenario_name=name, annual_energy_kwh=0.0,
        monthly_energy_kwh=[0.0] * 12, annual_eui=0.0,
        simulation_status="failed", simulation_runtime_seconds=runtime,
    )


async def _poll(call: ToolCaller, job_id: str,
                *, interval: float = POLL_INTERVAL_S,
                timeout: float = POLL_TIMEOUT_S) -> dict[str, Any]:
    """Poll get_simulation_status until terminal, or give up after `timeout`."""
    waited = 0.0
    while True:
        status = await call("get_simulation_status", job_id=job_id)
        if status.get("status") in ("success", "failed", "timeout"):
            return status
        if waited >= timeout:
            return {"status": "timeout", "error": "agent poll timeout",
                    "runtime_seconds": waited, "output_dir": status.get("output_dir")}
        await asyncio.sleep(interval)
        waited += interval


async def _simulate(call: ToolCaller, base_idf: str, epw: str,
                    scenario, floor_area: float, emit,
                    model_inputs: Optional[ModelInputs] = None,
                    run_tag: Optional[str] = None
                    ) -> tuple[SimulationResult, Optional[str]]:
    """Run one scenario. Returns (result, output_dir). output_dir is None on any
    failure before a successful sim, else the EnergyPlus job dir — the Sim Runner
    reads the baseline's dir for the authoritative floor area (Bug #12 fix).

    model_inputs (when present) are applied to the clone FIRST — they set the
    building's operating point — then the scenario's own measure modifications,
    so an efficiency measure (e.g. LED) correctly overrides an edited input.

    run_tag scopes this run's working IDFs so concurrent visitors don't collide.
    """
    name = scenario.name

    cloned = await call("clone_idf", idf_path=base_idf, scenario_name=name,
                        run_tag=run_tag)
    if "error" in cloned or "cloned_path" not in cloned:
        return _failed(name, f"clone_idf: {cloned.get('error', 'no cloned_path')}", emit), None
    work_idf = cloned["cloned_path"]

    if model_inputs is not None and model_inputs.has_any_edit():
        await apply_model_inputs(call, work_idf, model_inputs)

    for m in scenario.modifications:  # baseline has none → no-op
        res = await call("modify_idf_component", idf_path=work_idf,
                         object_type=m.object_type, object_name=m.object_name,
                         field=m.field, new_value=str(m.new_value))
        if "error" in res:
            return _failed(name, f"modify {m.object_name}.{m.field}: {res['error']}", emit), None

    started = await call("run_simulation", idf_path=work_idf,
                         epw_path=epw, scenario_name=name)
    if "error" in started or "job_id" not in started:
        return _failed(name, f"run_simulation: {started.get('error', 'no job_id')}", emit), None

    status = await _poll(call, started["job_id"])
    runtime = float(status.get("runtime_seconds") or 0.0)
    if status.get("status") != "success":
        return _failed(name, f"sim {status.get('status')}: {status.get('error')}",
                       emit, runtime=runtime), None
    out_dir = status.get("output_dir")

    annual = await call("get_annual_energy", output_dir=out_dir)
    monthly = await call("get_monthly_energy", output_dir=out_dir)
    eui = await call("get_eui", output_dir=out_dir, floor_area_m2=floor_area)
    end_uses = await call("get_energy_end_uses", output_dir=out_dir)

    monthly_kwh = monthly.get("monthly_kwh")
    if not isinstance(monthly_kwh, list) or len(monthly_kwh) != 12:
        # A success status but no 12-month profile = useless downstream (the
        # guardrail reads the monthly shape; a partial profile is garbage in).
        return _failed(name, f"monthly extraction: {monthly.get('error', 'len != 12')}",
                       emit, runtime=runtime), out_dir

    result = SimulationResult(
        scenario_name=name,
        annual_energy_kwh=float(annual.get("total_kwh", 0.0)),
        monthly_energy_kwh=[float(v) for v in monthly_kwh],
        annual_eui=float(eui.get("eui_kwh_m2", 0.0)),
        peak_demand_kw=0.0,  # no peak-demand extraction tool yet (see HANDOFF)
        energy_end_uses=end_uses.get("end_uses_kwh", {}) or {},
        simulation_status="success",
        simulation_runtime_seconds=runtime,
    )
    if emit:
        emit("sim_runner", "progress",
             {"scenario": name, "status": "success",
              "annual_kwh": result.annual_energy_kwh,
              "eui": result.annual_eui, "runtime_s": runtime})
    return result, out_dir


async def _authoritative_area(call: ToolCaller, out_dir: Optional[str],
                              fallback: float) -> tuple[float, bool]:
    """Read EnergyPlus' own net conditioned area from a finished sim's output.

    Returns (area, reconciled). reconciled is True only when a real, materially
    different area was found — so under test fakes (which don't implement
    get_building_area) nothing changes and the provisional area stands.
    """
    if not out_dir:
        return fallback, False
    res = await call("get_building_area", output_dir=out_dir)
    try:
        area = float(res.get("net_conditioned_area_m2")) if isinstance(res, dict) else None
    except (TypeError, ValueError):
        area = None
    if area is None or area <= 0 or abs(area - fallback) <= 1.0:
        return fallback, False
    return round(area, 1), True


def _reconcile_floor_area(state: RunState, area: float, emit,
                          user_override: bool = False) -> None:
    """Correct the run context once the authoritative area is known (Bug #12).

    area → size band → EUI, and re-cost every measure at the true area. The
    Modeler costed measures against the provisional (possibly 10×-wrong) area;
    the Analyzer reads these costs after the sim, so re-costing here flows
    straight through to payback / NPV. Mutates context + modeling scenarios in
    place; the LLM authors none of it (pure arithmetic + catalog lookups).
    """
    ctx = state.get("building_context")
    if ctx is not None:
        ctx.floor_area_m2 = area
        annual_kwh = getattr(getattr(ctx, "utility_data", None), "annual_kwh", None)
        if annual_kwh:
            ctx.current_eui = round(annual_kwh / area, 1)
        # Deterministic size band from the true area (no LLM): the Retriever may
        # have classified on a wrong fallback area (medium read as small).
        # The band boundaries MUST match the cohort/abuse-guard definition
        # (SIZE_BANDS_M2): the real CBD medium-office cohort spans 2,500–10,000 m².
        # A hardcoded 5,000 cutoff here misclassified a 5,001–10,000 m² medium
        # office (a valid, slider-reachable medium size) as "large_office" — for
        # which no verified cohort exists (n=0 in most cities) — so the Reviewer's
        # realism gate silently fell back to "illustrative" and an out-of-cohort
        # baseline was APPROVED instead of rejected. Use the cohort's own medium
        # upper bound so the gate applies across the whole medium band.
        btype = (ctx.building_type or "")
        if btype.endswith("_office") or btype == "office":
            ctx.building_type = office_band_for_area(area)

    modeling = state.get("modeling_output")
    if modeling is not None:
        for s in modeling.scenarios:
            if s.name in CATALOG:
                s.estimated_cost_aud = CATALOG[s.name].estimate_cost(area)

    if emit:
        note = ("user-asserted floor area (overrides authoritative reconciliation)"
                if user_override
                else "authoritative area from EnergyPlus output (Bug #12)")
        emit("sim_runner", "progress",
             {"status": "reconciled_area", "floor_area_m2": area,
              "building_type": getattr(ctx, "building_type", None),
              "user_override": user_override, "note": note})


async def _run_all(state: RunState, call: ToolCaller) -> SimRunnerOutput:
    modeling: ModelingOutput = state["modeling_output"]
    base_idf = state["idf_path"]
    epw = state.get("epw_path") or DEFAULT_EPW
    ctx = state.get("building_context")
    floor_area = getattr(ctx, "floor_area_m2", None) or DEFAULT_FLOOR_AREA_M2
    emit = state.get("emit")
    baseline_name = modeling.baseline_scenario.name

    raw_mi = state.get("model_inputs")
    mi = raw_mi if isinstance(raw_mi, ModelInputs) else None

    # Scope this run's WORKING IDFs (localized/profiled/per-scenario clones) with the
    # run id so two concurrent visitors on the same city/scenario don't overwrite each
    # other's in-flight working files. Sim OUTPUT dirs are already uuid-safe (job ids).
    run_tag = state.get("run_id") or None

    # Localize the model to its weather file ONCE per run (Site:Location, design
    # days, ground temps), then clone every scenario from the localized copy — so
    # "EPW location-matched" is genuinely true, not Chicago-with-AU-weather. Fakes
    # without this tool return {} → base_idf unchanged (back-compatible).
    localized = await call("localize_idf", idf_path=base_idf, epw_path=epw,
                           run_tag=run_tag)
    if isinstance(localized, dict) and localized.get("localized_path"):
        base_idf = localized["localized_path"]
        if emit:
            emit("sim_runner", "progress",
                 {"status": "localized", "site": localized.get("site_name"),
                  "epw": epw.split("/")[-1],
                  "note": "Site:Location + design days + ground temps matched to the EPW"})

    # Make the default model a realistic AU WHOLE building before any scenario:
    # add the base-building / central-services loads NABERS whole-building includes
    # but the DOE tenancy model omits, so the baseline sits in the real cohort
    # range rather than the idealised top quartile. Applied to the shared base so
    # EVERY clone (the baseline + every measure scenario) inherits it.
    if state.get("au_profile", True):
        profiled = await call("apply_au_office_profile", idf_path=base_idf,
                              run_tag=run_tag)
        if isinstance(profiled, dict) and profiled.get("profiled_path"):
            base_idf = profiled["profiled_path"]
            if emit:
                emit("sim_runner", "progress",
                     {"status": "au_profile",
                      "plug_w_m2": profiled.get("plug_w_m2"),
                      "base_services_w_m2": profiled.get("base_services_w_m2"),
                      "note": "AU whole-building loads added (tenant plug + 24/7 "
                              "central services) — adjusts inputs to AU norms"})

    # Sequential on purpose: EnergyPlus is heavy and runs under x86 emulation on
    # the Apple-Silicon Mac mini — parallel sims would thrash it. One at a time,
    # streaming per-scenario progress to the SSE trace. The baseline runs FIRST
    # so its authoritative floor area is known before the measure scenarios — the
    # whole run is then costed and EUI'd against the real area (Bug #12).
    ordered = sorted(modeling.scenarios, key=lambda s: s.name != baseline_name)
    results: list[SimulationResult] = []
    for scenario in ordered:
        if emit:
            emit("sim_runner", "progress", {"scenario": scenario.name, "status": "running"})
        result, out_dir = await _simulate(call, base_idf, epw, scenario, floor_area,
                                          emit, model_inputs=mi, run_tag=run_tag)

        if scenario.name == baseline_name and result.simulation_status == "success":
            auth_area, reconciled = await _authoritative_area(call, out_dir, floor_area)
            # Floor area is now baked into the GEOMETRY (scale_floor_area), so the
            # authoritative Net Conditioned Area EnergyPlus reports already reflects
            # any resize. Reconcile to it (Bug #12) — no denominator override.
            if reconciled and abs(auth_area - floor_area) > 1.0:
                floor_area = auth_area
                _reconcile_floor_area(state, floor_area, emit)
                # Baseline EUI was computed against the provisional area — recompute
                # from the area-independent annual kWh. Measures run AFTER this with
                # the corrected area already.
                result = result.model_copy(update={
                    "annual_eui": round(result.annual_energy_kwh / floor_area, 1)})
        results.append(result)

    baseline_result = next(
        (r for r in results if r.scenario_name == baseline_name), results[0])

    # The Reviewer's gate is the CBD cohort range check on this baseline EUI (see
    # agents/reviewer.py) — no measured-profile reference is needed, so an edited
    # baseline simply lands where the physics puts it and is judged against the
    # real cohort. (Editing an energy input off-default that pushes EUI outside
    # the cohort p25–p75 is what the Reviewer rejects.)
    return SimRunnerOutput(results=results, baseline_result=baseline_result)


# ── Public node API ────────────────────────────────────────────────────────
async def sim_runner_async(state: RunState,
                           caller: Optional[ToolCaller] = None) -> RunState:
    """Async LangGraph/pipeline node. `caller` is injected in tests; in
    production a fresh in-memory FastMCP session is opened for the run.
    """
    emit = state.get("emit")
    if emit:
        emit("sim_runner", "started", {})

    if caller is not None:
        output = await _run_all(state, caller)
    else:
        async with FastMCPCaller() as call:
            output = await _run_all(state, call)

    state["sim_output"] = output
    if emit:
        ok = sum(1 for r in output.results if r.simulation_status == "success")
        emit("sim_runner", "completed",
             {"scenarios_run": len(output.results), "succeeded": ok})
    return state


def sim_runner(state: RunState, caller: Optional[ToolCaller] = None) -> RunState:
    """Sync wrapper for non-async callers and tests. Must NOT be called from
    inside a running event loop — use `await sim_runner_async(...)` there
    (api/main's pipeline does exactly that).
    """
    return asyncio.run(sim_runner_async(state, caller))
