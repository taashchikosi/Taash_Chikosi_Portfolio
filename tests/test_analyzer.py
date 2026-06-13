"""Analyzer deterministic business-case math.

Every figure is hand-calculated here and checked against the implementation, so
the financial numbers in the final report are reproducible — which is exactly
what lets the Reviewer's LLM06 guardrail trust them.
"""
from __future__ import annotations

import pytest

from agents.analyzer import analyse
from tests.conftest import CARBON, SCENARIO_COSTS, TARIFF, make_sim


def _annuity_npv(annual: float, cost: float, years: int = 25, rate: float = 0.07) -> float:
    """Independent NPV so the test doesn't just re-run the implementation's code."""
    pv = sum(annual / (1 + rate) ** t for t in range(1, years + 1))
    return pv - cost


@pytest.fixture
def out():
    return analyse(
        sim=make_sim(),
        scenario_costs=SCENARIO_COSTS,
        tariff_aud_per_kwh=TARIFF,
        carbon_factor_kg_per_kwh=CARBON,
        tariff_source="AER DMO 2025-26",
        emission_factor_source="NGA 2025 NSW",
    )


def _by_name(out, name):
    return next(a for a in out.analyses if a.scenario_name == name)


def test_savings_kwh_and_pct(out):
    led = _by_name(out, "LED+HVAC")
    assert led.energy_savings_kwh == 20_000.0
    assert led.energy_savings_pct == 20.0


def test_cost_savings_and_payback(out):
    led = _by_name(out, "LED+HVAC")
    # 20,000 kWh × 0.30 AUD = 6,000 AUD/yr; 30,000 cost ÷ 6,000 = 5.0 yr
    assert led.cost_savings_aud_per_year == 6_000.0
    assert led.simple_payback_years == 5.0


def test_carbon_reduction(out):
    led = _by_name(out, "LED+HVAC")
    # 20,000 kWh × 0.66 kg ÷ 1000 = 13.2 tCO2e
    assert led.carbon_reduction_tco2e_per_year == 13.2


def test_npv_matches_independent_calc(out):
    led = _by_name(out, "LED+HVAC")
    assert led.npv_aud == pytest.approx(_annuity_npv(6_000.0, 30_000), abs=0.01)


def test_zero_savings_gives_sentinel_payback(out):
    nosave = _by_name(out, "NoSave")
    assert nosave.simple_payback_years == 999.0   # ∞ payback sentinel


def test_recommends_shortest_payback(out):
    # LED+HVAC (5.0 yr) beats Glazing (15.0 yr); NoSave excluded as non-viable.
    assert out.recommended_package.scenario_name == "LED+HVAC"


def test_totals_aggregate_all_scenarios(out):
    # 6,000 + 3,000 + 0 = 9,000 AUD ; 13.2 + 6.6 + 0 = 19.8 tCO2e
    assert out.total_potential_savings_aud == 9_000.0
    assert out.total_carbon_reduction_tco2e == 19.8


def test_analyses_sorted_by_payback(out):
    paybacks = [a.simple_payback_years for a in out.analyses]
    assert paybacks == sorted(paybacks)


def test_raises_when_no_non_baseline_scenarios():
    from tests.conftest import make_result
    from verification.pydantic_schemas import SimRunnerOutput
    base = make_result("baseline", 100_000)
    only_base = SimRunnerOutput(baseline_result=base, results=[base])
    with pytest.raises(ValueError):
        analyse(only_base, {}, TARIFF, CARBON, "t", "e")
