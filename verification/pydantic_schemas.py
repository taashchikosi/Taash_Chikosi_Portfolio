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


class ModelInputs(BaseModel):
    """The demo's six editable model inputs (spec §3). Each is None unless the
    user moved it OFF its calibrated default — so an untouched run is a true
    no-op (the default model lands inside the cohort range), and any set value is
    applied to the baseline IDF through REAL EnergyPlus before the sim. The LLM
    authors none of these; they are physical model parameters.

    Ranges fail closed (a bad value is rejected, never silently clamped to a
    plausible-looking number). Defaults live in the frontend catalog as the
    per-building calibrated set-points; the backend only applies what's sent.
    """
    hvac_cop: float | None = Field(None, ge=1.5, le=6.0)            # ↓ → ↑ EUI
    infiltration_ach: float | None = Field(None, ge=0.05, le=3.0)   # ↑ → ↑ EUI
    lighting_w_m2: float | None = Field(None, ge=1.0, le=25.0)      # ↑ → ↑ EUI
    equipment_w_m2: float | None = Field(None, ge=1.0, le=30.0)     # ↑ → ↑ EUI
    window_u: float | None = Field(None, ge=0.5, le=7.0)            # ↑ → ↑ EUI
    window_shgc: float | None = Field(None, ge=0.1, le=0.9)         # ↑ → ↑ cooling EUI
    wall_u: float | None = Field(None, ge=0.1, le=3.0)             # ↑ → ↑ EUI
    roof_u: float | None = Field(None, ge=0.1, le=3.0)            # ↑ → ↑ EUI
    # Floor area moves the EUI denominator (EUI = kWh / area), so it shifts the
    # baseline within/outside the CBD cohort range. Bounded to the medium-office
    # band (large is dropped from the demo), so the input itself can never be out
    # of range — the cohort check is the only realism rejection.
    floor_area_m2: float | None = Field(None, ge=2_500.0, le=10_000.0)

    def has_energy_edits(self) -> bool:
        """True if any of the eight kWh-moving inputs is set (floor area is
        denominator-only, so it's tracked separately)."""
        return any(getattr(self, f) is not None for f in ENERGY_INPUT_FIELDS)

    def has_any_edit(self) -> bool:
        return self.has_energy_edits() or self.floor_area_m2 is not None


# The eight energy drivers — the inputs that move the simulated baseline kWh
# (and so the EUI the cohort gate judges). Floor area is denominator-only.
ENERGY_INPUT_FIELDS = (
    "hvac_cop", "infiltration_ach", "lighting_w_m2", "equipment_w_m2",
    "window_u", "window_shgc", "wall_u", "roof_u",
)


class RetrofitScenario(BaseModel):
    name: str
    description: str
    modifications: list[IDFModification]
    estimated_cost_aud: float
    code_compliance: bool
    # Richer, honest NCC status (set by the real J7D3 check). code_compliance stays
    # for back-compat (== "compliant"); status distinguishes not-regulated /
    # requires-calculation from a genuine pass/fail.
    compliance_status: Literal[
        "compliant", "non_compliant", "not_regulated",
        "requires_calculation", "unverified",
    ] = "unverified"
    ncc_reference: str


class ModelingOutput(BaseModel):
    # min 2 = baseline + 1 measure. The demo lets the operator pick ONE measure at the
    # HITL gate (to keep the live run to 2 EnergyPlus sims ≈ ~45–50s); the Modeler still
    # proposes the full applicable set (baseline + up to 3) before the pick.
    scenarios: list[RetrofitScenario] = Field(..., min_length=2, max_length=6)
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
    # Realism gate: does the simulated baseline EUI land within the real CBD
    # whole-building office cohort's p25–p75 for this city + building size? Out of
    # range = not a realistic model → reject. Verified cohorts are built from the
    # disclosed register (all four cities for medium office); where none exists the
    # run is illustrative and `cohort_validated` is False — never silently
    # "approved as real".
    realistic: bool = True                 # False only when positively unrealistic
    cohort_validated: bool = False         # a verified cohort existed AND was applied
    within_cohort: bool | None = None      # baseline EUI within p25–p75 (None = no cohort)
    baseline_eui: float | None = None
    cohort_p25: float | None = None
    cohort_p75: float | None = None
    cohort_median: float | None = None
    cohort_n: int | None = None
    # Floor area is the one demoer-editable input that can be abused; it must sit
    # in the realistic band for the building size (medium 2,500–10,000 m²,
    # large 30,000–200,000 m²).
    floor_area_realistic: bool = True
    guardrail_passed: bool
    citations_present: bool
    feedback: str = ""
    # "inputs" = the demoer's model inputs produced an unrealistic baseline (out of
    # the cohort range, or an unrealistic floor area) → go adjust the inputs and
    # re-run. "modeler"/"analyzer" = agent-side re-work; "human"/"done" terminal.
    route_to: Literal["inputs", "modeler", "analyzer", "done", "human"] = "done"
