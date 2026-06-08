"""Download demo data: DOE reference building IDF + Sydney EPW weather.

Run once on your machine (needs normal internet):
    python scripts/download_reference_data.py
"""
import io
import zipfile
from pathlib import Path
from urllib.request import urlopen, Request

DATA = Path(__file__).resolve().parent.parent / "data" / "reference_buildings"
HEADERS = {"User-Agent": "RetrofitGPT/0.1 (portfolio project)"}

DOWNLOADS = {
    # DOE Small Office reference building — ships in the EnergyPlus test suite
    "RefBldgSmallOffice.idf": (
        "https://raw.githubusercontent.com/NREL/EnergyPlus/develop/testfiles/"
        "RefBldgSmallOfficeNew2004_Chicago.idf"
    ),
    # DOE Medium Office reference building
    "RefBldgMediumOffice.idf": (
        "https://raw.githubusercontent.com/NREL/EnergyPlus/develop/testfiles/"
        "RefBldgMediumOfficeNew2004_Chicago.idf"
    ),
}

# Sydney TMYx weather file (zip containing .epw) — climate.onebuilding.org
SYDNEY_ZIP = (
    "https://climate.onebuilding.org/WMO_Region_5_Southwest_Pacific/"
    "AUS_Australia/NSW_New_South_Wales/"
    "AUS_NSW_Sydney.Intl.AP.947670_TMYx.2009-2023.zip"
)


def fetch(url: str) -> bytes:
    print(f"  ↓ {url}")
    with urlopen(Request(url, headers=HEADERS), timeout=120) as r:
        return r.read()


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "weather").mkdir(exist_ok=True)

    for filename, url in DOWNLOADS.items():
        out = DATA / filename
        if out.exists():
            print(f"✅ {filename} already present")
            continue
        out.write_bytes(fetch(url))
        print(f"✅ {filename}")

    epws = list((DATA / "weather").glob("*.epw"))
    if not epws:
        blob = fetch(SYDNEY_ZIP)
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            for name in zf.namelist():
                if name.endswith(".epw"):
                    (DATA / "weather" / "AUS_NSW_Sydney.epw").write_bytes(zf.read(name))
                    print("✅ AUS_NSW_Sydney.epw")
    else:
        print(f"✅ weather file already present: {epws[0].name}")

    print("\nDone. Next: pre-cache baseline runs →  python scripts/precache_baselines.py")


if __name__ == "__main__":
    main()
