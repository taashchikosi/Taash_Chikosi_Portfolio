"""IDF localization to the weather file (spec §5).

Pure EPW-header parsing always runs; the eppy integration (Site:Location swap,
design-day replacement) runs only where the EnergyPlus IDD is present (Docker).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from mcp_server.tools.idf_tools import (
    epw_mean_drybulb, localize_idf_core, read_epw_location,
)

_IDD = Path("/usr/local/EnergyPlus/Energy+.idd")
_needs_idd = pytest.mark.skipif(not _IDD.exists(), reason="needs EnergyPlus IDD (Docker)")

_EPW_HEADER = "LOCATION,Sydney Airport,NSW,AUS,TMYx,947670,-33.95,151.18,10.0,6.0\n"


def _write_epw(tmp_path, drybulbs):
    lines = [_EPW_HEADER]
    lines += [f"H{i}\n" for i in range(7)]   # 7 more header lines (8 total)
    for i, db in enumerate(drybulbs):
        # Year,Month,Day,Hour,Minute,Source,DryBulb,...  → DryBulb is field index 6
        lines.append(f"2020,1,1,{i + 1},0,?,{db},0,0\n")
    p = tmp_path / "AUS_NSW_Sydney.epw"
    p.write_text("".join(lines))
    return str(p)


def test_read_epw_location(tmp_path):
    epw = _write_epw(tmp_path, [20.0])
    loc = read_epw_location(epw)
    assert loc["name"] == "Sydney Airport"
    assert loc["lat"] == -33.95 and loc["lon"] == 151.18
    assert loc["tz"] == 10.0 and loc["elev"] == 6.0


def test_read_epw_location_rejects_garbage(tmp_path):
    p = tmp_path / "bad.epw"
    p.write_text("not a location line\n")
    assert read_epw_location(str(p)) is None


def test_epw_mean_drybulb(tmp_path):
    epw = _write_epw(tmp_path, [10.0, 20.0, 30.0])
    assert epw_mean_drybulb(epw) == 20.0


@_needs_idd
def test_localize_medium_to_sydney_removes_chicago(tmp_path):
    from mcp_server.tools.idf_tools import _read_idf
    epw = _write_epw(tmp_path, [18.0] * 24)
    idf = _read_idf("data/reference_buildings/RefBldgMediumOffice.idf")
    # Pre-condition: ships Chicago.
    assert "chicago" in str(idf.idfobjects["SITE:LOCATION"][0].Name).lower()
    info = localize_idf_core(idf, epw)
    assert "error" not in info
    site = idf.idfobjects["SITE:LOCATION"][0]
    assert "chicago" not in str(site.Name).lower()
    assert abs(float(site.Latitude) - (-33.95)) < 0.01
    assert info["design_days_removed"] > 0
    # Sizing now comes from the weather file, not Chicago design days.
    assert idf.idfobjects.get("SIZINGPERIOD:WEATHERFILECONDITIONTYPE", [])
    assert not idf.idfobjects.get("SIZINGPERIOD:DESIGNDAY", [])
    assert info["ground_temp_c"] == 18.0
