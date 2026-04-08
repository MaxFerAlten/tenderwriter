"""Lightweight runner for Wave 1 verifications (no pytest dependency).

Runs: wave1_smoke.py and wave1_reload_test.py and reports a compact summary
that can be used in CI to ensure the basics are healthy.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PY = sys.executable
BASE = Path(__file__).parent.parent if Path(__file__).parent else Path('.')

def run_py(p: Path) -> tuple[int, str, str]:
    cmd = [str(PY), str(p)]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    out, _ = proc.communicate()
    return proc.returncode, out, cmd[1]

def main():
    results = {}
    for name in ["wave1_smoke.py", "wave1_reload_test.py"]:
        path = Path("D:/MY_AI/claude-code/TenderClaw/tools") / name
        if not path.exists():
            print(f"Missing test script: {path}")
            results[name] = {"status": "missing"}
            continue
        code, output, _ = run_py(path)
        results[name] = {"status": "ok" if code == 0 else "fail", "output_preview": output[:1000]}
        print(output)
    print("SUMMARY:", results)

if __name__ == "__main__":
    main()
