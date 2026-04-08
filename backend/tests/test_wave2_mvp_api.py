from __future__ import annotations

from fastapi.testclient import TestClient
from backend.main import app


def test_wave2_mvp_run_api():
    client = TestClient(app)
    resp = client.post("/api/mvp/run", json={"task": "sample wave2 MVP task", "history": []})
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert isinstance(data[0], dict)
    assert "stage" in data[0]
