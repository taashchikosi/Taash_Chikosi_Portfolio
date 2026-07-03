#!/usr/bin/env python3
"""Build the real CBD whole-building office EUI cohorts, per city, for benchmark
validation.

RUN THIS ON A MACHINE WITH THE CBD DOWNLOAD (not the sandbox — the file is ~6.6 MB
and the sandbox can't fetch it). See docs/RUN_CBD_COHORTS.md.

What it does (and the correctness rules it enforces):
  1. WHOLE-BUILDING ONLY — filters CRT_Nabers_RatingScope == 'Whole Building'.
     ~79% of CBD rows are base-building (landlord services only); comparing those
     to a whole-building simulation is apples-to-oranges.
  2. OFFICES, MEDIUM + LARGE ONLY — small offices (<1,000 m²) are not in the CBD
     data (mandatory disclosure threshold is ≥1,000 m²).
  3. PER CITY — each demo city is a (state, metro postcode band) filter:
       Sydney NSW 2000–2249 · Melbourne VIC 3000–3207 ·
       Brisbane QLD 4000–4179 · Perth WA 6000–6199.
     Override a single city's band with --postcode-min/--postcode-max --city.

It computes EUI = CRT_Nabers_AnnualConsumption / CRT_Nabers_RatedArea per building
(deduped to the most recent certificate per building), then writes per-city cohort
stats to data/benchmarks/cbd_office_cohorts.json with verified flags.

Usage:
  python3 scripts/build_cbd_cohorts.py --input <cbd.csv> [--input <beec2.csv> ...]
  python3 scripts/build_cbd_cohorts.py --input cbd_register.csv \
      --output data/benchmarks/cbd_office_cohorts.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

try:
    import pandas as pd
except ImportError:
    sys.exit("pandas required: pip install pandas")

# --- Canonical column names (what the rest of the script uses) -----------------
COL_CONSUMPTION = "CRT_Nabers_AnnualConsumption"   # raw annual energy (MJ or kWh — auto-detected)
COL_RATED_AREA = "CRT_Nabers_RatedArea"            # m²
COL_SCOPE = "CRT_Nabers_RatingScope"               # 'Whole Building' | 'Base Building'
COL_STAR = "CRT_Nabers_StarRating"
COL_STATE = "B_State"
COL_POSTCODE = "B_PostCode"
COL_BUILDING_KEY = "B_HashedKey"
COL_AREA = "CRT_BuildingNla"                       # building NLA for size banding
DATE_COLS = ["CRT_Nabers_CertifiedDate", "CRT_CertificateIssueDate", "CRT_NabersCertifiedDate"]

REQUIRED = [COL_CONSUMPTION, COL_RATED_AREA, COL_SCOPE, COL_STATE, COL_POSTCODE]

# --- Schema normalisation ------------------------------------------------------
# Two real schemas exist: the data.gov.au CC-BY mirror (CRT_*/B_* names) and the
# official cbd.gov.au BEEC download ("Field (Nabers Data) (NABERS Data)" names).
ALIASES = {
    COL_CONSUMPTION: ["AnnualConsumption (Nabers Data) (NABERS Data)"],
    COL_RATED_AREA:  ["Rated Area (Nabers Data) (NABERS Data)"],
    COL_SCOPE:       ["Rating Scope (Nabers Data) (NABERS Data)"],
    COL_STAR:        ["Star Rating (Nabers Data) (NABERS Data)"],
    COL_STATE:       ["State (Address / Building) (Building)"],
    COL_POSTCODE:    ["Post Code (Address / Building) (Building)"],
    COL_BUILDING_KEY:["Address / Building",
                      "Building Name (Address / Building) (Building)"],
    COL_AREA:        ["Building NLA"],
    DATE_COLS[0]:    ["Certified Date (Nabers Data) (NABERS Data)"],
}

MJ_PER_KWH = 3.6
MJ_DETECT_THRESHOLD = 400.0       # raw median EUI above this ⇒ MJ, convert to kWh
PLAUSIBLE_EUI_MIN, PLAUSIBLE_EUI_MAX = 50.0, 400.0   # final cohort-median sanity guard

# Demo cities → (state, metro postcode band inclusive). Bands are tunable; they
# target the CBD/inner-metro office stock and mirror data/reference_buildings/
# catalog.json. NCC zone + grid factor live in the catalog, not here.
CITIES = {
    "sydney":    ("NSW", 2000, 2249),
    "melbourne": ("VIC", 3000, 3207),
    "brisbane":  ("QLD", 4000, 4179),
    "perth":     ("WA",  6000, 6199),
}

# Size bands by building NLA (m²): (label, min, max).
BANDS = [("medium", 2_500, 10_000), ("large", 30_000, 200_000)]

MIN_N = 30                 # below this, a cohort isn't meaningful — flag it.
EUI_SANITY_MIN, EUI_SANITY_MAX = 30.0, 1_000.0   # drop obviously-garbage rows.


def normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    rename = {}
    for canonical, alts in ALIASES.items():
        if canonical in df.columns:
            continue
        for alt in alts:
            if alt in df.columns:
                rename[alt] = canonical
                break
    return df.rename(columns=rename)


def _read_one(p: Path) -> pd.DataFrame:
    if p.suffix.lower() in (".xlsx", ".xls"):
        return pd.read_excel(p, sheet_name=0)        # BEEC data is on the first sheet
    return pd.read_csv(p, low_memory=False)


def load(inputs: list[Path]) -> pd.DataFrame:
    frames = []
    for p in inputs:
        if not p.exists():
            sys.exit(f"input not found: {p}")
        frames.append(normalise_columns(_read_one(p)))
    df = pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        sys.exit(f"missing required columns {missing}.\nFound: {sorted(df.columns)[:40]}...")
    return df


def prepare_whole_building(df: pd.DataFrame) -> pd.DataFrame:
    """Whole-building only, positive consumption/area, MJ→kWh, dedupe. City/postcode
    filtering happens later (per city) so the units auto-detect sees the full set."""
    df = df.copy()
    df = df[df[COL_SCOPE].astype(str).str.strip().str.lower() == "whole building"]
    df[COL_CONSUMPTION] = pd.to_numeric(df[COL_CONSUMPTION], errors="coerce")
    df[COL_RATED_AREA] = pd.to_numeric(df[COL_RATED_AREA], errors="coerce")
    df = df[(df[COL_CONSUMPTION] > 0) & (df[COL_RATED_AREA] > 0)]
    raw_eui = df[COL_CONSUMPTION] / df[COL_RATED_AREA]
    if raw_eui.median() > MJ_DETECT_THRESHOLD:
        print(f"  [units] raw median EUI {raw_eui.median():.0f} > {MJ_DETECT_THRESHOLD:.0f} "
              f"⇒ consumption is MJ; dividing by {MJ_PER_KWH} to get kWh.")
        df["eui"] = raw_eui / MJ_PER_KWH
    else:
        print(f"  [units] raw median EUI {raw_eui.median():.0f} ⇒ treating consumption as kWh.")
        df["eui"] = raw_eui
    df = df[(df["eui"] >= EUI_SANITY_MIN) & (df["eui"] <= EUI_SANITY_MAX)]
    date_col = next((c for c in DATE_COLS if c in df.columns), None)
    if COL_BUILDING_KEY in df.columns:
        if date_col:
            df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
            df = df.sort_values(date_col).drop_duplicates(COL_BUILDING_KEY, keep="last")
        else:
            df = df.drop_duplicates(COL_BUILDING_KEY, keep="last")
    return df


def city_slice(df: pd.DataFrame, state: str, pc_min: int, pc_max: int) -> pd.DataFrame:
    out = df[df[COL_STATE].astype(str).str.upper().str.strip() == state.upper()]
    pc = pd.to_numeric(out[COL_POSTCODE], errors="coerce")
    return out[(pc >= pc_min) & (pc <= pc_max)]


def band_size_col(df: pd.DataFrame) -> str:
    return COL_AREA if COL_AREA in df.columns else COL_RATED_AREA


def cohort_for(df: pd.DataFrame, city: str, label: str, lo: float, hi: float,
               size_col: str) -> dict:
    area = pd.to_numeric(df[size_col], errors="coerce")
    sub = df[(area >= lo) & (area < hi)]
    n = len(sub)
    eui = sub["eui"]
    star = pd.to_numeric(sub[COL_STAR], errors="coerce") if COL_STAR in sub.columns else None
    cohort = {
        "building_type": "office", "size_band": label, "location": city.capitalize(),
        "scope": "whole_building", "n": int(n),
        "eui_kwh_m2_yr": {
            "min": round(float(eui.min()), 1) if n else None,
            "p25": round(float(eui.quantile(0.25)), 1) if n else None,
            "median": round(float(eui.median()), 1) if n else None,
            "p75": round(float(eui.quantile(0.75)), 1) if n else None,
            "max": round(float(eui.max()), 1) if n else None,
        },
        "typical_star": (round(float(star.median()), 1)
                         if star is not None and n and star.notna().any() else None),
        "size_filter_m2": [lo, hi],
        "source": f"Commercial Building Disclosure (CBD) register — NABERS Energy "
                  f"whole-building offices, {city.capitalize()} metro",
    }
    median = cohort["eui_kwh_m2_yr"]["median"]
    # Verified only if BIG ENOUGH *and* the median is a physically plausible office
    # EUI — the second guard fails closed against a units/column bug.
    big_enough = n >= MIN_N
    plausible = median is not None and PLAUSIBLE_EUI_MIN <= median <= PLAUSIBLE_EUI_MAX
    cohort["verified"] = bool(big_enough and plausible)
    if not big_enough:
        cohort["warning"] = f"cohort too small (n={n} < {MIN_N}); verified=false"
    elif not plausible:
        cohort["warning"] = (f"median EUI {median} outside plausible office range "
                             f"[{PLAUSIBLE_EUI_MIN}-{PLAUSIBLE_EUI_MAX}] — likely a units/column "
                             f"bug; verified=false")
    return cohort


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", action="append", required=True, type=Path,
                    help="CBD CSV/XLSX (repeat for multiple files)")
    ap.add_argument("--output", type=Path,
                    default=Path("data/benchmarks/cbd_office_cohorts.json"))
    ap.add_argument("--city", choices=sorted(CITIES),
                    help="override the postcode band for a single city")
    ap.add_argument("--postcode-min", type=int)
    ap.add_argument("--postcode-max", type=int)
    args = ap.parse_args()

    cities = dict(CITIES)
    if args.city and args.postcode_min and args.postcode_max:
        state = cities[args.city][0]
        cities[args.city] = (state, args.postcode_min, args.postcode_max)

    whole = prepare_whole_building(load(args.input))
    size_col = band_size_col(whole)

    out_cities: dict[str, dict] = {}
    for city, (state, pc_min, pc_max) in cities.items():
        sl = city_slice(whole, state, pc_min, pc_max)
        cohorts = [cohort_for(sl, city, *b, size_col) for b in BANDS]
        out_cities[city] = {
            "state": state, "postcode_band": [pc_min, pc_max],
            "rows_after_filter": int(len(sl)), "cohorts": cohorts,
        }

    out = {
        "status": "REAL",
        "generated": date.today().isoformat(),
        "provenance": "Built by scripts/build_cbd_cohorts.py from the CBD register. "
                      "Whole-building offices only; per-city metro postcode band; "
                      "EUI = AnnualConsumption/RatedArea; deduped to most recent "
                      "certificate per building.",
        "cities": out_cities,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, indent=2))

    print(f"\nWrote {args.output}")
    for city, blk in out_cities.items():
        print(f"  {city.capitalize()} ({blk['state']}, pc {blk['postcode_band']}, "
              f"{blk['rows_after_filter']} rows):")
        for c in blk["cohorts"]:
            e = c["eui_kwh_m2_yr"]
            flag = "✅" if c["verified"] else "⚠️ unverified"
            print(f"    {c['size_band']:7} n={c['n']:4}  median={e['median']}  "
                  f"range[{e['min']}–{e['max']}]  star≈{c['typical_star']}  {flag}")


if __name__ == "__main__":
    main()
