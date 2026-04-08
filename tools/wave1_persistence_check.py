"""Wave 1 persistence verification.

Creates a session and then inspects the .tenderclaw/state directory to
verify that a per-session snapshot file was created.
"""

from __future__ import annotations

import os
import json
import sys
sys.path.append('D:/MY_AI/claude-code/TenderClaw')

from backend.schemas.sessions import SessionCreate
from backend.services.session_store import session_store


def run():
    s = session_store.create(SessionCreate(model=None, system_prompt_append=None, working_directory='.'))
    sid = s.session_id
    print(f"created_session={sid}")
    # Look for disk snapshot
    state_dir = os.path.join('.tenderclaw', 'state')
    if not os.path.isdir(state_dir):
        print("state dir not found (Wave1 persistence may not have run yet)")
        return
    files = os.listdir(state_dir)
    print("state_files:", files)
    # If a snapshot exists, print its first line
    if files:
        path = os.path.join(state_dir, files[0])
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            print("snapshot_head:", list(data.keys())[:3])
        except Exception as e:
            print("failed to read snapshot:", e)


if __name__ == '__main__':
    run()
