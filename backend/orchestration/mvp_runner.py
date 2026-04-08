"""Minimal MVP runner for Wave 2 orchestration.

This module exposes a small, dependency-free simulation of the Oracle -> Metis
-> Sisyphus stages, using the existing Wave 2 MVP pipeline.
"""

from __future__ import annotations

from typing import AsyncIterator, Dict
import asyncio

from . import mvp_pipeline


async def run_mvp_for_task(task: str, history: list[Dict[str, object]] | None = None) -> AsyncIterator[Dict[str, object]]:
    """Yield MVP pipeline steps for a given task."""
    async for part in mvp_pipeline.run_mvp_pipeline(task, history):
        yield part
