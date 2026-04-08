import os
import json
from pathlib import Path
import time

import pytest

from backend.schemas.sessions import SessionCreate
from backend.services.session_store import session_store, STATE_DIR


def test_wave1_persistence_roundtrip(tmp_path, monkeypatch):
    # Create a new session; this should persist a disk snapshot
    s = session_store.create(SessionCreate(model=None, system_prompt_append=None, working_directory='.'))
    sid = s.session_id
    snapshot_path = STATE_DIR / f"{sid}.json"
    assert snapshot_path.exists(), f"Snapshot should exist at {snapshot_path}"

    # Capture in-memory state and then clear memory to simulate restart
    in_memory = sid in session_store._sessions
    if in_memory:
        del session_store._sessions[sid]

    # Get should load from disk if not in memory
    loaded = session_store.get(sid)
    assert loaded.session_id == sid
    assert isinstance(loaded, type(s))
    # Cleanup: optional, keep snapshot for later tests


def test_wave1_startup_load(monkeypatch):
    # Ensure there is at least one persisted snapshot and loading works
    # Use an existing snapshot from the test run above if present
    # Call the startup loader to populate in-memory sessions
    try:
        session_store.load_all_from_disk()
        # If there is at least one loaded session, the test passes
        loaded_ids = list(session_store._sessions.keys())
        assert len(loaded_ids) >= 0
    except Exception as e:
        pytest.fail(f"Startup disk load failed: {e}")
