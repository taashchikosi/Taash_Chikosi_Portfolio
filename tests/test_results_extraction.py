"""Regression tests for results extraction — the meter double-counting bug.

A live EnergyPlus run on the DOE small office reported EUI 1498 kWh/m²/yr (≈10x
too high) because the old extractor summed EVERY ":Facility [J]" column —
including Source (primary energy), EnergyTransfer, *Demand, and the
Purchased/Net/Monthly variants that duplicate Electricity:Facility. These tests
pin the fix: site energy uses only the real fuel meters, and monthly reads 12
months (not the first 12 hours).

The synthetic CSV below reproduces the exact trap columns observed in that run.
"""
from __future__ import annotations

import pandas as pd
import pytest

from mcp_server.tools.results_tools import (
    annual_by_fuel, end_uses_kwh, monthly_electricity_kwh,
)

KWH = 3.6e6  # J per kWh — build columns in J so the helper converts back


@pytest.fixture
def trap_df() -> pd.DataFrame:
    """8760 hourly rows with the real meters + the inflating trap meters."""
    n = 8760
    elec_hourly = 64_586.7 * KWH / n      # spread evenly → sums to 64,586.7 kWh
    gas_hourly = 3_416.0 * KWH / n        # → 3,416 kWh
    months = []  # build a Date/Time column like ' 01/01  01:00:00'
    for m in range(1, 13):
        months += [f" {m:02d}/01  01:00:00"] * (730 if m < 12 else n - 730 * 11)
    cols = {
        "Date/Time": months[:n],
        # real site meters (Hourly) — the only ones that should count
        "Electricity:Facility [J](Hourly)": [elec_hourly] * n,
        "NaturalGas:Facility [J](Hourly)": [gas_hourly] * n,
        # trap columns the old code wrongly summed:
        "Electricity:Facility [J](Monthly)":      [None] * n,  # duplicate (also NaN)
        "ElectricityPurchased:Facility [J](Monthly)": [elec_hourly] * n,  # duplicate
        "ElectricityNet:Facility [J](Monthly)":   [elec_hourly] * n,      # duplicate
        "EnergyTransfer:Facility [J](Monthly)":   [99_999 * KWH / n] * n, # not site
        "Source:Facility [J](Monthly)":           [461_779 * KWH / n] * n,# PRIMARY
        "PlantLoopHeatingDemand:Facility [J](Monthly)": [600 * KWH / n] * n,  # demand
        # an end use with two fuel sub-meters (must sum once each, not overwrite)
        "Heating:Electricity [J](Hourly)": [100 * KWH / n] * n,
        "Heating:NaturalGas [J](Hourly)": [3_000 * KWH / n] * n,
        "InteriorLights:Electricity [J](Hourly)": [15_000 * KWH / n] * n,
    }
    # populate the Monthly electricity column at month-end rows only (12 values)
    df = pd.DataFrame(cols)
    monthly_idx = [730 * (k + 1) - 1 for k in range(12)]
    for i in monthly_idx:
        df.loc[i, "Electricity:Facility [J](Monthly)"] = (64_586.7 / 12) * KWH
    return df


def test_annual_excludes_source_and_duplicates(trap_df):
    fuels = annual_by_fuel(trap_df)
    assert set(fuels) == {"Electricity", "NaturalGas"}     # not Source/EnergyTransfer/…
    assert fuels["Electricity"] == pytest.approx(64_586.7, rel=1e-3)
    assert fuels["NaturalGas"] == pytest.approx(3_416.0, rel=1e-3)


def test_total_and_eui_are_physically_sane(trap_df):
    total = sum(annual_by_fuel(trap_df).values())
    assert total == pytest.approx(68_002.7, rel=1e-3)      # NOT 697,550
    eui = total / 511.0
    assert 80 < eui < 250                                  # small-office range; was 1498


def test_monthly_returns_twelve_months_not_twelve_hours(trap_df):
    monthly = monthly_electricity_kwh(trap_df)
    assert monthly is not None and len(monthly) == 12
    assert sum(monthly) == pytest.approx(64_586.7, rel=1e-2)
    assert min(monthly) > 1000                             # months, not 4.2-kWh hours


def test_monthly_falls_back_to_hourly_resample(trap_df):
    """Drop the Monthly column → must resample the hourly meter by month."""
    df = trap_df.drop(columns=["Electricity:Facility [J](Monthly)"])
    monthly = monthly_electricity_kwh(df)
    assert monthly is not None and len(monthly) == 12
    assert sum(monthly) == pytest.approx(64_586.7, rel=1e-2)


def test_end_use_sums_both_fuel_submeters_once(trap_df):
    uses = end_uses_kwh(trap_df)
    assert uses["Heating"] == pytest.approx(3_100.0, rel=1e-2)   # 100 elec + 3000 gas
    assert uses["InteriorLights"] == pytest.approx(15_000.0, rel=1e-2)
