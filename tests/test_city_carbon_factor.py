"""The selected city's grid drives the emission factor — not a hardcoded NSW value.

Guards the multi-city scope: Perth/Brisbane/Melbourne/Sydney each map to their own
NGA 2025 grid factor, derived deterministically from the weather file's state.
"""
import json
from pathlib import Path

import pytest

from api.main import _state_from_epw, carbon_factor_for_state

_BASE = Path(__file__).resolve().parent.parent
_NGA = json.loads((_BASE / "data/factors/nga_factors_2025.json").read_text())
_SCOPE2 = _NGA["electricity_scope2_kgco2e_per_kwh"]


@pytest.mark.parametrize("epw,state", [
    ("data/reference_buildings/weather/AUS_NSW_Sydney.epw", "NSW"),
    ("data/reference_buildings/weather/AUS_VIC_Melbourne.epw", "VIC"),
    ("data/reference_buildings/weather/AUS_QLD_Brisbane.epw", "QLD"),
    ("data/reference_buildings/weather/AUS_WA_Perth.epw", "WA"),
])
def test_state_parsed_from_epw(epw, state):
    assert _state_from_epw(epw) == state


def test_unknown_epw_fails_closed_to_nsw():
    assert _state_from_epw("garbage.epw") == "NSW"
    assert _state_from_epw("") == "NSW"


@pytest.mark.parametrize("state", ["NSW", "VIC", "QLD", "WA"])
def test_factor_matches_nga_table(state):
    value, source = carbon_factor_for_state(state)
    assert value == _SCOPE2[state]
    assert source == f"NGA 2025 {state}"


def test_cities_have_distinct_factors():
    # The whole point of the multi-city scope: the carbon number must move per city.
    factors = {s: carbon_factor_for_state(s)[0] for s in ("NSW", "VIC", "QLD", "WA")}
    assert len(set(factors.values())) == 4, factors


def test_catalog_factors_match_nga():
    """The catalog's per-city factor must equal the authoritative NGA table."""
    cat = json.loads((_BASE / "data/reference_buildings/catalog.json").read_text())
    for c in cat["cities"]:
        assert c["electricity_scope2_kgco2e_per_kwh"] == _SCOPE2[c["state"]], c["key"]
