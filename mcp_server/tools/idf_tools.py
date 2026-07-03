"""IDF Management tools (5 of the 20 core tools).

load_idf · inspect_idf · clone_idf · modify_idf_component · validate_idf

Uses eppy for IDF parsing. Originals are never mutated — clone_idf first.
"""
import shutil
import uuid
from pathlib import Path

from mcp_server.schemas.tool_schemas import IDFSummary, wrap

WORK_DIR = Path("data/working")
WORK_DIR.mkdir(parents=True, exist_ok=True)


def _run_tag(run_tag: str | None) -> str:
    """A short, filesystem-safe token that makes a working filename unique per run.

    Concurrent visitors run the same city/scenario, so run-agnostic working
    filenames ({stem}__baseline.idf etc.) collide — one run overwrites another's
    in-flight working IDF. Callers thread the real run id (api pipeline → sim_runner
    → these tools); when absent (a bare tool call) we fall back to a uuid4 slice so
    the file is still unique. Sanitised to keep the filename well-formed.
    """
    tag = (run_tag or uuid.uuid4().hex[:8]).strip()
    safe = "".join(c if (c.isalnum() or c in "-_") else "_" for c in tag)
    return safe[:16] or uuid.uuid4().hex[:8]


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


# ── Assembly U-value (envelope) ────────────────────────────────────────────
# Still-air surface film resistances (m²·K/W), NCC/ASHRAE convention. Quote a
# target U INCLUDING these films. Named constants, not magic numbers.
WALL_FILMS_R = 0.13 + 0.04   # inside + outside, vertical surface  → 0.17
ROOF_FILMS_R = 0.10 + 0.04   # inside + outside, heat flow up      → 0.14
K_MIN, K_MAX = 0.005, 5.0    # physical conductivity clamp (W/m·K)
_R_INSUL_FLOOR = 0.01        # min insulation R when a target U is unachievably high


def _construction_layers(constr) -> list[str]:
    """Layer material names, outside→inside (Outside_Layer, Layer_2, …)."""
    out = []
    for f in getattr(constr, "fieldnames", []):
        if f == "Outside_Layer" or f.startswith("Layer_"):
            v = getattr(constr, f, "")
            if v:
                out.append(v)
    return out


def _material_r(idf, name: str):
    """(R m²·K/W, kind, object) for a layer. kind ∈ {mass, nomass, other}.

    mass   = Material (R = Thickness/Conductivity, editable via Conductivity)
    nomass = Material:NoMass / Material:AirGap (editable via Thermal_Resistance)
    other  = window/unknown → not an editable opaque-insulation layer.
    """
    m = idf.getobject("MATERIAL", name)
    if m is not None:
        t, k = _num(m.Thickness), _num(m.Conductivity)
        if t and k:
            return t / k, "mass", m
    for cls in ("MATERIAL:NOMASS", "MATERIAL:AIRGAP"):
        m = idf.getobject(cls, name)
        if m is not None:
            r = _num(getattr(m, "Thermal_Resistance", None))
            if r:
                return r, "nomass", m
    return None, "other", None


def _is_attic_zone(idf, zone_name: str) -> bool:
    """An unconditioned attic: name says so, or no internal loads reference it.

    DOE Small Office puts the roof deck over an unconditioned attic — the real
    insulation is the attic FLOOR (ceiling of the conditioned space), not the
    membrane. We detect the attic so the roof U edits the right construction.
    """
    if "attic" in (zone_name or "").lower():
        return True
    for cls in ("LIGHTS", "ELECTRICEQUIPMENT", "PEOPLE"):
        for o in idf.idfobjects.get(cls, []):
            if getattr(o, "Zone_or_ZoneList_or_Space_or_SpaceList_Name",
                       getattr(o, "Zone_or_ZoneList_Name", "")) == zone_name:
                return False
    return True


def _construction_insulation_r(idf, cname: str) -> float:
    """Max editable opaque-layer R in a construction (its 'insulation' R), else 0.

    The real thermal boundary of a roof is whichever candidate construction has
    the most insulation — this is what distinguishes a genuine insulated roof
    deck / attic-floor from an interior drop-ceiling.
    """
    constr = idf.getobject("CONSTRUCTION", cname)
    if constr is None:
        return 0.0
    best = 0.0
    for ln in _construction_layers(constr):
        r, kind, _ = _material_r(idf, ln)
        if r is not None and kind in ("mass", "nomass"):
            best = max(best, r)
    return best


def _target_constructions(idf, surface_class: str) -> list[str]:
    """Construction names for outdoor walls / roofs (walk surfaces, never name-match).

    Roof: the real insulated boundary may be the attic FLOOR/ceiling rather than
    the membrane (Small office, unconditioned attic) or the roof deck itself
    (Medium office, return plenum). Rather than guess from zone type, we collect
    both the roof constructions and the ceiling/floor constructions of any
    unconditioned roof-side zone, then keep the candidate(s) with the most
    insulation — the genuine thermal boundary — and drop interior drop-ceilings.
    """
    surfaces = idf.idfobjects.get("BUILDINGSURFACE:DETAILED", [])
    want = "wall" if surface_class == "wall" else "roof"
    names, zones = [], set()
    for s in surfaces:
        obc = str(getattr(s, "Outside_Boundary_Condition", "")).lower()
        st = str(getattr(s, "Surface_Type", "")).lower()
        if obc == "outdoors" and st == want:
            cn = s.Construction_Name
            if cn and cn not in names:
                names.append(cn)
            zones.add(s.Zone_Name)

    if surface_class != "roof":
        return names

    candidates = list(names)
    for z in zones:
        if not _is_attic_zone(idf, z):
            continue
        for s in surfaces:
            st = str(getattr(s, "Surface_Type", "")).lower()
            obc = str(getattr(s, "Outside_Boundary_Condition", "")).lower()
            if (s.Zone_Name == z and st in ("floor", "ceiling") and obc == "surface"
                    and s.Construction_Name and s.Construction_Name not in candidates):
                candidates.append(s.Construction_Name)

    scored = [(c, _construction_insulation_r(idf, c)) for c in candidates]
    best_r = max((r for _, r in scored), default=0.0)
    if best_r <= 0:
        return names
    # Keep genuinely insulated boundaries; drop interior ceilings (low R).
    threshold = max(0.3, 0.5 * best_r)
    return [c for c, r in scored if r >= threshold] or names


def required_insulation_r(r_other: float, r_films: float, target_u: float) -> float:
    """The insulation layer's required R to hit `target_u` (assembly, incl. films).

    R_total_target = 1/U ; R_insul_target = R_total_target − R_films − R_other.
    Pure arithmetic — unit-tested against the spec §3.1 worked example.
    """
    return (1.0 / target_u) - r_films - r_other


def set_construction_u_value_core(idf, surface_class: str, target_u: float) -> dict:
    """Retune wall/roof assembly U by adjusting the insulation layer (R-inversion).

    Opaque constructions expose no U field, so U is changed by retuning the
    highest-R (insulation) layer. Operates on a parsed eppy IDF and mutates it in
    place (caller saves). Returns achieved vs target U per construction.
    """
    surface_class = (surface_class or "").lower()
    if surface_class not in ("wall", "roof"):
        return {"error": f"surface_class must be 'wall' or 'roof', got {surface_class!r}"}
    tu = _num(target_u)
    if tu is None or tu <= 0:
        return {"error": f"target_u must be a positive number, got {target_u!r}"}

    r_films = WALL_FILMS_R if surface_class == "wall" else ROOF_FILMS_R
    targets = _target_constructions(idf, surface_class)
    if not targets:
        return {"error": f"no outdoor {surface_class} constructions found"}

    out = []
    for cname in targets:
        constr = idf.getobject("CONSTRUCTION", cname)
        if constr is None:
            continue
        layers = [(ln, *_material_r(idf, ln)) for ln in _construction_layers(constr)]
        editable = [(ln, r, kind, obj) for ln, r, kind, obj in layers
                    if r is not None and kind in ("mass", "nomass")]
        if not editable:
            out.append({"construction": cname, "error": "no editable opaque layer"})
            continue
        ins_name, r_insul, kind, obj = max(editable, key=lambda x: x[1])
        r_materials = sum(r for _, r, _, _ in layers if r is not None)
        r_other = r_materials - r_insul

        r_target = required_insulation_r(r_other, r_films, tu)
        warning = None
        if r_target <= _R_INSUL_FLOOR:
            r_target = _R_INSUL_FLOOR
            warning = ("target U too high for this assembly even with minimal "
                       f"insulation; achievable U_max ≈ "
                       f"{round(1.0 / (r_films + r_other + _R_INSUL_FLOOR), 3)}")

        if kind == "mass":
            thickness = _num(obj.Thickness)
            k_new = thickness / r_target
            k_new = max(K_MIN, min(K_MAX, k_new))
            old, obj.Conductivity = _num(obj.Conductivity), k_new
            r_insul_new, new_value = thickness / k_new, round(k_new, 6)
            field = "Conductivity"
        else:  # nomass / airgap
            old = _num(obj.Thermal_Resistance)
            new_value = round(r_target, 4)
            obj.Thermal_Resistance = new_value
            r_insul_new, field = new_value, "Thermal_Resistance"

        achieved_u = 1.0 / (r_films + r_other + r_insul_new)
        out.append({
            "construction": cname, "layer_changed": ins_name, "layer_kind": kind,
            "field": field, "old_value": old, "new_value": new_value,
            "achieved_u": round(achieved_u, 4), "target_u": tu,
            "within_tol": abs(achieved_u - tu) / tu <= 0.02, "warning": warning,
        })

    achieved = [c["achieved_u"] for c in out if "achieved_u" in c]
    return {
        "surface_class": surface_class, "target_u": tu, "r_films": r_films,
        "achieved_u": round(sum(achieved) / len(achieved), 4) if achieved else None,
        "constructions": out,
        "units": "U in W/m²·K (assembly, including standard air films)",
        "note": "nominal still-air-film U; EnergyPlus uses dynamic films at "
                "runtime, so verify by simulated EUI direction (RULES #8), not .eio U.",
    }


# ── Localization (EPW location-matched) ────────────────────────────────────
def read_epw_location(epw_path: str):
    """Parse an EPW's LOCATION header → site name + coordinates.

    Line 1 of every EPW: LOCATION,<city>,<state>,<country>,<source>,<WMO>,
    <lat>,<lon>,<timezone>,<elevation>.
    """
    try:
        with open(epw_path, encoding="latin-1") as f:
            parts = f.readline().strip().split(",")
    except OSError:
        return None
    if len(parts) < 10 or parts[0].strip().upper() != "LOCATION":
        return None
    try:
        return {"name": parts[1].strip() or "Site",
                "lat": float(parts[6]), "lon": float(parts[7]),
                "tz": float(parts[8]), "elev": float(parts[9])}
    except (ValueError, IndexError):
        return None


def epw_mean_drybulb(epw_path: str):
    """Annual mean dry-bulb (°C) from an EPW — a defensible undisturbed-ground
    approximation, far closer than a Chicago ground profile for an AU site."""
    total, n = 0.0, 0
    try:
        with open(epw_path, encoding="latin-1") as f:
            for _ in range(8):       # skip the 8 EPW header lines
                f.readline()
            for line in f:
                cols = line.split(",")
                if len(cols) > 6:
                    v = _num(cols[6])
                    if v is not None and -70 < v < 70:
                        total += v
                        n += 1
    except OSError:
        return None
    return round(total / n, 1) if n else None


def localize_idf_core(idf, epw_path: str) -> dict:
    """Re-point an IDF's SITE to its weather file (spec §5): Site:Location from the
    EPW header, Chicago design days → weather-file-driven sizing, ground temps →
    the EPW annual mean. Makes 'EPW location-matched' literally true instead of
    only swapping the weather at run time while the model still thinks it's Chicago.
    """
    loc = read_epw_location(epw_path)
    if not loc:
        return {"error": f"could not read LOCATION from EPW: {epw_path}"}

    sites = idf.idfobjects.get("SITE:LOCATION", [])
    before = getattr(sites[0], "Name", None) if sites else None
    if sites:
        s = sites[0]
        s.Name, s.Latitude, s.Longitude = loc["name"], loc["lat"], loc["lon"]
        s.Time_Zone, s.Elevation = loc["tz"], loc["elev"]
    else:
        idf.newidfobject("SITE:LOCATION", Name=loc["name"], Latitude=loc["lat"],
                         Longitude=loc["lon"], Time_Zone=loc["tz"],
                         Elevation=loc["elev"])

    # Chicago design days → size from THIS weather file's extreme periods.
    removed = 0
    for d in list(idf.idfobjects.get("SIZINGPERIOD:DESIGNDAY", [])):
        idf.removeidfobject(d)
        removed += 1
    have_wfct = bool(idf.idfobjects.get("SIZINGPERIOD:WEATHERFILECONDITIONTYPE", []))
    if removed and not have_wfct:
        for nm, sel in (("Summer Extreme Week", "SummerExtreme"),
                        ("Winter Extreme Week", "WinterExtreme")):
            idf.newidfobject(
                "SIZINGPERIOD:WEATHERFILECONDITIONTYPE", Name=nm,
                Period_Selection=sel, Day_of_Week_for_Start_Day="Monday",
                Use_Weather_File_Daylight_Saving_Period="No",
                Use_Weather_File_Rain_and_Snow_Indicators="No")

    # Ground temps → EPW annual mean (Chicago values are far too cold for AU).
    ground = epw_mean_drybulb(epw_path)
    if ground is not None:
        for g in idf.idfobjects.get("SITE:GROUNDTEMPERATURE:BUILDINGSURFACE", []):
            for mon in ("January", "February", "March", "April", "May", "June",
                        "July", "August", "September", "October", "November",
                        "December"):
                setattr(g, f"{mon}_Ground_Temperature", ground)

    return {"site_name": loc["name"], "was": before, "latitude": loc["lat"],
            "longitude": loc["lon"], "time_zone": loc["tz"],
            "design_days_removed": removed, "ground_temp_c": ground,
            "sizing": "weather-file extreme periods"}


# ── Australian whole-building office realism profile ────────────────────────
# The DOE reference office is a code-minimum, TENANCY-HOURS model: out of hours the
# building essentially shuts down (HVAC off → fans only ~2.5% of energy), so it runs
# like an idealised empty office and lands in the top-performing quartile, BELOW the
# real NABERS whole-building cohort we benchmark against. A real whole building never
# fully shuts down — base-building HVAC conditions the building after hours, comms /
# server rooms and idle equipment run continuously, and security / common-area
# lighting stays on. This profile applies those documented AU operating assumptions
# so the baseline reflects a real whole building. It corrects OPERATION (not just the
# total) so the end-use MIX stays realistic — it never fits the output.
# Typical EXISTING Australian office values (the cohort is existing stock, not new
# code-builds). Each is independently defensible for AU existing offices — chosen to
# represent a real typical building, never to hit a target EUI.
AU_PLUG_W_M2 = 12.0          # tenant plug/IT density — modern AU office (NCC/NABERS ~11–15)
AU_HVAC_COP = 2.8           # typical existing DX/chiller (new-build ~3.2–4; existing stock lower)
AU_INFILTRATION_ACH = 0.5   # leakier existing envelope (new-build ~0.3)
AU_VAV_MIN_FLOW = 0.40      # existing VAV min flow / over-ventilated zones → more fan + reheat
AU_OCC_BASE, AU_LIGHT_BASE, AU_EQUIP_BASE = 0.05, 0.15, 0.40  # after-hours base (building never fully off)
AU_OCC_PEAK, AU_LIGHT_PEAK, AU_EQUIP_PEAK = 1.0, 0.9, 0.9     # 7am–7pm occupied
AU_HOURS = ("07:00", "19:00")  # AU office operating window


def _refs(idf, cls: str, field: str) -> set[str]:
    out = set()
    for o in idf.idfobjects.get(cls.upper(), []):
        v = getattr(o, field, None)
        if v:
            out.add(str(v))
    return out


def _set_au_schedule(idf, name: str, base: float, peak: float,
                     start: str = AU_HOURS[0], end: str = AU_HOURS[1]) -> bool:
    """Rewrite a fraction Schedule:Compact to a 7am–7pm AU office week: peak in the
    occupied window, an after-hours `base` floor (never fully off), Saturday part-
    load. Skips constant ('ALWAYS_*') and lift schedules so we don't break them."""
    up = name.upper()
    if "ALWAYS" in up or "ELEVATOR" in up or "LIFT" in up:
        return False
    sch = idf.getobject("SCHEDULE:COMPACT", name)
    if sch is None:
        return False
    tl = sch.obj[2] if len(sch.obj) > 2 else "Fraction"
    sat = round(base + (peak - base) * 0.5, 3)
    sch.obj = [sch.obj[0], name, tl,
               "Through: 12/31",
               "For: Weekdays", f"Until: {start}", base, f"Until: {end}", peak,
               "Until: 24:00", base,
               "For: Saturday", "Until: 08:00", base, "Until: 14:00", sat,
               "Until: 24:00", base,
               "For: AllOtherDays", "Until: 24:00", base]
    return True


def _set_cop(idf, cop: float) -> int:
    n = 0
    for o in idf.idfobjects.get("COIL:COOLING:DX:TWOSPEED", []):
        o.High_Speed_Gross_Rated_Cooling_COP = cop
        o.Low_Speed_Gross_Rated_Cooling_COP = cop
        n += 1
    for o in idf.idfobjects.get("COIL:COOLING:DX:SINGLESPEED", []):
        o.Gross_Rated_Cooling_COP = cop
        n += 1
    for cls in ("CHILLER:ELECTRIC:REFORMULATEDEIR", "CHILLER:ELECTRIC:EIR"):
        for o in idf.idfobjects.get(cls, []):
            o.Reference_COP = cop
            n += 1
    return n


def _set_infiltration_ach(idf, ach: float) -> int:
    n = 0
    for o in idf.idfobjects.get("ZONEINFILTRATION:DESIGNFLOWRATE", []):
        o.Design_Flow_Rate_Calculation_Method = "AirChanges/Hour"
        o.Air_Changes_per_Hour = ach
        n += 1
    return n


def _set_vav_min_flow(idf, frac: float) -> int:
    n = 0
    for o in idf.idfobjects.get("AIRTERMINAL:SINGLEDUCT:VAV:REHEAT", []):
        if str(getattr(o, "Zone_Minimum_Air_Flow_Input_Method", "")).strip() == "Constant":
            o.Constant_Minimum_Air_Flow_Fraction = frac
            n += 1
    return n


_ENDUSE_METERS = (
    "InteriorLights:Electricity", "InteriorEquipment:Electricity",
    "Fans:Electricity", "Cooling:Electricity", "Heating:Electricity",
    "Heating:NaturalGas", "Pumps:Electricity", "HeatRejection:Electricity",
    "WaterSystems:Electricity", "ExteriorLights:Electricity",
)


def _ensure_enduse_meters(idf) -> list[str]:
    """Make sure every HVAC end-use meter is written to eplusout.csv. The DOE IDFs
    output Fans/Cooling/Heating but NOT Pumps or HeatRejection, so a central-plant
    building's pump + cooling-tower energy is in the total but unattributed in the
    end-use breakdown. Add the missing meters so HVAC share is complete + provable."""
    existing = {str(getattr(o, "Key_Name", "")) for o in
                idf.idfobjects.get("OUTPUT:METER", [])}
    added = []
    for m in _ENDUSE_METERS:
        if m not in existing:
            idf.newidfobject("OUTPUT:METER", Key_Name=m, Reporting_Frequency="Hourly")
            added.append(m)
    return added


def apply_au_office_profile_core(idf, *, plug_w_m2: float = AU_PLUG_W_M2,
                                 hvac_cop: float = AU_HVAC_COP,
                                 infiltration_ach: float = AU_INFILTRATION_ACH,
                                 vav_min_flow: float = AU_VAV_MIN_FLOW) -> dict:
    """Turn the idealised DOE new-build into a typical EXISTING AU whole-building
    office (the cohort population). Mutates in place; resolves schedules BY
    REFERENCE so it works for any DOE prototype. Returns exactly what was applied."""
    # 1. Tenant plug/IT load.
    plug_set = 0
    for o in idf.idfobjects.get("ELECTRICEQUIPMENT", []):
        if str(getattr(o, "Design_Level_Calculation_Method", "")).lower().strip() == "watts/area":
            o.Watts_per_Floor_Area = plug_w_m2
            plug_set += 1

    # 2. Operating profile — 7am–7pm + after-hours base. Resolve the schedules
    #    actually referenced (works on Medium AND Large), skip lift/always.
    occ = sorted(_refs(idf, "People", "Number_of_People_Schedule_Name"))
    lit = sorted(_refs(idf, "Lights", "Schedule_Name"))
    eqp = sorted(_refs(idf, "ElectricEquipment", "Schedule_Name"))
    hvac = sorted(_refs(idf, "Fan:VariableVolume", "Availability_Schedule_Name")
                  | _refs(idf, "Fan:SystemModel", "Availability_Schedule_Name")
                  | _refs(idf, "Fan:ConstantVolume", "Availability_Schedule_Name"))
    sched_done = []
    for nm in occ:
        sched_done.append((nm, _set_au_schedule(idf, nm, AU_OCC_BASE, AU_OCC_PEAK)))
    for nm in lit:
        sched_done.append((nm, _set_au_schedule(idf, nm, AU_LIGHT_BASE, AU_LIGHT_PEAK)))
    for nm in eqp:
        sched_done.append((nm, _set_au_schedule(idf, nm, AU_EQUIP_BASE, AU_EQUIP_PEAK)))
    for nm in hvac:
        sched_done.append((nm, _set_au_schedule(idf, nm, 1.0, 1.0)))  # 24/7 available

    # 3. Typical-existing plant + envelope.
    cop_n = _set_cop(idf, hvac_cop)
    inf_n = _set_infiltration_ach(idf, infiltration_ach)
    vav_n = _set_vav_min_flow(idf, vav_min_flow)

    # 4. Complete end-use metering (so pumps + cooling towers are attributed).
    meters_added = _ensure_enduse_meters(idf)

    return {
        "meters_added": meters_added,
        "plug_w_m2": plug_w_m2, "plug_objects_set": plug_set,
        "operating_hours": f"{AU_HOURS[0]}–{AU_HOURS[1]} weekdays + Sat part-load + after-hours base",
        "schedules_rewritten": [n for n, ok in sched_done if ok],
        "hvac_cop": hvac_cop, "cop_objects": cop_n,
        "infiltration_ach": infiltration_ach, "infiltration_objects": inf_n,
        "vav_min_flow_fraction": vav_min_flow, "vav_terminals": vav_n,
    }


# ── Floor-area resize (REAL plan-geometry scaling) ─────────────────────────
_GEOM_TYPES = (
    "BUILDINGSURFACE:DETAILED", "FENESTRATIONSURFACE:DETAILED",
    "SHADING:SITE:DETAILED", "SHADING:BUILDING:DETAILED", "SHADING:ZONE:DETAILED",
    "DAYLIGHTING:REFERENCEPOINT",
)


def _surface_xy(obj) -> list[tuple[float, float]]:
    """(x, y) of a detailed surface's vertices, in field order."""
    xs: dict[int, float] = {}
    ys: dict[int, float] = {}
    for fname in obj.fieldnames:
        norm = fname.lower().replace("_", "")
        if "vertex" not in norm:
            continue
        digits = "".join(c for c in fname if c.isdigit())
        if not digits:
            continue
        v = _num(getattr(obj, fname, None))
        if v is None:
            continue
        if norm.endswith("xcoordinate"):
            xs[int(digits)] = v
        elif norm.endswith("ycoordinate"):
            ys[int(digits)] = v
    return [(xs[i], ys[i]) for i in sorted(xs) if i in ys]


def _polygon_area(xy: list[tuple[float, float]]) -> float:
    """Shoelace area of a (horizontal) polygon."""
    n = len(xy)
    if n < 3:
        return 0.0
    s = 0.0
    for i in range(n):
        x1, y1 = xy[i]
        x2, y2 = xy[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def _conditioned_floor_area(idf) -> float:
    """Conditioned floor area from geometry (sum of Floor surfaces in non-plenum
    zones) — available pre-sim, when Zone Floor_Area is 'autocalculate'."""
    total = 0.0
    for s in idf.idfobjects.get("BUILDINGSURFACE:DETAILED", []):
        if str(getattr(s, "Surface_Type", "")).lower() != "floor":
            continue
        if "plenum" in str(getattr(s, "Zone_Name", "")).lower():
            continue
        total += _polygon_area(_surface_xy(s))
    return round(total, 2)


def _scale_obj_xy(obj, k: float) -> int:
    """Scale every x/y coordinate + x/y origin on an object by k (z untouched).
    Returns how many fields were scaled."""
    n = 0
    for fname in obj.fieldnames:
        norm = fname.lower().replace("_", "")
        is_x = norm.endswith("xcoordinate") or norm == "xorigin"
        is_y = norm.endswith("ycoordinate") or norm == "yorigin"
        if not (is_x or is_y):
            continue
        v = _num(getattr(obj, fname, None))
        if v is None:
            continue
        setattr(obj, fname, round(v * k, 4))
        n += 1
    return n


def scale_floor_area_core(idf, target_area_m2: float) -> dict:
    """Resize the building to `target_area_m2` by scaling its PLAN geometry — the
    x,y of every surface/window/shading vertex AND every zone origin — by
    k = sqrt(target / current). Height (z) is unchanged; uniform scaling about the
    origin preserves every surface's shape, planarity, and inter-zone adjacency.

    This is a REAL geometry change EnergyPlus re-simulates: per-area loads (W/m²),
    envelope areas, and HVAC autosizing all follow, so a bigger building genuinely
    uses more energy. It is NOT a denominator rescale. Mutates in place."""
    current = _conditioned_floor_area(idf)
    if not current or current <= 0:
        return {"error": "could not measure current floor area from geometry"}
    k = (target_area_m2 / current) ** 0.5

    zones = sum(1 for z in idf.idfobjects.get("ZONE", []) if _scale_obj_xy(z, k))
    surfaces = 0
    for t in _GEOM_TYPES:
        for o in idf.idfobjects.get(t, []):
            if _scale_obj_xy(o, k):
                surfaces += 1

    return {
        "target_area_m2": round(target_area_m2, 1),
        "previous_area_m2": current,
        "achieved_area_m2": _conditioned_floor_area(idf),
        "scale_factor": round(k, 5),
        "zones_scaled": zones, "surfaces_scaled": surfaces,
    }


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
    def clone_idf(idf_path: str, scenario_name: str,
                  run_tag: str | None = None) -> dict:
        """Create a working copy for modification — never mutate originals.

        run_tag scopes the working filename to one run so concurrent visitors
        running the same scenario don't overwrite each other's working IDF
        (defaults to a uuid4 slice when a caller doesn't pass a run id).
        """
        src = Path(idf_path)
        if not src.exists():
            return wrap("clone_idf", {"error": f"file not found: {idf_path}"})
        dst = WORK_DIR / f"{src.stem}__{_run_tag(run_tag)}__{scenario_name}.idf"
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
    def localize_idf(idf_path: str, epw_path: str,
                     run_tag: str | None = None) -> dict:
        """Localize an IDF to its EPW (Site:Location, design days, ground temps)
        and save a localized working copy. Returns {localized_path, ...}.

        The DOE reference IDFs ship Chicago-localized; only the EPW is swapped to
        Australia at run time, so design days + ground temps stayed Chicago. This
        makes the site genuinely match the weather file before the sim runs.

        run_tag scopes the working filename per run so concurrent visitors on the
        same city don't clobber each other's localized IDF (uuid4 slice by default).
        """
        idf = _read_idf(idf_path)
        info = localize_idf_core(idf, epw_path)
        if "error" in info:
            return wrap("localize_idf", info)
        stem = Path(idf_path).stem
        epw_tag = Path(epw_path).stem.replace("AUS_", "").split(".")[0]
        dst = WORK_DIR / f"{stem}__{_run_tag(run_tag)}__loc_{epw_tag}.idf"
        idf.saveas(str(dst))
        info["localized_path"] = str(dst)
        return wrap("localize_idf", info)

    @mcp.tool()
    def apply_au_office_profile(idf_path: str, plug_w_m2: float = AU_PLUG_W_M2,
                                run_tag: str | None = None) -> dict:
        """Apply the Australian whole-building office realism profile and save a
        working copy. Lifts after-hours operation (HVAC availability, equipment +
        lighting floors) and the tenant plug load to AU norms, so the baseline
        reflects a real whole building instead of an idealised office-hours one.
        Returns {profiled_path, ...} listing exactly what was applied.

        run_tag scopes the working filename per run so concurrent visitors don't
        clobber each other's profiled IDF (uuid4 slice by default).
        """
        idf = _read_idf(idf_path)
        info = apply_au_office_profile_core(idf, plug_w_m2=plug_w_m2)
        dst = WORK_DIR / f"{Path(idf_path).stem}__{_run_tag(run_tag)}__au.idf"
        idf.saveas(str(dst))
        info["profiled_path"] = str(dst)
        return wrap("apply_au_office_profile", info)

    @mcp.tool()
    def set_construction_u_value(idf_path: str, surface_class: str,
                                 target_u: float) -> dict:
        """Set a wall/roof assembly U-value (W/m²·K, incl. air films) by retuning
        its insulation layer (R-value inversion).

        Opaque constructions have no U field, so U is changed by adjusting the
        highest-R layer's Conductivity (mass) or Thermal_Resistance (no-mass).
        surface_class ∈ {wall, roof}; walks BuildingSurface:Detailed to find the
        real constructions (handles the Small-office roof-over-attic case). The
        envelope-U editable input the demo exposes (spec §3, Tier B).
        """
        idf = _read_idf(idf_path)
        result = set_construction_u_value_core(idf, surface_class, target_u)
        if "error" not in result and any(
                "achieved_u" in c for c in result.get("constructions", [])):
            idf.save()
        return wrap("set_construction_u_value", result)

    @mcp.tool()
    def scale_floor_area(idf_path: str, target_area_m2: float) -> dict:
        """Resize the building to target_area_m2 by scaling its plan geometry
        (x,y of every vertex + zone origin) — a REAL geometry change EnergyPlus
        re-simulates, so per-area loads, envelope, and HVAC sizing all follow and
        a bigger building genuinely uses more energy. Height is unchanged. The
        floor-area editable input (spec §3) goes through here, not a denominator
        rescale; EUI stays ~area-invariant, as the physics dictates."""
        idf = _read_idf(idf_path)
        result = scale_floor_area_core(idf, target_area_m2)
        if "error" not in result:
            idf.save()
        return wrap("scale_floor_area", result)

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
