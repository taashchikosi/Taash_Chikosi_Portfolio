"""Model router — sends each task to the right model tier (project plan §6).

90% DeepSeek V4 Flash · 8% DeepSeek V4 Pro · 2% Claude Sonnet (Reviewer only).

DeepSeek is called via the OpenAI-compatible client (base_url swap).
Claude is called via the Anthropic SDK.

Every call logs model + token usage to Langfuse upstream (decorators on agents).
"""
from __future__ import annotations

import os
from dataclasses import dataclass

FLASH = "deepseek-chat"          # DeepSeek V4 Flash (OpenAI-compatible id)
PRO = "deepseek-reasoner"        # DeepSeek V4 Pro / reasoning tier
SONNET = "claude-sonnet-4-6"     # Reviewer gate only


@dataclass
class ModelChoice:
    provider: str   # "deepseek" | "anthropic"
    model: str


def route_task(task_type: str, complexity: float = 0.0) -> ModelChoice:
    """Pick a model from task type + complexity (0.0 trivial → 1.0 hard)."""
    if task_type == "verification":
        return ModelChoice("anthropic", SONNET)
    if task_type in ("analysis", "calculation", "modelling") and complexity >= 0.7:
        return ModelChoice("deepseek", PRO)
    return ModelChoice("deepseek", FLASH)  # retrieval, extraction, formatting, default


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
    """
    choice = route_task(task_type, complexity)

    if choice.provider == "anthropic":
        client = _anthropic_client()
        resp = client.messages.create(
            model=choice.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
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
    return {
        "text": resp.choices[0].message.content,
        "model": choice.model,
        "usage": {"input": resp.usage.prompt_tokens,
                  "output": resp.usage.completion_tokens},
    }
