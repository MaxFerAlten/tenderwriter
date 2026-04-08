"""Lightweight health check for TenderClaw Wave 1/2 readiness.

This script imports the health endpoint logic and executes it in-process to
verify basic runtime health wo/ spinning up a server. It is not a replacement
for an actual HTTP health probe but provides immediate validation in CI.
"""

from __future__ import annotations

import asyncio
import sys
sys.path.append('D:/MY_AI/claude-code/TenderClaw')

from backend.api.health import health_check


async def run():
    res = await health_check()
    print("HEALTH:", res)

if __name__ == '__main__':
    asyncio.run(run())
