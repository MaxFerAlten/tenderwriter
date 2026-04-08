"""Cost calculator — compute USD cost from token usage per model.

Pricing as of mid-2025. All values in USD per 1,000 tokens.
Format: model_id -> (input_cost_per_1k, output_cost_per_1k)
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Pricing table — (input_usd_per_1k, output_usd_per_1k)
# ---------------------------------------------------------------------------
PRICING: dict[str, tuple[float, float]] = {
    # Anthropic — Claude 4 series
    "claude-opus-4-20250514":       (0.015,  0.075),
    "claude-sonnet-4-20250514":     (0.003,  0.015),
    "claude-haiku-4-20250514":      (0.00025, 0.00125),
    # Anthropic — Claude 3.x (legacy)
    "claude-3-opus-20240229":       (0.015,  0.075),
    "claude-3-sonnet-20240229":     (0.003,  0.015),
    "claude-3-haiku-20240307":      (0.00025, 0.00125),
    "claude-3-5-sonnet-20241022":   (0.003,  0.015),
    "claude-3-5-haiku-20241022":    (0.00080, 0.004),
    # OpenAI — GPT-4o series
    "gpt-4o":                       (0.005,  0.015),
    "gpt-4o-mini":                  (0.00015, 0.0006),
    "gpt-4o-2024-11-20":            (0.0025, 0.010),
    "gpt-4-turbo":                  (0.010,  0.030),
    "gpt-4":                        (0.030,  0.060),
    "gpt-3.5-turbo":                (0.0005, 0.0015),
    # OpenAI — o-series reasoning
    "o1":                           (0.015,  0.060),
    "o1-mini":                      (0.003,  0.012),
    "o3":                           (0.010,  0.040),
    "o4-mini":                      (0.0011, 0.0044),
    # Google — Gemini 2.x
    "gemini-2.5-pro-preview-06-05": (0.00125, 0.010),
    "gemini-2.5-pro":               (0.00125, 0.010),
    "gemini-2.0-flash":             (0.00010, 0.00040),
    "gemini-2.0-flash-lite":        (0.000075, 0.0003),
    "gemini-1.5-pro":               (0.00125, 0.005),
    "gemini-1.5-flash":             (0.000075, 0.0003),
    # xAI — Grok
    "grok-3":                       (0.003,  0.015),
    "grok-3-mini":                  (0.0003, 0.0005),
    "grok-2":                       (0.002,  0.010),
    # DeepSeek
    "deepseek-chat":                (0.00027, 0.0011),
    "deepseek-coder":               (0.00027, 0.0011),
    "deepseek-reasoner":            (0.00055, 0.00219),
    # Ollama & LM Studio — local, always free
    # (matched by prefix in compute_cost, not exact id)
}

# Providers that are always free (local inference)
_FREE_PREFIXES = ("llama", "mistral", "codellama", "phi", "qwen", "gemma", "deepseek-r1")


def get_pricing(model: str) -> tuple[float, float]:
    """Return (input_cost_per_1k, output_cost_per_1k) for a model.

    Falls back to (0.0, 0.0) for unknown / local models.
    """
    # Exact match first
    if model in PRICING:
        return PRICING[model]

    # LM Studio uses namespaced ids like "lmstudio/qwen3.5-9b"
    if "/" in model:
        return (0.0, 0.0)

    model_lower = model.lower()

    # Check free local prefixes
    for prefix in _FREE_PREFIXES:
        if model_lower.startswith(prefix):
            return (0.0, 0.0)

    # Fuzzy prefix match against pricing table
    for key, price in PRICING.items():
        if model_lower.startswith(key.split("-")[0]):
            return price

    return (0.0, 0.0)


def compute_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Compute USD cost for a given number of tokens.

    Returns a float rounded to 8 decimal places.
    """
    in_price, out_price = get_pricing(model)
    cost = (input_tokens / 1000.0) * in_price + (output_tokens / 1000.0) * out_price
    return round(cost, 8)


def format_cost(cost_usd: float) -> str:
    """Format a cost in USD for display (e.g. '$0.0023' or '<$0.0001')."""
    if cost_usd < 0.0001:
        return "<$0.0001"
    if cost_usd < 0.01:
        return f"${cost_usd:.4f}"
    return f"${cost_usd:.3f}"
