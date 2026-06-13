"""NCC 2022 Section J compliance checks (real, deterministic).

Replaces the old hardcoded `code_compliance=True`. The point of this module is to
encode *what the National Construction Code actually regulates* — which is not a
uniform "value ≤ threshold" for every retrofit:

  • Lighting power density  → REGULATED. NCC 2022 J7D3, Table J7D3a sets a maximum
    illumination power density (W/m²) per space type. A real numeric check.
  • Equipment / plug loads  → NOT REGULATED. J7 explicitly excludes appliances
    plugged into general-purpose socket outlets. Claiming compliance is meaningless.
  • Glazing / fabric        → REQUIRES CALCULATION. NCC J4 uses a façade calculation
    (U-value × area + SHGC), not a single U-value limit. Not a one-number check.

Values are PRIMARY-VERIFIED against the ABCB NCC 2022 Volume One text (Part J7D3,
Table J7D3a — verified June 2026).

WHAT'S IMPLEMENTED (be precise in interviews):

  • TIER 1.5 — per-space limit (`check_lighting_power_density`) AND the real
    AGGREGATE area-weighted method (`check_aggregate_lighting_compliance`). J7D3(2)(a)
    requires that the *aggregate* design illumination power load (Σ area × design IPD)
    not exceed the sum of allowances (Σ area × max IPD per Table J7D3a). A single-space
    pass/fail is a simplification; a mixed-use floor is only truly compliant on the
    aggregate. Both are now real, deterministic checks.
  • TIER 2 (Phase 3 RAG, NOT yet implemented, honestly flagged):
      – Table J7D3b/c ADJUSTMENT FACTORS (room aspect, occupancy/daylight sensors,
        high colour-rendition) that legitimately raise the allowance.
      – NCC J4 building-fabric façade calculation (returns `requires_calculation`).
    These will source clause-level citations from the live NCC document.
"""
from __future__ import annotations

from typing import Literal

ComplianceStatus = Literal[
    "compliant", "non_compliant", "not_regulated", "requires_calculation", "unverified",
]

LIGHTING_STANDARD = "NCC 2022 Volume One, J7D3, Table J7D3a"
FABRIC_STANDARD = "NCC 2022 Volume One, Part J4 (Building fabric — façade calculation)"

# NCC 2022 Vol One, Table J7D3a — maximum illumination power density (W/m²) by
# space type. PRIMARY-VERIFIED against the ABCB NCC 2022 text (subset of the table).
NCC_J7D3A_IPD_W_M2: dict[str, float] = {
    "office_200lx_or_more": 4.5,   # "Office – artificially lit to ambient ≥200 lx"
    "office_under_200lx": 2.5,     # "Office – artificially lit to ambient <200 lx"
    "board_room": 5.0,
    "conference_room": 5.0,
    "corridor": 5.0,
    "carpark_general": 2.0,
    "storage": 1.5,
    "toilet_staff_room": 3.0,
    "stairway": 2.0,
    "retail": 14.0,
    "restaurant_cafe_bar": 14.0,
    "school_learning_area": 4.5,
}

# Components NCC Section J does not regulate as a single-value limit.
_NOT_REGULATED = {"equipment_power_density", "plug_load", "plug_load_power_density"}
_REQUIRES_CALC = {"glazing_u_value", "glazing", "wall_r_value", "roof_r_value",
                  "fabric", "facade"}


def check_lighting_power_density(
    value_w_m2: float, space: str = "office_200lx_or_more",
) -> dict:
    """Real NCC J7D3 check: is the lighting power density within the Table J7D3a max?"""
    limit = NCC_J7D3A_IPD_W_M2.get(space)
    if limit is None:
        return {"status": "unverified", "regulated": True,
                "clause": LIGHTING_STANDARD,
                "detail": f"no Table J7D3a value seeded for space '{space}'"}
    compliant = value_w_m2 <= limit
    margin = round(limit - value_w_m2, 2)
    return {
        "status": "compliant" if compliant else "non_compliant",
        "regulated": True, "limit_w_m2": limit, "value_w_m2": value_w_m2,
        "margin_w_m2": margin, "clause": LIGHTING_STANDARD,
        "detail": (f"{value_w_m2} W/m² vs max {limit} W/m² ({space}) → "
                   f"{'within' if compliant else 'EXCEEDS'} limit by {abs(margin)} W/m²"),
    }


def check_aggregate_lighting_compliance(spaces: list[dict]) -> dict:
    """Real J7D3(2)(a) aggregate check for a building / floor of mixed space types.

    NCC 2022 J7D3(2)(a): the *aggregate* design illumination power load must not
    exceed the sum of the allowances obtained by multiplying the area of each space
    by the maximum illumination power density in Table J7D3a. i.e.

        Σ (design_ipd × area)   ≤   Σ (max_ipd[space_type] × area)

    A per-space pass/fail can mislead on a mixed-use floor: an over-lit office can be
    offset by an under-lit store on aggregate (or vice-versa). This is the check a
    certifier actually applies.

    `spaces`: list of {"space": <Table J7D3a key>, "area_m2": float,
                       "design_ipd_w_m2": float}.

    Fail-closed: any space whose type isn't seeded in Table J7D3a makes the whole
    result `unverified` (we never silently pass an unknown space type). Does NOT yet
    apply Table J7D3b/c adjustment factors — that's Tier 2 (would only ever *raise*
    the allowance, so this check is conservative).
    """
    if not spaces:
        return {"status": "unverified", "regulated": True, "clause": LIGHTING_STANDARD,
                "detail": "no spaces supplied for aggregate lighting check"}

    total_design_w = 0.0
    total_allowance_w = 0.0
    breakdown: list[dict] = []
    unknown: list[str] = []

    for sp in spaces:
        space = str(sp.get("space", "")).strip().lower()
        area = float(sp.get("area_m2", 0.0))
        design_ipd = float(sp.get("design_ipd_w_m2", 0.0))
        limit = NCC_J7D3A_IPD_W_M2.get(space)
        if limit is None:
            unknown.append(space or "<blank>")
            continue
        design_w = design_ipd * area
        allow_w = limit * area
        total_design_w += design_w
        total_allowance_w += allow_w
        breakdown.append({
            "space": space, "area_m2": area, "design_ipd_w_m2": design_ipd,
            "max_ipd_w_m2": limit, "design_w": round(design_w, 1),
            "allowance_w": round(allow_w, 1),
        })

    if unknown:
        return {"status": "unverified", "regulated": True, "clause": LIGHTING_STANDARD,
                "detail": f"no Table J7D3a value seeded for space(s): {sorted(set(unknown))}",
                "breakdown": breakdown}

    compliant = total_design_w <= total_allowance_w
    margin_w = round(total_allowance_w - total_design_w, 1)
    return {
        "status": "compliant" if compliant else "non_compliant",
        "regulated": True, "method": "aggregate (J7D3(2)(a))",
        "total_design_w": round(total_design_w, 1),
        "total_allowance_w": round(total_allowance_w, 1),
        "margin_w": margin_w, "clause": LIGHTING_STANDARD,
        "breakdown": breakdown,
        "detail": (f"aggregate design {round(total_design_w):,} W vs allowance "
                   f"{round(total_allowance_w):,} W → "
                   f"{'within' if compliant else 'EXCEEDS'} by {abs(margin_w):,} W"),
    }


def check_ncc_compliance(
    component: str, value: float | None = None,
    climate_zone: int | None = None, space: str = "office_200lx_or_more",
) -> dict:
    """Dispatch a retrofit component to the right NCC Section J treatment.

    Returns {status, clause, detail, ...}. Crucially distinguishes *not regulated*
    and *requires calculation* from genuine compliant/non-compliant — so the system
    never claims code compliance for a parameter the code doesn't actually govern.
    """
    comp = component.strip().lower()

    if comp in ("lighting_power_density", "illumination_power_density"):
        if value is None:
            return {"status": "unverified", "regulated": True,
                    "clause": LIGHTING_STANDARD, "detail": "no value supplied"}
        return check_lighting_power_density(value, space)

    if comp in _NOT_REGULATED:
        return {
            "status": "not_regulated", "regulated": False,
            "clause": "NCC 2022 Volume One, Part J7 (does not apply)",
            "detail": ("plug-load / equipment power density is not regulated by NCC "
                       "Section J — appliances on general-purpose socket outlets are "
                       "explicitly excluded. Energy benefit is real; code compliance "
                       "is N/A."),
        }

    if comp in _REQUIRES_CALC:
        return {
            "status": "requires_calculation", "regulated": True,
            "clause": FABRIC_STANDARD,
            "detail": ("NCC J4 building-fabric compliance uses a façade/fabric "
                       "calculation (U-value × area + SHGC, by climate zone), not a "
                       "single-value limit. Full check needs the J4 calculator (Tier 2)."),
        }

    return {"status": "unverified", "regulated": None,
            "clause": "NCC 2022 Section J (component not mapped)",
            "detail": f"no NCC mapping for component '{component}'"}
