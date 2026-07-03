"""set_construction_u_value — the envelope-U R-inversion tool (spec §3.1).

Two layers:
  • Pure arithmetic (always runs): the §3.1 worked example.
  • Real IDF integration (Docker only — needs the EnergyPlus IDD): set a target U
    on the actual Small/Medium walls + roofs and confirm the achieved assembly U
    lands within 2%, picking the correct insulation layer (incl. the Small-office
    roof-over-attic case where the insulation is the attic FLOOR, not the membrane).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from mcp_server.tools.idf_tools import (
    ROOF_FILMS_R, WALL_FILMS_R, required_insulation_r,
    set_construction_u_value_core,
)

_IDD = Path("/usr/local/EnergyPlus/Energy+.idd")
_needs_idd = pytest.mark.skipif(
    not _IDD.exists(), reason="needs EnergyPlus IDD (run in Docker)")
_MED = "data/reference_buildings/RefBldgMediumOffice.idf"
_SMALL = "data/reference_buildings/RefBldgSmallOffice.idf"


# ── Pure arithmetic — the spec §3.1 worked example ─────────────────────────
def test_required_insulation_r_worked_example():
    # Wall, target U 0.50, films 0.17, other layers R = 0.30 → R_insul = 1.53
    r_insul = required_insulation_r(r_other=0.30, r_films=WALL_FILMS_R, target_u=0.50)
    assert round(r_insul, 2) == 1.53
    # Insulation thickness 0.0889 m → Conductivity 0.0889/1.53 = 0.0581 W/m·K
    assert round(0.0889 / r_insul, 4) == 0.0581
    # Recompute: U = 1 / (0.17 + 0.30 + 1.53) = 0.50
    assert round(1.0 / (WALL_FILMS_R + 0.30 + r_insul), 2) == 0.50


def test_films_constants():
    assert round(WALL_FILMS_R, 2) == 0.17
    assert round(ROOF_FILMS_R, 2) == 0.14


def test_core_rejects_bad_inputs():
    class _Dummy:  # never reached — validation happens first
        pass
    assert "error" in set_construction_u_value_core(_Dummy(), "floor", 0.5)
    assert "error" in set_construction_u_value_core(_Dummy(), "wall", 0)
    assert "error" in set_construction_u_value_core(_Dummy(), "wall", -1)


# ── Real IDF integration (Docker) ──────────────────────────────────────────
def _read(idf_path):
    from mcp_server.tools.idf_tools import _read_idf
    return _read_idf(idf_path)


def _assert_hits(result, target_u):
    assert "error" not in result, result
    constrs = result["constructions"]
    assert constrs, "no constructions matched"
    for c in constrs:
        assert "achieved_u" in c, c
        assert c["within_tol"], c
        assert abs(c["achieved_u"] - target_u) / target_u <= 0.02
    return constrs


@_needs_idd
def test_medium_steel_frame_wall_hits_target():
    res = set_construction_u_value_core(_read(_MED), "wall", 0.45)
    constrs = _assert_hits(res, 0.45)
    assert any("Insulation" in c["layer_changed"] for c in constrs)


@_needs_idd
def test_medium_roof_hits_target():
    res = set_construction_u_value_core(_read(_MED), "roof", 0.30)
    constrs = _assert_hits(res, 0.30)
    assert any("Roof Insulation" in c["layer_changed"] for c in constrs)


@_needs_idd
def test_small_mass_wall_hits_target():
    res = set_construction_u_value_core(_read(_SMALL), "wall", 0.50)
    constrs = _assert_hits(res, 0.50)
    assert any("Insulation" in c["layer_changed"] for c in constrs)


@_needs_idd
def test_small_roof_uses_attic_floor_insulation():
    """Small office: roof is over an unconditioned attic — the tool must follow to
    the attic-floor/ceiling construction and edit its insulation, not the membrane."""
    res = set_construction_u_value_core(_read(_SMALL), "roof", 0.25)
    constrs = _assert_hits(res, 0.25)
    layers = {c["layer_changed"] for c in constrs}
    assert any("AtticFloor" in n or "Attic" in n for n in layers), layers


@_needs_idd
def test_unachievable_high_u_clamps_with_warning():
    # A very high target U can't be met even with no insulation → clamp + warn.
    res = set_construction_u_value_core(_read(_MED), "wall", 50.0)
    c = res["constructions"][0]
    assert c["warning"] is not None
