"""Pre-run baseline simulations and cache results → instant demo mode.

Runs EnergyPlus for each reference building against the Sydney weather file,
extracts the key results, and stores them as JSON so get_reference_building
returns instantly (no 2-10 min wait during a live demo).

Run inside Docker (needs the energyplus binary):
    docker compose run --rm app python scripts/precache_baselines.py
"""
import json
import subprocess
import sys
from pathlib import Path

REF = Path("data/reference_buildings")
CACHE = REF / "cached_results"
EPW = REF / "weather" / "AUS_NSW_Sydney.epw"

BUILDINGS = {
    "small_office": REF / "RefBldgSmallOffice.idf",
    "medium_office": REF / "RefBldgMediumOffice.idf",
}


def run_one(name: str, idf: Path) -> dict | None:
    out_dir = CACHE / f"{name}_run"
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"⚙️  simulating {name} …")
    proc = subprocess.run(
        ["energyplus", "--weather", str(EPW), "--output-directory", str(out_dir),
         "--readvars", "--annual", str(idf)],
        capture_output=True, text=True, timeout=1800,
    )
    if proc.returncode != 0:
        print(f"❌ {name} failed:\n{proc.stderr[-800:]}")
        return None

    import pandas as pd  # lazy import — keeps syntax-check dependency-free

    csv = out_dir / "eplusout.csv"
    df = pd.read_csv(csv) if csv.exists() else None
    if df is None:
        print(f"❌ {name}: no eplusout.csv")
        return None

    j_to_kwh = 1 / 3.6e6
    elec = [c for c in df.columns if "Electricity:Facility" in c and "[J]" in c]
    monthly = [round(v * j_to_kwh, 1) for v in df[elec[0]].tolist()[:12]] if elec else []
    total = sum(df[c].sum() * j_to_kwh for c in df.columns
                if ":Facility" in c and "[J]" in c)
    return {"building": name, "annual_kwh": round(total, 1),
            "monthly_kwh": monthly, "weather": EPW.name}


def main() -> None:
    if not EPW.exists():
        sys.exit("❌ weather file missing — run scripts/download_reference_data.py first")
    CACHE.mkdir(parents=True, exist_ok=True)
    for name, idf in BUILDINGS.items():
        if not idf.exists():
            print(f"⏭️  skip {name}: {idf} missing")
            continue
        result = run_one(name, idf)
        if result:
            out = CACHE / f"{name}_baseline.json"
            out.write_text(json.dumps(result, indent=2))
            print(f"✅ cached → {out}")
    print("\nDone.")


if __name__ == "__main__":
    main()
