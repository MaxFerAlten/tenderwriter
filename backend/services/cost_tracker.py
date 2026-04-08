"""Cost tracking service layer."""

from pathlib import Path
from backend.runtime.usage_tracker import UsageTracker
from backend.services.session_store import session_store

COSTS_DIR = Path(".tenderclaw/costs")


class CostTracker:
    """Service for managing cost tracking across sessions."""
    
    _trackers: dict[str, UsageTracker] = {}
    
    @classmethod
    def get_tracker(cls, session_id: str) -> UsageTracker:
        """Get or create tracker for session."""
        if session_id not in cls._trackers:
            cost_path = COSTS_DIR / f"{session_id}.json"
            if cost_path.exists():
                cls._trackers[session_id] = UsageTracker.load_from_disk(cost_path)
            else:
                cls._trackers[session_id] = UsageTracker(session_id=session_id)
        return cls._trackers[session_id]
    
    @classmethod
    def record_usage(
        cls,
        session_id: str,
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_usd: float = 0.0,
        cache_read_tokens: int = 0,
        cache_create_tokens: int = 0,
        web_search_requests: int = 0,
        api_duration_ms: float = 0.0,
    ) -> None:
        """Record usage for session."""
        tracker = cls.get_tracker(session_id)
        tracker.add(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            cache_read_tokens=cache_read_tokens,
            cache_create_tokens=cache_create_tokens,
            web_search_requests=web_search_requests,
            api_duration_ms=api_duration_ms,
        )
        cls._save_tracker(tracker)
    
    @classmethod
    def get_session_cost(cls, session_id: str) -> dict:
        """Get cost summary for session."""
        tracker = cls.get_tracker(session_id)
        total_input, total_output = tracker.get_total_tokens()
        return {
            "session_id": session_id,
            "total_cost_usd": tracker.total_cost_usd,
            "total_api_duration_ms": tracker.total_api_duration_ms,
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "model_usage": tracker.model_usage,
        }
    
    @classmethod
    def get_all_costs(cls) -> list[dict]:
        """Get costs for all sessions."""
        cls._load_all_from_disk()
        results = []
        for session_id in cls._trackers:
            results.append(cls.get_session_cost(session_id))
        return results
    
    @classmethod
    def _save_tracker(cls, tracker: UsageTracker) -> None:
        """Save tracker to disk."""
        if tracker.session_id:
            path = COSTS_DIR / f"{tracker.session_id}.json"
            tracker.save_to_disk(path)
    
    @classmethod
    def _load_all_from_disk(cls) -> None:
        """Load all cost trackers from disk."""
        if not COSTS_DIR.exists():
            COSTS_DIR.mkdir(parents=True, exist_ok=True)
            return
        
        for f in COSTS_DIR.glob("*.json"):
            session_id = f.stem
            if session_id not in cls._trackers:
                try:
                    cls._trackers[session_id] = UsageTracker.load_from_disk(f)
                except Exception:
                    pass


cost_tracker = CostTracker
