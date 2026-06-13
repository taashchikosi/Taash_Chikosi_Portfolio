"""Shared fixtures/factories for the deterministic agent tests."""
from __future__ import annotations

from verification.pydantic_schemas import SimulationResult, SimRunnerOutput


def make_result(name: str, annual_kwh: float, eui: float = 150.0) -> SimulationResult:
    """A minimal valid SimulationResult with 12 even monthly values."""
    return SimulationResult(
        scenario_name=name,
        annual_energy_kwh=annual_kwh,
        monthly_energy_kwh=[annual_kwh / 12] * 12,
        annual_eui=eui,
        simulation_status="success",
    )


def make_sim() -> SimRunnerOutput:
    """Baseline 100,000 kWh + three retrofit scenarios with known deltas.

      LED+HVAC  80,000 → saves 20,000 (20 %)
      Glazing   90,000 → saves 10,000 (10 %)
      NoSave   100,000 → saves 0       (∞ payback)
    """
    baseline = make_result("baseline", 100_000)
    return SimRunnerOutput(
        baseline_result=baseline,
        results=[
            baseline,
            make_result("LED+HVAC", 80_000),
            make_result("Glazing", 90_000),
            make_result("NoSave", 100_000),
        ],
    )


SCENARIO_COSTS = {"LED+HVAC": 30_000, "Glazing": 45_000, "NoSave": 10_000}
TARIFF = 0.30          # AUD/kWh
CARBON = 0.66          # kg CO2e/kWh (NGA 2025 NSW)
