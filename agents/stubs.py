"""Phase-2 placeholders for agents 1-4.

Each returns schema-valid output so the FastAPI runner + frontend can be built
and demoed end-to-end before the real LLM logic lands. They emit SSE events via
state["emit"] exactly like the finished agents will, so nothing downstream changes
when these are replaced.

Replace order: retriever → modeler → sim_runner → analyzer (Phase 2).
Reviewer is already real (agents/reviewer.py).
"""
from __future__ import annotations

from agents.supervisor import RunState
from verification.pydantic_schemas import (
    AnalyzerOutput, BuildingContext, IDFModification, ModelingOutput,
    RetrofitAnalysis, RetrofitScenario, SimRunnerOutput, SimulationResult,
    UtilityData,
)


def _emit(state: RunState, agent: str, status: str, payload: dict) -> None:
    fn = state.get("emit")
    if fn:
        fn(agent, status, payload)


def retriever(state: RunState) -> RunState:
    _emit(state, "retriever", "started", {})
    u = state["raw_utility"]
    state["building_context"] = BuildingContext(
        building_type="small_office", floor_area_m2=511.0, ncc_climate_zone=5,
        hvac_system="packaged DX + gas heat", current_eui=180.0,
        annual_energy_cost_aud=u["annual_cost_aud"],
        idf_path=state["idf_path"],
        utility_data=UtilityData(**u),
    )
    _emit(state, "retriever", "completed",
          {"building_type": "small_office", "climate_zone": 5})
    return state


def modeler(state: RunState) -> RunState:
    _emit(state, "modeler", "started", {})
    baseline = RetrofitScenario(
        name="baseline", description="As-built", modifications=[],
        estimated_cost_aud=0, code_compliance=True, ncc_reference="—")
    scenarios = [
        baseline,
        RetrofitScenario(name="heat_pump", description="Replace gas heat with ASHP",
                         modifications=[IDFModification(
                             object_type="Coil:Heating:Fuel", object_name="Main Heat",
                             field="Nominal_Efficiency", new_value="3.5")],
                         estimated_cost_aud=42000, code_compliance=True,
                         ncc_reference="NCC 2022 J6D (VERIFY)"),
        RetrofitScenario(name="glazing", description="Double glazing upgrade",
                         modifications=[IDFModification(
                             object_type="WindowMaterial:SimpleGlazingSystem",
                             object_name="Win", field="UFactor", new_value="1.8")],
                         estimated_cost_aud=28000, code_compliance=True,
                         ncc_reference="NCC 2022 J4D (VERIFY)"),
    ]
    state["modeling_output"] = ModelingOutput(
        scenarios=scenarios, baseline_scenario=baseline, modeling_confidence=0.8)
    _emit(state, "modeler", "awaiting_approval",
          {"scenarios": [s.name for s in scenarios]})
    return state


def sim_runner(state: RunState) -> RunState:
    _emit(state, "sim_runner", "started", {})
    measured = state["raw_utility"]["monthly_kwh"]
    base = SimulationResult(
        scenario_name="baseline", annual_energy_kwh=sum(measured),
        monthly_energy_kwh=measured, annual_eui=180.0, peak_demand_kw=45.0,
        energy_end_uses={"Heating": 22000, "Cooling": 14000, "InteriorLights": 9000},
        simulation_status="success", simulation_runtime_seconds=0.0)
    hp = SimulationResult(
        scenario_name="heat_pump", annual_energy_kwh=sum(measured) * 0.7,
        monthly_energy_kwh=[m * 0.7 for m in measured], annual_eui=126.0,
        peak_demand_kw=38.0, energy_end_uses={"Heating": 8000, "Cooling": 14000},
        simulation_status="success", simulation_runtime_seconds=0.0)
    state["sim_output"] = SimRunnerOutput(results=[base, hp], baseline_result=base)
    _emit(state, "sim_runner", "completed", {"scenarios_run": 2})
    return state


def analyzer(state: RunState) -> RunState:
    _emit(state, "analyzer", "started", {})
    sim = state["sim_output"]
    base = sim.baseline_result
    hp = next(r for r in sim.results if r.scenario_name == "heat_pump")
    saved = base.annual_energy_kwh - hp.annual_energy_kwh
    hp_analysis = RetrofitAnalysis(
        scenario_name="heat_pump", energy_savings_kwh=round(saved, 1),
        energy_savings_pct=round(saved / base.annual_energy_kwh * 100, 1),
        cost_savings_aud_per_year=round(saved * 0.30, 1), retrofit_cost_aud=42000,
        simple_payback_years=round(42000 / (saved * 0.30), 1),
        npv_aud=0.0, carbon_reduction_tco2e_per_year=round(saved * 0.66 / 1000, 2),
        tariff_source="CDR Energy PRD (stub)", emission_factor_source="NGA 2025 NSW",
        confidence_score=0.8)
    state["analysis"] = AnalyzerOutput(
        analyses=[hp_analysis], recommended_package=hp_analysis,
        total_potential_savings_aud=hp_analysis.cost_savings_aud_per_year,
        total_carbon_reduction_tco2e=hp_analysis.carbon_reduction_tco2e_per_year)
    _emit(state, "analyzer", "completed",
          {"recommended": "heat_pump", "payback_years": hp_analysis.simple_payback_years})
    return state
