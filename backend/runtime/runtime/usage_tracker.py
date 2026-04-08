"""Enhanced usage tracker with per-model tracking and persistence."""

from dataclasses import dataclass, field
from typing import TypedDict
from pathlib import Path
import json


class ModelUsage(TypedDict):
    input_tokens: int
    output_tokens: int
    cache_read_input_tokens: int
    cache_creation_input_tokens: int
    web_search_requests: int
    cost_usd: float
    context_window: int
    max_output_tokens: int
    api_duration_ms: float


@dataclass
class UsageTracker:
    """Enhanced usage tracker with per-model tracking."""
    
    session_id: str = ""
    total_cost_usd: float = 0.0
    total_api_duration_ms: float = 0.0
    model_usage: dict[str, ModelUsage] = field(default_factory=dict)
    
    def add(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        cache_read_tokens: int = 0,
        cache_create_tokens: int = 0,
        web_search_requests: int = 0,
        api_duration_ms: float = 0.0,
    ) -> None:
        """Add usage for a model."""
        if model not in self.model_usage:
            self.model_usage[model] = ModelUsage(
                input_tokens=0,
                output_tokens=0,
                cache_read_input_tokens=0,
                cache_creation_input_tokens=0,
                web_search_requests=0,
                cost_usd=0.0,
                context_window=0,
                max_output_tokens=0,
                api_duration_ms=0.0,
            )
        
        usage = self.model_usage[model]
        usage["input_tokens"] += input_tokens
        usage["output_tokens"] += output_tokens
        usage["cache_read_input_tokens"] += cache_read_tokens
        usage["cache_creation_input_tokens"] += cache_create_tokens
        usage["web_search_requests"] += web_search_requests
        usage["cost_usd"] += cost_usd
        usage["api_duration_ms"] += api_duration_ms
        
        self.total_cost_usd += cost_usd
        self.total_api_duration_ms += api_duration_ms
    
    def get_model_usage(self, model: str) -> ModelUsage:
        """Get usage for a specific model."""
        if model not in self.model_usage:
            return ModelUsage(
                input_tokens=0,
                output_tokens=0,
                cache_read_input_tokens=0,
                cache_creation_input_tokens=0,
                web_search_requests=0,
                cost_usd=0.0,
                context_window=0,
                max_output_tokens=0,
                api_duration_ms=0.0,
            )
        return self.model_usage[model]
    
    def get_total_tokens(self) -> tuple[int, int]:
        """Get total input/output tokens across all models."""
        total_input = 0
        total_output = 0
        for usage in self.model_usage.values():
            total_input += usage["input_tokens"]
            total_output += usage["output_tokens"]
        return total_input, total_output
    
    def save_to_disk(self, path: Path) -> None:
        """Persist tracker state to disk."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
    
    @classmethod
    def load_from_disk(cls, path: Path) -> "UsageTracker":
        """Load tracker state from disk."""
        if not path.exists():
            return cls()
        
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        return cls.from_dict(data)
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "session_id": self.session_id,
            "total_cost_usd": self.total_cost_usd,
            "total_api_duration_ms": self.total_api_duration_ms,
            "model_usage": self.model_usage,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "UsageTracker":
        """Create tracker from dictionary."""
        return cls(
            session_id=data.get("session_id", ""),
            total_cost_usd=data.get("total_cost_usd", 0.0),
            total_api_duration_ms=data.get("total_api_duration_ms", 0.0),
            model_usage=data.get("model_usage", {}),
        )
