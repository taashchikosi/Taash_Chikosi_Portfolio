"""Deploy-safety guards: hard token/cost cap + locked CORS.

The per-IP rate-limit (test_rate_limit.py) caps how OFTEN the public agent runs;
these cap how much it can SPEND and WHO can call it.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api import main
from api.main import app, _allowed_origins
from router import model_router

client = TestClient(app)

VALID_BODY = {
    "utility": {"monthly_kwh": [1000.0] * 12, "annual_cost_aud": 4200.0,
                "tariff_type": "single rate"}
}


@pytest.fixture(autouse=True)
def _clean():
    model_router.reset_token_budget()
    main._RATE_HITS.clear()
    main._RATE_LIMIT_PER_MIN = 30
    yield
    model_router.reset_token_budget()


# ── Token budget (the wallet guard) ───────────────────────────────────────────
def test_budget_not_exhausted_below_limit(monkeypatch):
    monkeypatch.setattr(model_router, "MAX_TOKENS_PER_DAY", 1000)
    model_router._record_tokens(400)
    assert model_router.tokens_used_last_day() == 400
    assert model_router.budget_exhausted() is False


def test_budget_exhausted_at_limit(monkeypatch):
    monkeypatch.setattr(model_router, "MAX_TOKENS_PER_DAY", 1000)
    model_router._record_tokens(1000)
    assert model_router.budget_exhausted() is True


def test_zero_limit_disables_the_cap(monkeypatch):
    monkeypatch.setattr(model_router, "MAX_TOKENS_PER_DAY", 0)
    model_router._record_tokens(10_000_000)
    assert model_router.budget_exhausted() is False


def test_complete_raises_before_touching_provider_when_exhausted(monkeypatch):
    # Budget check runs FIRST, so an exhausted budget never imports/calls a client —
    # i.e. it costs nothing. (No API key / network needed for this test.)
    monkeypatch.setattr(model_router, "MAX_TOKENS_PER_DAY", 100)
    model_router._record_tokens(100)
    with pytest.raises(model_router.TokenBudgetExceeded):
        model_router.complete("retrieval", "sys", "user")


def test_api_refuses_runs_with_503_when_budget_spent(monkeypatch):
    monkeypatch.setattr(model_router, "MAX_TOKENS_PER_DAY", 100)
    model_router._record_tokens(100)
    r = client.post("/api/runs", json=VALID_BODY)
    assert r.status_code == 503
    assert "budget" in r.json()["detail"].lower()


def test_health_reports_budget(monkeypatch):
    monkeypatch.setattr(model_router, "MAX_TOKENS_PER_DAY", 1000)
    model_router._record_tokens(250)
    body = client.get("/health").json()
    assert body["token_budget"]["used_last_24h"] == 250
    assert body["token_budget"]["exhausted"] is False


# ── CORS allowlist (the who-can-call guard) ───────────────────────────────────
def test_cors_defaults_to_localhost(monkeypatch):
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    assert _allowed_origins() == ["http://localhost:3000"]


def test_cors_parses_env_allowlist(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS",
                       "https://platform.vercel.app, https://www.example.com ")
    assert _allowed_origins() == ["https://platform.vercel.app",
                                  "https://www.example.com"]


def test_cors_is_not_wildcard(monkeypatch):
    # Regression guard: never ship allow_origins=['*'] on a public agent.
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://platform.vercel.app")
    assert "*" not in _allowed_origins()
