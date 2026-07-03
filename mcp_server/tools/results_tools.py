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
import re
from pathlib import Path

import pandas as pd

from mcp_server.schemas.tool_schemas import wrap

NGA_FACTORS = Path("data/factors/nga_factors_2025.json")
J_TO_KWH = 1 / 3.6e6

# Real site-delivered fuel meters. NOT Source (primary), EnergyTransfer, demand,
# or the Purchased/Net/Surplus electricity variants (which duplicate Electricity).
SITE_FUEL_METERS = ("Electricity:Facility", "NaturalGas:Facility")
_END_USES = ("Heating", "Cooling", "InteriorLights", "InteriorEquipment",
             "Fans", "Pumps", "HeatRejection", "WaterSystems", "ExteriorLights")
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


# ── Authoritative floor area (Bug #12 fix) ─────────────────────────────────
def _to_float(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _eio_col_name(token: str) -> str:
    """Normalise an .eio column descriptor → a stable lookup key.

    'Floor Area {m2}' → 'floor area' · '! <Zone Information>' → 'zone information'
    · ' Part of Total Building Area' → 'part of total building area'.
    """
    token = token.strip()
    if "{" in token:                       # strip a trailing unit, e.g. {m2}
        token = token[: token.index("{")].strip()
    return token.strip("!").strip().strip("<>").strip().lower()


def net_conditioned_area_from_eio(eio_text: str):
    """Authoritative building floor area (m²) from EnergyPlus' .eio Zone Information.

    Sums each zone's reported `Floor Area {m2}` × Zone Multiplier × Zone List
    Multiplier over zones flagged `Part of Total Building Area = Yes`. This is
    EnergyPlus' OWN computed area — geometry-derived even when the IDF declares a
    zone's Floor_Area as `autocalculate` — and it counts zone FLOORS, not
    surfaces, so it never double-counts inter-floor slabs (the Bug #12 trap that a
    naïve geometry summation falls into).

    Header-driven: column positions are read from the `! <Zone Information>`
    descriptor line, never hardcoded — EnergyPlus versions reorder these fields,
    so a fixed index is exactly the kind of version-coupled constant that §11
    warns against. Returns {area_m2, zones:[...]} or None if absent.
    """
    cols: dict[str, int] = {}
    zones: list[dict] = []
    for line in eio_text.splitlines():
        if line.lstrip().startswith("! <Zone Information>"):
            cols = {_eio_col_name(t): i for i, t in enumerate(line.split(","))}
            continue
        if not cols or not line.lstrip().startswith("Zone Information,"):
            continue
        parts = line.split(",")

        def field(name, default=None):
            idx = cols.get(name)
            return parts[idx].strip() if idx is not None and idx < len(parts) else default

        fa = _to_float(field("floor area"))
        if fa is None:
            continue
        mult = (_to_float(field("zone multiplier"), 1.0)
                * _to_float(field("zone list multiplier"), 1.0))
        included = (field("part of total building area", "") or "").lower() == "yes"
        zones.append({"zone": field("zone name"), "floor_area_m2": fa,
                      "multiplier": mult, "included": included})
    if not zones:
        return None
    area = round(sum(z["floor_area_m2"] * z["multiplier"]
                     for z in zones if z["included"]), 1)
    return {"area_m2": area, "zones": zones}


def area_from_tabular_htm(html: str):
    """Fallback: the 'Net Conditioned Building Area' value from eplustbl.htm."""
    for label in ("Net Conditioned Building Area", "Total Building Area"):
        m = re.search(label + r"\s*</td>\s*<td[^>]*>\s*([0-9][0-9.,]*)", html, re.I)
        if m:
            return _to_float(m.group(1).replace(",", ""))
    return None


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
        """Monthly electricity profile (12 kWh values) — feeds the guardrail's traceable-value set."""
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
    def get_building_area(output_dir: str) -> dict:
        """Authoritative net conditioned floor area (m²) from EnergyPlus output.

        Primary: eplusout.eio Zone Information (always written; geometry-derived;
        counts zone floors, not surfaces). Fallback: the Net Conditioned Building
        Area row in eplustbl.htm. Fixes Bug #12 — the DOE Medium Office declares
        every zone Floor_Area as `autocalculate`, so a pre-sim read returns
        nothing and a wrong fallback area gives a ~10× EUI. After the baseline
        sim, the true area is known and the Sim Runner reconciles against it.
        """
        out = Path(output_dir)
        eio = out / "eplusout.eio"
        if eio.exists():
            parsed = net_conditioned_area_from_eio(eio.read_text(errors="ignore"))
            if parsed and parsed["area_m2"] > 0:
                return wrap("get_building_area", {
                    "net_conditioned_area_m2": parsed["area_m2"],
                    "source": "eplusout.eio Zone Information "
                              "(Part of Total Building Area = Yes)",
                    "zones": [z for z in parsed["zones"] if z["included"]],
                })
        htm = out / "eplustbl.htm"
        if htm.exists():
            area = area_from_tabular_htm(htm.read_text(errors="ignore"))
            if area and area > 0:
                return wrap("get_building_area", {
                    "net_conditioned_area_m2": round(area, 1),
                    "source": "eplustbl.htm Net Conditioned Building Area"})
        return wrap("get_building_area",
                    {"error": f"no authoritative area source in {output_dir}"})

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
