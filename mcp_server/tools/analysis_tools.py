"""Analysis tools (4 of the 20 core tools) — completes the v1 MCP surface.

calculate_savings · calculate_payback · calculate_npv · ashrae_calibration_check

Pure deterministic finance/physics math. No LLM. Every figure an agent reports
must come from one of these — that's what the Reviewer's LLM06 guardrail enforces.
"""
from __future__ import annotations

from mcp_server.schemas.tool_schemas import wrap
from verification.ashrae_checks import calibration_report


def register_analysis_tools(mcp) -> None:
    @mcp.tool()
    def calculate_savings(baseline_kwh: float, retrofit_kwh: float,
                          tariff_aud_per_kwh: float) -> dict:
        """Energy + cost savings of a retrofit vs baseline."""
        saved_kwh = baseline_kwh - retrofit_kwh
        pct = (saved_kwh / baseline_kwh * 100) if baseline_kwh else 0.0
        return wrap("calculate_savings", {
            "energy_savings_kwh": round(saved_kwh, 1),
            "energy_savings_pct": round(pct, 1),
            "cost_savings_aud_per_year": round(saved_kwh * tariff_aud_per_kwh, 2),
        })

    @mcp.tool()
    def calculate_payback(retrofit_cost_aud: float,
                          annual_savings_aud: float) -> dict:
        """Simple payback period (years) = cost / annual savings."""
        if annual_savings_aud <= 0:
            return wrap("calculate_payback",
                        {"simple_payback_years": None,
                         "note": "no positive annual savings — payback undefined"})
        return wrap("calculate_payback", {
            "simple_payback_years": round(retrofit_cost_aud / annual_savings_aud, 1),
        })

    @mcp.tool()
    def calculate_npv(annual_savings_aud: float, retrofit_cost_aud: float,
                      years: int = 25, discount_rate: float = 0.07) -> dict:
        """Net Present Value of a retrofit over N years at a discount rate.

        NPV = -cost + Σ savings / (1+r)^t  for t = 1..N
        """
        pv = sum(annual_savings_aud / (1 + discount_rate) ** t
                 for t in range(1, years + 1))
        npv = pv - retrofit_cost_aud
        return wrap("calculate_npv", {
            "npv_aud": round(npv, 2),
            "years": years, "discount_rate": discount_rate,
            "present_value_of_savings_aud": round(pv, 2),
        })

    @mcp.tool()
    def ashrae_calibration_check(simulated_monthly: list[float],
                                 measured_monthly: list[float]) -> dict:
        """NMBE + CV(RMSE) vs measured bills (ASHRAE GL14, 12 monthly values)."""
        return wrap("ashrae_calibration_check",
                    calibration_report(simulated_monthly, measured_monthly))
