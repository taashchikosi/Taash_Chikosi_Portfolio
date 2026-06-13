"""Retriever tests — fake MCP client + fake LLM (no IDD, no live Claude).

Pins the deterministic/LLM split: numbers must be reproducible from inputs;
the LLM only sets building_type/hvac_system and must degrade to a deterministic
fallback when it errors or returns junk.
"""
from __future__ import annotations

import json

import pytest

from agents.retriever import retriever
from mcp_server.tools.reference_tools import ncc_climate_zone
from verification.pydantic_schemas import BuildingContext


# ── Fakes ──────────────────────────────────────────────────────────────────
def make_caller(meta: dict):
    async def caller(name, **kwargs):
        assert name == "inspect_idf"
        return meta
    return caller


def llm_returning(payload):
    """payload: dict→serialised JSON, str→returned raw, Exception→raised."""
    def llm(system, user):
        if isinstance(payload, Exception):
            raise payload
        return payload if isinstance(payload, str) else json.dumps(payload)
    return llm


SYDNEY_META = {
    "zone_count": 5, "floor_area_m2": 511.0,
    "location": {"name": "Sydney", "latitude": -33.9, "longitude": 151.2},
    "hvac_objects": ["AIRLOOPHVAC", "ZONEHVAC:PACKAGEDTERMINALAIRCONDITIONER"],
    "constructions": 12,
}


def _state(meta=SYDNEY_META):
    return {
        "idf_path": "data/reference_buildings/RefBldgSmallOffice.idf",
        "raw_utility": {"monthly_kwh": [5000.0] * 12,
                        "annual_cost_aud": 18000.0, "tariff_type": "single rate"},
        "emit": None,
    }


# ── Deterministic fields ────────────────────────────────────────────────────
def test_happy_path_builds_valid_context():
    ctx = retriever(_state(),
                    caller=make_caller(SYDNEY_META),
                    llm=llm_returning({"building_type": "small_office",
                                       "hvac_system": "packaged DX + gas heat"}))["building_context"]
    assert isinstance(ctx, BuildingContext)
    assert ctx.floor_area_m2 == 511.0
    assert ctx.current_eui == round(60_000 / 511.0, 1)      # deterministic
    assert ctx.annual_energy_cost_aud == 18_000.0           # from the bill
    assert ctx.ncc_climate_zone == 5                        # Sydney
    assert ctx.building_type == "small_office"              # from LLM
    assert ctx.hvac_system == "packaged DX + gas heat"


def test_eui_is_pure_arithmetic_not_from_llm():
    """Even if the LLM hallucinates, EUI/area/cost stay derived from inputs."""
    ctx = retriever(_state(),
                    caller=make_caller(SYDNEY_META),
                    llm=llm_returning({"building_type": "spaceship",
                                       "hvac_system": "warp core"}))["building_context"]
    assert ctx.current_eui == round(60_000 / 511.0, 1)
    assert ctx.floor_area_m2 == 511.0
    assert ctx.building_type == "spaceship"   # LLM owns type; numbers it can't touch


# ── Fallbacks ───────────────────────────────────────────────────────────────
def test_autocalc_floor_area_falls_back():
    meta = {**SYDNEY_META, "floor_area_m2": None}   # IDF used autocalc geometry
    ctx = retriever(_state(meta),
                    caller=make_caller(meta),
                    llm=llm_returning({"building_type": "x", "hvac_system": "y"}))["building_context"]
    assert ctx.floor_area_m2 == 511.0   # documented demo fallback


def test_llm_failure_uses_deterministic_fallback():
    ctx = retriever(_state(),
                    caller=make_caller(SYDNEY_META),
                    llm=llm_returning(RuntimeError("model down")))["building_context"]
    assert ctx.building_type == "small_office"          # area heuristic (<1000)
    assert "AIRLOOPHVAC" in ctx.hvac_system             # joined hvac_objects


def test_classify_prompt_anchors_office_size_thresholds():
    # Regression guard: the size convention must stay explicit in the prompt so every
    # provider classifies the same building identically. (Tier B caught DeepSeek
    # rounding a 511 m² small office up to medium_office when this was implicit.)
    from agents.retriever import _CLASSIFY_SYSTEM
    p = _CLASSIFY_SYSTEM.lower()
    assert "<1000" in p and "small_office" in p
    assert "1000-5000" in p and "medium_office" in p
    assert ">5000" in p and "large_office" in p


def test_llm_json_fence_is_tolerated():
    fenced = '```json\n{"building_type": "retail", "hvac_system": "VRF"}\n```'
    ctx = retriever(_state(),
                    caller=make_caller(SYDNEY_META),
                    llm=llm_returning(fenced))["building_context"]
    assert ctx.building_type == "retail" and ctx.hvac_system == "VRF"


def test_climate_zone_from_latitude_when_city_unknown():
    meta = {**SYDNEY_META,
            "location": {"name": "Nowhereville", "latitude": -37.8, "longitude": 145}}
    ctx = retriever(_state(meta),
                    caller=make_caller(meta),
                    llm=llm_returning({"building_type": "x", "hvac_system": "y"}))["building_context"]
    assert ctx.ncc_climate_zone == 6   # ~Melbourne latitude band


def test_us_prototype_latitude_does_not_map_to_a_real_zone():
    """The DOE prototype's +41.8° (Chicago) must NOT become a real AU zone; it
    falls back to the NSW default with an honest basis (the live-verify bug)."""
    meta = {**SYDNEY_META, "location": {"name": "Chicago Ohare", "latitude": 41.8}}
    events = []
    state = {**_state(meta), "emit": lambda a, s, p: events.append((s, p))}
    ctx = retriever(state, caller=make_caller(meta),
                    llm=llm_returning({"building_type": "x", "hvac_system": "y"}))["building_context"]
    assert ctx.ncc_climate_zone == 5   # defaulted, not "1 — tropical"
    basis = next(p["climate_zone_basis"] for s, p in events if s == "completed")
    assert "outside Australia" in basis and "default" in basis.lower()


def test_climate_zone_from_weather_file_overrides_idf_location():
    """Project geography wins: a Melbourne EPW → zone 6 even though the IDF's
    embedded location is the US prototype."""
    meta = {**SYDNEY_META, "location": {"name": "Chicago", "latitude": 41.8}}
    state = {**_state(meta),
             "epw_path": "data/reference_buildings/weather/AUS_VIC_Melbourne.epw"}
    ctx = retriever(state, caller=make_caller(meta),
                    llm=llm_returning({"building_type": "x", "hvac_system": "y"}))["building_context"]
    assert ctx.ncc_climate_zone == 6   # VIC


def test_explicit_building_location_has_highest_priority():
    state = {**_state(), "building_location": {"state": "QLD"}}
    ctx = retriever(state, caller=make_caller(SYDNEY_META),
                    llm=llm_returning({"building_type": "x", "hvac_system": "y"}))["building_context"]
    assert ctx.ncc_climate_zone == 2   # QLD beats the Sydney IDF latitude


# ── Climate-zone helper ──────────────────────────────────────────────────────
def test_ncc_zone_city_match():
    assert ncc_climate_zone(location_name="Sydney Airport")["zone"] == 5
    assert ncc_climate_zone(location_name="Darwin")["zone"] == 1


def test_ncc_zone_latitude_and_empty():
    assert ncc_climate_zone(latitude=-33.9)["zone"] == 5
    assert ncc_climate_zone()["zone"] is None


def test_ncc_zone_by_state():
    assert ncc_climate_zone(state="NSW")["zone"] == 5
    assert ncc_climate_zone(state="qld")["zone"] == 2


def test_ncc_zone_rejects_non_australian_latitude():
    r = ncc_climate_zone(latitude=41.8)   # Chicago
    assert r["zone"] is None and "outside Australia" in r["basis"]
