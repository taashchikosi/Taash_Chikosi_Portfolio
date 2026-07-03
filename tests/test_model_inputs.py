"""The six editable model inputs: schema, building-aware application, and the
floor-area override wiring.

No EnergyPlus — a recording fake MCP caller proves the *orchestration*: which
tools fire with which fields, that an unedited run is a true no-op, and that an
edited run applies its inputs to the baseline clone before the sim.
"""
from __future__ import annotations

import asyncio

import pytest

from agents.model_inputs import apply_model_inputs
from agents.sim_runner import sim_runner
from verification.pydantic_schemas import (
    BuildingContext, ModelingOutput, ModelInputs, RetrofitScenario, UtilityData,
)


class RecordingCaller:
    """Records every (tool, kwargs). Canned data; get_building_area returns
    nothing so reconciliation only fires when a test wants it."""

    def __init__(self, monthly=None, area=None):
        self.calls: list[tuple[str, dict]] = []
        self._monthly = monthly or [1_000.0] * 12
        self._area = area

    async def __call__(self, name, **kw):
        self.calls.append((name, kw))
        if name == "clone_idf":
            return {"cloned_path": f"/work/{kw['scenario_name']}.idf"}
        if name == "modify_idf_component":
            return {"objects_modified": 3, "field": kw["field"]}
        if name == "set_construction_u_value":
            return {"achieved_u": kw["target_u"], "surface_class": kw["surface_class"]}
        if name == "run_simulation":
            return {"job_id": f"{kw['scenario_name']}-j", "status": "running"}
        if name == "get_simulation_status":
            return {"status": "success", "runtime_seconds": 1.0,
                    "output_dir": "/out/" + kw["job_id"], "error": None}
        if name == "get_annual_energy":
            return {"total_kwh": 100_000.0}
        if name == "get_monthly_energy":
            return {"monthly_kwh": list(self._monthly)}
        if name == "get_eui":
            return {"eui_kwh_m2": round(100_000.0 / kw["floor_area_m2"], 1)}
        if name == "get_energy_end_uses":
            return {"end_uses_kwh": {}}
        if name == "get_building_area":
            return {"net_conditioned_area_m2": self._area} if self._area else {}
        return {}

    def fields(self):
        return [kw["field"] for n, kw in self.calls if n == "modify_idf_component"]

    def clones(self):
        return [kw["scenario_name"] for n, kw in self.calls if n == "clone_idf"]


# ── Schema ──────────────────────────────────────────────────────────────────
def test_energy_edits_vs_floor_area():
    assert not ModelInputs().has_any_edit()
    assert not ModelInputs(floor_area_m2=3_000).has_energy_edits()  # area ≠ energy
    assert ModelInputs(floor_area_m2=3_000).has_any_edit()
    assert ModelInputs(hvac_cop=3.0).has_energy_edits()


def test_ranges_fail_closed():
    with pytest.raises(Exception):
        ModelInputs(hvac_cop=0.1)          # below 1.5
    with pytest.raises(Exception):
        ModelInputs(window_shgc=2.0)       # above 0.9


# ── Building-aware application ──────────────────────────────────────────────
def test_apply_maps_to_real_fields_and_is_coil_aware():
    caller = RecordingCaller()
    inputs = ModelInputs(hvac_cop=3.0, infiltration_ach=0.5, lighting_w_m2=6.0,
                         window_u=2.0, wall_u=0.4, roof_u=0.25)
    asyncio.run(apply_model_inputs(caller, "/work/x.idf", inputs))
    f = caller.fields()
    # COP — both DX:TwoSpeed speeds AND DX:SingleSpeed attempted (coil-agnostic).
    assert "High_Speed_Gross_Rated_Cooling_COP" in f
    assert "Low_Speed_Gross_Rated_Cooling_COP" in f
    assert "Gross_Rated_Cooling_COP" in f
    # Infiltration — method switched BEFORE the ACH value (else ACH is ignored).
    assert f.index("Design_Flow_Rate_Calculation_Method") < f.index("Air_Changes_per_Hour")
    # Internal gains — only lighting was set (equipment left untouched).
    assert f.count("Watts_per_Floor_Area") == 1
    assert "UFactor" in f
    # Envelope U via the dedicated tool, both surfaces.
    surfaces = {kw["surface_class"] for n, kw in caller.calls
                if n == "set_construction_u_value"}
    assert surfaces == {"wall", "roof"}


def test_apply_noop_when_unedited():
    caller = RecordingCaller()
    asyncio.run(apply_model_inputs(caller, "/work/x.idf", ModelInputs()))
    assert caller.calls == []


# ── Floor-area override wiring in the Sim Runner ───────────────────────────
def _state(model_inputs, area=None):
    utility = UtilityData(monthly_kwh=[5_000.0] * 12, annual_cost_aud=18_000.0)
    ctx = BuildingContext(
        building_type="medium_office", floor_area_m2=4_982.0, ncc_climate_zone=5,
        hvac_system="VAV", current_eui=12.0, annual_energy_cost_aud=18_000.0,
        idf_path="data/reference_buildings/RefBldgMediumOffice.idf",
        utility_data=utility)
    scns = [
        RetrofitScenario(name="baseline", description="b", modifications=[],
                         estimated_cost_aud=0.0, code_compliance=False, ncc_reference="—"),
        RetrofitScenario(name="led_lighting", description="LED", modifications=[],
                         estimated_cost_aud=1.0, code_compliance=True, ncc_reference="J7D3"),
        RetrofitScenario(name="efficient_equipment", description="EE", modifications=[],
                         estimated_cost_aud=1.0, code_compliance=False, ncc_reference="—"),
    ]
    return {
        "run_id": "t", "idf_path": ctx.idf_path,
        "epw_path": "data/reference_buildings/weather/AUS_NSW_Sydney.epw",
        "building_context": ctx, "model_inputs": model_inputs,
        "modeling_output": ModelingOutput(scenarios=scns, baseline_scenario=scns[0],
                                          modeling_confidence=0.7),
    }


def test_edited_baseline_gets_model_inputs_applied():
    # Energy edits are applied to the baseline clone before its sim; the Reviewer's
    # CBD-cohort gate then judges the resulting EUI (no reference-baseline sim
    # is run).
    state = _state(ModelInputs(hvac_cop=2.5))
    caller = RecordingCaller()
    sim_runner(state, caller)
    on_base = [kw["field"] for n, kw in caller.calls
               if n == "modify_idf_component" and kw["idf_path"] == "/work/baseline.idf"]
    assert "High_Speed_Gross_Rated_Cooling_COP" in on_base
    assert not any("calref" in c for c in caller.clones())  # no reference-baseline sim


def test_floor_area_drives_a_real_geometry_resize():
    # Floor area now goes through scale_floor_area (a REAL geometry resize), not a
    # denominator override: setting it fires the tool on the baseline clone with
    # the target area, before the sim runs.
    state = _state(ModelInputs(floor_area_m2=3_000.0))
    caller = RecordingCaller(area=4_982.0)
    sim_runner(state, caller)
    base_scale = [kw for n, kw in caller.calls
                  if n == "scale_floor_area" and kw["idf_path"] == "/work/baseline.idf"]
    assert base_scale, "floor area should resize the baseline geometry"
    assert abs(base_scale[0]["target_area_m2"] - 3_000.0) < 1e-6
