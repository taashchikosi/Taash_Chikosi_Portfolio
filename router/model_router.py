"""Model router — sends each task to the right model tier (project plan §6).

90% DeepSeek V4 Flash · 8% DeepSeek V4 Pro · 2% Claude Sonnet (Reviewer only).

DeepSeek is called via the OpenAI-compatible client (base_url swap).
Claude is called via the Anthropic SDK.

Every call logs model + token usage to Langfuse upstream (decorators on agents).
"""
from __future__ import annotations

import os
import threading
import time
from collections import deque
from dataclasses import dataclass

FLASH = "deepseek-chat"          # DeepSeek V4 Flash (OpenAI-compatible id)
PRO = "deepseek-reasoner"        # DeepSeek V4 Pro / reasoning tier
SONNET = "claude-sonnet-4-6"     # Reviewer gate only

# ── Hard token/cost cap (abuse protection for the public demo) ─────────────────
# Every LLM call funnels through complete(), so a single rolling 24h token budget
# here protects the wallet no matter how many runs/IPs hit the live endpoint. The
# per-IP request rate-limit (api/main.py) caps frequency; THIS caps spend. Tune with
# LLM_MAX_TOKENS_PER_DAY (set ≤0 to disable, e.g. local dev / tests that want it off).
MAX_TOKENS_PER_DAY = int(os.environ.get("LLM_MAX_TOKENS_PER_DAY", "500000"))
_TOKEN_WINDOW_S = 86_400.0
_TOKEN_LOCK = threading.Lock()
_TOKEN_HITS: deque[tuple[float, int]] = deque()   # (monotonic_ts, tokens)


class TokenBudgetExceeded(RuntimeError):
    """Raised by complete() when the rolling 24h token budget is spent."""


def _prune(now: float) -> None:
    while _TOKEN_HITS and now - _TOKEN_HITS[0][0] > _TOKEN_WINDOW_S:
        _TOKEN_HITS.popleft()


def tokens_used_last_day() -> int:
    with _TOKEN_LOCK:
        _prune(time.monotonic())
        return sum(t for _, t in _TOKEN_HITS)


def budget_exhausted() -> bool:
    """True if the rolling 24h budget is spent (≤0 limit disables the cap)."""
    if MAX_TOKENS_PER_DAY <= 0:
        return False
    return tokens_used_last_day() >= MAX_TOKENS_PER_DAY


def _record_tokens(n: int) -> None:
    with _TOKEN_LOCK:
        _TOKEN_HITS.append((time.monotonic(), max(0, int(n))))


def reset_token_budget() -> None:
    """Clear the budget window (tests / manual ops)."""
    with _TOKEN_LOCK:
        _TOKEN_HITS.clear()


@dataclass
class ModelChoice:
    provider: str   # "deepseek" | "anthropic"
    model: str


def _provider_override() -> str | None:
    """Global provider switch, read from env at call time so a `.env` flip needs
    no code change. Set LLM_PROVIDER in `.env`:

      LLM_PROVIDER=anthropic  → DEV: route *everything* to Claude (best prompt
                                quality while building Retriever/Modeler).
      LLM_PROVIDER=deepseek   → force *everything* to DeepSeek, incl. the Reviewer
                                gate (max cost saving / if no Anthropic key).
      (unset / "auto")        → DEPLOY default: cost-tiered — mostly DeepSeek,
                                Claude only for the ~2% Reviewer gate.
    """
    val = os.environ.get("LLM_PROVIDER", "").strip().lower()
    return val if val in ("anthropic", "deepseek") else None


def route_task(task_type: str, complexity: float = 0.0) -> ModelChoice:
    """Pick a model from task type + complexity (0.0 trivial → 1.0 hard)."""
    override = _provider_override()
    if override == "anthropic":
        # One model for all tasks in dev; override the id with ANTHROPIC_MODEL.
        return ModelChoice("anthropic", os.environ.get("ANTHROPIC_MODEL", SONNET))
    if override == "deepseek":
        if task_type in ("analysis", "calculation", "modelling", "verification") and complexity >= 0.7:
            return ModelChoice("deepseek", PRO)
        return ModelChoice("deepseek", FLASH)

    # ── Deploy default: cost-tiered routing ──
    if task_type == "verification":
        return ModelChoice("anthropic", SONNET)            # the Reviewer gate
    # Retriever CLASSIFICATION → Claude. Tier B live eval (12 Jun 2026) showed
    # DeepSeek stably mis-classifies building type (mis-sized a 511 m² office as
    # medium; an explicit-threshold prompt fix then destabilised retail + mislabelled
    # a school). Eval-gated decision: classify runs on Claude. NOTE: a cheaper Claude
    # (Haiku) is a future cost-optimisation but MUST be Tier-B gated before swapping
    # in — see verification/... / evals/. Don't hardcode a cheaper model un-gated.
    if task_type == "retrieval":
        return ModelChoice("anthropic", os.environ.get("ANTHROPIC_MODEL", SONNET))
    if task_type in ("analysis", "calculation", "modelling") and complexity >= 0.7:
        return ModelChoice("deepseek", PRO)
    return ModelChoice("deepseek", FLASH)  # modelling/extraction/formatting, default


# ── Thin client wrappers ────────────────────────────────────────────

def _deepseek_client():
    from openai import OpenAI  # OpenAI-compatible
    return OpenAI(
        api_key=os.environ["DEEPSEEK_API_KEY"],
        base_url="https://api.deepseek.com",
    )


def _anthropic_client():
    from anthropic import Anthropic
    return Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def complete(
    task_type: str,
    system: str,
    user: str,
    complexity: float = 0.0,
    max_tokens: int = 2048,
) -> dict:
    """Unified completion call. Returns {text, model, usage}.

    Kept provider-agnostic so agents never branch on which model ran.

    Raises TokenBudgetExceeded BEFORE contacting the provider once the rolling 24h
    budget is spent — so an exhausted budget costs nothing.
    """
    if budget_exhausted():
        raise TokenBudgetExceeded(
            f"Daily LLM token budget reached ({MAX_TOKENS_PER_DAY:,}/day). "
            "The public demo pauses LLM calls until the window rolls over.")

    choice = route_task(task_type, complexity)

    if choice.provider == "anthropic":
        client = _anthropic_client()
        resp = client.messages.create(
            model=choice.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        _record_tokens(resp.usage.input_tokens + resp.usage.output_tokens)
        return {
            "text": resp.content[0].text,
            "model": choice.model,
            "usage": {"input": resp.usage.input_tokens,
                      "output": resp.usage.output_tokens},
        }

    client = _deepseek_client()
    resp = client.chat.completions.create(
        model=choice.model,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    _record_tokens(resp.usage.prompt_tokens + resp.usage.completion_tokens)
    return {
        "text": resp.choices[0].message.content,
        "model": choice.model,
        "usage": {"input": resp.usage.prompt_tokens,
                  "output": resp.usage.completion_tokens},
    }
