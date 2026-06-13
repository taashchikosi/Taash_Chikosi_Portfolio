"""Agent 2: Modeler — proposes retrofit scenarios from the BuildingContext (plan §2).

Deterministic/LLM split (same discipline as the Retriever):
    LLM (judgement):  WHICH catalog measures suit this building + why
    DETERMINISTIC:    cost (seed catalog) · NCC reference (get_ncc_requirement)
                      · validate each measure's target type exists in the IDF
                      · build the wildcard IDFModification

Targets use object_name='*' (building-wide), so retrofits apply without the LLM
ever guessing a specific EnergyPlus object name — the fragile part. Output is a
ModelingOutput (baseline + ≥2 retrofits) handed to the HITL gate, then the Sim
Runner. MCP + LLM injectable → unit-tested with fakes; live proof via
scripts/verify_modeler.py (Docker + Claude).
"""
from __future__ import annotations

import asyncio
import json
from typing import Callable, Optional

from agents.retrofit_catalog import CATALOG, Measure
from agents.sim_runner import FastMCPCaller, ToolCaller
from agents.supervisor import RunState
from verification.pydantic_schemas import (
    BuildingContext, ModelingOutput, RetrofitScenario,
)

LLMFn = Callable[[str, str], str]
MIN_RETROFITS = 2   # ModelingOutput needs ≥3 scenarios total (baseline + 2)

_SELECT_SYSTEM = (
    "You are a building-energy retrofit advisor. From the catalog, pick the 2–3 "
    "measures best suited to the building. Respond with STRICT JSON only: "
    '{"measures": ["<key>", ...], "rationale": "<one sentence>"}. '
    "Use only catalog keys. No prose, no markdown."
)


def _default_llm(system: str, user: str) -> str:
    from router.model_router import complete  # lazy: keeps tests model-free
    return complete("modelling", system, user, complexity=0.6, max_tokens=300)["text"]


def _strip_fence(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("```", 2)[1] if t.count("```") >= 2 else t.strip("`")
        if t.lstrip().lower().startswith("json"):
            t = t.lstrip()[4:]
    return t.strip()


def _select_measures(llm: LLMFn, ctx: BuildingContext) -> list[str]:
    """LLM picks catalog keys; deterministic fallback = the whole catalog."""
    fallback = list(CATALOG)
    try:
        user = json.dumps({
            "building_type": ctx.building_type,
            "floor_area_m2": ctx.floor_area_m2,
            "ncc_climate_zone": ctx.ncc_climate_zone,
            "hvac_system": ctx.hvac_system,
            "current_eui": ctx.current_eui,
            "catalog": {k: m.description for k, m in CATALOG.items()},
        })
        parsed = json.loads(_strip_fence(llm(_SELECT_SYSTEM, user)))
        keys = [k for k in parsed.get("measures", []) if k in CATALOG]
        return keys or fallback
    except Exception:  # noqa: BLE001 — any LLM/parse failure → propose the catalog
        return fallback


async def _scenario(call: ToolCaller, measure: Measure,
                    ctx: BuildingContext) -> RetrofitScenario:
    # REAL NCC Section J check via the MCP tool (no more hardcoded True). The tool
    # knows what the code actually regulates: lighting → J7D3 numeric limit;
    # equipment → not regulated; glazing/fabric → requires J4 façade calculation.
    # Keeping this behind get_ncc_requirement means Tier 2 (RAG over the live NCC)
    # slots into the tool — the agent code never changes.
    try:
        value: Optional[float] = float(measure.new_value)
    except (TypeError, ValueError):
        value = None
    res = await call("get_ncc_requirement", component=measure.ncc_component,
                     climate_zone=ctx.ncc_climate_zone, value=value)
    status = res.get("status", "unverified")
    clause = res.get("clause") or "NCC 2022 Section J (VERIFY)"
    return RetrofitScenario(
        name=measure.key,
        description=measure.description,
        modifications=[measure.modification()],
        estimated_cost_aud=measure.estimate_cost(ctx.floor_area_m2),
        code_compliance=(status == "compliant"),
        compliance_status=status,
        ncc_reference=clause,
    )


async def _model(state: RunState, call: ToolCaller, llm: LLMFn) -> RunState:
    emit = state.get("emit")
    if emit:
        emit("modeler", "started", {})
    ctx: BuildingContext = state["building_context"]

    # Which object types actually exist in this model (for validation).
    meta = await call("inspect_idf", idf_path=ctx.idf_path)
    present = {t.upper() for t in (meta.get("object_types") or [])}

    def applies(m: Measure) -> bool:
        # If the IDF didn't report object_types, don't over-filter (trust + let
        # the Sim Runner fail any scenario whose modify doesn't apply).
        return not present or m.object_type.upper() in present

    selected = _select_measures(llm, ctx)
    chosen = [CATALOG[k] for k in selected if applies(CATALOG[k])]

    # Backfill to MIN_RETROFITS from the rest of the (applicable) catalog.
    for k, m in CATALOG.items():
        if len(chosen) >= MIN_RETROFITS:
            break
        if m not in chosen and applies(m):
            chosen.append(m)

    if len(chosen) < MIN_RETROFITS:
        raise ValueError(
            "model lacks enough modifiable targets for retrofit scenarios "
            f"(found {len(chosen)}, need {MIN_RETROFITS})")

    baseline = RetrofitScenario(
        name="baseline", description="As-built (no modifications)",
        modifications=[], estimated_cost_aud=0.0,
        code_compliance=False, compliance_status="unverified",
        ncc_reference="— (as-built baseline, not a code-assessed design)")
    retrofits = [await _scenario(call, m, ctx) for m in chosen[:5]]

    state["modeling_output"] = ModelingOutput(
        scenarios=[baseline, *retrofits],
        baseline_scenario=baseline,
        modeling_confidence=0.7 if present else 0.5)
    if emit:
        emit("modeler", "completed",
             {"scenarios": [s.name for s in retrofits],
              "count": len(retrofits)})
    return state


async def modeler_async(state: RunState,
                        caller: Optional[ToolCaller] = None,
                        llm: Optional[LLMFn] = None) -> RunState:
    """Async pipeline node. Clients injected in tests; production opens a fresh
    in-memory FastMCP session and routes the LLM through model_router."""
    llm = llm or _default_llm
    if caller is not None:
        return await _model(state, caller, llm)
    async with FastMCPCaller() as call:
        return await _model(state, call, llm)


def modeler(state: RunState,
            caller: Optional[ToolCaller] = None,
            llm: Optional[LLMFn] = None) -> RunState:
    """Sync wrapper for tests / non-async callers (not from a running loop)."""
    return asyncio.run(modeler_async(state, caller, llm))
