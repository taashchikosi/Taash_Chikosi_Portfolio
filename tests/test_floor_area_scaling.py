"""Geometry math for the real floor-area resize (scale_floor_area).

These test the PURE geometry transform with mock objects — no eppy/IDD/EnergyPlus
needed, so they run in the sandbox. The full IDF parse + EnergyPlus sim is the
Docker/Mac step (eppy needs the EnergyPlus IDD to read a real .idf).
"""
from __future__ import annotations

import math

from mcp_server.tools.idf_tools import (
    _conditioned_floor_area, _polygon_area, _scale_obj_xy, _surface_xy,
    scale_floor_area_core,
)


class FakeObj:
    """Mimics an eppy IDF object: named fields + a fieldnames list."""

    def __init__(self, fields: dict):
        self.fieldnames = list(fields.keys())
        for k, v in fields.items():
            setattr(self, k, v)


class FakeIDF:
    def __init__(self, objs: dict):
        self.idfobjects = objs


def _rect_floor(zone: str, w: float, h: float) -> FakeObj:
    """A rectangular Floor surface (w × h), counter-clockwise, at z=0."""
    return FakeObj({
        "Surface_Type": "Floor", "Zone_Name": zone,
        "Vertex_1_Xcoordinate": 0.0, "Vertex_1_Ycoordinate": 0.0, "Vertex_1_Zcoordinate": 0.0,
        "Vertex_2_Xcoordinate": w,   "Vertex_2_Ycoordinate": 0.0, "Vertex_2_Zcoordinate": 0.0,
        "Vertex_3_Xcoordinate": w,   "Vertex_3_Ycoordinate": h,   "Vertex_3_Zcoordinate": 0.0,
        "Vertex_4_Xcoordinate": 0.0, "Vertex_4_Ycoordinate": h,   "Vertex_4_Zcoordinate": 0.0,
    })


def test_polygon_area_rectangle():
    assert _polygon_area([(0, 0), (10, 0), (10, 5), (0, 5)]) == 50.0


def test_surface_xy_order():
    s = _rect_floor("Core", 40, 40)
    assert _surface_xy(s) == [(0.0, 0.0), (40.0, 0.0), (40.0, 40.0), (0.0, 40.0)]


def test_scale_obj_xy_scales_x_y_not_z():
    o = FakeObj({
        "X_Origin": 2.0, "Y_Origin": 3.0, "Z_Origin": 9.0,
        "Vertex_1_Xcoordinate": 10.0, "Vertex_1_Ycoordinate": 4.0, "Vertex_1_Zcoordinate": 7.0,
    })
    n = _scale_obj_xy(o, 2.0)
    assert n == 4  # X_Origin, Y_Origin, Vertex_1_Xcoordinate, Vertex_1_Ycoordinate
    assert o.X_Origin == 4.0 and o.Y_Origin == 6.0
    assert o.Vertex_1_Xcoordinate == 20.0 and o.Vertex_1_Ycoordinate == 8.0
    assert o.Z_Origin == 9.0 and o.Vertex_1_Zcoordinate == 7.0  # z untouched


def test_conditioned_area_excludes_plenums():
    idf = FakeIDF({"BUILDINGSURFACE:DETAILED": [
        _rect_floor("Core_bottom", 40, 40),       # 1600
        _rect_floor("TopFloor_Plenum", 40, 40),   # excluded
        FakeObj({"Surface_Type": "Roof", "Zone_Name": "Core_bottom"}),  # not a floor
    ]})
    assert _conditioned_floor_area(idf) == 1600.0


def test_scale_floor_area_core_hits_target_and_scales_vertices():
    floor = _rect_floor("Core", 40, 40)           # 1600 m²
    plenum = _rect_floor("Top_Plenum", 40, 40)    # excluded from area, still scaled
    zone = FakeObj({"X_Origin": 5.0, "Y_Origin": 0.0, "Z_Origin": 0.0})
    idf = FakeIDF({"BUILDINGSURFACE:DETAILED": [floor, plenum], "ZONE": [zone]})

    res = scale_floor_area_core(idf, target_area_m2=3200.0)   # 2× → k = √2

    assert "error" not in res
    assert res["previous_area_m2"] == 1600.0
    assert abs(res["achieved_area_m2"] - 3200.0) < 0.5
    assert math.isclose(res["scale_factor"], math.sqrt(2), rel_tol=1e-4)
    assert res["surfaces_scaled"] == 2 and res["zones_scaled"] == 1
    # the floor's vertices genuinely moved (x scaled by √2)
    assert math.isclose(floor.Vertex_2_Xcoordinate, 40 * math.sqrt(2), rel_tol=1e-4)
    assert zone.X_Origin == round(5.0 * math.sqrt(2), 4)


def test_scale_floor_area_core_errors_when_no_geometry():
    idf = FakeIDF({"BUILDINGSURFACE:DETAILED": []})
    assert "error" in scale_floor_area_core(idf, 3000.0)
