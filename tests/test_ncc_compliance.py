"""NCC 2022 Section J compliance — real, primary-verified checks.

Pins the domain truths that make this honest (not a hardcoded True):
  • Lighting power density IS regulated (J7D3, Table J7D3a) — a numeric check.
  • Equipment plug loads are NOT regulated by Section J.
  • Glazing/fabric needs the J4 façade calculation, not a flat limit.
"""
from __future__ import annotations

from verification.ncc_compliance import (
    NCC_J7D3A_IPD_W_M2, check_aggregate_lighting_compliance,
    check_lighting_power_density, check_ncc_compliance,
)


# ── Lighting (the one genuinely numeric check) ───────────────────────────────
def test_office_ipd_limit_is_the_verified_value():
    # NCC 2022 J7D3 Table J7D3a: office ≥200 lx → 4.5 W/m².
    assert NCC_J7D3A_IPD_W_M2["office_200lx_or_more"] == 4.5
    assert NCC_J7D3A_IPD_W_M2["office_under_200lx"] == 2.5


def test_led_at_limit_is_compliant():
    r = check_lighting_power_density(4.5, space="office_200lx_or_more")
    assert r["status"] == "compliant"
    assert r["limit_w_m2"] == 4.5
    assert r["margin_w_m2"] == 0.0


def test_six_watts_exceeds_office_limit():
    # The old catalog value (6.0) must be flagged non-compliant — this is the bug.
    r = check_lighting_power_density(6.0, space="office_200lx_or_more")
    assert r["status"] == "non_compliant"
    assert r["margin_w_m2"] == -1.5


def test_baseline_lpd_is_non_compliant():
    # DOE prototype baseline (10.76 W/m²) exceeds the NCC office max.
    assert check_lighting_power_density(10.76)["status"] == "non_compliant"


# ── Things NCC Section J does NOT regulate as a flat limit ────────────────────
def test_equipment_plug_loads_not_regulated():
    r = check_ncc_compliance("equipment_power_density", value=8.0, climate_zone=5)
    assert r["status"] == "not_regulated"
    assert r["regulated"] is False


def test_glazing_requires_calculation():
    r = check_ncc_compliance("glazing_u_value", value=1.8, climate_zone=5)
    assert r["status"] == "requires_calculation"


def test_lighting_through_dispatch_matches_direct_check():
    r = check_ncc_compliance("lighting_power_density", value=4.5, climate_zone=5)
    assert r["status"] == "compliant"
    assert "J7D3" in r["clause"]


def test_unknown_component_is_unverified_not_compliant():
    r = check_ncc_compliance("mystery_component", value=1.0)
    assert r["status"] == "unverified"


# ── Aggregate area-weighted check (the real J7D3(2)(a) method) ────────────────
def test_aggregate_all_under_limit_is_compliant():
    spaces = [
        {"space": "office_200lx_or_more", "area_m2": 400, "design_ipd_w_m2": 4.5},
        {"space": "corridor", "area_m2": 60, "design_ipd_w_m2": 4.0},
        {"space": "storage", "area_m2": 40, "design_ipd_w_m2": 1.2},
    ]
    r = check_aggregate_lighting_compliance(spaces)
    assert r["status"] == "compliant"
    assert r["total_design_w"] <= r["total_allowance_w"]


def test_aggregate_office_over_limit_is_non_compliant():
    # An office lit at 10.76 W/m² (DOE baseline) dominates → fails on aggregate.
    spaces = [
        {"space": "office_200lx_or_more", "area_m2": 460, "design_ipd_w_m2": 10.76},
        {"space": "storage", "area_m2": 51, "design_ipd_w_m2": 1.0},
    ]
    r = check_aggregate_lighting_compliance(spaces)
    assert r["status"] == "non_compliant"
    assert r["margin_w"] < 0


def test_aggregate_offsets_a_per_space_failure():
    # KEY: per-space, the office FAILS (5.0 > 4.5). But a large under-lit retail area
    # (2.0 vs 14.0 max) leaves huge headroom, so the building PASSES on aggregate —
    # which is exactly what J7D3(2)(a) assesses. A per-space-only checker would
    # wrongly reject this building.
    office_only = check_lighting_power_density(5.0, "office_200lx_or_more")
    assert office_only["status"] == "non_compliant"

    spaces = [
        {"space": "office_200lx_or_more", "area_m2": 100, "design_ipd_w_m2": 5.0},
        {"space": "retail", "area_m2": 400, "design_ipd_w_m2": 2.0},
    ]
    r = check_aggregate_lighting_compliance(spaces)
    assert r["status"] == "compliant"


def test_aggregate_unknown_space_fails_closed():
    spaces = [{"space": "spaceship_bridge", "area_m2": 50, "design_ipd_w_m2": 3.0}]
    assert check_aggregate_lighting_compliance(spaces)["status"] == "unverified"


def test_aggregate_empty_is_unverified():
    assert check_aggregate_lighting_compliance([])["status"] == "unverified"
