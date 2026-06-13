"""One-click demo plumbing: disclosed demo-calibration + the result endpoint.

The live pipeline (EnergyPlus + LLM) only runs on a real host, so here we pin the
deterministic seams the UI depends on: the demo bills calibrate (GL14 passes), the
run carries the flag, and /result has the right contract.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api import main
from api.main import app, demo_bills_from_baseline
from router import model_router
from verification.ashrae_checks import calibration_report

client = TestClient(app)

VALID_BODY = {
    "utility": {"monthly_kwh": [1000.0] * 12, "annual_cost_aud": 4200.0,
                "tariff_type": "single rate"}
}


@pytest.fixture(autouse=True)
def _clean():
    main._RATE_HITS.clear()
    main._RATE_LIMIT_PER_MIN = 30
    model_router.reset_token_budget()
    yield
    model_router.reset_token_budget()


def test_demo_bills_calibrate_against_baseline():
    # Synthesised bills must pass GL14 monthly (NMBE≈0, CV-RMSE≈5%) — that's what
    # makes the disclosed demo run green honestly.
    baseline = [5000.0, 4800, 4200, 3600, 3100, 2900,
                3000, 3200, 3500, 3900, 4300, 4700]
    bills = demo_bills_from_baseline(baseline)
    report = calibration_report(baseline, bills)
    assert report["passed"] is True
    assert report["resolution"] == "monthly"
    assert abs(report["nmbe"]["nmbe_pct"]) <= 5.0
    assert report["cvrmse"]["cvrmse_pct"] <= 15.0


def test_create_run_records_demo_calibrate_flag():
    r = client.post("/api/runs", json={**VALID_BODY, "demo_calibrate": True})
    assert r.status_code == 200
    run_id = r.json()["run_id"]
    assert main._RUNS[run_id]["demo_calibrate"] is True


def test_create_run_defaults_demo_calibrate_false():
    run_id = client.post("/api/runs", json=VALID_BODY).json()["run_id"]
    assert main._RUNS[run_id]["demo_calibrate"] is False


def test_result_404_for_unknown_run():
    assert client.get("/api/runs/nope/result").status_code == 404


def test_result_425_when_not_finished():
    run_id = client.post("/api/runs", json=VALID_BODY).json()["run_id"]
    assert client.get(f"/api/runs/{run_id}/result").status_code == 425


def test_result_returns_payload_when_ready():
    main._RUNS["fixed"] = {"result": {"recommended": {"scenario": "led_lighting"},
                                      "review": {"approved": True},
                                      "demo_calibration": True}}
    body = client.get("/api/runs/fixed/result").json()
    assert body["recommended"]["scenario"] == "led_lighting"
    assert body["demo_calibration"] is True
    del main._RUNS["fixed"]
