"""One-click demo plumbing: the validation flag + the result endpoint contract.

The live pipeline (EnergyPlus + LLM) only runs on a real host, so here we pin the
deterministic seams the UI depends on: the run carries the `validate` flag (the
"Run without validation" toggle), and /result has the right contract.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api import main
from api.main import app
from router import model_router

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


def test_create_run_records_validate_flag_off():
    r = client.post("/api/runs", json={**VALID_BODY, "validate_realism": False})
    assert r.status_code == 200
    run_id = r.json()["run_id"]
    assert main._RUNS[run_id]["validate"] is False


def test_create_run_defaults_validate_true():
    run_id = client.post("/api/runs", json=VALID_BODY).json()["run_id"]
    assert main._RUNS[run_id]["validate"] is True


def test_result_404_for_unknown_run():
    assert client.get("/api/runs/nope/result").status_code == 404


def test_result_425_when_not_finished():
    run_id = client.post("/api/runs", json=VALID_BODY).json()["run_id"]
    assert client.get(f"/api/runs/{run_id}/result").status_code == 425


def test_result_returns_payload_when_ready():
    main._RUNS["fixed"] = {"result": {"recommended": {"scenario": "led_lighting"},
                                      "review": {"approved": True, "within_cohort": True},
                                      "cohort_validated": True}}
    body = client.get("/api/runs/fixed/result").json()
    assert body["recommended"]["scenario"] == "led_lighting"
    assert body["cohort_validated"] is True
    del main._RUNS["fixed"]
