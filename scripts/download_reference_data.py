"""Download demo data: DOE reference building IDF + Sydney EPW weather.

Run once on your machine (needs normal internet):
    python scripts/download_reference_data.py
"""
from __future__ import annotations  # allow `bytes | None` on Python 3.9

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

# Sydney TMYx weather (zip containing .epw) — climate.onebuilding.org.
# Filenames on onebuilding change over time, so try several known candidates
# and stop at the first that works.
SYDNEY_ZIP_CANDIDATES = [
    "https://climate.onebuilding.org/WMO_Region_5_Southwest_Pacific/AUS_Australia/"
    "NSW_New_South_Wales/AUS_NSW_Sydney-Kingsford.Smith.Intl.AP.947670_TMYx.2009-2023.zip",
    "https://climate.onebuilding.org/WMO_Region_5_Southwest_Pacific/AUS_Australia/"
    "NSW_New_South_Wales/AUS_NSW_Sydney.Observatory.Hill.947680_TMYx.2009-2023.zip",
    "https://climate.onebuilding.org/WMO_Region_5_Southwest_Pacific/AUS_Australia/"
    "NSW_New_South_Wales/AUS_NSW_Sydney-Kingsford.Smith.Intl.AP.947670_TMYx.zip",
]


def fetch(url: str) -> bytes:
    print(f"  ↓ {url}")
    with urlopen(Request(url, headers=HEADERS), timeout=120) as r:
        return r.read()


def fetch_first_ok(urls: list[str]) -> bytes | None:
    """Try each URL; return the first that succeeds, else None."""
    from urllib.error import HTTPError, URLError
    for url in urls:
        try:
            return fetch(url)
        except (HTTPError, URLError) as exc:
            print(f"    ✗ {exc} — trying next…")
    return None


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
    if epws:
        print(f"✅ weather file already present: {epws[0].name}")
    else:
        blob = fetch_first_ok(SYDNEY_ZIP_CANDIDATES)
        if blob is None:
            print(
                "\n⚠️  Could not auto-download the Sydney weather file.\n"
                "   Manual (1 min): open\n"
                "     https://climate.onebuilding.org/WMO_Region_5_Southwest_Pacific/"
                "AUS_Australia/NSW_New_South_Wales/\n"
                "   download any 'Sydney … TMYx … .zip', unzip it, and place the .epw at\n"
                f"     {DATA / 'weather' / 'AUS_NSW_Sydney.epw'}\n"
            )
        else:
            with zipfile.ZipFile(io.BytesIO(blob)) as zf:
                for name in zf.namelist():
                    if name.endswith(".epw"):
                        (DATA / "weather" / "AUS_NSW_Sydney.epw").write_bytes(zf.read(name))
                        print("✅ AUS_NSW_Sydney.epw")
                        break

    print("\nDone. Next: pre-cache baseline runs →  python scripts/precache_baselines.py")


if __name__ == "__main__":
    main()
