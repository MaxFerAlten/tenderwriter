from __future__ import annotations

from backend.schemas.sessions import SessionCreate
from backend.services.session_store import session_store
from backend.utils.errors import SessionNotFoundError


def test_wave1_resume_minimal_roundtrip():
    # Create a session and ensure it persists to disk
    state = session_store.create(SessionCreate(model=None, system_prompt_append=None, working_directory='.'))
    sid = state.session_id
    # Ensure we can load it via get() even if not in memory
    if sid in session_store._sessions:
        del session_store._sessions[sid]
    loaded = session_store.get(sid)
    assert loaded.session_id == sid
    assert loaded.model == (state.model or '')
    # Clean up not required here; snapshots are left for manual inspection
