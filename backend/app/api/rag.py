"""
TenderWriter — RAG API

Endpoints for the HybridRAG engine: query, generate sections,
check compliance, and analyze requirements.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete, select

from app.api.auth import get_current_user, UserResponse
from app.config import settings
from app.db.database import get_db
from app.models import AppSettings, SearchHistory
from app.privacy_audit import persist_privacy_audit
from app.privacy_policy import EffectivePrivacyPolicy, resolve_effective_privacy_policy
from app.rag.engine import QueryMode, RAGQuery

router = APIRouter()


def _encode_sse_data(payload: str) -> str:
    """Encode text as a valid SSE data frame, preserving embedded newlines."""
    normalized = str(payload).replace("\r\n", "\n").replace("\r", "\n")
    return "".join(f"data: {line}\n" for line in normalized.split("\n")) + "\n"


async def _load_runtime_anonymizer_enabled(db: AsyncSession) -> bool:
    result = await db.execute(select(AppSettings).limit(1))
    row = result.scalar_one_or_none()
    if row and isinstance(row.data, dict) and "anonymizer_enabled" in row.data:
        return bool(row.data["anonymizer_enabled"])
    return settings.anonymizer_enabled


async def _resolve_runtime_privacy_policy(
    db: AsyncSession,
    *,
    route_key: str = "tender",
    tender_id: int | None = None,
) -> EffectivePrivacyPolicy:
    anonymizer_enabled = await _load_runtime_anonymizer_enabled(db)
    return await resolve_effective_privacy_policy(
        db,
        route_key=route_key,
        tender_id=tender_id,
        anonymizer_enabled_override=anonymizer_enabled,
    )


# ── Schemas ──


class RAGQueryRequest(BaseModel):
    query: str
    mode: str = "qa"
    filters: dict = {}
    top_k: int | None = None
    retrieval_top_k: int | None = None
    temperature: float = 0.3
    stream: bool = False
    save_history: bool = True
    retrievers: dict[str, bool] = {}
    fusion_weights: dict[str, float] = {}
    route_key: str = "tender"
    tender_id: int | None = None


class GenerateSectionRequest(BaseModel):
    query: str
    section_title: str
    instructions: str = ""
    requirements: str = ""
    filters: dict = {}
    temperature: float = 0.3
    route_key: str = "tender"
    tender_id: int | None = None


class ComplianceCheckRequest(BaseModel):
    requirement: str
    section_content: str
    filters: dict = {}
    route_key: str = "tender"
    tender_id: int | None = None


class AnalyzeRequirementsRequest(BaseModel):
    document_text: str
    route_key: str = "tender"
    tender_id: int | None = None


class RAGSourceResponse(BaseModel):
    text: str
    score: float
    metadata: dict


class RAGResponse(BaseModel):
    answer: str
    sources: list[RAGSourceResponse]
    mode: str
    llm_route: str | None = None
    anonymized: bool = False


def _should_save_search_history(data: RAGQueryRequest) -> bool:
    return bool(data.save_history)


async def _audit_rag_result(
    *,
    db: AsyncSession,
    action: str,
    current_user: UserResponse,
    rag_query: RAGQuery,
    policy: EffectivePrivacyPolicy,
    llm_route: str | None,
    anonymized: bool,
    payload: dict,
) -> None:
    await persist_privacy_audit(
        db=db,
        action=action,
        current_user=current_user,
        tender_id=rag_query.tender_id,
        route_key=rag_query.route_key,
        llm_route=llm_route,
        anonymized=anonymized,
        target_id=policy.target_id,
        target_provider=policy.target_provider,
        target_base_url=policy.target_base_url,
        payload=payload,
    )


# ── Routes ──


@router.post("/query", response_model=RAGResponse)
async def rag_query(
    data: RAGQueryRequest, 
    request: Request,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Query the HybridRAG engine and save to search history.

    Supports modes: search, qa, write_section, exec_summary, analyze_reqs, compliance
    """
    engine = request.app.state.rag_engine
    policy = await _resolve_runtime_privacy_policy(
        db,
        route_key=data.route_key,
        tender_id=data.tender_id,
    )

    try:
        mode = QueryMode(data.mode)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mode: {data.mode}. Valid modes: {[m.value for m in QueryMode]}"
        )

    rag_query = RAGQuery(
        text=data.query,
        mode=mode,
        filters=data.filters,
        top_k=data.top_k,
        retrieval_top_k=data.retrieval_top_k,
        temperature=data.temperature,
        retrievers=data.retrievers,
        fusion_weights=data.fusion_weights,
        anonymizer_enabled_override=policy.anonymizer_enabled,
        route_key=policy.route_key,
        tender_id=policy.tender_id,
        external_target_url=policy.target_base_url,
        external_target_model=policy.target_model,
        external_target_provider=policy.target_provider,
        external_target_api_key=policy.target_api_key,
        external_target_id=policy.target_id,
        external_target_timeout_ms=policy.target_timeout_ms,
    )

    if data.stream:
        # Streaming response
        async def stream_generator():
            full_response = ""
            async for token in engine.query_stream(rag_query):
                full_response += token
                yield _encode_sse_data(token)

            # Save history when stream completes
            try:
                if _should_save_search_history(data):
                    history = SearchHistory(
                        user_id=current_user.id,
                        query=data.query,
                        response=full_response
                    )
                    db.add(history)
                await _audit_rag_result(
                    db=db,
                    action="rag_query_stream",
                    current_user=current_user,
                    rag_query=rag_query,
                    policy=policy,
                    llm_route=None,
                    anonymized=policy.mode == "external_anonymized",
                    payload={"mode": mode.value, "stream": True, "policy": policy.as_dict()},
                )
                await db.commit()
            except Exception:
                import structlog
                structlog.get_logger().warning(
                    "Failed to save search history during stream",
                    user_id=current_user.id,
                )

            yield _encode_sse_data("[DONE]")

        return StreamingResponse(
            stream_generator(),
            media_type="text/event-stream",
        )

    result = await engine.query(rag_query)

    # Save to history
    if _should_save_search_history(data):
        history = SearchHistory(
            user_id=current_user.id,
            query=data.query,
            response=result.answer
        )
        db.add(history)
    await _audit_rag_result(
        db=db,
        action="rag_query",
        current_user=current_user,
        rag_query=rag_query,
        policy=policy,
        llm_route=result.llm_route.value if result.llm_route else None,
        anonymized=result.anonymized,
        payload={"mode": mode.value, "stream": False, "policy": policy.as_dict()},
    )
    await db.commit()

    return RAGResponse(
        answer=result.answer,
        sources=[
            RAGSourceResponse(
                text=s["text"],
                score=s.get("score", 0),
                metadata=s.get("metadata", {}),
            )
            for s in result.sources
        ],
        mode=result.mode.value,
        llm_route=result.llm_route.value if result.llm_route else None,
        anonymized=result.anonymized,
    )

@router.get("/history")
async def get_search_history(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get the search history for the current user."""
    result = await db.execute(
        select(SearchHistory)
        .where(SearchHistory.user_id == current_user.id)
        .order_by(SearchHistory.created_at.desc())
        .limit(50)
    )
    history = result.scalars().all()
    
    return [
        {
            "id": h.id,
            "query": h.query,
            "response": h.response,
            "created_at": h.created_at
        }
        for h in history
    ]


@router.delete("/history")
async def clear_search_history(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete the current user's search history."""
    result = await db.execute(
        delete(SearchHistory).where(SearchHistory.user_id == current_user.id)
    )
    await db.commit()
    return {"deleted": int(result.rowcount or 0)}


@router.post("/generate-section", response_model=RAGResponse)
async def generate_section(
    data: GenerateSectionRequest,
    request: Request,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate a proposal section using RAG.

    Retrieves relevant context and generates professional proposal text
    for the specified section.
    """
    engine = request.app.state.rag_engine
    policy = await _resolve_runtime_privacy_policy(
        db,
        route_key=data.route_key,
        tender_id=data.tender_id,
    )

    rag_query = RAGQuery(
        text=data.query,
        mode=QueryMode.WRITE_SECTION,
        section_title=data.section_title,
        instructions=data.instructions,
        requirements=data.requirements,
        filters=data.filters,
        temperature=data.temperature,
        anonymizer_enabled_override=policy.anonymizer_enabled,
        route_key=policy.route_key,
        tender_id=policy.tender_id,
        external_target_url=policy.target_base_url,
        external_target_model=policy.target_model,
        external_target_provider=policy.target_provider,
        external_target_api_key=policy.target_api_key,
        external_target_id=policy.target_id,
        external_target_timeout_ms=policy.target_timeout_ms,
    )

    result = await engine.query(rag_query)
    await _audit_rag_result(
        db=db,
        action="rag_generate_section",
        current_user=current_user,
        rag_query=rag_query,
        policy=policy,
        llm_route=result.llm_route.value if result.llm_route else None,
        anonymized=result.anonymized,
        payload={"mode": QueryMode.WRITE_SECTION.value, "policy": policy.as_dict()},
    )
    await db.commit()

    return RAGResponse(
        answer=result.answer,
        sources=[
            RAGSourceResponse(
                text=s["text"],
                score=s.get("score", 0),
                metadata=s.get("metadata", {}),
            )
            for s in result.sources
        ],
        mode=result.mode.value,
        llm_route=result.llm_route.value if result.llm_route else None,
        anonymized=result.anonymized,
    )


@router.post("/compliance-check")
async def compliance_check(
    data: ComplianceCheckRequest,
    request: Request,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Check if a proposal section adequately addresses a requirement.

    Returns compliance status, gaps, and suggestions for improvement.
    """
    engine = request.app.state.rag_engine
    policy = await _resolve_runtime_privacy_policy(
        db,
        route_key=data.route_key,
        tender_id=data.tender_id,
    )

    rag_query = RAGQuery(
        text=data.requirement,
        mode=QueryMode.COMPLIANCE,
        requirements=data.requirement,
        section_content=data.section_content,
        filters=data.filters,
        temperature=0.1,  # Low temperature for factual analysis
        anonymizer_enabled_override=policy.anonymizer_enabled,
        route_key=policy.route_key,
        tender_id=policy.tender_id,
        external_target_url=policy.target_base_url,
        external_target_model=policy.target_model,
        external_target_provider=policy.target_provider,
        external_target_api_key=policy.target_api_key,
        external_target_id=policy.target_id,
        external_target_timeout_ms=policy.target_timeout_ms,
    )

    result = await engine.query(rag_query)
    await _audit_rag_result(
        db=db,
        action="rag_compliance_check",
        current_user=current_user,
        rag_query=rag_query,
        policy=policy,
        llm_route=result.llm_route.value if result.llm_route else None,
        anonymized=result.anonymized,
        payload={"mode": QueryMode.COMPLIANCE.value, "policy": policy.as_dict()},
    )
    await db.commit()

    # Try to parse JSON from LLM response
    import json
    try:
        assessment = json.loads(result.answer)
    except json.JSONDecodeError:
        assessment = {
            "status": "unknown",
            "explanation": result.answer,
            "gaps": [],
            "suggestions": [],
        }

    return {
        "assessment": assessment,
        "sources": result.sources,
    }


@router.post("/analyze-requirements")
async def analyze_requirements(
    data: AnalyzeRequirementsRequest,
    request: Request,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Extract and categorize requirements from tender document text.

    Returns a structured list of requirements with categories and priorities.
    """
    engine = request.app.state.rag_engine
    policy = await _resolve_runtime_privacy_policy(
        db,
        route_key=data.route_key,
        tender_id=data.tender_id,
    )

    rag_query = RAGQuery(
        text="Extract requirements from the tender document",
        mode=QueryMode.ANALYZE_REQS,
        document_text=data.document_text,
        temperature=0.1,
        anonymizer_enabled_override=policy.anonymizer_enabled,
        route_key=policy.route_key,
        tender_id=policy.tender_id,
        external_target_url=policy.target_base_url,
        external_target_model=policy.target_model,
        external_target_provider=policy.target_provider,
        external_target_api_key=policy.target_api_key,
        external_target_id=policy.target_id,
        external_target_timeout_ms=policy.target_timeout_ms,
    )

    result = await engine.query(rag_query)
    await _audit_rag_result(
        db=db,
        action="rag_analyze_requirements",
        current_user=current_user,
        rag_query=rag_query,
        policy=policy,
        llm_route=result.llm_route.value if result.llm_route else None,
        anonymized=result.anonymized,
        payload={"mode": QueryMode.ANALYZE_REQS.value, "policy": policy.as_dict()},
    )
    await db.commit()

    # Try to parse JSON array from LLM response
    import json
    try:
        requirements = json.loads(result.answer)
    except json.JSONDecodeError:
        requirements = [{"text": result.answer, "category": "general", "priority": "medium"}]

    return {
        "requirements": requirements,
        "count": len(requirements),
    }


@router.get("/health")
async def rag_health(request: Request):
    """Check the health of all RAG engine components."""
    engine = request.app.state.rag_engine

    health = {
        "engine_initialized": engine._initialized,
        "dense_retriever": engine.dense_retriever is not None,
        "sparse_retriever": engine.sparse_retriever is not None,
        "sparse_corpus_size": engine.sparse_retriever.corpus_size if engine.sparse_retriever else 0,
        "graph_retriever": engine.graph_retriever is not None,
        "generator": engine.generator is not None,
    }

    # Check Ollama
    if engine.generator:
        health["ollama_available"] = await engine.generator.check_health()

    return health
