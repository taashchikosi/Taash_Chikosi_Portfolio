"""ASHRAE Guideline 14 calibration checks (project plan §7).

Method is country-neutral; thresholds are public knowledge, hardcoded with
citation (no ASHRAE PDF needed in the repo).

GL14-2014 §5.2.2 acceptance criteria are RESOLUTION-DEPENDENT — the limit you
apply must match the granularity of the measured data:

    ┌────────────┬──────────────┬───────────────┐
    │ Data       │  |NMBE|      │  CV(RMSE)     │
    ├────────────┼──────────────┼───────────────┤
    │ Monthly    │  ≤ 5 %       │  ≤ 15 %       │  ← 12 utility-bill points
    │ Hourly     │  ≤ 10 %      │  ≤ 30 %       │  ← 8760/8784 points
    └────────────┴──────────────┴───────────────┘

Applying the looser HOURLY limit to MONTHLY data would wave through an
uncalibrated model — a classic M&V error and the first thing a reviewer checks.
So `calibration_report` infers the resolution from the data length and applies
the matching limit. RetrofitGPT calibrates against 12 monthly bills → 5 % / 15 %.
"""
from __future__ import annotations

from math import sqrt

STANDARD = "ASHRAE Guideline 14-2014, Section 5.2.2"

# (|NMBE| limit %, CV-RMSE limit %) by data resolution.
MONTHLY_NMBE_LIMIT, MONTHLY_CVRMSE_LIMIT = 5.0, 15.0
HOURLY_NMBE_LIMIT, HOURLY_CVRMSE_LIMIT = 10.0, 30.0


def resolution_limits(n: int) -> tuple[str, float, float] | tuple[None, None, None]:
    """Map a data-point count to (resolution, nmbe_limit, cvrmse_limit).

    12 → monthly; 8760/8784 (incl. leap year) → hourly; anything else → unknown.
    """
    if n == 12:
        return "monthly", MONTHLY_NMBE_LIMIT, MONTHLY_CVRMSE_LIMIT
    if n in (8760, 8784):
        return "hourly", HOURLY_NMBE_LIMIT, HOURLY_CVRMSE_LIMIT
    return None, None, None


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs)


def check_nmbe(simulated: list[float], measured: list[float],
               nmbe_limit: float = MONTHLY_NMBE_LIMIT) -> dict:
    """Normalised Mean Bias Error — systematic over/under-prediction."""
    n = len(measured)
    nmbe = (sum(m - s for m, s in zip(measured, simulated))
            / (n * _mean(measured))) * 100
    return {"nmbe_pct": round(nmbe, 2), "passed": abs(nmbe) <= nmbe_limit,
            "limit_pct": nmbe_limit, "standard": STANDARD}


def check_cvrmse(simulated: list[float], measured: list[float],
                 cvrmse_limit: float = MONTHLY_CVRMSE_LIMIT) -> dict:
    """CV(RMSE) — random error in prediction."""
    rmse = sqrt(_mean([(m - s) ** 2 for m, s in zip(measured, simulated)]))
    cvrmse = (rmse / _mean(measured)) * 100
    return {"cvrmse_pct": round(cvrmse, 2), "passed": cvrmse <= cvrmse_limit,
            "limit_pct": cvrmse_limit, "standard": STANDARD}


def calibration_report(simulated: list[float], measured: list[float]) -> dict:
    """Both checks + overall pass, with the limit matched to data resolution.

    Both lists must be the same recognised length (12 monthly or 8760/8784
    hourly). Mismatched or unrecognised lengths fail closed — an uncalibratable
    input is never silently treated as calibrated.
    """
    if len(simulated) != len(measured):
        return {"passed": False,
                "error": f"length mismatch: simulated {len(simulated)} "
                         f"vs measured {len(measured)}"}
    resolution, nmbe_limit, cvrmse_limit = resolution_limits(len(measured))
    if resolution is None:
        return {"passed": False,
                "error": "GL14 calibration needs 12 (monthly) or 8760/8784 "
                         f"(hourly) values; got {len(measured)}"}
    nmbe = check_nmbe(simulated, measured, nmbe_limit)
    cvrmse = check_cvrmse(simulated, measured, cvrmse_limit)
    return {"passed": nmbe["passed"] and cvrmse["passed"],
            "resolution": resolution, "nmbe": nmbe, "cvrmse": cvrmse,
            "standard": STANDARD}
