"""
TenderWriter — RAG API

Endpoints for the HybridRAG engine: query, generate sections,
check compliance, and analyze requirements.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.rag.engine import QueryMode, RAGQuery

router = APIRouter()


# ── Schemas ──


class RAGQueryRequest(BaseModel):
    query: str
    mode: str = "qa"
    filters: dict = {}
    top_k: int | None = None
    temperature: float = 0.3
    stream: bool = False


class GenerateSectionRequest(BaseModel):
    query: str
    section_title: str
    instructions: str = ""
    requirements: str = ""
    filters: dict = {}
    temperature: float = 0.3


class ComplianceCheckRequest(BaseModel):
    requirement: str
    section_content: str
    filters: dict = {}


class AnalyzeRequirementsRequest(BaseModel):
    document_text: str


class RAGSourceResponse(BaseModel):
    text: str
    score: float
    metadata: dict


class RAGResponse(BaseModel):
    answer: str
    sources: list[RAGSourceResponse]
    mode: str


# ── Routes ──


@router.post("/query", response_model=RAGResponse)
async def rag_query(data: RAGQueryRequest, request: Request):
    """
    Query the HybridRAG engine.

    Supports modes: search, qa, write_section, exec_summary, analyze_reqs, compliance
    """
    engine = request.app.state.rag_engine

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
        temperature=data.temperature,
    )

    if data.stream:
        # Streaming response
        async def stream_generator():
            async for token in engine.query_stream(rag_query):
                yield f"data: {token}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            stream_generator(),
            media_type="text/event-stream",
        )

    result = await engine.query(rag_query)

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
    )


@router.post("/generate-section", response_model=RAGResponse)
async def generate_section(data: GenerateSectionRequest, request: Request):
    """
    Generate a proposal section using RAG.

    Retrieves relevant context and generates professional proposal text
    for the specified section.
    """
    engine = request.app.state.rag_engine

    rag_query = RAGQuery(
        text=data.query,
        mode=QueryMode.WRITE_SECTION,
        section_title=data.section_title,
        instructions=data.instructions,
        requirements=data.requirements,
        filters=data.filters,
        temperature=data.temperature,
    )

    result = await engine.query(rag_query)

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
    )


@router.post("/compliance-check")
async def compliance_check(data: ComplianceCheckRequest, request: Request):
    """
    Check if a proposal section adequately addresses a requirement.

    Returns compliance status, gaps, and suggestions for improvement.
    """
    engine = request.app.state.rag_engine

    rag_query = RAGQuery(
        text=data.requirement,
        mode=QueryMode.COMPLIANCE,
        requirements=data.requirement,
        section_content=data.section_content,
        filters=data.filters,
        temperature=0.1,  # Low temperature for factual analysis
    )

    result = await engine.query(rag_query)

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
async def analyze_requirements(data: AnalyzeRequirementsRequest, request: Request):
    """
    Extract and categorize requirements from tender document text.

    Returns a structured list of requirements with categories and priorities.
    """
    engine = request.app.state.rag_engine

    rag_query = RAGQuery(
        text="Extract requirements from the tender document",
        mode=QueryMode.ANALYZE_REQS,
        document_text=data.document_text,
        temperature=0.1,
    )

    result = await engine.query(rag_query)

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
