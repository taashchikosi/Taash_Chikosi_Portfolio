"""Results Extraction tools (5 of the 20 core tools).

get_annual_energy · get_monthly_energy · get_eui · get_energy_end_uses · get_carbon_emissions

Reads EnergyPlus output (eplusout.csv) from a job's output dir.
Carbon uses NGA factors (DCCEEW) from data/factors/nga_factors_2025.json.

⚠️ The eplusout.csv from `--readvars` is HOURLY (8760 rows) and contains many
overlapping ":Facility" meters — including Source (PRIMARY energy), EnergyTransfer,
*Demand, and Purchased/Net/Surplus/Monthly variants that DUPLICATE the real
Electricity:Facility meter. Naively summing every ":Facility [J]" column inflates
site energy ~10x (e.g. a small office EUI of ~1500 instead of ~130). The pure
helpers below extract *site delivered energy* only, and are unit-tested against a
synthetic CSV that reproduces those trap columns.
"""
import json
from pathlib import Path

import pandas as pd

from mcp_server.schemas.tool_schemas import wrap

NGA_FACTORS = Path("data/factors/nga_factors_2025.json")
J_TO_KWH = 1 / 3.6e6

# Real site-delivered fuel meters. NOT Source (primary), EnergyTransfer, demand,
# or the Purchased/Net/Surplus electricity variants (which duplicate Electricity).
SITE_FUEL_METERS = ("Electricity:Facility", "NaturalGas:Facility")
_END_USES = ("Heating", "Cooling", "InteriorLights", "InteriorEquipment",
             "Fans", "Pumps", "WaterSystems", "ExteriorLights")
# Reporting-frequency preference: pick ONE column per meter so we never sum the
# same meter twice (e.g. its Hourly and Monthly variants both appear in the CSV).
_FREQ_PREF = ("(Hourly)", "(Timestep)", "(Detailed)", "(RunPeriod)", "(Annual)")


# ── Pure extraction helpers (importable + unit-tested) ─────────────────────
def _csv(output_dir: str) -> "pd.DataFrame | None":
    path = Path(output_dir) / "eplusout.csv"
    return pd.read_csv(path) if path.exists() else None


def _meter_col(df: pd.DataFrame, meter: str) -> "str | None":
    """One column for a meter, preferring the most detailed reporting frequency."""
    cands = [c for c in df.columns if c.startswith(meter + " ") and "[J]" in c]
    if not cands:
        return None
    for pref in _FREQ_PREF:
        hit = next((c for c in cands if pref in c), None)
        if hit:
            return hit
    return cands[0]


def _dedupe_sum_kwh(df: pd.DataFrame, cols: list) -> float:
    """Sum columns in kWh, collapsing multiple reporting frequencies of the same
    base meter to a single column so nothing is double-counted."""
    by_base: dict[str, list] = {}
    for c in cols:
        by_base.setdefault(c.split(" [J]")[0], []).append(c)
    total = 0.0
    for variants in by_base.values():
        col = next((v for pref in _FREQ_PREF for v in variants if pref in v), variants[0])
        total += float(df[col].sum()) * J_TO_KWH
    return total


def annual_by_fuel(df: pd.DataFrame) -> dict:
    """Site delivered energy by fuel (kWh) — real fuel meters only."""
    out = {}
    for meter in SITE_FUEL_METERS:
        col = _meter_col(df, meter)
        if col is not None:
            out[meter.split(":")[0]] = round(float(df[col].sum()) * J_TO_KWH, 1)
    return out


def monthly_electricity_kwh(df: pd.DataFrame) -> "list[float] | None":
    """12 monthly electricity totals (kWh). Prefer the Monthly meter column
    (month-end cumulative, NaN elsewhere → dropna); else resample the hourly
    meter by calendar month from the Date/Time column."""
    monthly_cols = [c for c in df.columns
                    if c.startswith("Electricity:Facility ")
                    and "(Monthly)" in c and "[J]" in c]
    if monthly_cols:
        vals = df[monthly_cols[0]].dropna().tolist()
        if len(vals) >= 12:
            return [round(v * J_TO_KWH, 1) for v in vals[:12]]

    hourly = _meter_col(df, "Electricity:Facility")
    if hourly is not None and len(df) >= 8760:
        months = df.iloc[:, 0].astype(str).str.strip().str[:2]
        grouped = (df[hourly].groupby(months).sum() * J_TO_KWH).round(1)
        if len(grouped) >= 12:
            return grouped.tolist()[:12]
    return None


def end_uses_kwh(df: pd.DataFrame) -> dict:
    """Energy by end use (kWh), summing each use's fuel sub-meters once."""
    out = {}
    for use in _END_USES:
        cols = [c for c in df.columns if c.startswith(use + ":") and "[J]" in c]
        if cols:
            out[use] = round(_dedupe_sum_kwh(df, cols), 1)
    return out


# ── MCP tools (thin wrappers over the helpers) ─────────────────────────────
def register_results_tools(mcp) -> None:
    @mcp.tool()
    def get_annual_energy(output_dir: str) -> dict:
        """Total annual SITE energy (kWh) by fuel type."""
        df = _csv(output_dir)
        if df is None:
            return wrap("get_annual_energy", {"error": "eplusout.csv not found"})
        fuels = annual_by_fuel(df)
        return wrap("get_annual_energy", {"annual_kwh_by_fuel": fuels,
                                          "total_kwh": round(sum(fuels.values()), 1)})

    @mcp.tool()
    def get_monthly_energy(output_dir: str) -> dict:
        """Monthly electricity profile (12 kWh values) — used for GL14 calibration."""
        df = _csv(output_dir)
        if df is None:
            return wrap("get_monthly_energy", {"error": "eplusout.csv not found"})
        monthly = monthly_electricity_kwh(df)
        if monthly is None or len(monthly) < 12:
            return wrap("get_monthly_energy",
                        {"error": "monthly electricity not found — add "
                                  "Output:Meter,Electricity:Facility,Monthly; to the IDF"})
        return wrap("get_monthly_energy", {"monthly_kwh": monthly})

    @mcp.tool()
    def get_eui(output_dir: str, floor_area_m2: float) -> dict:
        """Energy Use Intensity: total SITE kWh / floor area (kWh/m²/year)."""
        df = _csv(output_dir)
        if df is None or floor_area_m2 <= 0:
            return wrap("get_eui", {"error": "missing results or invalid floor area"})
        total = round(sum(annual_by_fuel(df).values()), 1)  # same basis as get_annual_energy
        return wrap("get_eui", {"eui_kwh_m2": round(total / floor_area_m2, 1),
                                "total_kwh": total,
                                "floor_area_m2": floor_area_m2})

    @mcp.tool()
    def get_energy_end_uses(output_dir: str) -> dict:
        """Breakdown by end use: heating, cooling, lighting, equipment, fans…"""
        df = _csv(output_dir)
        if df is None:
            return wrap("get_energy_end_uses", {"error": "eplusout.csv not found"})
        return wrap("get_energy_end_uses", {"end_uses_kwh": end_uses_kwh(df)})

    @mcp.tool()
    def get_carbon_emissions(annual_kwh_by_fuel: dict, state: str = "NSW") -> dict:
        """tCO₂e/year using NGA (DCCEEW) factors for the given Australian state."""
        if not NGA_FACTORS.exists():
            return wrap("get_carbon_emissions", {"error": "nga_factors_2025.json missing"})
        factors = json.loads(NGA_FACTORS.read_text())
        grid = factors["electricity_scope2_kgco2e_per_kwh"].get(state.upper())
        if grid is None:
            return wrap("get_carbon_emissions", {"error": f"no factor for state: {state}"})
        gas = factors["natural_gas_kgco2e_per_kwh"]
        total_kg = 0.0
        detail = {}
        for fuel, kwh in annual_kwh_by_fuel.items():
            f = grid if "electric" in fuel.lower() else gas if "gas" in fuel.lower() else None
            if f is not None:
                detail[fuel] = round(kwh * f / 1000, 3)  # tCO2e
                total_kg += kwh * f
        return wrap("get_carbon_emissions", {
            "tco2e_per_year": round(total_kg / 1000, 3),
            "by_fuel_tco2e": detail,
            "state": state.upper(),
            "source": factors["source"],
        })
