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
# Filenames change over time, so we DISCOVER the current file from the NSW
# directory listing instead of hardcoding a name that breaks.
#
# KEY: onebuilding does NOT put "Sydney" in the filename — stations are named by
# site + WMO code. We therefore search by the stable WMO code for Sydney Airport
# (Kingsford Smith) = 947670; codes survive filename reformats. Fallbacks widen
# the net to nearby Sydney-basin stations if the airport file is ever missing.
NSW_INDEX = (
    "https://climate.onebuilding.org/WMO_Region_5_Southwest_Pacific/"
    "AUS_Australia/NSW_New_South_Wales/"
)
SYDNEY_PRIMARY_CODES = ("947670",)            # Sydney Airport (Kingsford Smith)
SYDNEY_FALLBACK_CODES = ("947660", "947680")  # Canterbury Park, Observatory Hill basin


def fetch(url: str) -> bytes:
    print(f"  ↓ {url}")
    with urlopen(Request(url, headers=HEADERS), timeout=120) as r:
        return r.read()


def _zip_filenames(html: str) -> list[str]:
    """All NSW TMYx zip filenames in the index.

    Matches the bare filename, so it works whether the index serves relative
    hrefs (raw Apache listing) or absolute URLs (proxied/rendered).
    """
    import re
    return re.findall(r"AUS_NSW_[^\"'<>)\s]*_TMYx[^\"'<>)\s]*\.zip", html)


def discover_sydney_zip() -> str | None:
    """Find the current Sydney TMYx zip on the NSW index; return its full URL."""
    try:
        html = fetch(NSW_INDEX).decode("latin-1", errors="ignore")
    except Exception as exc:  # noqa: BLE001
        print(f"    ✗ could not read index: {exc}")
        return None

    names = [n.split("/")[-1] for n in _zip_filenames(html)]
    if not names:
        return None

    def pick(codes: tuple[str, ...]) -> str | None:
        hits = sorted({n for n in names if any(c in n for c in codes)})
        # The base "<station>_TMYx.zip" sorts last vs dated periods → canonical.
        return hits[-1] if hits else None

    name = (
        pick(SYDNEY_PRIMARY_CODES)
        or next((n for n in sorted(names) if "Sydney" in n), None)
        or pick(SYDNEY_FALLBACK_CODES)
    )
    if not name:
        return None
    print(f"    → matched {name}")
    return NSW_INDEX + name


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
        url = discover_sydney_zip()
        blob = fetch(url) if url else None
        if blob is None:
            print(
                "\n⚠️  Could not auto-download the Sydney weather file.\n"
                "   Manual (1 min): open\n"
                f"     {NSW_INDEX}\n"
                "   download any 'Sydney … TMYx … .zip', unzip it, and place the .epw at\n"
                f"     {DATA / 'weather' / 'AUS_NSW_Sydney.epw'}\n"
            )
        else:
            with zipfile.ZipFile(io.BytesIO(blob)) as zf:
                for name in zf.namelist():
                    if name.endswith(".epw"):
                        (DATA / "weather" / "AUS_NSW_Sydney.epw").write_bytes(zf.read(name))
                        print(f"✅ AUS_NSW_Sydney.epw  (from {url.split('/')[-1]})")
                        break

    print("\nDone. Next: pre-cache baseline runs →  python scripts/precache_baselines.py")


if __name__ == "__main__":
    main()
