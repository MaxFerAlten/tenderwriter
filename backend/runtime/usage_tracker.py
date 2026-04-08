"""Simple usage tracking for Wave 1."""

from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass
class UsageTracker:
    input_tokens: int = 0
    output_tokens: int = 0
    total_cost_usd: float = 0.0

    def add(self, input_tokens: int, output_tokens: int, cost_per_1k_input: float = 0.0, cost_per_1k_output: float = 0.0) -> None:
        self.input_tokens += int(input_tokens)
        self.output_tokens += int(output_tokens)
        self.total_cost_usd += ((input_tokens / 1000) * cost_per_1k_input) + ((output_tokens / 1000) * cost_per_1k_output)

    def to_dict(self) -> dict:
        return asdict(self)
