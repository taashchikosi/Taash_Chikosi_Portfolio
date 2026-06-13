"""Agent 1: Retriever — turns an IDF + utility bills into a BuildingContext (plan §2).

Design principle: the LLM only does what arithmetic can't.
    DETERMINISTIC (reproducible, no model):
      • floor_area_m2     ← inspect_idf (MCP)
      • current_eui       ← measured annual kWh / floor area
      • annual_cost_aud   ← the utility bill
      • ncc_climate_zone  ← deterministic location → zone lookup
    LLM (Claude via the router — judgement, not numbers):
      • building_type     ← classify from metadata
      • hvac_system       ← short human-readable summary
    The LLM step is schema-checked and has a deterministic fallback, so a model
    hiccup degrades gracefully instead of poisoning the context. RAG-sourced
    `applicable_codes` arrive in Phase 3; left empty here.

Both the MCP client and the LLM are injectable — unit-tested with fakes (no
EnergyPlus IDD, no live Claude). Live proof: scripts/verify_retriever.py (Docker).
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Callable, Optional

from agents.sim_runner import FastMCPCaller, ToolCaller
from agents.supervisor import RunState
from mcp_server.tools.reference_tools import ncc_climate_zone
from verification.pydantic_schemas import BuildingContext, UtilityData

# LLM interface: (system, user) -> raw text. Default routes through model_router.
LLMFn = Callable[[str, str], str]

DEFAULT_FLOOR_AREA_M2 = 511.0   # DOE small office — documented demo fallback only
DEFAULT_CLIMATE_ZONE = 5        # NSW (Sydney) if location can't be derived

_CLASSIFY_SYSTEM = (
    "You are a building-energy analyst. Given EnergyPlus model metadata, classify "
    "the building and summarise its HVAC in plain English. First decide the USE "
    "(office, retail, school, etc.) from the HVAC, constructions and location. "
    "If it is an OFFICE, size it strictly by floor_area_m2: "
    "<1000 m² = small_office, 1000-5000 m² = medium_office, >5000 m² = large_office. "
    "(This size convention is fixed so every model classifies the same building "
    "identically — do not deviate from these thresholds.) "
    "Respond with STRICT JSON only: "
    '{"building_type": "<e.g. small_office|medium_office|large_office|retail|school>", '
    '"hvac_system": "<short phrase>"}. No prose, no markdown.'
)


def _default_llm(system: str, user: str) -> str:
    from router.model_router import complete  # lazy: keeps tests model-free
    return complete("retrieval", system, user, max_tokens=300)["text"]


def _epw_location(epw_path: str) -> tuple:
    """Parse an onebuilding-style EPW name → (city, state). e.g.
    'AUS_NSW_Sydney.epw' → ('Sydney', 'NSW'). This is the *project's* site
    (the weather you simulate against), not the energy model's embedded location."""
    if not epw_path:
        return None, None
    parts = Path(epw_path).stem.split("_")
    state = parts[1] if len(parts) > 1 else None
    city = parts[2] if len(parts) > 2 else None
    return city, state


def _resolve_climate_zone(state: RunState, idf_location: dict) -> dict:
    """NCC zone from the building's geography, in priority order:
       1. explicit project location in state['building_location'] (customer input)
       2. the Australian weather file (epw_path) — the site being simulated
       3. the IDF's own Site:Location latitude (guarded to Australia)
    NCC zones are defined by physical location, NOT by a (possibly foreign,
    e.g. US DOE prototype) energy model's embedded Site:Location.
    """
    explicit = state.get("building_location") or {}
    cz = ncc_climate_zone(location_name=explicit.get("city"),
                          state=explicit.get("state"))
    if cz["zone"]:
        return cz

    city, st = _epw_location(state.get("epw_path", ""))
    cz = ncc_climate_zone(location_name=city, state=st)
    if cz["zone"]:
        return cz

    return ncc_climate_zone(latitude=(idf_location or {}).get("latitude"))


def _fallback_type(floor_area_m2: float) -> str:
    if floor_area_m2 < 1000:
        return "small_office"
    if floor_area_m2 < 5000:
        return "medium_office"
    return "large_office"


def _classify(llm: LLMFn, meta: dict, floor_area_m2: float) -> dict:
    """LLM classification with a strict-JSON parse and deterministic fallback."""
    hvac_objects = meta.get("hvac_objects", [])
    fallback = {
        "building_type": _fallback_type(floor_area_m2),
        "hvac_system": ", ".join(hvac_objects) or "unknown",
    }
    try:
        user = json.dumps({
            "zone_count": meta.get("zone_count"),
            "floor_area_m2": floor_area_m2,
            "hvac_objects": hvac_objects,
            "constructions": meta.get("constructions"),
            "location": meta.get("location"),
        })
        raw = llm(_CLASSIFY_SYSTEM, user)
        parsed = json.loads(_strip_fence(raw))
        return {
            "building_type": str(parsed.get("building_type") or fallback["building_type"]),
            "hvac_system": str(parsed.get("hvac_system") or fallback["hvac_system"]),
        }
    except Exception:  # noqa: BLE001 — any LLM/parse failure → deterministic fallback
        return fallback


def _strip_fence(text: str) -> str:
    """Tolerate ```json … ``` fences some models add despite instructions."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("```", 2)[1] if t.count("```") >= 2 else t.strip("`")
        if t.lstrip().lower().startswith("json"):
            t = t.lstrip()[4:]
    return t.strip()


async def _retrieve(state: RunState, call: ToolCaller, llm: LLMFn) -> RunState:
    emit = state.get("emit")
    if emit:
        emit("retriever", "started", {})

    utility = UtilityData(**state["raw_utility"])

    # 1. Deterministic extraction over MCP.
    meta = await call("inspect_idf", idf_path=state["idf_path"])

    floor_area = meta.get("floor_area_m2")
    floor_area_estimated = not (isinstance(floor_area, (int, float)) and floor_area > 0)
    if floor_area_estimated:
        floor_area = DEFAULT_FLOOR_AREA_M2  # IDF used autocalc geometry — see HANDOFF

    # 2. Deterministic arithmetic.
    current_eui = round(utility.annual_kwh / floor_area, 1) if floor_area else 0.0

    # 3. Deterministic location → NCC climate zone (project geography, not the IDF).
    cz = _resolve_climate_zone(state, meta.get("location"))
    climate_zone = cz["zone"] or DEFAULT_CLIMATE_ZONE
    if not cz["zone"]:
        cz = {**cz, "basis": cz["basis"] + f" → defaulted to NSW zone {DEFAULT_CLIMATE_ZONE}"}

    # 4. LLM judgement (with fallback).
    classified = _classify(llm, meta, float(floor_area))

    ctx = BuildingContext(
        building_type=classified["building_type"],
        floor_area_m2=float(floor_area),
        ncc_climate_zone=int(climate_zone),
        hvac_system=classified["hvac_system"],
        current_eui=current_eui,
        annual_energy_cost_aud=utility.annual_cost_aud,
        idf_path=state["idf_path"],
        utility_data=utility,
    )
    state["building_context"] = ctx
    if emit:
        emit("retriever", "completed", {
            "building_type": ctx.building_type,
            "floor_area_m2": ctx.floor_area_m2,
            "floor_area_estimated": floor_area_estimated,
            "ncc_climate_zone": ctx.ncc_climate_zone,
            "climate_zone_basis": cz["basis"],
            "current_eui": ctx.current_eui,
        })
    return state


async def retriever_async(state: RunState,
                          caller: Optional[ToolCaller] = None,
                          llm: Optional[LLMFn] = None) -> RunState:
    """Async pipeline node. `caller`/`llm` injected in tests; production opens a
    fresh in-memory FastMCP session and routes the LLM through model_router."""
    llm = llm or _default_llm
    if caller is not None:
        return await _retrieve(state, caller, llm)
    async with FastMCPCaller() as call:
        return await _retrieve(state, call, llm)


def retriever(state: RunState,
              caller: Optional[ToolCaller] = None,
              llm: Optional[LLMFn] = None) -> RunState:
    """Sync wrapper for tests / non-async callers (don't call from a running loop)."""
    return asyncio.run(retriever_async(state, caller, llm))
