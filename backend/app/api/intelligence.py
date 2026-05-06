"""Intelligence API router — exposes Wave-1 read-only tools to the frontend."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.auth import UserResponse, get_current_user
from app.api.tenders import check_tender_access
from app.db.database import get_db
from app.intelligence.agent import TenderIntelligenceAgent
from app.intelligence.lifecycle_projector import (
    get_active_rag_engine,
    reconcile_tender_lifecycle_projection,
)
from app.intelligence.proposal_writer_agent import (
    ProposalWriterAgent,
    ProposalWriterError,
)
from app.intelligence.proposal_writer_models import (
    ProposalWriterRequest,
    ProposalWriterResult,
)
from app.intelligence.rehearsal import TenderRehearsalService
from app.intelligence.rehearsal_converter import (
    AcceptOverrides,
    accept_recommendation,
    dismiss_recommendation,
)
from app.intelligence.rehearsal_summary import (
    build_rehearsal_summary,
    empty_rehearsal_summary,
)
from app.intelligence.result_models import AgentQueryRequest, AgentQueryResult
from app.intelligence.schemas import (
    PersonaEvaluationResponse,
    PersonaFinding,
    PersonaQuestion,
    RehearsalCreateRequest,
    RehearsalRecommendationAcceptRequest,
    RehearsalRecommendationActionResponse,
    RehearsalRecommendationDismissRequest,
    RehearsalRecommendationResponse,
    RehearsalRunResponse,
    RehearsalSummaryResponse,
)
from app.intelligence.tool_registry import TenderToolRegistry, ToolDescriptor
from app.intelligence.tools import build_default_tool_registry
from app.models import (
    Proposal,
    RehearsalRecommendation,
    RehearsalRun,
    Tender,
    TenderStatus,
)

_REHEARSAL_BLOCKED_TENDER_STATUSES = frozenset(
    {TenderStatus.SUBMITTED, TenderStatus.WON, TenderStatus.LOST, TenderStatus.CANCELLED}
)


def _require_admin(current_user: UserResponse) -> None:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail="Admin access required",
        )


router = APIRouter()


_registry: TenderToolRegistry | None = None
_agent: TenderIntelligenceAgent | None = None
_rehearsal_service: TenderRehearsalService | None = None
_proposal_writer_agent: ProposalWriterAgent | None = None


def get_tool_registry() -> TenderToolRegistry:
    """Return the process-wide tool registry (lazy-initialised)."""

    global _registry
    if _registry is None:
        _registry = build_default_tool_registry()
    return _registry


def get_intelligence_agent() -> TenderIntelligenceAgent:
    """Return the process-wide intelligence agent (lazy-initialised)."""

    global _agent
    if _agent is None:
        _agent = TenderIntelligenceAgent(get_tool_registry())
    return _agent


def get_rehearsal_service() -> TenderRehearsalService:
    """Return the process-wide rehearsal service (lazy-initialised)."""

    global _rehearsal_service
    if _rehearsal_service is None:
        _rehearsal_service = TenderRehearsalService(get_tool_registry())
    return _rehearsal_service


def get_proposal_writer_agent() -> ProposalWriterAgent:
    """Return the process-wide proposal writer agent (lazy-initialised).

    The RAG engine is resolved at call time from the lifecycle registry
    so the agent shares the singleton ``HybridRAGEngine`` initialised in
    the FastAPI lifespan.
    """

    global _proposal_writer_agent
    if _proposal_writer_agent is None:
        _proposal_writer_agent = ProposalWriterAgent(
            registry=get_tool_registry(),
            rag_engine=get_active_rag_engine(),
        )
    return _proposal_writer_agent


def set_proposal_writer_agent_for_testing(
    agent: ProposalWriterAgent | None,
) -> None:
    """Swap the process-wide proposal writer agent. Intended for tests only."""

    global _proposal_writer_agent
    _proposal_writer_agent = agent


def set_tool_registry_for_testing(registry: TenderToolRegistry | None) -> None:
    """Swap the process-wide registry. Intended for tests only."""

    global _registry, _agent, _rehearsal_service, _proposal_writer_agent
    _registry = registry
    _agent = None
    _rehearsal_service = None
    _proposal_writer_agent = None


def set_intelligence_agent_for_testing(agent: TenderIntelligenceAgent | None) -> None:
    """Swap the process-wide agent. Intended for tests only."""

    global _agent
    _agent = agent


def set_rehearsal_service_for_testing(
    service: TenderRehearsalService | None,
) -> None:
    """Swap the process-wide rehearsal service. Intended for tests only."""

    global _rehearsal_service
    _rehearsal_service = service


def _enqueue_rehearsal(rehearsal_run_id: int) -> None:
    """Dispatch the Celery task — kept module-level so tests can monkeypatch."""

    from app.tasks import run_rehearsal_task

    run_rehearsal_task.delay(rehearsal_run_id)


class ToolDescriptorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    input_keys: list[str] = Field(default_factory=list)


class ToolListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tools: list[ToolDescriptorResponse]


class ToolEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str
    status: str = "ok"
    result: dict[str, Any]


class CoverageAnalyzerInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tender_id: int


class EvidenceAuditorInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tender_id: int
    only_high_priority: bool = False


class CompliancePanoramaInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tender_id: int


class GraphPathExplainerInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tender_id: int
    requirement_id: int


class ContradictionFinderInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tender_id: int


def _describe(descriptor: ToolDescriptor) -> ToolDescriptorResponse:
    return ToolDescriptorResponse(
        name=descriptor.name,
        description=descriptor.description,
        input_keys=list(descriptor.input_keys),
    )


async def _run_tool(
    *,
    name: str,
    tender_id: int,
    current_user: UserResponse,
    db: AsyncSession,
    inputs: dict[str, Any],
) -> ToolEnvelope:
    registry = get_tool_registry()
    if not registry.contains(name):
        raise HTTPException(status_code=404, detail=f"Unknown intelligence tool '{name}'")
    # Authorise the caller on this tender before running any tool.
    await check_tender_access(tender_id, current_user, db)
    try:
        result = await registry.run(name, db=db, inputs=inputs)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ToolEnvelope(tool=name, status="ok", result=result)


@router.get("/tools", response_model=ToolListResponse, tags=["Intelligence"])
async def list_intelligence_tools(
    current_user: UserResponse = Depends(get_current_user),
) -> ToolListResponse:
    registry = get_tool_registry()
    return ToolListResponse(tools=[_describe(descriptor) for descriptor in registry.list_tools()])


@router.post(
    "/tools/coverage-analyzer",
    response_model=ToolEnvelope,
    tags=["Intelligence"],
)
async def run_coverage_analyzer(
    payload: CoverageAnalyzerInput,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ToolEnvelope:
    return await _run_tool(
        name="coverage_analyzer",
        tender_id=payload.tender_id,
        current_user=current_user,
        db=db,
        inputs={"tender_id": payload.tender_id},
    )


@router.post(
    "/tools/evidence-auditor",
    response_model=ToolEnvelope,
    tags=["Intelligence"],
)
async def run_evidence_auditor(
    payload: EvidenceAuditorInput,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ToolEnvelope:
    return await _run_tool(
        name="evidence_auditor",
        tender_id=payload.tender_id,
        current_user=current_user,
        db=db,
        inputs={
            "tender_id": payload.tender_id,
            "only_high_priority": payload.only_high_priority,
        },
    )


@router.post(
    "/tools/compliance-panorama",
    response_model=ToolEnvelope,
    tags=["Intelligence"],
)
async def run_compliance_panorama(
    payload: CompliancePanoramaInput,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ToolEnvelope:
    return await _run_tool(
        name="compliance_panorama",
        tender_id=payload.tender_id,
        current_user=current_user,
        db=db,
        inputs={"tender_id": payload.tender_id},
    )


@router.post(
    "/tools/graph-path-explainer",
    response_model=ToolEnvelope,
    tags=["Intelligence"],
)
async def run_graph_path_explainer(
    payload: GraphPathExplainerInput,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ToolEnvelope:
    return await _run_tool(
        name="graph_path_explainer",
        tender_id=payload.tender_id,
        current_user=current_user,
        db=db,
        inputs={
            "tender_id": payload.tender_id,
            "requirement_id": payload.requirement_id,
        },
    )


@router.post(
    "/tools/contradiction-finder",
    response_model=ToolEnvelope,
    tags=["Intelligence"],
)
async def run_contradiction_finder(
    payload: ContradictionFinderInput,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ToolEnvelope:
    return await _run_tool(
        name="contradiction_finder",
        tender_id=payload.tender_id,
        current_user=current_user,
        db=db,
        inputs={"tender_id": payload.tender_id},
    )


@router.post(
    "/query",
    response_model=AgentQueryResult,
    tags=["Intelligence"],
)
async def run_intelligence_query(
    payload: AgentQueryRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentQueryResult:
    await check_tender_access(payload.tender_id, current_user, db)
    agent = get_intelligence_agent()
    try:
        return await agent.query(
            db=db,
            tender_id=payload.tender_id,
            question=payload.question,
            only_high_priority=payload.only_high_priority,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _persona_result_to_response(row: Any) -> PersonaEvaluationResponse:
    findings = [PersonaFinding.model_validate(item) for item in (row.findings_json or [])]
    questions = [PersonaQuestion.model_validate(item) for item in (row.questions_json or [])]
    return PersonaEvaluationResponse(
        persona_id=row.persona_id,
        display_name=row.display_name,
        reviewer_type=row.reviewer_type,
        score=float(row.score) if row.score is not None else 0.0,
        findings=findings,
        questions=questions,
        metrics=dict(row.metrics_json or {}),
    )


def _recommendation_to_response(row: Any) -> RehearsalRecommendationResponse:
    return RehearsalRecommendationResponse(
        id=row.id,
        scope_type=row.scope_type,
        scope_id=row.scope_id,
        severity=row.severity,
        is_blocking=bool(row.is_blocking),
        rationale=row.rationale,
        suggested_owner_role=row.suggested_owner_role,
        source_persona_id=row.source_persona_id,
        status=row.status.value if hasattr(row.status, "value") else row.status,
        linked_rework_action_id=row.linked_rework_action_id,
    )


def _rehearsal_run_to_response(run: RehearsalRun) -> RehearsalRunResponse:
    persona_results = [_persona_result_to_response(r) for r in (run.persona_results or [])]
    recommendations = [_recommendation_to_response(r) for r in (run.recommendations or [])]
    return RehearsalRunResponse(
        id=run.id,
        tender_id=run.tender_id,
        proposal_id=run.proposal_id,
        mode=run.mode.value if hasattr(run.mode, "value") else run.mode,
        status=run.status.value if hasattr(run.status, "value") else run.status,
        overall_score=run.overall_score,
        health_projection=run.health_projection,
        persona_divergence=run.persona_divergence,
        started_at=run.started_at,
        completed_at=run.completed_at,
        persona_results=persona_results,
        recommendations=recommendations,
        error_message=run.error_message,
        version=run.version,
    )


async def _load_rehearsal_run(db: AsyncSession, run_id: int) -> RehearsalRun:
    stmt = (
        select(RehearsalRun)
        .where(RehearsalRun.id == run_id)
        .options(
            selectinload(RehearsalRun.persona_results),
            selectinload(RehearsalRun.recommendations),
        )
    )
    result = await db.execute(stmt)
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail=f"Rehearsal run {run_id} not found")
    return run


@router.post(
    "/rehearsals",
    response_model=RehearsalRunResponse,
    status_code=201,
    tags=["Intelligence"],
)
async def create_rehearsal_run(
    payload: RehearsalCreateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RehearsalRunResponse:
    await check_tender_access(payload.tender_id, current_user, db)

    tender = await db.get(Tender, payload.tender_id)
    if tender is None:
        raise HTTPException(status_code=404, detail=f"Tender {payload.tender_id} not found")
    if tender.status in _REHEARSAL_BLOCKED_TENDER_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot start rehearsal for tender in status '{tender.status.value}'."
                " Rehearsal is only allowed before submission."
            ),
        )

    proposal = await db.get(Proposal, payload.proposal_id)
    if proposal is None or proposal.tender_id != payload.tender_id:
        raise HTTPException(
            status_code=404,
            detail=f"Proposal {payload.proposal_id} not found for tender {payload.tender_id}",
        )

    service = get_rehearsal_service()
    try:
        run = await service.create_rehearsal_run(
            db,
            tender_id=payload.tender_id,
            proposal_id=payload.proposal_id,
            mode=payload.mode,
            persona_ids=list(payload.persona_ids),
            proposal_section_ids=list(payload.proposal_section_ids),
            include_forecast_context=payload.include_forecast_context,
            requested_by=current_user.id,
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    _enqueue_rehearsal(run.id)

    loaded = await _load_rehearsal_run(db, run.id)
    return _rehearsal_run_to_response(loaded)


@router.get(
    "/rehearsals/{run_id}",
    response_model=RehearsalRunResponse,
    tags=["Intelligence"],
)
async def get_rehearsal_run(
    run_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RehearsalRunResponse:
    run = await _load_rehearsal_run(db, run_id)
    await check_tender_access(run.tender_id, current_user, db)
    return _rehearsal_run_to_response(run)


@router.get(
    "/rehearsals",
    response_model=list[RehearsalRunResponse],
    tags=["Intelligence"],
)
async def list_rehearsal_runs(
    tender_id: int = Query(..., gt=0),
    proposal_id: int | None = Query(default=None, gt=0),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[RehearsalRunResponse]:
    await check_tender_access(tender_id, current_user, db)

    stmt = (
        select(RehearsalRun)
        .where(RehearsalRun.tender_id == tender_id)
        .options(
            selectinload(RehearsalRun.persona_results),
            selectinload(RehearsalRun.recommendations),
        )
        .order_by(RehearsalRun.created_at.desc())
        .limit(limit)
    )
    if proposal_id is not None:
        stmt = stmt.where(RehearsalRun.proposal_id == proposal_id)

    result = await db.execute(stmt)
    runs = result.scalars().all()
    return [_rehearsal_run_to_response(run) for run in runs]


async def _load_recommendation_for_run(
    db: AsyncSession, *, run_id: int, recommendation_id: int
) -> tuple[RehearsalRun, RehearsalRecommendation]:
    run = await db.get(RehearsalRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Rehearsal run {run_id} not found")
    recommendation = await db.get(RehearsalRecommendation, recommendation_id)
    if recommendation is None or recommendation.rehearsal_run_id != run_id:
        raise HTTPException(
            status_code=404,
            detail=f"Recommendation {recommendation_id} not found on run {run_id}",
        )
    return run, recommendation


@router.post(
    "/rehearsals/{run_id}/recommendations/{recommendation_id}/accept",
    response_model=RehearsalRecommendationActionResponse,
    tags=["Intelligence"],
)
async def accept_rehearsal_recommendation(
    run_id: int,
    recommendation_id: int,
    payload: RehearsalRecommendationAcceptRequest | None = None,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RehearsalRecommendationActionResponse:
    _require_admin(current_user)
    run, recommendation = await _load_recommendation_for_run(
        db, run_id=run_id, recommendation_id=recommendation_id
    )
    await check_tender_access(run.tender_id, current_user, db)

    body = payload or RehearsalRecommendationAcceptRequest()
    overrides = AcceptOverrides(
        assigned_to_user_id=body.assigned_to_user_id,
        due_at=body.due_at,
        severity=body.severity,
        is_blocking=body.is_blocking,
        notes=body.notes,
    )

    try:
        rework = await accept_recommendation(
            db,
            recommendation=recommendation,
            tender_id=run.tender_id,
            actor_id=current_user.id,
            overrides=overrides,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await db.commit()
    await db.refresh(recommendation)

    return RehearsalRecommendationActionResponse(
        recommendation=_recommendation_to_response(recommendation),
        rework_action_id=rework.id,
    )


@router.post(
    "/rehearsals/{run_id}/recommendations/{recommendation_id}/dismiss",
    response_model=RehearsalRecommendationActionResponse,
    tags=["Intelligence"],
)
async def dismiss_rehearsal_recommendation(
    run_id: int,
    recommendation_id: int,
    payload: RehearsalRecommendationDismissRequest | None = None,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RehearsalRecommendationActionResponse:
    _require_admin(current_user)
    run, recommendation = await _load_recommendation_for_run(
        db, run_id=run_id, recommendation_id=recommendation_id
    )
    await check_tender_access(run.tender_id, current_user, db)

    body = payload or RehearsalRecommendationDismissRequest()

    try:
        await dismiss_recommendation(
            db,
            recommendation=recommendation,
            actor_id=current_user.id,
            reason=body.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await db.commit()
    await db.refresh(recommendation)

    return RehearsalRecommendationActionResponse(
        recommendation=_recommendation_to_response(recommendation),
        rework_action_id=recommendation.linked_rework_action_id,
    )


@router.get(
    "/tenders/{tender_id}/rehearsal-summary",
    response_model=RehearsalSummaryResponse,
    tags=["Intelligence"],
)
async def get_rehearsal_summary(
    tender_id: int,
    proposal_id: int | None = Query(default=None, gt=0),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RehearsalSummaryResponse:
    await check_tender_access(tender_id, current_user, db)
    summary = await build_rehearsal_summary(db, tender_id=tender_id, proposal_id=proposal_id)
    if summary is None:
        payload = empty_rehearsal_summary()
        payload["tender_id"] = tender_id
        payload["proposal_id"] = proposal_id
        return RehearsalSummaryResponse.model_validate(payload)
    return RehearsalSummaryResponse.model_validate(summary)


class LifecycleReconcileResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = Field(default="ok")
    summary: dict[str, Any]


@router.post(
    "/tenders/{tender_id}/lifecycle/reconcile",
    response_model=LifecycleReconcileResponse,
    tags=["Intelligence"],
)
async def reconcile_tender_lifecycle(
    tender_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LifecycleReconcileResponse:
    """Rebuild every requirement projection for ``tender_id`` from PG truth.

    Admin-only. Used for backfill / drift recovery; per-requirement
    failures are recorded in the response without aborting the run.
    """
    _require_admin(current_user)
    await check_tender_access(tender_id, current_user, db)

    summary = await reconcile_tender_lifecycle_projection(
        rag_engine=get_active_rag_engine(),
        db=db,
        tender_id=tender_id,
    )
    return LifecycleReconcileResponse(status="ok", summary=summary)


@router.post(
    "/proposal-writer/draft",
    response_model=ProposalWriterResult,
    tags=["Intelligence"],
)
async def run_proposal_writer(
    payload: ProposalWriterRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProposalWriterResult:
    """Run the ProposalWriterAgent for a single section.

    ``apply=False`` returns a preview without mutating any database row.
    ``apply=True`` updates the targeted ``proposal_section`` only — no
    other tables are touched. Permissions are gated on tender access.
    """
    await check_tender_access(payload.tender_id, current_user, db)
    agent = get_proposal_writer_agent()
    try:
        return await agent.execute(db, payload)
    except ProposalWriterError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
