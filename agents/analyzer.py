"""Agent 4: Analyzer — turns simulation numbers into a business case (plan §3).

Deterministic financial math (no LLM): savings, payback, NPV, carbon. Every
figure here is reproducible and traceable — that's what lets the Reviewer's
LLM06 guardrail pass. Tariff + carbon factors come from cited sources.
"""
from __future__ import annotations

from agents.supervisor import RunState
from verification.pydantic_schemas import (
    AnalyzerOutput, RetrofitAnalysis, SimRunnerOutput,
)

NPV_YEARS = 25
DISCOUNT_RATE = 0.07


def _npv(annual_savings: float, cost: float,
         years: int = NPV_YEARS, rate: float = DISCOUNT_RATE) -> float:
    pv = sum(annual_savings / (1 + rate) ** t for t in range(1, years + 1))
    return pv - cost


def analyse(
    sim: SimRunnerOutput,
    scenario_costs: dict[str, float],
    tariff_aud_per_kwh: float,
    carbon_factor_kg_per_kwh: float,
    tariff_source: str,
    emission_factor_source: str,
) -> AnalyzerOutput:
    """Compute the full business case for every non-baseline scenario."""
    base = sim.baseline_result
    analyses: list[RetrofitAnalysis] = []

    for result in sim.results:
        if result.scenario_name == base.scenario_name:
            continue
        saved_kwh = base.annual_energy_kwh - result.annual_energy_kwh
        pct = (saved_kwh / base.annual_energy_kwh * 100) if base.annual_energy_kwh else 0.0
        cost_savings = saved_kwh * tariff_aud_per_kwh
        retrofit_cost = scenario_costs.get(result.scenario_name, 0.0)
        payback = (retrofit_cost / cost_savings) if cost_savings > 0 else float("inf")
        carbon = saved_kwh * carbon_factor_kg_per_kwh / 1000  # tCO2e

        analyses.append(RetrofitAnalysis(
            scenario_name=result.scenario_name,
            energy_savings_kwh=round(saved_kwh, 1),
            energy_savings_pct=round(pct, 1),
            cost_savings_aud_per_year=round(cost_savings, 2),
            retrofit_cost_aud=retrofit_cost,
            simple_payback_years=round(payback, 1) if payback != float("inf") else 999.0,
            npv_aud=round(_npv(cost_savings, retrofit_cost), 2),
            carbon_reduction_tco2e_per_year=round(carbon, 2),
            tariff_source=tariff_source,
            emission_factor_source=emission_factor_source,
            confidence_score=0.85,
        ))

    if not analyses:
        raise ValueError("no non-baseline scenarios to analyse")

    # Recommend the shortest-payback scenario (with positive savings)
    viable = [a for a in analyses if a.simple_payback_years < 999]
    recommended = min(viable or analyses, key=lambda a: a.simple_payback_years)

    return AnalyzerOutput(
        analyses=sorted(analyses, key=lambda a: a.simple_payback_years),
        recommended_package=recommended,
        total_potential_savings_aud=round(
            sum(a.cost_savings_aud_per_year for a in analyses), 2),
        total_carbon_reduction_tco2e=round(
            sum(a.carbon_reduction_tco2e_per_year for a in analyses), 2),
    )


def analyzer(state: RunState) -> RunState:
    """LangGraph node wrapper. Pulls tariff + carbon factors from state context."""
    emit = state.get("emit")
    if emit:
        emit("analyzer", "started", {})

    sim: SimRunnerOutput = state["sim_output"]
    ctx = state.get("analysis_context", {})
    out = analyse(
        sim=sim,
        scenario_costs=ctx.get("scenario_costs", {}),
        tariff_aud_per_kwh=ctx.get("tariff_aud_per_kwh", 0.30),
        carbon_factor_kg_per_kwh=ctx.get("carbon_factor_kg_per_kwh", 0.66),
        tariff_source=ctx.get("tariff_source", "CDR Energy PRD"),
        emission_factor_source=ctx.get("emission_factor_source", "NGA 2025 NSW"),
    )
    state["analysis"] = out
    if emit:
        emit("analyzer", "completed", {
            "recommended": out.recommended_package.scenario_name,
            "payback_years": out.recommended_package.simple_payback_years,
            "carbon_tco2e": out.recommended_package.carbon_reduction_tco2e_per_year,
        })
    return state
