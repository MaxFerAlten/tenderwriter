"""Wave 1 disk check: show contents of the session state dir."""

from __future__ import annotations

import os
import json
import sys
sys.path.append('D:/MY_AI/claude-code/TenderClaw')

STATE_DIR = os.path.join('.tenderclaw', 'state')

def main():
    if not os.path.isdir(STATE_DIR):
        print("STATE_DIR not found:", STATE_DIR)
        return
    files = os.listdir(STATE_DIR)
    print("STATE_FILES:", files)
    if files:
        path = os.path.join(STATE_DIR, files[0])
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            print("HEAD:", list(data.keys())[:5])
        except Exception as e:
            print("ERR reading snapshot:", e)

if __name__ == '__main__':
    main()
