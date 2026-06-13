"""Modeler tests — fake MCP client + fake LLM (no IDD, no live Claude).

Pins the deterministic/LLM split: the LLM picks WHICH measures; cost, NCC
reference, wildcard targeting, and target-type validation are deterministic.
"""
from __future__ import annotations

import json

import pytest

from agents.modeler import modeler
from agents.retrofit_catalog import CATALOG
from verification.pydantic_schemas import (
    BuildingContext, ModelingOutput, UtilityData,
)

ALL_TYPES = ["LIGHTS", "ELECTRICEQUIPMENT", "WINDOWMATERIAL:SIMPLEGLAZINGSYSTEM", "ZONE"]


class FakeCaller:
    def __init__(self, object_types=None):
        self.calls = []
        self.object_types = ALL_TYPES if object_types is None else object_types

    async def __call__(self, name, **kw):
        self.calls.append((name, kw))
        if name == "inspect_idf":
            return {"object_types": self.object_types, "zone_count": 6}
        if name == "get_ncc_requirement":
            # Delegate to the REAL deterministic NCC check (what the MCP tool wraps),
            # so wiring tests exercise genuine compliance logic, not a canned string.
            from verification.ncc_compliance import check_ncc_compliance
            return check_ncc_compliance(
                kw.get("component"), kw.get("value"), kw.get("climate_zone"))
        return {}


def llm_picks(keys):
    def f(system, user):
        return json.dumps({"measures": keys, "rationale": "demo"})
    return f


def llm_raises(system, user):
    raise RuntimeError("model down")


def _ctx(floor=511.0, zone=5):
    return BuildingContext(
        building_type="small_office", floor_area_m2=floor, ncc_climate_zone=zone,
        hvac_system="VAV AHU", current_eui=126.4, annual_energy_cost_aud=19_500.0,
        idf_path="data/reference_buildings/RefBldgSmallOffice.idf",
        utility_data=UtilityData(monthly_kwh=[5000.0] * 12, annual_cost_aud=19_500.0))


def _state(ctx=None, emit=None):
    return {"building_context": ctx or _ctx(), "emit": emit}


# ── Core behaviour ───────────────────────────────────────────────────────────
def test_builds_baseline_plus_selected_retrofits():
    out = modeler(_state(), caller=FakeCaller(),
                  llm=llm_picks(["led_lighting", "double_glazing"]))["modeling_output"]
    assert isinstance(out, ModelingOutput)
    names = [s.name for s in out.scenarios]
    assert names[0] == "baseline" and out.baseline_scenario.name == "baseline"
    assert "led_lighting" in names and "double_glazing" in names
    assert len(out.scenarios) >= 3   # schema minimum


def test_modifications_are_building_wide_wildcards():
    out = modeler(_state(), caller=FakeCaller(),
                  llm=llm_picks(["led_lighting"]))["modeling_output"]
    led = next(s for s in out.scenarios if s.name == "led_lighting")
    assert led.modifications[0].object_name == "*"
    assert led.modifications[0].object_type == "Lights"


def test_cost_is_deterministic_from_catalog_not_llm():
    out = modeler(_state(_ctx(floor=511.0)), caller=FakeCaller(),
                  llm=llm_picks(["led_lighting"]))["modeling_output"]
    led = next(s for s in out.scenarios if s.name == "led_lighting")
    assert led.estimated_cost_aud == CATALOG["led_lighting"].estimate_cost(511.0)
    assert led.estimated_cost_aud == 14_775.0   # 2000 + 25×511


def test_led_lighting_is_really_ncc_compliant():
    """led_lighting targets 4.5 W/m² → meets NCC 2022 J7D3 office max → compliant,
    cited to the real clause (no more hardcoded True)."""
    out = modeler(_state(), caller=FakeCaller(),
                  llm=llm_picks(["led_lighting"]))["modeling_output"]
    led = next(s for s in out.scenarios if s.name == "led_lighting")
    assert led.compliance_status == "compliant"
    assert led.code_compliance is True
    assert "J7D3" in led.ncc_reference


def test_equipment_retrofit_is_not_regulated_not_falsely_compliant():
    """NCC Section J does not regulate plug-load equipment power density → status
    must be 'not_regulated', NOT a fabricated compliant=True."""
    out = modeler(_state(), caller=FakeCaller(),
                  llm=llm_picks(["efficient_equipment"]))["modeling_output"]
    eq = next(s for s in out.scenarios if s.name == "efficient_equipment")
    assert eq.compliance_status == "not_regulated"
    assert eq.code_compliance is False   # not 'compliant' → bool is False, honestly


def test_glazing_requires_calculation():
    out = modeler(_state(), caller=FakeCaller(),
                  llm=llm_picks(["double_glazing"]))["modeling_output"]
    gl = next(s for s in out.scenarios if s.name == "double_glazing")
    assert gl.compliance_status == "requires_calculation"


# ── Validation against the model's object types ──────────────────────────────
def test_absent_target_type_is_filtered_and_backfilled():
    """No SimpleGlazingSystem in the model → glazing dropped, but still ≥2
    retrofits via backfill (led + efficient_equipment)."""
    types = ["LIGHTS", "ELECTRICEQUIPMENT", "ZONE"]   # no glazing
    out = modeler(_state(), caller=FakeCaller(object_types=types),
                  llm=llm_picks(["double_glazing", "led_lighting"]))["modeling_output"]
    names = [s.name for s in out.scenarios]
    assert "double_glazing" not in names
    assert len([n for n in names if n != "baseline"]) >= 2


def test_raises_when_no_modifiable_targets():
    out_types = ["ZONE", "BUILDING"]   # nothing the catalog can touch
    with pytest.raises(ValueError, match="modifiable targets"):
        modeler(_state(), caller=FakeCaller(object_types=out_types),
                llm=llm_picks(["led_lighting"]))


# ── LLM fallback ─────────────────────────────────────────────────────────────
def test_llm_failure_falls_back_to_catalog():
    out = modeler(_state(), caller=FakeCaller(), llm=llm_raises)["modeling_output"]
    retrofits = [s.name for s in out.scenarios if s.name != "baseline"]
    assert len(retrofits) >= 2   # proposed the catalog deterministically


def test_unknown_llm_key_ignored():
    out = modeler(_state(), caller=FakeCaller(),
                  llm=llm_picks(["led_lighting", "teleporter"]))["modeling_output"]
    names = [s.name for s in out.scenarios]
    assert "teleporter" not in names and "led_lighting" in names


# ── Contract: output is Sim-Runner-ready ─────────────────────────────────────
def test_output_is_sim_runner_ready():
    out = modeler(_state(), caller=FakeCaller(),
                  llm=llm_picks(["led_lighting", "efficient_equipment"]))["modeling_output"]
    assert out.baseline_scenario.modifications == []   # baseline runs as-built
    for s in out.scenarios:
        if s.name != "baseline":
            assert s.modifications and s.modifications[0].object_name == "*"
