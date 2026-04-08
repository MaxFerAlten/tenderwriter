"""Wave 1 Restart Simulation (Wave 2 readiness).

This script simulates a soft restart: it clears in-memory sessions, loads
persisted sessions from disk, and creates a new session to verify that the
startup-load and resume paths survive a restart scenario.
"""

from __future__ import annotations

import os
import sys
import json
from pathlib import Path

sys.path.append('D:/MY_AI/claude-code/TenderClaw')

from backend.services.session_store import session_store, STATE_DIR
from backend.schemas.sessions import SessionCreate


def main():
    print("=== Wave 1 Restart Simulation (Wave 2 readiness) ===")
    # Clear in-memory sessions to simulate process restart
    session_store._sessions.clear()  # type: ignore[attr-defined]
    # Load from disk to repopulate state
    try:
        session_store.load_all_from_disk()
        print("Loaded persisted sessions:", list(session_store._sessions.keys()))  # type: ignore[attr-defined]
    except Exception as e:
        print("Failed to load persisted sessions:", e)

    # Create a new session to verify persistence continues to work after restart
    new_state = session_store.create(SessionCreate(model=None, system_prompt_append=None, working_directory='.'))
    print("New session after restart:", new_state.session_id)
    snapshot = STATE_DIR / f"{new_state.session_id}.json"
    print("New snapshot path:", snapshot)
    if snapshot.exists():
        with open(snapshot, 'r', encoding='utf-8') as f:
            data = json.load(f)
        print("Snapshot header:", list(data.keys())[:3])
    else:
        print("Warning: new snapshot was not persisted yet (Wave 1 behavior)")


if __name__ == '__main__':
    main()
