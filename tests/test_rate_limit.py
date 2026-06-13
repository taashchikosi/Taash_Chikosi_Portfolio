"""Per-IP rate limiting on run creation (public-agent abuse protection)."""
from __future__ import annotations

from fastapi.testclient import TestClient

from api import main
from api.main import app

client = TestClient(app)

VALID_BODY = {
    "utility": {
        "monthly_kwh": [1000.0] * 12,
        "annual_cost_aud": 4200.0,
        "tariff_type": "single rate",
    }
}


def _reset(limit: int):
    main._RATE_HITS.clear()
    main._RATE_LIMIT_PER_MIN = limit


def test_allows_up_to_limit_then_429():
    _reset(3)
    for _ in range(3):
        assert client.post("/api/runs", json=VALID_BODY).status_code == 200
    # The 4th request in the window must be rejected.
    blocked = client.post("/api/runs", json=VALID_BODY)
    assert blocked.status_code == 429
    assert "Rate limit" in blocked.json()["detail"]


def test_separate_ips_have_separate_budgets():
    _reset(1)
    h1 = {"X-Forwarded-For": "203.0.113.1"}
    h2 = {"X-Forwarded-For": "203.0.113.2"}
    assert client.post("/api/runs", json=VALID_BODY, headers=h1).status_code == 200
    assert client.post("/api/runs", json=VALID_BODY, headers=h1).status_code == 429
    # A different client IP is unaffected by the first IP's usage.
    assert client.post("/api/runs", json=VALID_BODY, headers=h2).status_code == 200


def test_reset_restores_capacity():
    # Housekeeping: leave globals at defaults so other test files are unaffected.
    _reset(30)
