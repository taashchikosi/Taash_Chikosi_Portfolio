"""Provider-switch routing tests (no API calls — pure model selection).

Protects the dev(Claude)↔deploy(DeepSeek) flip so a stray env value can't
silently route the public demo to the wrong/expensive model.
"""
from __future__ import annotations

import pytest

from router.model_router import route_task


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)


# ── DEV override: everything → Claude ──────────────────────────────────────
def test_anthropic_override_routes_all_tasks_to_claude(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    for task in ("retrieval", "modelling", "analysis", "verification", "formatting"):
        choice = route_task(task, complexity=0.0)
        assert choice.provider == "anthropic"


def test_anthropic_model_id_is_overridable(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-opus-4-8")
    assert route_task("retrieval").model == "claude-opus-4-8"


# ── Force DeepSeek: everything → DeepSeek, incl. the Reviewer gate ──────────
def test_deepseek_override_forces_deepseek_even_for_verification(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    assert route_task("verification").provider == "deepseek"
    assert route_task("modelling", complexity=0.9).model == "deepseek-reasoner"
    assert route_task("retrieval").model == "deepseek-chat"


# ── DEPLOY default (unset): cost-tiered, eval-gated per node ────────────────
def test_default_routes_verification_and_retrieval_to_claude():
    # Claude runs the two quality-critical judgement nodes: the Reviewer gate AND
    # building classification (Tier B showed DeepSeek mis-classifies — see router).
    assert route_task("verification").provider == "anthropic"
    assert route_task("retrieval").provider == "anthropic"
    # Bulk work stays on DeepSeek for cost.
    assert route_task("modelling", complexity=0.9).model == "deepseek-reasoner"
    assert route_task("formatting").provider == "deepseek"


def test_garbage_provider_value_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gpt5-please")
    assert route_task("retrieval").provider == "anthropic"   # not crashed, default
    assert route_task("verification").provider == "anthropic"
    assert route_task("modelling").provider == "deepseek"
