from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Standard API pricing, USD per 1M tokens.
# Keep centralized so pricing can be updated without touching UI logic.
MODEL_PRICING_USD_PER_MTOK = {
    "gpt-5.6-luna": {"input": 0.20, "output": 1.20},
}

DEFAULT_MODEL = "gpt-5.6-luna"


@dataclass(frozen=True)
class UsageCost:
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float


def token_usage(response: Any) -> tuple[int, int]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return 0, 0
    input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
    output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
    return max(0, input_tokens), max(0, output_tokens)


def estimate_usage_cost(model: str, input_tokens: int, output_tokens: int) -> UsageCost:
    normalized = str(model or DEFAULT_MODEL).strip()
    pricing = MODEL_PRICING_USD_PER_MTOK.get(normalized)
    if pricing is None:
        # Unknown/custom model: don't invent a price.
        return UsageCost(normalized, int(input_tokens), int(output_tokens), 0.0)
    cost = (
        max(0, int(input_tokens)) / 1_000_000 * pricing["input"]
        + max(0, int(output_tokens)) / 1_000_000 * pricing["output"]
    )
    return UsageCost(normalized, int(input_tokens), int(output_tokens), float(cost))


def format_cost_usd(value: float) -> str:
    value = max(0.0, float(value or 0.0))
    if value < 0.01:
        return f"${value:.4f}"
    return f"${value:.2f}"
