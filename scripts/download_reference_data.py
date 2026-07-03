"""Download demo data: DOE reference building IDFs + Australian EPW weather.

Run once on your machine (needs normal internet — the sandbox can't reach
climate.onebuilding.org):

    python scripts/download_reference_data.py

What it fetches:
  • RefBldgSmallOffice.idf, RefBldgMediumOffice.idf, RefBldgLargeOffice.idf
    (DOE Commercial Reference Buildings, from the EnergyPlus test suite).
  • One TMYx .epw per demo city: Sydney, Melbourne, Brisbane, Perth — named
    AUS_<STATE>_<City>.epw so the retriever can derive the NCC climate zone and
    grid carbon factor straight from the filename (see api/main.py CITY_BY_KEY
    and data/reference_buildings/catalog.json).

Idempotent: files already present are skipped.
"""
from __future__ import annotations  # allow `bytes | None` on Python 3.9

import io
import re
import zipfile
from pathlib import Path
from urllib.request import urlopen, Request

DATA = Path(__file__).resolve().parent.parent / "data" / "reference_buildings"
HEADERS = {"User-Agent": "RetrofitGPT/0.2 (portfolio project)"}

# DOE reference building IDFs — ship in the EnergyPlus test suite (Chicago variant;
# the geometry/loads are reused and re-pointed to Australian weather at run time).
DOWNLOADS = {
    "RefBldgSmallOffice.idf": (
        "https://raw.githubusercontent.com/NREL/EnergyPlus/develop/testfiles/"
        "RefBldgSmallOfficeNew2004_Chicago.idf"
    ),
    "RefBldgMediumOffice.idf": (
        "https://raw.githubusercontent.com/NREL/EnergyPlus/develop/testfiles/"
        "RefBldgMediumOfficeNew2004_Chicago.idf"
    ),
    "RefBldgLargeOffice.idf": (
        "https://raw.githubusercontent.com/NREL/EnergyPlus/develop/testfiles/"
        "RefBldgLargeOfficeNew2004_Chicago.idf"
    ),
}

# Australian TMYx weather (zip containing .epw) — climate.onebuilding.org.
# onebuilding does NOT put the city in the filename; stations are named by site +
# WMO code, and codes survive filename reformats. So we DISCOVER the current file
# from the state's directory listing and match on the stable WMO code, with
# nearby-station fallbacks. One entry per demo city.
ONEBUILDING_BASE = (
    "https://climate.onebuilding.org/WMO_Region_5_Southwest_Pacific/AUS_Australia/"
)
STATE_DIR = {
    "NSW": "NSW_New_South_Wales/",
    "VIC": "VIC_Victoria/",
    "QLD": "QLD_Queensland/",
    "WA": "WA_Western_Australia/",
}

# city → (state, output filename, primary WMO codes, fallback WMO codes)
CITIES = {
    "Sydney":    ("NSW", "AUS_NSW_Sydney.epw",    ("947670",), ("947660", "947680")),
    "Melbourne": ("VIC", "AUS_VIC_Melbourne.epw", ("948660",), ("947680", "948700")),
    "Brisbane":  ("QLD", "AUS_QLD_Brisbane.epw",  ("945780",), ("945760", "945790")),
    "Perth":     ("WA",  "AUS_WA_Perth.epw",      ("946100",), ("946080", "946150")),
}


def fetch(url: str) -> bytes:
    print(f"  ↓ {url}")
    with urlopen(Request(url, headers=HEADERS), timeout=120) as r:
        return r.read()


def _zip_filenames(html: str, state: str) -> list[str]:
    """All TMYx zip filenames for a state in the index (bare filename, so it works
    whether hrefs are relative or absolute)."""
    return re.findall(rf"AUS_{state}_[^\"'<>)\s]*_TMYx[^\"'<>)\s]*\.zip", html)


def discover_city_zip(city: str) -> str | None:
    """Find the current TMYx zip for a city on its state index; return full URL."""
    state, _out, primary, fallback = CITIES[city]
    index = ONEBUILDING_BASE + STATE_DIR[state]
    try:
        html = fetch(index).decode("latin-1", errors="ignore")
    except Exception as exc:  # noqa: BLE001
        print(f"    ✗ could not read {state} index: {exc}")
        return None

    names = [n.split("/")[-1] for n in _zip_filenames(html, state)]
    if not names:
        return None

    def pick(codes: tuple[str, ...]) -> str | None:
        hits = sorted({n for n in names if any(c in n for c in codes)})
        # The base "<station>_TMYx.zip" sorts last vs dated periods → canonical.
        return hits[-1] if hits else None

    name = (
        pick(primary)
        or next((n for n in sorted(names) if city in n), None)
        or pick(fallback)
    )
    if not name:
        return None
    print(f"    → {city}: matched {name}")
    return index + name


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    weather = DATA / "weather"
    weather.mkdir(exist_ok=True)

    # 1) Reference building IDFs
    for filename, url in DOWNLOADS.items():
        out = DATA / filename
        if out.exists():
            print(f"✅ {filename} already present")
            continue
        out.write_bytes(fetch(url))
        print(f"✅ {filename}")

    # 2) One EPW per demo city
    for city, (_state, out_name, *_codes) in CITIES.items():
        out = weather / out_name
        if out.exists():
            print(f"✅ {out_name} already present")
            continue
        url = discover_city_zip(city)
        blob = fetch(url) if url else None
        if blob is None:
            index = ONEBUILDING_BASE + STATE_DIR[CITIES[city][0]]
            print(
                f"\n⚠️  Could not auto-download the {city} weather file.\n"
                f"   Manual (1 min): open\n     {index}\n"
                f"   download any '{city} … TMYx … .zip', unzip it, and place the .epw at\n"
                f"     {out}\n"
            )
            continue
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            for name in zf.namelist():
                if name.endswith(".epw"):
                    out.write_bytes(zf.read(name))
                    print(f"✅ {out_name}  (from {url.split('/')[-1]})")
                    break


if __name__ == "__main__":
    main()
