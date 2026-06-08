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
        """Extract building metadata: zones, HVAC, envelope, schedules."""
        idf = _read_idf(idf_path)
        data = {
            "zones": [z.Name for z in idf.idfobjects.get("ZONE", [])],
            "hvac_objects": sorted(
                {k for k in idf.idfobjects.keys()
                 if k.startswith(("HVACTEMPLATE", "AIRLOOPHVAC", "ZONEHVAC"))
                 and idf.idfobjects[k]}
            ),
            "materials": len(idf.idfobjects.get("MATERIAL", [])),
            "constructions": len(idf.idfobjects.get("CONSTRUCTION", [])),
            "schedules": len(idf.idfobjects.get("SCHEDULE:COMPACT", [])),
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
        """Update one field on one IDF object (e.g. a U-value or setpoint) and save."""
        idf = _read_idf(idf_path)
        objs = idf.idfobjects.get(object_type.upper(), [])
        target = next((o for o in objs if getattr(o, "Name", "") == object_name), None)
        if target is None:
            return wrap("modify_idf_component",
                        {"error": f"{object_type} '{object_name}' not found"})
        old_value = getattr(target, field, None)
        setattr(target, field, new_value)
        idf.save()
        return wrap("modify_idf_component", {
            "object_type": object_type, "object_name": object_name,
            "field": field, "old_value": str(old_value), "new_value": new_value,
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
