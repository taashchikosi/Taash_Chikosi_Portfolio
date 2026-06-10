"""Shared Pydantic output schemas for the agent pipeline (project plan §3).

Every agent emits one of these; the LangGraph state carries them between nodes.
Validation here is the deterministic governance layer — bad values never reach
EnergyPlus or the final report.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class CodeReference(BaseModel):
    document: str          # "NCC 2022 Volume One"
    section: str           # "J4D3"
    clause_text: str
    page: int | None = None
    relevance_score: float = 0.0


class UtilityData(BaseModel):
    monthly_kwh: list[float] = Field(..., min_length=12, max_length=12)
    annual_cost_aud: float
    tariff_type: str = "single rate"

    @property
    def annual_kwh(self) -> float:
        return sum(self.monthly_kwh)


class BuildingContext(BaseModel):
    building_type: str
    floor_area_m2: float
    ncc_climate_zone: int = Field(..., ge=1, le=8)
    hvac_system: str
    current_eui: float
    annual_energy_cost_aud: float
    applicable_codes: list[CodeReference] = []
    idf_path: str
    utility_data: UtilityData


class IDFModification(BaseModel):
    object_type: str
    object_name: str
    field: str
    new_value: str


class RetrofitScenario(BaseModel):
    name: str
    description: str
    modifications: list[IDFModification]
    estimated_cost_aud: float
    code_compliance: bool
    ncc_reference: str


class ModelingOutput(BaseModel):
    scenarios: list[RetrofitScenario] = Field(..., min_length=3, max_length=6)
    baseline_scenario: RetrofitScenario
    modeling_confidence: float = Field(..., ge=0, le=1)


class SimulationResult(BaseModel):
    scenario_name: str
    annual_energy_kwh: float
    monthly_energy_kwh: list[float] = Field(..., min_length=12, max_length=12)
    annual_eui: float
    peak_demand_kw: float = 0.0
    energy_end_uses: dict[str, float] = {}
    simulation_status: Literal["success", "failed", "timeout"]
    simulation_runtime_seconds: float = 0.0


class SimRunnerOutput(BaseModel):
    results: list[SimulationResult]
    baseline_result: SimulationResult


class RetrofitAnalysis(BaseModel):
    scenario_name: str
    energy_savings_kwh: float
    energy_savings_pct: float
    cost_savings_aud_per_year: float
    retrofit_cost_aud: float
    simple_payback_years: float
    npv_aud: float
    carbon_reduction_tco2e_per_year: float
    tariff_source: str
    emission_factor_source: str
    confidence_score: float = Field(..., ge=0, le=1)


class AnalyzerOutput(BaseModel):
    analyses: list[RetrofitAnalysis]
    recommended_package: RetrofitAnalysis
    total_potential_savings_aud: float
    total_carbon_reduction_tco2e: float


class ReviewResult(BaseModel):
    approved: bool
    calibration_passed: bool
    nmbe_pct: float | None = None
    cvrmse_pct: float | None = None
    guardrail_passed: bool
    citations_present: bool
    feedback: str = ""
    route_to: Literal["modeler", "analyzer", "done", "human"] = "done"
