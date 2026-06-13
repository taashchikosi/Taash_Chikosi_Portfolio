"""IDF Management tools (5 of the 20 core tools).

load_idf · inspect_idf · clone_idf · modify_idf_component · validate_idf

Uses eppy for IDF parsing. Originals are never mutated — clone_idf first.
"""
import shutil
from pathlib import Path

from mcp_server.schemas.tool_schemas import IDFSummary, wrap

WORK_DIR = Path("data/working")
WORK_DIR.mkdir(parents=True, exist_ok=True)


def _read_idf(idf_path: str):
    """Parse an IDF with eppy. Requires the matching IDD shipped with EnergyPlus."""
    from eppy.modeleditor import IDF  # lazy import — heavy

    idd = Path("/usr/local/EnergyPlus/Energy+.idd")
    if IDF.getiddname() is None and idd.exists():
        IDF.setiddname(str(idd))
    return IDF(idf_path)


def _num(value):
    """Safe float — IDF fields may be '', 'autocalculate', or None."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _zone_floor_area_m2(zones):
    """Sum ZONE Floor_Area (× Multiplier) where numerically declared.

    DOE reference IDFs declare Floor_Area per zone; if a model leaves it
    'autocalculate' (computed from geometry at run time) this returns None and
    the Retriever falls back. EnergyPlus' own Net Conditioned Area is only in the
    *post-run* table output, so pre-sim we use the declared zone areas.
    """
    total = 0.0
    for z in zones:
        fa = _num(getattr(z, "Floor_Area", None))
        if fa is None:
            continue
        mult = _num(getattr(z, "Multiplier", 1)) or 1.0
        total += fa * mult
    return round(total, 1) if total > 0 else None


def register_idf_tools(mcp) -> None:
    @mcp.tool()
    def load_idf(idf_path: str) -> dict:
        """Load a .idf file and return a parsed summary."""
        path = Path(idf_path)
        if not path.exists():
            return wrap("load_idf", {"error": f"file not found: {idf_path}"})
        idf = _read_idf(idf_path)
        zones = [z.Name for z in idf.idfobjects.get("ZONE", [])]
        summary = IDFSummary(
            idf_path=str(path),
            building_name=(idf.idfobjects["BUILDING"][0].Name
                           if idf.idfobjects.get("BUILDING") else None),
            zone_count=len(zones),
            zones=zones[:50],
            construction_count=len(idf.idfobjects.get("CONSTRUCTION", [])),
        )
        return wrap("load_idf", summary.model_dump())

    @mcp.tool()
    def inspect_idf(idf_path: str) -> dict:
        """Extract building metadata: zones, HVAC, envelope, floor area, location."""
        idf = _read_idf(idf_path)
        zones = idf.idfobjects.get("ZONE", [])

        location = None
        locs = idf.idfobjects.get("SITE:LOCATION", [])
        if locs:
            site = locs[0]
            location = {
                "name": getattr(site, "Name", None),
                "latitude": _num(getattr(site, "Latitude", None)),
                "longitude": _num(getattr(site, "Longitude", None)),
                "elevation_m": _num(getattr(site, "Elevation", None)),
            }

        data = {
            "zones": [z.Name for z in zones],
            "zone_count": len(zones),
            "floor_area_m2": _zone_floor_area_m2(zones),   # None if autocalculated
            "location": location,                          # None if no Site:Location
            "hvac_objects": sorted(
                {k for k in idf.idfobjects.keys()
                 if k.startswith(("HVACTEMPLATE", "AIRLOOPHVAC", "ZONEHVAC"))
                 and idf.idfobjects[k]}
            ),
            "materials": len(idf.idfobjects.get("MATERIAL", [])),
            "constructions": len(idf.idfobjects.get("CONSTRUCTION", [])),
            "schedules": len(idf.idfobjects.get("SCHEDULE:COMPACT", [])),
            # Present object types (non-empty) — lets the Modeler validate that a
            # retrofit's target type actually exists before proposing it.
            "object_types": sorted(k for k, v in idf.idfobjects.items() if v),
        }
        return wrap("inspect_idf", data)

    @mcp.tool()
    def clone_idf(idf_path: str, scenario_name: str) -> dict:
        """Create a working copy for modification — never mutate originals."""
        src = Path(idf_path)
        if not src.exists():
            return wrap("clone_idf", {"error": f"file not found: {idf_path}"})
        dst = WORK_DIR / f"{src.stem}__{scenario_name}.idf"
        shutil.copy2(src, dst)
        return wrap("clone_idf", {"cloned_path": str(dst), "scenario": scenario_name})

    @mcp.tool()
    def modify_idf_component(
        idf_path: str, object_type: str, object_name: str,
        field: str, new_value: str,
    ) -> dict:
        """Update a field on IDF object(s) and save.

        object_name='*' or 'ALL' applies the change to EVERY object of that type —
        how building-wide retrofits work (re-lamp all fixtures, reglaze all
        windows). A specific name targets one object.
        """
        idf = _read_idf(idf_path)
        objs = idf.idfobjects.get(object_type.upper(), [])
        if not objs:
            return wrap("modify_idf_component",
                        {"error": f"no objects of type {object_type}"})

        wildcard = object_name in ("*", "ALL", "all")
        targets = list(objs) if wildcard else \
            [o for o in objs if getattr(o, "Name", "") == object_name]
        if not targets:
            return wrap("modify_idf_component",
                        {"error": f"{object_type} '{object_name}' not found"})

        # Validate the field exists on the target object(s) BEFORE mutating —
        # eppy field names track the EnergyPlus version (e.g. E+ 24.2 renamed
        # Lights "Watts per Zone Floor Area" → "Watts per Floor Area"). A bad
        # field must surface as a structured error the agent can recover from,
        # not an unhandled exception that aborts the whole run.
        valid_fields = list(getattr(targets[0], "fieldnames", []))
        if valid_fields and field not in valid_fields:
            return wrap("modify_idf_component", {
                "error": f"field '{field}' not found on {object_type}",
                "valid_fields": valid_fields,
            })

        old_values = []
        for o in targets:
            old_values.append(str(getattr(o, field, None)))
            setattr(o, field, new_value)
        idf.save()
        return wrap("modify_idf_component", {
            "object_type": object_type, "object_name": object_name,
            "field": field, "new_value": new_value,
            "objects_modified": len(targets),
            "old_value": old_values[0] if len(old_values) == 1 else old_values,
        })

    @mcp.tool()
    def validate_idf(idf_path: str) -> dict:
        """Check IDF syntax parses and report basic completeness."""
        try:
            idf = _read_idf(idf_path)
        except Exception as exc:  # noqa: BLE001 — surface parse errors to agent
            return wrap("validate_idf", {"valid": False, "error": str(exc)})
        problems = []
        if not idf.idfobjects.get("BUILDING"):
            problems.append("no BUILDING object")
        if not idf.idfobjects.get("ZONE"):
            problems.append("no ZONE objects")
        return wrap("validate_idf", {"valid": not problems, "problems": problems})
