"""CBD cohort benchmark — the realistic-range gate's data source.

The Reviewer's realism check: does the simulated baseline EUI land within the
range of REAL disclosed Australian offices of the same size + city? If it falls
outside that cohort's p25–p75, the number is not realistic and is rejected.

Data: data/benchmarks/cbd_office_cohorts.json, produced by
scripts/build_cbd_cohorts.py from the CBD register (whole-building offices only,
per-city metro postcode band, deduped to the most recent certificate per
building). Only a VERIFIED cohort (n ≥ 30, plausible median) can gate; an absent
or unverified cohort returns None so the caller treats that building/city combo
as illustrative — it is never silently passed off as validated against real data.

No LLM, no fabrication: every value traces to the disclosed register.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

_BASE = Path(__file__).resolve().parent.parent
_COHORTS_PATH = _BASE / "data/benchmarks/cbd_office_cohorts.json"

# Size band → (min m², max m²). Single source of truth, mirrors
# scripts/build_cbd_cohorts.py BANDS. Used to (a) pick the right cohort and
# (b) validate that a demoer-supplied floor area is realistic for the size:
# the one model input that can be abused (a "medium" office sized like a closet
# or a stadium isn't a medium office). Small office has no CBD cohort (below the
# 1,000 m² disclosure threshold) and is not part of the gated demo.
SIZE_BANDS_M2: dict[str, tuple[float, float]] = {
    "medium": (2_500.0, 10_000.0),
    "large": (30_000.0, 200_000.0),
}


@dataclass(frozen=True)
class Cohort:
    """A real disclosed-office EUI cohort for one city + size band."""
    city: str
    size_band: str
    n: int
    p25: float
    median: float
    p75: float
    source: str

    def contains(self, eui: float) -> bool:
        """True if an EUI lands within the realistic range (p25 ≤ eui ≤ p75)."""
        return self.p25 <= eui <= self.p75


def office_band_for_area(area_m2: float) -> str:
    """Deterministic office size-band key ('small_office'|'medium_office'|
    'large_office') from a floor area, using the SAME medium bound the cohort
    gate uses (SIZE_BANDS_M2["medium"]). This MUST stay tied to SIZE_BANDS_M2: a
    slider-valid medium area (2,500–10,000 m²) misclassified as large_office —
    which has no verified cohort — would make load_cohort return None and the
    Reviewer's realism gate silently fall back to "illustrative" (approving an
    out-of-cohort baseline). Below 1,000 m² is treated as small_office (no CBD
    cohort by design — below the disclosure threshold)."""
    med_hi = SIZE_BANDS_M2["medium"][1]
    if area_m2 < 1000:
        return "small_office"
    if area_m2 <= med_hi:
        return "medium_office"
    return "large_office"


def size_band_for(building_type: str) -> Optional[str]:
    """'medium_office' → 'medium', 'large_office' → 'large', else None.

    Accepts the bare band ('medium') too, so callers can pass either the
    BuildingContext.building_type or a catalog size key.
    """
    bt = (building_type or "").strip().lower()
    if bt in SIZE_BANDS_M2:
        return bt
    if bt.endswith("_office"):
        band = bt[: -len("_office")]
        return band if band in SIZE_BANDS_M2 else None
    return None


def city_from_epw(epw_path: str) -> Optional[str]:
    """'…/AUS_NSW_Sydney.epw' → 'sydney'. The weather file fixes the site, so it
    also fixes which city's cohort applies. Returns None if unparseable."""
    if not epw_path:
        return None
    parts = Path(epw_path).stem.split("_")
    return parts[2].lower() if len(parts) >= 3 else None


def floor_area_realistic(floor_area_m2: float, building_type: str
                         ) -> tuple[bool, Optional[tuple[float, float]]]:
    """Is a floor area within the realistic band for the building size?

    Returns (ok, (lo, hi)). ok is True when the size has no defined band
    (nothing to check) or the area falls inside it. Returns (True, None) for an
    unknown size — the Reviewer's cohort check still applies, this is only the
    abuse-guard on the floor-area input.
    """
    band = size_band_for(building_type)
    if band is None:
        return True, None
    lo, hi = SIZE_BANDS_M2[band]
    return (lo <= float(floor_area_m2) <= hi), (lo, hi)


def load_cohort(city: Optional[str], building_type: str,
                path: Path = _COHORTS_PATH) -> Optional[Cohort]:
    """Load the VERIFIED cohort for a city + building size, or None.

    None means "no real cohort to gate against" (absent file, missing city,
    unverified/too-small cohort, or incomplete p25/p75) — the caller must then
    treat the run as illustrative, never as validated. Fail-closed by omission,
    never by inventing a range.
    """
    band = size_band_for(building_type)
    if not city or band is None or not path.exists():
        return None
    try:
        doc = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None

    block = (doc.get("cities") or {}).get(city.lower())
    if not block:
        return None
    for c in block.get("cohorts", []):
        if c.get("size_band") != band or not c.get("verified"):
            continue
        eui = c.get("eui_kwh_m2_yr") or {}
        p25, p75 = eui.get("p25"), eui.get("p75")
        if p25 is None or p75 is None:        # a range gate needs both bounds
            return None
        return Cohort(
            city=city.lower(), size_band=band, n=int(c.get("n", 0)),
            p25=float(p25), median=float(eui.get("median") or 0.0),
            p75=float(p75), source=str(c.get("source", "CBD register")),
        )
    return None
