"""Agent 5: Reviewer — verification gate (project plan §3, §7).

ONE rejection: the simulated baseline EUI must land within the range of REAL
disclosed Australian offices of the same size + city — the CBD whole-building
office cohort's p25–p75. A baseline outside that range is not a realistic model,
so its numbers are withheld and the demoer is routed back to adjust the inputs.

Every demoer input feeds this single check — inputs 1–8 move the kWh (via real
EnergyPlus), and floor area moves the EUI denominator. Floor area is bounded to
the medium band at the slider, so it can never itself be out of range; the cohort
check is the sole rejection.

The OWASP LLM06 guardrail + citation presence are still computed and reported as
PROOF the LLM authored no number (every figure traces to the sim) — in this
deterministic pipeline they always pass, so they never reject.
"""
from __future__ import annotations

from typing import Optional

from verification.cohort_benchmark import Cohort
from verification.guardrails import enforce_llm06_guardrail
from verification.pydantic_schemas import (
    AnalyzerOutput, BuildingContext, ReviewResult, SimRunnerOutput,
)


def review(
    analysis: AnalyzerOutput,
    sim_output: SimRunnerOutput,
    building_context: BuildingContext,
    cohort: Optional[Cohort] = None,
    *,
    validate: bool = True,
) -> ReviewResult:
    """Deterministic gate. Returns a ReviewResult with routing decision.

    cohort: the verified CBD cohort for this city + size, or None when none was
        built — the realism range check then can't run and the result is flagged
        cohort_validated=False, never passed off as real.
    validate: False = "Run without validation"; the realism gate is skipped and
        the run is left unvalidated (honest-failure path).
    """
    baseline = sim_output.baseline_result
    baseline_eui = baseline.annual_eui
    cohort_fields = dict(
        baseline_eui=baseline_eui,
        cohort_p25=cohort.p25 if cohort else None,
        cohort_p75=cohort.p75 if cohort else None,
        cohort_median=cohort.median if cohort else None,
        cohort_n=cohort.n if cohort else None,
    )

    # Infra failure ≠ out-of-cohort baseline. If the baseline sim did NOT succeed
    # (EnergyPlus crash/timeout → _failed() returns simulation_status != "success"
    # with a 0.0 EUI, see agents/sim_runner.py ~112-125), the cohort gate must NOT
    # run: a 0.0 EUI would fail the p25–p75 check and be reported as "your inputs
    # produce an unrealistic baseline — adjust the inputs", which is a lie. Surface
    # an honest engine-failure verdict instead and route to human, not to inputs.
    if baseline.simulation_status != "success":
        return ReviewResult(
            approved=False, realistic=True, cohort_validated=False,
            within_cohort=None, floor_area_realistic=True,
            guardrail_passed=True, citations_present=False,
            feedback=("The baseline EnergyPlus simulation did not complete "
                      f"(status: {baseline.simulation_status}), so no verified "
                      "result can be produced. This is an engine/infrastructure "
                      "failure, not a problem with your model inputs."),
            route_to="human", **cohort_fields,
        )

    # Proof (not a rejection): every reported figure traces to a simulated value,
    # and every analysis cites its sources — the "LLM never authored a number"
    # receipts. Always pass in this deterministic pipeline.
    allowed = _collect_simulated_values(sim_output, analysis)
    claim_text = " ".join(
        f"{a.energy_savings_pct} {a.simple_payback_years} "
        f"{a.carbon_reduction_tco2e_per_year} {a.cost_savings_aud_per_year}"
        for a in analysis.analyses
    )
    guard = enforce_llm06_guardrail(claim_text, allowed)
    citations_ok = all(a.tariff_source and a.emission_factor_source
                       for a in analysis.analyses)

    # THE ONLY REJECTION — realism range. The simulated baseline EUI must sit
    # inside the real CBD cohort's p25–p75 for this city + size. Runs only with a
    # verified cohort and when validation is on; out of range routes the demoer
    # back to the inputs to adjust + re-run.
    cohort_validated = cohort is not None and validate
    within_cohort: Optional[bool] = None
    if cohort_validated:
        within_cohort = cohort.contains(baseline_eui)
        if not within_cohort:
            return ReviewResult(
                approved=False, realistic=False, cohort_validated=True,
                within_cohort=False, floor_area_realistic=True,
                guardrail_passed=guard["passed"], citations_present=citations_ok,
                feedback=(f"Baseline EUI {baseline_eui:.1f} kWh/m²·yr is outside "
                          f"the realistic range for {cohort.city.capitalize()} "
                          f"{cohort.size_band} offices (real CBD cohort p25 "
                          f"{cohort.p25:.1f} – p75 {cohort.p75:.1f}, n={cohort.n}). "
                          "The model inputs you set don't produce a realistic "
                          f"{cohort.size_band}-office baseline — adjust the inputs "
                          "and re-run."),
                route_to="inputs", **cohort_fields,
            )

    return ReviewResult(
        approved=True, realistic=(within_cohort is not False),
        cohort_validated=cohort_validated, within_cohort=within_cohort,
        floor_area_realistic=True,
        guardrail_passed=guard["passed"], citations_present=citations_ok,
        feedback=("All checks passed." if cohort_validated else
                  "Checks passed; baseline not range-validated (no real CBD "
                  "cohort for this city/size yet — illustrative)."),
        route_to="done", **cohort_fields,
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
