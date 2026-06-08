"""Reference tools (4 of the 20 core tools).

get_reference_building · get_carbon_factor · get_ncc_requirement · get_utility_rate

get_reference_building returns pre-cached simulation results instantly (demo mode).
get_utility_rate hits the public CDR Energy Product Reference Data API (Phase 3 wiring).
"""
import json
from pathlib import Path

from mcp_server.schemas.tool_schemas import wrap

REF_DIR = Path("data/reference_buildings")
CACHE_DIR = REF_DIR / "cached_results"
NGA_FACTORS = Path("data/factors/nga_factors_2025.json")

# Minimal NCC Section J seed data (Phase 1). Phase 3 replaces lookups with RAG
# over the full NCC Volume One. Values must be verified against NCC 2022.
NCC_SEED = {
    ("wall_r_value", 5): {"requirement": "R1.4 (total R-value, climate zone 5)",
                          "clause": "NCC 2022 Vol One, J4D3 (VERIFY)"},
    ("roof_r_value", 5): {"requirement": "R3.7 (total R-value, climate zone 5)",
                          "clause": "NCC 2022 Vol One, J4D4 (VERIFY)"},
}


def register_reference_tools(mcp) -> None:
    @mcp.tool()
    def get_reference_building(name: str = "small_office") -> dict:
        """Load a pre-cached reference building + baseline results (instant demo)."""
        idf = REF_DIR / f"RefBldg{''.join(w.capitalize() for w in name.split('_'))}.idf"
        cache = CACHE_DIR / f"{name}_baseline.json"
        data = {
            "idf_path": str(idf) if idf.exists() else None,
            "idf_available": idf.exists(),
            "cached_baseline": json.loads(cache.read_text()) if cache.exists() else None,
        }
        if not idf.exists():
            data["hint"] = "run: python scripts/download_reference_data.py"
        return wrap("get_reference_building", data)

    @mcp.tool()
    def get_carbon_factor(fuel: str = "electricity", state: str = "NSW") -> dict:
        """NGA (DCCEEW) emission factor for a fuel + Australian state (kg CO₂e/kWh)."""
        if not NGA_FACTORS.exists():
            return wrap("get_carbon_factor", {"error": "nga_factors_2025.json missing"})
        factors = json.loads(NGA_FACTORS.read_text())
        if fuel == "electricity":
            value = factors["electricity_scope2_kgco2e_per_kwh"].get(state.upper())
        elif fuel == "natural_gas":
            value = factors["natural_gas_kgco2e_per_kwh"]
        else:
            value = None
        return wrap("get_carbon_factor", {
            "fuel": fuel, "state": state.upper(),
            "kgco2e_per_kwh": value, "source": factors["source"],
        })

    @mcp.tool()
    def get_ncc_requirement(component: str, climate_zone: int) -> dict:
        """NCC 2022 Section J minimum requirement (Phase 1 seed; Phase 3 = RAG)."""
        hit = NCC_SEED.get((component, climate_zone))
        if hit is None:
            return wrap("get_ncc_requirement", {
                "error": f"no seed data for {component} zone {climate_zone}",
                "note": "full NCC lookup arrives with the RAG layer (Phase 3)",
            })
        return wrap("get_ncc_requirement", {"component": component,
                                            "climate_zone": climate_zone, **hit})

    @mcp.tool()
    def get_utility_rate(state: str = "NSW", tariff_type: str = "single rate") -> dict:
        """Australian retail electricity tariff (CDR Energy PRD API — wired in Phase 3)."""
        return wrap("get_utility_rate", {
            "status": "stub",
            "note": "Phase 3 wires the public CDR Energy Product Reference Data API "
                    "(no key needed). Until then agents must not invent prices.",
            "state": state.upper(), "tariff_type": tariff_type,
        })
