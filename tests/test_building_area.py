"""Authoritative floor-area extraction + Bug #12 reconciliation.

Two layers, no EnergyPlus needed:
  1. The pure .eio / .htm parsers (header-driven, multiplier-aware) against
     synthetic fixtures that reproduce the real EnergyPlus column structure.
  2. The Sim Runner's reconciliation: a fake MCP caller that reports an
     authoritative area different from the provisional one must correct the
     context (area → size band → EUI) and re-cost the measures.
"""
from __future__ import annotations

from agents.retrofit_catalog import CATALOG
from agents.sim_runner import sim_runner
from mcp_server.tools.results_tools import (
    area_from_tabular_htm, net_conditioned_area_from_eio,
)
from verification.pydantic_schemas import (
    BuildingContext, IDFModification, ModelingOutput, RetrofitScenario, UtilityData,
)

# A structurally faithful .eio: real column names, but ORDER DELIBERATELY DIFFERENT
# from EnergyPlus' real layout to prove the parser is header-driven, not positional.
# Zone List Multiplier on MIDFLOOR is 5 (the DOE middle-floor multiplier pattern).
_EIO = """\
Program Version,EnergyPlus, Version 24.2.0-e7ecb2d53b
! <Zone Information>, Zone Name, Type, Zone Multiplier, Zone List Multiplier, Floor Area {m2}, Volume {m3}, Part of Total Building Area
 Zone Information, ATTIC,1,1,1,567.98,720.19,No
 Zone Information, CORE_ZN,1,1,1,149.66,456.46,Yes
 Zone Information, PERIMETER_ZN_1,1,1,1,113.45,346.02,Yes
 Zone Information, MIDFLOOR,1,1,5,100.00,300.00,Yes
"""
# Conditioned (Part=Yes): 149.66 + 113.45 + 100.00×(1×5) = 763.11
_EXPECTED_AREA = 763.1


def test_eio_area_is_header_driven_and_multiplier_aware():
    parsed = net_conditioned_area_from_eio(_EIO)
    assert parsed is not None
    assert parsed["area_m2"] == _EXPECTED_AREA
    # The unconditioned attic is excluded from the conditioned total.
    included = {z["zone"] for z in parsed["zones"] if z["included"]}
    assert "ATTIC" not in included
    assert "CORE_ZN" in included


def test_eio_column_reorder_still_resolves():
    """Move Part-of-Total before Floor Area: header-driven lookup must still work."""
    reordered = _EIO.replace(
        "Floor Area {m2}, Volume {m3}, Part of Total Building Area",
        "Part of Total Building Area, Floor Area {m2}, Volume {m3}",
    ).replace(  # realign the data rows to the new column order
        "567.98,720.19,No", "No,567.98,720.19").replace(
        "149.66,456.46,Yes", "Yes,149.66,456.46").replace(
        "113.45,346.02,Yes", "Yes,113.45,346.02").replace(
        "100.00,300.00,Yes", "Yes,100.00,300.00")
    parsed = net_conditioned_area_from_eio(reordered)
    assert parsed["area_m2"] == _EXPECTED_AREA


def test_eio_none_when_no_zone_information():
    assert net_conditioned_area_from_eio("Program Version,EnergyPlus\n") is None


def test_tabular_htm_fallback():
    html = ('<tr><td>Net Conditioned Building Area</td>'
            '<td align="right">    4982.19</td></tr>')
    assert area_from_tabular_htm(html) == 4982.19
    assert area_from_tabular_htm("<td>nothing here</td>") is None


# ── Reconciliation (Bug #12) via a fake MCP caller ─────────────────────────
class _ReconcilingCaller:
    """Fake caller that reports an authoritative area (4,982 m²) unlike the
    provisional one (511 m²), so the reconciliation path actually fires."""

    AUTH_AREA = 4982.0
    BASELINE_ANNUAL_KWH = 685_520.0

    async def __call__(self, name, **kw):
        if name == "clone_idf":
            return {"cloned_path": f"/work/{kw['scenario_name']}.idf"}
        if name == "modify_idf_component":
            return {"object_name": kw["object_name"]}
        if name == "run_simulation":
            return {"job_id": f"{kw['scenario_name']}-j", "status": "running"}
        if name == "get_simulation_status":
            return {"status": "success", "runtime_seconds": 18.0,
                    "output_dir": "/out/" + kw["job_id"], "error": None}
        if name == "get_annual_energy":
            return {"total_kwh": self.BASELINE_ANNUAL_KWH}
        if name == "get_monthly_energy":
            return {"monthly_kwh": [self.BASELINE_ANNUAL_KWH / 12] * 12}
        if name == "get_eui":  # provisional (wrong) area → ~10× too high
            return {"eui_kwh_m2": round(self.BASELINE_ANNUAL_KWH / kw["floor_area_m2"], 1)}
        if name == "get_energy_end_uses":
            return {"end_uses_kwh": {"Cooling": 1000.0}}
        if name == "get_building_area":
            return {"net_conditioned_area_m2": self.AUTH_AREA}
        return {}


def _medium_state_with_wrong_area():
    utility = UtilityData(monthly_kwh=[60_000.0] * 12, annual_cost_aud=200_000.0)
    ctx = BuildingContext(
        building_type="small_office",          # MISclassified on the 511 fallback
        floor_area_m2=511.0,                    # provisional (autocalc fallback)
        ncc_climate_zone=5, hvac_system="VAV",
        current_eui=round(utility.annual_kwh / 511.0, 1),
        annual_energy_cost_aud=200_000.0,
        idf_path="data/reference_buildings/RefBldgMediumOffice.idf",
        utility_data=utility,
    )
    measures = [
        RetrofitScenario(name="baseline", description="as-built", modifications=[],
                         estimated_cost_aud=0.0, code_compliance=False,
                         ncc_reference="—"),
        RetrofitScenario(
            name="led_lighting", description="LED",
            modifications=[IDFModification(object_type="Lights", object_name="*",
                                           field="Watts_per_Floor_Area", new_value="4.5")],
            estimated_cost_aud=CATALOG["led_lighting"].estimate_cost(511.0),
            code_compliance=True, ncc_reference="J7D3"),
        RetrofitScenario(
            name="efficient_equipment", description="Plug loads",
            modifications=[IDFModification(object_type="ElectricEquipment",
                                           object_name="*",
                                           field="Watts_per_Floor_Area", new_value="8.0")],
            estimated_cost_aud=CATALOG["efficient_equipment"].estimate_cost(511.0),
            code_compliance=False, ncc_reference="—"),
    ]
    return {
        "run_id": "t", "idf_path": ctx.idf_path,
        "epw_path": "data/reference_buildings/weather/AUS_NSW_Sydney.epw",
        "building_context": ctx,
        "modeling_output": ModelingOutput(
            scenarios=measures, baseline_scenario=measures[0],
            modeling_confidence=0.7),
    }


def test_reconciliation_corrects_area_band_eui_and_cost():
    state = _medium_state_with_wrong_area()
    sim_runner(state, caller=_ReconcilingCaller())
    out = state["sim_output"]

    ctx = state["building_context"]
    # area → size band → EUI all corrected off the authoritative area
    assert ctx.floor_area_m2 == 4982.0
    assert ctx.building_type == "medium_office"          # reclassified from area
    # baseline EUI is now the real ~137.6, not the ~1,341 the wrong area produced
    assert out.baseline_result.annual_eui == round(685_520.0 / 4982.0, 1)
    assert 130 < out.baseline_result.annual_eui < 145
    # measures re-costed at the true area (much higher than the 511 m² estimate)
    led = next(s for s in state["modeling_output"].scenarios if s.name == "led_lighting")
    assert led.estimated_cost_aud == CATALOG["led_lighting"].estimate_cost(4982.0)
    assert led.estimated_cost_aud > CATALOG["led_lighting"].estimate_cost(511.0)
