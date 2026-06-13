"""Reviewer deterministic gate + routing.

The Reviewer must:
  • block an uncalibrated model         → route_to "modeler"
  • block missing citations             → route_to "analyzer"
  • approve a clean, cited, calibrated run → route_to "done"
"""
from __future__ import annotations

from agents.analyzer import analyse
from agents.reviewer import review
from tests.conftest import CARBON, SCENARIO_COSTS, TARIFF, make_sim


def _analysis():
    return analyse(
        sim=make_sim(),
        scenario_costs=SCENARIO_COSTS,
        tariff_aud_per_kwh=TARIFF,
        carbon_factor_kg_per_kwh=CARBON,
        tariff_source="AER DMO 2025-26",
        emission_factor_source="NGA 2025 NSW",
    )


# Baseline is 100,000 kWh spread evenly → each month 8,333.3 kWh.
MEASURED_MATCH = [100_000 / 12] * 12


def test_clean_run_is_approved():
    sim = make_sim()
    res = review(_analysis(), sim, measured_monthly=MEASURED_MATCH)
    assert res.approved is True
    assert res.route_to == "done"
    assert res.calibration_passed and res.guardrail_passed and res.citations_present


def test_uncalibrated_model_routes_to_modeler():
    sim = make_sim()
    # Measured is double the simulated → ~50 % NMBE → calibration fails.
    bad_measured = [v * 2 for v in MEASURED_MATCH]
    res = review(_analysis(), sim, measured_monthly=bad_measured)
    assert res.approved is False
    assert res.calibration_passed is False
    assert res.route_to == "modeler"


def test_missing_citation_routes_to_analyzer():
    sim = make_sim()
    analysis = _analysis()
    # Strip a required source → citation check must fail (calibration still OK).
    analysis.analyses[0].emission_factor_source = ""
    res = review(analysis, sim, measured_monthly=MEASURED_MATCH)
    assert res.approved is False
    assert res.calibration_passed is True
    assert res.citations_present is False
    assert res.route_to == "analyzer"
