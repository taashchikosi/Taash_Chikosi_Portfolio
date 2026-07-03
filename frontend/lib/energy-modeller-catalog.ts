/**
 * Agentic Energy Modeller — building + city catalog (frontend mirror).
 *
 * This is the UI-side mirror of `data/reference_buildings/catalog.json`.
 * The backend resolves a (buildingKey, cityKey) pair to an IDF + EPW + carbon
 * factor from the JSON; this file feeds the demo's selector and characteristics
 * card. Keep the two in sync.
 *
 * Honesty rules baked in:
 *  - `nominalFloorAreaM2` is the DOE prototype's display area; the live run reads
 *    the authoritative area straight from the IDF, so the result may differ.
 *  - NCC zone + grid carbon factor are deterministic lookups, never LLM-authored.
 *  - A cohort benchmark only appears when it's been built locally from the real
 *    CBD register (verified=true). Absent ⇒ "builds locally", never faked.
 */

// Office scope is locked to Medium: it's the only size with a real disclosed CBD
// whole-building cohort to validate against (Large is n=4 — not benchmarkable).
export type BuildingKey = "medium_office";
export type CityKey = "sydney" | "melbourne" | "brisbane" | "perth";

export type BuildingDef = {
  key: BuildingKey;
  label: string;
  /** Real EnergyPlus model filename — sent to the backend as `idf_path` (pathsFor).
   *  MUST stay a `.idf` the backend has on disk, or `inspect_idf` fails and the run
   *  dies at the Retriever. Do NOT point this at the `.txt` download copy. */
  idf: string;
  /** Readable copy served from /public/models for the in-page download link only
   *  (browsers show `.txt` inline; the raw `.idf` would download as an unknown type).
   *  Display/UX only — never sent to the backend. */
  download: string;
  type: string;
  nominalFloorAreaM2: number;
  storeys: number;
  blurb: string;
};

export type CityDef = {
  key: CityKey;
  label: string;
  state: string;
  epw: string;
  nccClimateZone: number;
  nccZoneDescriptor: string;
  grid: string;
  electricityScope2: number; // kg CO2e / kWh, NGA 2025
  emissionFactorSource: string;
};

/** A real CBD whole-building office cohort, built locally via build_cbd_cohorts.py.
 *  p25/p75 are the realistic-range bounds the verification strip plots (and the
 *  backend Reviewer gates on); EUI in kWh/m²·yr. */
export type Cohort = { n: number; p25: number; medianEui: number; p75: number; verified: boolean };

export const REF_DIR = "data/reference_buildings";

export const BUILDINGS: BuildingDef[] = [
  {
    key: "medium_office",
    label: "Medium Office",
    idf: "RefBldgMediumOffice.idf",
    download: "RefBldgMediumOffice.txt",
    type: "office",
    nominalFloorAreaM2: 4982,
    storeys: 3,
    blurb:
      "DOE Commercial Reference Medium Office — 3 storeys, ~4,982 m². In the mandatory-disclosure size band, so every city has a real CBD whole-building office cohort.",
  },
  // Large office dropped: its CBD cohort is n=4 (not benchmarkable), so it can't be
  // validated against real disclosed data.
];

export const CITIES: CityDef[] = [
  {
    key: "sydney",
    label: "Sydney",
    state: "NSW",
    epw: "AUS_NSW_Sydney.epw",
    nccClimateZone: 5,
    nccZoneDescriptor: "Warm temperate",
    grid: "NSW grid",
    electricityScope2: 0.64,
    emissionFactorSource: "NGA 2025 NSW",
  },
  {
    key: "melbourne",
    label: "Melbourne",
    state: "VIC",
    epw: "AUS_VIC_Melbourne.epw",
    nccClimateZone: 6,
    nccZoneDescriptor: "Mild temperate",
    grid: "VIC grid",
    electricityScope2: 0.78,
    emissionFactorSource: "NGA 2025 VIC",
  },
  {
    key: "brisbane",
    label: "Brisbane",
    state: "QLD",
    epw: "AUS_QLD_Brisbane.epw",
    nccClimateZone: 2,
    nccZoneDescriptor: "Warm humid summer, mild winter",
    grid: "QLD grid",
    electricityScope2: 0.67,
    emissionFactorSource: "NGA 2025 QLD",
  },
  {
    key: "perth",
    label: "Perth",
    state: "WA",
    epw: "AUS_WA_Perth.epw",
    nccClimateZone: 5,
    nccZoneDescriptor: "Warm temperate",
    grid: "WA SWIS grid",
    electricityScope2: 0.5,
    emissionFactorSource: "NGA 2025 WA (SWIS)",
  },
];

/**
 * Verified CBD whole-building office cohorts, keyed `${cityKey}_${buildingKey}`.
 * Built from the REAL CBD register via scripts/build_cbd_cohorts.py (mirrors
 * data/benchmarks/cbd_office_cohorts.json, status=REAL, 2026-06-26). All four
 * medium-office cohorts clear n ≥ 30, so each city benchmarks against its OWN
 * disclosed-office IQR (p25–p75). EUI in kWh/m²·yr. Do not hand-edit — regenerate
 * from the script output.
 */
export const COHORTS: Partial<Record<string, Cohort>> = {
  sydney_medium_office:    { n: 96,  p25: 166.1, medianEui: 212.9, p75: 305.8, verified: true },
  melbourne_medium_office: { n: 130, p25: 126.2, medianEui: 182.8, p75: 300.0, verified: true },
  brisbane_medium_office:  { n: 78,  p25: 136.7, medianEui: 189.3, p75: 261.3, verified: true },
  perth_medium_office:     { n: 61,  p25: 133.3, medianEui: 192.8, p75: 273.1, verified: true },
};

export const cohortFor = (city: CityKey, building: BuildingKey): Cohort | undefined =>
  COHORTS[`${city}_${building}`];

/**
 * The six editable model inputs (spec §3). `field` is the backend `model_inputs`
 * key. `def` is the model's calibrated set-point — the slider's resting value and
 * "reset" target. CRITICAL: only inputs the user moves OFF `def` are sent to the
 * backend; an untouched input is omitted (null), so a default run is a true no-op
 * (the baseline lands inside the CBD cohort). Pushing an input far enough off `def`
 * moves the real EnergyPlus baseline EUI outside the cohort's p25–p75 → the Reviewer
 * genuinely withholds and routes back to the inputs. `worse` is the direction that
 * raises EUI (for the live hint). Defaults are the typical-existing AU office
 * operating point the backend applies by default (COP 2.8, infiltration 0.5 ACH,
 * plug 12 W/m², 7am–7pm hours) — so an untouched slider matches the realistic baseline.
 */
export type ModelInputDef = {
  field: string;
  label: string;
  unit: string;
  min: number;
  max: number;
  step: number;
  def: number;
  worse: "up" | "down";
  energy: boolean; // whether the input moves the simulated kWh (all feed the cohort gate via EUI)
  help: string;
};

export const MODEL_INPUTS: ModelInputDef[] = [
  { field: "hvac_cop", label: "HVAC cooling COP", unit: "W/W", min: 1.5, max: 6.0, step: 0.05, def: 2.8, worse: "down", energy: true,
    help: "DX/chiller efficiency (typical existing AU office). Lower COP → more energy to cool → higher EUI." },
  { field: "infiltration_ach", label: "Infiltration", unit: "ACH", min: 0.1, max: 2.0, step: 0.05, def: 0.5, worse: "up", energy: true,
    help: "Air changes per hour from leakage. Leakier envelope → higher EUI." },
  // Editable floor is clamped ABOVE the LED measure target (4.5 W/m²) so the what-if is always a real reduction.
  { field: "lighting_w_m2", label: "Lighting power", unit: "W/m²", min: 7.5, max: 20, step: 0.25, def: 10.76, worse: "up", energy: true,
    help: "Installed lighting power density. Higher → higher EUI." },
  // Floor clamped above the efficient-equipment target (8.0 W/m²).
  { field: "equipment_w_m2", label: "Equipment power", unit: "W/m²", min: 10.5, max: 25, step: 0.25, def: 12.0, worse: "up", energy: true,
    help: "Plug/equipment load density (modern AU office). Higher → higher EUI." },
  // Floor clamped above the double-glazing target (U 1.8 W/m²·K).
  { field: "window_u", label: "Window U-value", unit: "W/m²·K", min: 2.3, max: 6.0, step: 0.05, def: 3.24, worse: "up", energy: true,
    help: "Glazing conductance. Higher U → more heat flow → higher EUI." },
  { field: "window_shgc", label: "Window SHGC", unit: "—", min: 0.15, max: 0.85, step: 0.01, def: 0.39, worse: "up", energy: true,
    help: "Solar heat gain coefficient. Higher → more cooling load → higher EUI." },
  { field: "wall_u", label: "Wall U-value", unit: "W/m²·K", min: 0.15, max: 1.5, step: 0.01, def: 0.47, worse: "up", energy: true,
    help: "Wall assembly conductance (set via R-inversion). Higher → higher EUI." },
  { field: "roof_u", label: "Roof U-value", unit: "W/m²·K", min: 0.1, max: 1.2, step: 0.01, def: 0.36, worse: "up", energy: true,
    help: "Roof assembly conductance (set via R-inversion). Higher → higher EUI." },
  { field: "floor_area_m2", label: "Floor area", unit: "m²", min: 2500, max: 10000, step: 100, def: 4982, worse: "down", energy: false,
    help: "Bounded to the medium-office band (2,500–10,000 m²). Resizes the building's geometry (scales the plan), so EnergyPlus re-simulates a genuinely bigger/smaller building — per-area loads, envelope and HVAC sizing all follow. Total energy scales; EUI stays roughly flat (real physics)." },
];

export const buildingDef = (key: BuildingKey) => BUILDINGS.find((b) => b.key === key)!;
export const cityDef = (key: CityKey) => CITIES.find((c) => c.key === key)!;

/** Resolve the backend payload paths for a selection. */
export function pathsFor(building: BuildingKey, city: CityKey) {
  return {
    idf_path: `${REF_DIR}/${buildingDef(building).idf}`,
    epw_path: `${REF_DIR}/weather/${cityDef(city).epw}`,
    city,
  };
}
