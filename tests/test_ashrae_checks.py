"""ASHRAE Guideline 14-2014 §5.2.2 calibration checks.

These tests pin the two statistics that decide whether a baseline EnergyPlus
model is trustworthy enough to build a business case on:
  • NMBE   — systematic bias (model consistently over/under-predicts)
  • CV(RMSE) — random scatter (month-to-month error)
GL14 monthly thresholds: |NMBE| ≤ 5 %, CV(RMSE) ≤ 15 %
(hourly data would use the looser ≤ 10 % / ≤ 30 %).
"""
from __future__ import annotations

from verification.ashrae_checks import (
    calibration_report, check_cvrmse, check_nmbe, resolution_limits,
)


def _flat(v: float) -> list[float]:
    """12 identical monthly values."""
    return [v] * 12


# ── NMBE ────────────────────────────────────────────────────────────────────
def test_nmbe_perfect_match_is_zero():
    r = check_nmbe(simulated=_flat(100), measured=_flat(100))
    assert r["nmbe_pct"] == 0.0
    assert r["passed"] is True


def test_nmbe_three_percent_under_passes():
    # measured 100, simulated 97 → bias = 3/100 = +3 % (within monthly ±5 %)
    r = check_nmbe(simulated=_flat(97), measured=_flat(100))
    assert r["nmbe_pct"] == 3.0
    assert r["passed"] is True


def test_nmbe_fifty_percent_off_fails():
    # measured 100, simulated 50 → +50 % bias, well outside ±10 %
    r = check_nmbe(simulated=_flat(50), measured=_flat(100))
    assert r["nmbe_pct"] == 50.0
    assert r["passed"] is False


# ── CV(RMSE) ────────────────────────────────────────────────────────────────
def test_cvrmse_perfect_match_is_zero():
    r = check_cvrmse(simulated=_flat(100), measured=_flat(100))
    assert r["cvrmse_pct"] == 0.0
    assert r["passed"] is True


def test_cvrmse_large_scatter_fails():
    # ±40 around a mean of 100 → RMSE 40 → CV(RMSE) 40 % (> monthly 15 % limit).
    # Note bias is zero here (errors cancel), so this isolates SCATTER from BIAS.
    sim = [60.0, 140.0] * 6
    r = check_cvrmse(simulated=sim, measured=_flat(100))
    assert r["cvrmse_pct"] == 40.0
    assert r["passed"] is False


# ── combined report ─────────────────────────────────────────────────────────
def test_report_passes_when_both_pass():
    rep = calibration_report(simulated=_flat(97), measured=_flat(100))
    assert rep["passed"] is True
    assert rep["nmbe"]["passed"] and rep["cvrmse"]["passed"]


def test_report_fails_if_scatter_fails_even_when_bias_ok():
    # Bias 0 % (pass) but scatter 40 % (fail) → overall MUST fail (AND logic).
    rep = calibration_report(simulated=[60.0, 140.0] * 6, measured=_flat(100))
    assert rep["passed"] is False
    assert rep["nmbe"]["passed"] is True
    assert rep["cvrmse"]["passed"] is False


def test_report_rejects_wrong_length():
    # GL14 calibration needs a recognised resolution (12 or 8760/8784).
    rep = calibration_report(simulated=_flat(100)[:11], measured=_flat(100))
    assert rep["passed"] is False
    assert "length mismatch" in rep["error"]


# ── data-aware thresholds (regression: monthly must use 5 %/15 %, not 10 %/30 %) ─
def test_resolution_limits_pick_correct_thresholds():
    assert resolution_limits(12) == ("monthly", 5.0, 15.0)
    assert resolution_limits(8760) == ("hourly", 10.0, 30.0)
    assert resolution_limits(8784) == ("hourly", 10.0, 30.0)  # leap year
    assert resolution_limits(7) == (None, None, None)


def test_monthly_cvrmse_17pct_fails_but_would_pass_as_hourly():
    """The exact bug: 17.7 % scatter on 12 monthly bills must FAIL (limit 15 %).
    Under the old hourly 30 % limit it wrongly passed."""
    sim = [100 - 17.7, 100 + 17.7] * 6      # zero bias, CV-RMSE ≈ 17.7 %
    rep = calibration_report(simulated=sim, measured=_flat(100))
    assert rep["resolution"] == "monthly"
    assert rep["cvrmse"]["cvrmse_pct"] == 17.7
    assert rep["cvrmse"]["limit_pct"] == 15.0
    assert rep["passed"] is False           # ← the fix; was True before


def test_report_rejects_unrecognised_length():
    rep = calibration_report(simulated=_flat(100)[:7], measured=_flat(100)[:7])
    assert rep["passed"] is False
    assert "8760" in rep["error"]
