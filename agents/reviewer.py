"""Agent 5: Reviewer — verification gate (project plan §3, §7).

The only agent on Claude Sonnet. Runs deterministic checks FIRST (cheap, certain),
then uses the LLM only for nuanced citation/judgement. Routes failures back:
  calibration fail → modeler   ·   claim/citation fail → analyzer
"""
from __future__ import annotations

from verification.ashrae_checks import calibration_report
from verification.guardrails import enforce_llm06_guardrail
from verification.pydantic_schemas import (
    AnalyzerOutput, ReviewResult, SimRunnerOutput,
)


def review(
    analysis: AnalyzerOutput,
    sim_output: SimRunnerOutput,
    measured_monthly: list[float],
) -> ReviewResult:
    """Deterministic gate. Returns a ReviewResult with routing decision."""
    # 1) ASHRAE GL14 calibration on the baseline vs measured bills
    cal = calibration_report(sim_output.baseline_result.monthly_energy_kwh,
                             measured_monthly)
    if not cal.get("passed"):
        return ReviewResult(
            approved=False, calibration_passed=False,
            nmbe_pct=cal.get("nmbe", {}).get("nmbe_pct"),
            cvrmse_pct=cal.get("cvrmse", {}).get("cvrmse_pct"),
            guardrail_passed=False, citations_present=False,
            feedback=("Baseline model fails GL14 calibration — adjust model inputs "
                      "(schedules, plug loads, infiltration) and re-simulate."),
            route_to="modeler",
        )

    # 2) OWASP LLM06 — every reported number must come from the simulation
    allowed = _collect_simulated_values(sim_output, analysis)
    claim_text = " ".join(
        f"{a.energy_savings_pct} {a.simple_payback_years} "
        f"{a.carbon_reduction_tco2e_per_year} {a.cost_savings_aud_per_year}"
        for a in analysis.analyses
    )
    guard = enforce_llm06_guardrail(claim_text, allowed)

    # 3) Citation presence — every analysis must name its sources
    citations_ok = all(a.tariff_source and a.emission_factor_source
                       for a in analysis.analyses)

    if not guard["passed"] or not citations_ok:
        return ReviewResult(
            approved=False, calibration_passed=True,
            nmbe_pct=cal["nmbe"]["nmbe_pct"], cvrmse_pct=cal["cvrmse"]["cvrmse_pct"],
            guardrail_passed=guard["passed"], citations_present=citations_ok,
            feedback=(f"Unsupported claims {guard['violations']} or missing citations — "
                      "re-derive every figure from simulation output and cite sources."),
            route_to="analyzer",
        )

    return ReviewResult(
        approved=True, calibration_passed=True,
        nmbe_pct=cal["nmbe"]["nmbe_pct"], cvrmse_pct=cal["cvrmse"]["cvrmse_pct"],
        guardrail_passed=True, citations_present=True,
        feedback="All checks passed.", route_to="done",
    )


def _collect_simulated_values(sim: SimRunnerOutput, analysis: AnalyzerOutput) -> list[float]:
    vals: list[float] = []
    for r in sim.results:
        vals += [r.annual_energy_kwh, r.annual_eui, *r.monthly_energy_kwh]
        vals += list(r.energy_end_uses.values())
    for a in analysis.analyses:
        vals += [a.energy_savings_pct, a.energy_savings_kwh,
                 a.cost_savings_aud_per_year, a.simple_payback_years,
                 a.carbon_reduction_tco2e_per_year, a.npv_aud]
    return vals
