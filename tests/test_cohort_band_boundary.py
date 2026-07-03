"""Regression: the Reviewer's cohort gate must apply across the WHOLE medium
floor-area band (2,500–10,000 m²), for every city.

Bug (fixed): sim_runner classified any area > 5,000 m² as 'large_office'. No
verified large cohort exists (n=0 in most cities), so load_cohort returned None,
the realism gate fell back to 'illustrative', and an out-of-cohort baseline (e.g.
a Brisbane medium office at EUI 430.1, far above the p75 of 261.3) was APPROVED
instead of rejected. The medium band is 2,500–10,000 m² (SIZE_BANDS_M2 / the
floor-area slider), so a 5,001–10,000 m² medium office must stay 'medium_office'
and the gate must still fire. The prior negative-control eval used area=5,000,
which sat below the buggy cutoff and so never caught this.
"""
from __future__ import annotations

import pytest

from verification.cohort_benchmark import (
    SIZE_BANDS_M2, city_from_epw, load_cohort, office_band_for_area,
)

CITY_EPW = {
    "sydney": "data/reference_buildings/weather/AUS_NSW_Sydney.epw",
    "melbourne": "data/reference_buildings/weather/AUS_VIC_Melbourne.epw",
    "brisbane": "data/reference_buildings/weather/AUS_QLD_Brisbane.epw",
    "perth": "data/reference_buildings/weather/AUS_WA_Perth.epw",
}


@pytest.mark.parametrize("area,expected", [
    (2_500.0, "medium_office"),
    (4_982.0, "medium_office"),
    (5_001.0, "medium_office"),   # the boundary the old 5,000 cutoff got wrong
    (8_000.0, "medium_office"),
    (10_000.0, "medium_office"),  # top of the slider / medium band
    (10_001.0, "large_office"),
    (500.0, "small_office"),
])
def test_office_band_tracks_cohort_medium_band(area, expected):
    assert office_band_for_area(area) == expected


def test_office_band_upper_bound_equals_cohort_definition():
    # The classifier's medium ceiling MUST equal the cohort/abuse-guard band, or
    # a slider-valid medium area is misrouted to a band with no verified cohort.
    med_hi = SIZE_BANDS_M2["medium"][1]
    assert office_band_for_area(med_hi) == "medium_office"
    assert office_band_for_area(med_hi + 0.1) == "large_office"


@pytest.mark.parametrize("city,epw", CITY_EPW.items())
@pytest.mark.parametrize("area", [2_500.0, 5_001.0, 8_000.0, 10_000.0])
def test_gate_is_reachable_across_medium_band_for_every_city(city, epw, area):
    # Across the full medium band, every city resolves a VERIFIED medium cohort,
    # so the realism gate can fire (it is not skipped as 'illustrative').
    band = office_band_for_area(area)
    cohort = load_cohort(city_from_epw(epw), band)
    assert cohort is not None, f"{city} @ {area} m² → no cohort (gate would be skipped)"
    assert cohort.city == city and cohort.size_band == "medium"
    assert cohort.p25 < cohort.p75


@pytest.mark.parametrize("city,epw", CITY_EPW.items())
def test_out_of_cohort_baseline_rejected_at_large_medium_area(city, epw):
    # A high baseline well above p75, at an 8,000 m² medium office, must be OUT of
    # cohort for every city (the gate rejects). Mirrors the screenshot's 430.1.
    cohort = load_cohort(city_from_epw(epw), office_band_for_area(8_000.0))
    assert cohort is not None
    assert cohort.contains(cohort.p75 + 80.0) is False   # too high → reject
    assert cohort.contains(cohort.p25 - 40.0) is False    # too low → reject
    assert cohort.contains((cohort.p25 + cohort.p75) / 2) is True  # in range → approve
