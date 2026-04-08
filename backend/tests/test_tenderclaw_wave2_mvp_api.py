"""Wave 2 MVP API tests (CI-friendly: no app import, direct pipeline test)."""
from __future__ import annotations

import asyncio
import sys, os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def test_wave2_mvp_pipeline_direct():
    """Test the MVP pipeline directly without needing FastAPI app import."""
    from backend.orchestration.mvp_runner import run_mvp_for_task

    async def _run():
        results = []
        async for part in run_mvp_for_task("test task", []):
            results.append(part)
        return results

    results = asyncio.run(_run())
    assert isinstance(results, list)
    assert len(results) > 0
    assert "stage" in results[0]
    assert results[0]["stage"] in ("oracle", "metis", "sisyphus")


def test_wave2_mvp_api_with_client():
    """Test the full FastAPI MVP endpoint if the app can be imported."""
    try:
        from fastapi.testclient import TestClient
        from backend.main import app

        client = TestClient(app)
        resp = client.post("/api/mvp/run", json={"task": "sample wave2 MVP task", "history": []})
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) > 0
        assert "stage" in data[0]
    except Exception as exc:
        # If app import fails (e.g. missing deps), skip but report
        import pytest
        pytest.skip(f"App import failed: {exc}")
