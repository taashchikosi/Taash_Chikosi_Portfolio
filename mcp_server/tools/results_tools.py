"""Results Extraction tools (5 of the 20 core tools).

get_annual_energy · get_monthly_energy · get_eui · get_energy_end_uses · get_carbon_emissions

Reads EnergyPlus output (eplusout.csv / eplustbl.htm) from a job's output dir.
Carbon uses NGA factors (DCCEEW) from data/factors/nga_factors_2025.json.
"""
import json
from pathlib import Path

import pandas as pd

from mcp_server.schemas.tool_schemas import wrap

NGA_FACTORS = Path("data/factors/nga_factors_2025.json")


def _csv(output_dir: str) -> pd.DataFrame | None:
    path = Path(output_dir) / "eplusout.csv"
    return pd.read_csv(path) if path.exists() else None


def _electricity_cols(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if "Electricity:Facility" in c]


J_TO_KWH = 1 / 3.6e6


def register_results_tools(mcp) -> None:
    @mcp.tool()
    def get_annual_energy(output_dir: str) -> dict:
        """Total annual energy consumption (kWh) by fuel type."""
        df = _csv(output_dir)
        if df is None:
            return wrap("get_annual_energy", {"error": "eplusout.csv not found"})
        fuels = {}
        for col in df.columns:
            if ":Facility" in col and "[J]" in col:
                fuel = col.split(":")[0].strip()
                fuels[fuel] = round(df[col].sum() * J_TO_KWH, 1)
        return wrap("get_annual_energy", {"annual_kwh_by_fuel": fuels,
                                          "total_kwh": round(sum(fuels.values()), 1)})

    @mcp.tool()
    def get_monthly_energy(output_dir: str) -> dict:
        """Monthly electricity profile (12 kWh values) — used for GL14 calibration."""
        df = _csv(output_dir)
        if df is None:
            return wrap("get_monthly_energy", {"error": "eplusout.csv not found"})
        cols = _electricity_cols(df)
        if not cols or len(df) < 12:
            return wrap("get_monthly_energy",
                        {"error": "monthly electricity output not found — "
                                  "ensure Output:Meter,Electricity:Facility,Monthly in IDF"})
        monthly = [round(v * J_TO_KWH, 1) for v in df[cols[0]].tolist()[:12]]
        return wrap("get_monthly_energy", {"monthly_kwh": monthly})

    @mcp.tool()
    def get_eui(output_dir: str, floor_area_m2: float) -> dict:
        """Energy Use Intensity: total kWh / floor area (kWh/m²/year)."""
        df = _csv(output_dir)
        if df is None or floor_area_m2 <= 0:
            return wrap("get_eui", {"error": "missing results or invalid floor area"})
        total = sum(df[c].sum() * J_TO_KWH for c in df.columns
                    if ":Facility" in c and "[J]" in c)
        return wrap("get_eui", {"eui_kwh_m2": round(total / floor_area_m2, 1),
                                "total_kwh": round(total, 1),
                                "floor_area_m2": floor_area_m2})

    @mcp.tool()
    def get_energy_end_uses(output_dir: str) -> dict:
        """Breakdown by end use: heating, cooling, lighting, equipment, fans…"""
        df = _csv(output_dir)
        if df is None:
            return wrap("get_energy_end_uses", {"error": "eplusout.csv not found"})
        end_uses = {}
        for col in df.columns:
            for use in ("Heating", "Cooling", "InteriorLights", "InteriorEquipment",
                        "Fans", "Pumps", "WaterSystems"):
                if col.startswith(f"{use}:") and "[J]" in col:
                    end_uses[use] = round(df[col].sum() * J_TO_KWH, 1)
        return wrap("get_energy_end_uses", {"end_uses_kwh": end_uses})

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
