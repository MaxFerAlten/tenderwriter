"""Minimal MVP orchestration pipeline (Wave 2).

This module provides a tiny, dependency-free orchestration path that simulates
the Oracle -> Metis -> Sisyphus stages by yielding small progress blocks.
It is intended as a scaffold for real integration with the existing agent
framework.
"""

from __future__ import annotations

from typing import AsyncIterator, Dict
import asyncio


async def run_mvp_pipeline(task: str, messages: list[Dict[str, object]] | None = None) -> AsyncIterator[Dict[str, object]]:
    # Stage 1: Oracle
    yield {"stage": "oracle", "status": "start", "task": task}
    await asyncio.sleep(0.1)
    yield {"stage": "oracle", "status": "done", "plan": f"Detailed plan for: {task}"}

    # Stage 2: Metis
    yield {"stage": "metis", "status": "start"}
    await asyncio.sleep(0.1)
    yield {"stage": "metis", "status": "done", "plan": f"Implementation plan for: {task}"}

    # Stage 3: Sisyphus (execute)
    yield {"stage": "sisyphus", "status": "start"}
    await asyncio.sleep(0.1)
    yield {"stage": "sisyphus", "status": "done", "execution": f"Executed plan for: {task}"}
