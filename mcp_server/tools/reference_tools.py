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

# NCC Section J requirement values now live in verification/ncc_compliance.py
# (primary-verified against NCC 2022 J7D3). get_ncc_requirement calls into it.

# Capital-city / major-city → NCC 2022 climate zone (1–8). SEED — verify against
# the ABCB climate-zone map (zones are defined per local government area, so a
# city name or lat band is an approximation, not an authority).
_NCC_ZONE_BY_CITY = {
    "darwin": 1, "cairns": 1, "townsville": 1, "broome": 1,
    "brisbane": 2, "gold coast": 2, "byron": 2,
    "rockhampton": 3, "alice springs": 3, "longreach": 3,
    "perth": 5, "adelaide": 5, "sydney": 5,
    "melbourne": 6, "geelong": 6, "ballarat": 7,
    "canberra": 7, "hobart": 7, "launceston": 7,
    "thredbo": 8, "cooma": 8, "mount hotham": 8,
}


# State/territory → representative NCC zone (capital-city based; SEED, VERIFY).
_NCC_ZONE_BY_STATE = {
    "NSW": 5, "ACT": 7, "VIC": 6, "QLD": 2,
    "SA": 5, "WA": 5, "TAS": 7, "NT": 1,
}

# Australia spans roughly 10°S–44°S. A latitude outside this band is NOT an
# Australian site (e.g. a US prototype IDF at +41.8°) → must not map to a zone.
_AU_LAT_MIN, _AU_LAT_MAX = -45.0, -9.0


def _zone_by_latitude(lat: float):
    """Rough NCC zone from Australian latitude (more negative = cooler). Returns
    None if the latitude isn't within Australia, so a foreign coordinate can't
    silently produce a real zone."""
    if not (_AU_LAT_MIN <= lat <= _AU_LAT_MAX):
        return None
    if lat > -20:   # tropical north
        return 1
    if lat > -26:
        return 2
    if lat > -30:
        return 3
    if lat > -35:   # Sydney ≈ -33.9, Perth/Adelaide ≈ -32/-35
        return 5
    if lat > -38:   # Melbourne ≈ -37.8
        return 6
    return 7        # Tasmania / alpine fringe (zone 8 = alpine, needs the LGA map)


def ncc_climate_zone(location_name: str = None, latitude: float = None,
                     state: str = None) -> dict:
    """Deterministic NCC 2022 climate-zone lookup from (in priority order) an
    Australian state/territory, a city name, or an Australian latitude.

    Returns {zone, basis, verified}. `verified=False` everywhere — this is seed
    data; the authority is the ABCB climate-zone map (Phase 3 RAG).
    """
    if state:
        zone = _NCC_ZONE_BY_STATE.get(state.strip().upper())
        if zone is not None:
            return {"zone": zone, "basis": f"state: {state.upper()}", "verified": False}
    if location_name:
        key = location_name.strip().lower()
        for city, zone in _NCC_ZONE_BY_CITY.items():
            if city in key:
                return {"zone": zone, "basis": f"city match: {city}", "verified": False}
    if latitude is not None:
        zone = _zone_by_latitude(latitude)
        if zone is not None:
            return {"zone": zone,
                    "basis": f"latitude {latitude:.1f}° approximation", "verified": False}
        return {"zone": None,
                "basis": f"latitude {latitude:.1f}° is outside Australia", "verified": False}
    return {"zone": None, "basis": "insufficient location data", "verified": False}


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
    def get_ncc_requirement(component: str, climate_zone: int,
                            value: float | None = None) -> dict:
        """Real NCC 2022 Section J check (Tier 1, primary-verified values).

        Returns a compliance verdict for `component` (and `value` if numeric):
        lighting → J7D3 numeric limit; equipment plug loads → not regulated;
        glazing/fabric → requires the J4 façade calculation. Tier 2 (Phase 3)
        swaps the values for RAG over the live NCC — this tool's contract is stable.
        """
        from verification.ncc_compliance import check_ncc_compliance
        result = check_ncc_compliance(component, value, climate_zone)
        return wrap("get_ncc_requirement", {
            "component": component, "climate_zone": climate_zone, **result,
        })

    @mcp.tool()
    def get_utility_rate(state: str = "NSW", tariff_type: str = "single rate") -> dict:
        """Australian retail electricity tariff (CDR Energy PRD API — wired in Phase 3)."""
        return wrap("get_utility_rate", {
            "status": "stub",
            "note": "Phase 3 wires the public CDR Energy Product Reference Data API "
                    "(no key needed). Until then agents must not invent prices.",
            "state": state.upper(), "tariff_type": tariff_type,
        })
