"""MVP orchestration API.

Exposes a minimal Wave 2 orchestrator endpoint to run a task through the
Oracle -> Metis -> Sisyphus stages in a dependency-free way.
"""

from __future__ import annotations

from typing import List, Dict
from fastapi import APIRouter
from pydantic import BaseModel

from backend.orchestration.mvp_runner import run_mvp_for_task

router = APIRouter()


class MVPRunRequest(BaseModel):
    task: str
    history: List[Dict[str, object]] | None = None


@router.post("/run", response_model=List[Dict[str, object]])
async def run_mvp(request: MVPRunRequest) -> List[Dict[str, object]]:
    task = request.task
    history = request.history or []
    results: List[Dict[str, object]] = []
    async for part in run_mvp_for_task(task, history):
        results.append(part)
    return results
