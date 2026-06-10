"""ASHRAE Guideline 14 calibration checks (project plan §7).

Method is country-neutral; thresholds are public knowledge, hardcoded with
citation (no ASHRAE PDF needed in the repo).

NMBE  ≤ ±10%  for monthly data  (GL14 §5.2.2)
CVRMSE ≤ 30%   for monthly data  (GL14 §5.2.2)
"""
from __future__ import annotations

from math import sqrt

STANDARD = "ASHRAE Guideline 14-2014, Section 5.2.2"
NMBE_LIMIT = 10.0
CVRMSE_LIMIT = 30.0


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs)


def check_nmbe(simulated: list[float], measured: list[float]) -> dict:
    """Normalised Mean Bias Error — systematic over/under-prediction."""
    n = len(measured)
    nmbe = (sum(m - s for m, s in zip(measured, simulated))
            / (n * _mean(measured))) * 100
    return {"nmbe_pct": round(nmbe, 2), "passed": abs(nmbe) <= NMBE_LIMIT,
            "standard": STANDARD}


def check_cvrmse(simulated: list[float], measured: list[float]) -> dict:
    """CV(RMSE) — random error in prediction."""
    rmse = sqrt(_mean([(m - s) ** 2 for m, s in zip(measured, simulated)]))
    cvrmse = (rmse / _mean(measured)) * 100
    return {"cvrmse_pct": round(cvrmse, 2), "passed": cvrmse <= CVRMSE_LIMIT,
            "standard": STANDARD}


def calibration_report(simulated: list[float], measured: list[float]) -> dict:
    """Both checks + overall pass (both must pass per GL14)."""
    if len(simulated) != 12 or len(measured) != 12:
        return {"passed": False,
                "error": "GL14 monthly calibration needs exactly 12 values each"}
    nmbe = check_nmbe(simulated, measured)
    cvrmse = check_cvrmse(simulated, measured)
    return {"passed": nmbe["passed"] and cvrmse["passed"],
            "nmbe": nmbe, "cvrmse": cvrmse}
