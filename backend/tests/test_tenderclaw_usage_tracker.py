"""Tests for enhanced usage tracker."""

import pytest
import tempfile
from pathlib import Path
from backend.runtime.usage_tracker import UsageTracker, ModelUsage


class TestUsageTracker:
    """Test cases for UsageTracker."""
    
    def test_add_basic(self):
        """Test adding usage for a model."""
        tracker = UsageTracker(session_id="test_session")
        
        tracker.add(
            model="claude-sonnet-4-20250514",
            input_tokens=1000,
            output_tokens=500,
            cost_usd=0.015,
        )
        
        usage = tracker.get_model_usage("claude-sonnet-4-20250514")
        assert usage["input_tokens"] == 1000
        assert usage["output_tokens"] == 500
        assert usage["cost_usd"] == 0.015
    
    def test_add_multiple_models(self):
        """Test adding usage for multiple models."""
        tracker = UsageTracker(session_id="test_session")
        
        tracker.add("model-a", 1000, 500, 0.01)
        tracker.add("model-b", 2000, 1000, 0.02)
        
        assert tracker.total_cost_usd == 0.03
        assert tracker.get_model_usage("model-a")["input_tokens"] == 1000
        assert tracker.get_model_usage("model-b")["input_tokens"] == 2000
    
    def test_add_accumulates(self):
        """Test that adding to same model accumulates."""
        tracker = UsageTracker(session_id="test_session")
        
        tracker.add("claude-sonnet-4-20250514", 1000, 500, 0.015)
        tracker.add("claude-sonnet-4-20250514", 500, 250, 0.0075)
        
        usage = tracker.get_model_usage("claude-sonnet-4-20250514")
        assert usage["input_tokens"] == 1500
        assert usage["output_tokens"] == 750
        assert tracker.total_cost_usd == 0.0225
    
    def test_get_total_tokens(self):
        """Test total token calculation."""
        tracker = UsageTracker(session_id="test_session")
        
        tracker.add("model-a", 1000, 500, 0.01)
        tracker.add("model-b", 2000, 1000, 0.02)
        
        total_input, total_output = tracker.get_total_tokens()
        assert total_input == 3000
        assert total_output == 1500
    
    def test_get_model_usage_missing(self):
        """Test getting usage for missing model returns zeros."""
        tracker = UsageTracker(session_id="test_session")
        
        usage = tracker.get_model_usage("nonexistent")
        
        assert usage["input_tokens"] == 0
        assert usage["output_tokens"] == 0
        assert usage["cost_usd"] == 0.0
    
    def test_save_load_disk(self):
        """Test saving and loading from disk."""
        tracker = UsageTracker(session_id="test_session")
        tracker.add("claude-sonnet-4-20250514", 1000, 500, 0.015)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.json"
            tracker.save_to_disk(path)
            
            loaded = UsageTracker.load_from_disk(path)
            
            assert loaded.session_id == "test_session"
            assert loaded.total_cost_usd == 0.015
            assert loaded.get_model_usage("claude-sonnet-4-20250514")["input_tokens"] == 1000
    
    def test_to_dict(self):
        """Test serialization to dict."""
        tracker = UsageTracker(session_id="test_session", total_cost_usd=0.05)
        tracker.add("model-a", 100, 50, 0.001)
        
        data = tracker.to_dict()
        
        assert data["session_id"] == "test_session"
        assert abs(data["total_cost_usd"] - 0.051) < 0.001
        assert "model_usage" in data
        assert data["model_usage"]["model-a"]["input_tokens"] == 100
    
    def test_from_dict(self):
        """Test deserialization from dict."""
        data = {
            "session_id": "test_session",
            "total_cost_usd": 0.05,
            "total_api_duration_ms": 1000.0,
            "model_usage": {
                "model-a": {
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "cache_read_input_tokens": 0,
                    "cache_creation_input_tokens": 0,
                    "web_search_requests": 0,
                    "cost_usd": 0.001,
                    "context_window": 200000,
                    "max_output_tokens": 8192,
                    "api_duration_ms": 500.0,
                }
            }
        }
        
        tracker = UsageTracker.from_dict(data)
        
        assert tracker.session_id == "test_session"
        assert tracker.total_cost_usd == 0.05
        assert tracker.get_model_usage("model-a")["input_tokens"] == 100


class TestCostTracker:
    """Test cases for CostTracker service."""
    
    def test_get_tracker(self):
        """Test getting tracker for session."""
        from backend.services.cost_tracker import CostTracker
        
        tracker = CostTracker.get_tracker("session_123")
        
        assert tracker.session_id == "session_123"
    
    def test_record_usage(self):
        """Test recording usage through CostTracker service."""
        import uuid
        from backend.services.cost_tracker import CostTracker, COSTS_DIR
        
        # Use unique session ID to avoid collision
        session_id = f"test_record_usage_{uuid.uuid4().hex[:8]}"
        CostTracker._trackers.clear()
        
        # Clean up any existing file
        cost_file = COSTS_DIR / f"{session_id}.json"
        if cost_file.exists():
            cost_file.unlink()
        
        CostTracker.record_usage(
            session_id=session_id,
            model="claude-sonnet-4-20250514",
            input_tokens=1000,
            output_tokens=500,
            cost_usd=0.015,
        )
        
        tracker = CostTracker.get_tracker(session_id)
        assert tracker.total_cost_usd == 0.015
    
    def test_get_session_cost(self):
        """Test getting session cost summary."""
        import uuid
        from backend.services.cost_tracker import CostTracker, COSTS_DIR
        
        # Use unique session ID to avoid collision
        session_id = f"test_get_session_{uuid.uuid4().hex[:8]}"
        CostTracker._trackers.clear()
        
        # Clean up any existing file
        cost_file = COSTS_DIR / f"{session_id}.json"
        if cost_file.exists():
            cost_file.unlink()
        
        CostTracker.record_usage(
            session_id=session_id,
            model="claude-sonnet-4-20250514",
            input_tokens=1000,
            output_tokens=500,
            cost_usd=0.015,
        )
        
        cost = CostTracker.get_session_cost(session_id)
        
        assert cost["session_id"] == session_id
        assert cost["total_cost_usd"] == 0.015
        assert cost["total_input_tokens"] == 1000
        assert cost["total_output_tokens"] == 500
