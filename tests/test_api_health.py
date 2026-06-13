"""Smoke tests for the /health readiness probe.

/health drives the unified portfolio site's 🟢/🔴 status dot, so its shape is a
contract the frontend depends on — these tests pin it.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_health_200_and_shape():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["service"] == "retrofitgpt-api"
    assert set(body["checks"]) == {
        "energyplus", "carbon_factors", "reference_building", "weather_epw",
    }
    assert isinstance(body["live_simulation_available"], bool)
    assert body["status"] in {"ok", "degraded"}


def test_health_demo_ready_with_committed_data():
    # The repo ships the carbon factors JSON + reference IDFs (both git-tracked),
    # so the cached-demo path is serveable → green dot.
    body = client.get("/health").json()
    assert body["checks"]["carbon_factors"] is True
    assert body["checks"]["reference_building"] is True
    assert body["status"] == "ok"


def test_health_live_sim_flag_is_consistent():
    body = client.get("/health").json()
    expected = body["checks"]["energyplus"] and body["checks"]["weather_epw"]
    assert body["live_simulation_available"] is expected
