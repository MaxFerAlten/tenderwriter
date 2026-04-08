"""Wave 1 reload test: create session and verify snapshot on disk."""

from __future__ import annotations

import json
import os
import sys
sys.path.append('D:/MY_AI/claude-code/TenderClaw')

from backend.schemas.sessions import SessionCreate
from backend.services.session_store import session_store, STATE_DIR


def main():
    s = session_store.create(SessionCreate(model=None, system_prompt_append=None, working_directory='.'))
    sid = s.session_id
    print(f"created={sid}")
    # inspect disk
    path = os.path.join(STATE_DIR.as_posix())
    print("STATE_DIR:", path)
    files = []
    if os.path.isdir(str(STATE_DIR)):
        files = os.listdir(str(STATE_DIR))
    print("files:", files)
    for f in files[:2]:
        p = os.path.join(str(STATE_DIR), f)
        try:
            with open(p, 'r', encoding='utf-8') as fh:
                data = json.load(fh)
            print("HEAD-", f, list(data.keys())[:3])
        except Exception as e:
            print("ERR reading", f, e)

if __name__ == '__main__':
    main()
