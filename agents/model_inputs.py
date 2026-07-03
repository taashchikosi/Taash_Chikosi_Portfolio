"""Apply the demo's six editable model inputs to a working IDF — through REAL
EnergyPlus objects, not a projection (spec §4).

Every edit goes through the MCP tools on a *cloned* baseline IDF before the
baseline sim, so the resulting EUI is whatever the physics produces. Building-
aware where the spec's single field mapping doesn't hold across the prototypes
(verified against the on-disk IDFs):

  • HVAC COP   — Medium/Large use Coil:Cooling:DX:TwoSpeed (High + Low speed COP);
                 Small uses Coil:Cooling:DX:SingleSpeed. We set whichever exists.
  • Infiltration — Medium declares ZoneInfiltration as Flow/ExteriorArea, so the
                 Air_Changes_per_Hour field is IGNORED until the calculation
                 method is switched to AirChanges/Hour. We switch it, then set ACH.
  • Envelope U  — opaque constructions have no U field → the set_construction_u_value
                 tool (R-inversion) handles wall + roof.
  • Floor area  — a REAL geometry resize via scale_floor_area (scales x,y of every
                 vertex), so EnergyPlus re-simulates a genuinely bigger/smaller
                 building. NOT a denominator rescale; EUI stays ~area-invariant.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from verification.pydantic_schemas import ModelInputs

ToolCaller = Callable[..., Awaitable[dict[str, Any]]]


async def apply_model_inputs(call: ToolCaller, work_idf: str,
                             inputs: ModelInputs) -> list[dict]:
    """Apply every set energy input to `work_idf` in place. Returns a list of
    applied changes (for the SSE trace). Unset (None) inputs are never touched —
    so a default run is a true no-op."""
    changes: list[dict] = []

    async def _set(object_type: str, field: str, value) -> bool:
        res = await call("modify_idf_component", idf_path=work_idf,
                         object_type=object_type, object_name="*",
                         field=field, new_value=str(value))
        ok = isinstance(res, dict) and "error" not in res
        if ok:
            changes.append({"input": object_type, "field": field, "value": value,
                            "objects": res.get("objects_modified")})
        return ok

    # 1. HVAC COP — system-aware. Medium uses DX:TwoSpeed (two speeds), Small uses
    #    DX:SingleSpeed, and the Large office runs a central chilled-water plant
    #    (Chiller:Electric:ReformulatedEIR). Each call no-ops harmlessly where that
    #    equipment is absent, so one knob works across all three prototypes.
    if inputs.hvac_cop is not None:
        cop = inputs.hvac_cop
        if await _set("Coil:Cooling:DX:TwoSpeed",
                      "High_Speed_Gross_Rated_Cooling_COP", cop):
            await _set("Coil:Cooling:DX:TwoSpeed",
                       "Low_Speed_Gross_Rated_Cooling_COP", cop)
        await _set("Coil:Cooling:DX:SingleSpeed", "Gross_Rated_Cooling_COP", cop)
        await _set("Chiller:Electric:ReformulatedEIR", "Reference_COP", cop)
        await _set("Chiller:Electric:EIR", "Reference_COP", cop)

    # 2. Infiltration — force AirChanges/Hour first, else the ACH value is ignored
    #    on models that use Flow/ExteriorArea (the Medium office).
    if inputs.infiltration_ach is not None:
        await _set("ZoneInfiltration:DesignFlowRate",
                   "Design_Flow_Rate_Calculation_Method", "AirChanges/Hour")
        await _set("ZoneInfiltration:DesignFlowRate",
                   "Air_Changes_per_Hour", inputs.infiltration_ach)

    # 3. Internal gains.
    if inputs.lighting_w_m2 is not None:
        await _set("Lights", "Watts_per_Floor_Area", inputs.lighting_w_m2)
    if inputs.equipment_w_m2 is not None:
        await _set("ElectricEquipment", "Watts_per_Floor_Area", inputs.equipment_w_m2)

    # 4. Windows.
    if inputs.window_u is not None:
        await _set("WindowMaterial:SimpleGlazingSystem", "UFactor", inputs.window_u)
    if inputs.window_shgc is not None:
        await _set("WindowMaterial:SimpleGlazingSystem",
                   "Solar_Heat_Gain_Coefficient", inputs.window_shgc)

    # 5. Envelope U — Tier B, via the R-inversion tool (no direct U field).
    for surface_class, target in (("wall", inputs.wall_u), ("roof", inputs.roof_u)):
        if target is not None:
            res = await call("set_construction_u_value", idf_path=work_idf,
                             surface_class=surface_class, target_u=target)
            if isinstance(res, dict) and "error" not in res:
                changes.append({"input": f"{surface_class}_u", "target_u": target,
                                "achieved_u": res.get("achieved_u")})

    # 6. Floor area — a REAL geometry resize (scales x,y of every vertex + zone
    #    origin), so EnergyPlus re-simulates a genuinely bigger/smaller building
    #    (per-area loads + envelope + HVAC sizing all follow). NOT a denominator
    #    rescale — the authoritative area read after the sim drives the EUI.
    if inputs.floor_area_m2 is not None:
        res = await call("scale_floor_area", idf_path=work_idf,
                         target_area_m2=inputs.floor_area_m2)
        if isinstance(res, dict) and "error" not in res:
            changes.append({"input": "floor_area_m2",
                            "target_area_m2": inputs.floor_area_m2,
                            "achieved_area_m2": res.get("achieved_area_m2")})

    return changes
