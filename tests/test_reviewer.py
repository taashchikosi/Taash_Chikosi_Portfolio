"""Reviewer gate — the CBD cohort realism check is the ONE rejection.

The Reviewer must:
  • reject a baseline EUI outside the real cohort p25–p75   → route_to "inputs"
  • approve an in-cohort run                                → route_to "done"
  • when no verified cohort exists, run illustratively (not validated, not faked)
  • when the demoer turns validation off, skip the cohort gate (honest-failure path)
  • report guardrail + citations as proof — they never reject in this pipeline
  (Floor area is bounded to the medium band at the input, so it can't be out of
  range; there is no separate floor-area or citation rejection.)
"""
from __future__ import annotations

from agents.analyzer import analyse
from agents.reviewer import review
from tests.conftest import CARBON, SCENARIO_COSTS, TARIFF, make_sim
from verification.cohort_benchmark import Cohort
from verification.pydantic_schemas import BuildingContext, UtilityData


def _analysis():
    return analyse(
        sim=make_sim(),
        scenario_costs=SCENARIO_COSTS,
        tariff_aud_per_kwh=TARIFF,
        carbon_factor_kg_per_kwh=CARBON,
        tariff_source="AER DMO 2025-26",
        emission_factor_source="NGA 2025 NSW",
    )


def _ctx(floor_area: float = 4_982.0, btype: str = "medium_office") -> BuildingContext:
    return BuildingContext(
        building_type=btype, floor_area_m2=floor_area, ncc_climate_zone=5,
        hvac_system="VAV", current_eui=150.0, annual_energy_cost_aud=100_000.0,
        idf_path="x.idf",
        utility_data=UtilityData(monthly_kwh=[8_333.3] * 12, annual_cost_aud=100_000.0),
    )


# make_sim()'s baseline EUI is 150.0.
IN = Cohort("sydney", "medium", 96, 100.0, 150.0, 200.0, "CBD register")    # 150 within
OUT = Cohort("sydney", "medium", 96, 200.0, 250.0, 300.0, "CBD register")   # 150 below p25


def test_in_cohort_clean_run_is_approved():
    res = review(_analysis(), make_sim(), _ctx(), cohort=IN)
    assert res.approved is True
    assert res.route_to == "done"
    assert res.within_cohort is True and res.cohort_validated is True
    assert res.guardrail_passed and res.citations_present


def test_baseline_outside_cohort_routes_to_inputs():
    # Out-of-range baseline = the demoer's inputs aren't producing a realistic
    # medium-office result → send them back to the inputs, not the Modeler.
    res = review(_analysis(), make_sim(), _ctx(), cohort=OUT)
    assert res.approved is False
    assert res.within_cohort is False
    assert res.realistic is False
    assert res.route_to == "inputs"


def test_no_cohort_is_illustrative_not_validated():
    res = review(_analysis(), make_sim(), _ctx(), cohort=None)
    assert res.approved is True
    assert res.cohort_validated is False
    assert res.within_cohort is None          # nothing to range-check against


def test_run_without_validation_skips_cohort_gate():
    # validate=False ("Run without validation") → the out-of-range baseline is NOT
    # rejected, but the run is left explicitly unvalidated (honest-failure path).
    res = review(_analysis(), make_sim(), _ctx(), cohort=OUT, validate=False)
    assert res.cohort_validated is False
    assert res.within_cohort is None


def test_citations_are_reported_not_a_rejection():
    # Cohort range is the ONLY rejection. A missing citation is REPORTED
    # (citations_present=False) but does not by itself withhold the run.
    analysis = _analysis()
    analysis.analyses[0].emission_factor_source = ""
    res = review(analysis, make_sim(), _ctx(), cohort=IN)
    assert res.citations_present is False
    assert res.approved is True
    assert res.route_to == "done"
