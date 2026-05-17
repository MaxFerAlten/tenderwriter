"""
TenderWriter — HybridRAG Engine Orchestrator

The main engine that coordinates all retrieval strategies (dense, sparse, graph),
fuses results, re-ranks them, and generates responses using a local LLM.
"""

from __future__ import annotations

import asyncio
import math
import re
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from difflib import SequenceMatcher
from enum import Enum
from typing import TYPE_CHECKING, Any

import httpx
import structlog

from app.config import settings
from app.rag.chunker import ChunkMetadata, SemanticChunker, TextChunk
from app.rag.context_quality import compress_context_block, deduplicate_context_items
from app.rag.dense_retriever import DenseRetriever
from app.rag.embedder import Embedder, get_embedder
from app.rag.fusion import RankFusion
from app.rag.generator import GenerationResult, Generator
from app.rag.graph_retriever import GraphRetriever
from app.rag.internal_prompting import (
    default_language,
    load_retrieval_query_variants,
)
from app.rag.localization import (
    get_engine_cleanup_patterns,
    get_engine_language_markers,
    get_engine_messages,
    get_engine_response_constraints,
    get_guardrail_messages,
    get_intent_regexes,
    get_prompt_leakage_regexes,
    get_prompt_template_text,
)
from app.rag.planningcoverage import normalize_planning_coverage_config, run_planning_coverage
from app.rag.procedure_guardrails import (
    BLOCKED_OUTPUT_MESSAGE,
    PROCEDURE_ANCHORS,
    FactSheet,
    build_fact_sheet,
    classify_chunk_procedure,
    classify_guardrail_failures,
    contamination_re_for,
    fact_sheet_from_guarded_context,
    fact_sheet_missing_critical_slots,
    filter_long_form_amounts,
    guardrail_issue_snippets,
    identity_re_for,
    normalize_guardrail_config,
    repair_unsupported_protected_facts,
    source_procedure_labels_from_guarded_context,
    validate_guarded_answer,
)
from app.rag.reranker import Reranker
from app.rag.sparse_retriever import SparseRetriever

if TYPE_CHECKING:
    from app.rag.procedure_profiles import ProcedureProfile

logger = structlog.get_logger()

_INTENT_REGEXES = get_intent_regexes(default_language())

WORD_COUNT_REQUEST_RE = _INTENT_REGEXES.word_count_request
LINE_COUNT_REQUEST_RE = _INTENT_REGEXES.line_count_request
WORD_RE = re.compile(r"\b[\wÀ-ÿ]+\b", re.UNICODE)
CONTINUATION_HEADING_RE = _INTENT_REGEXES.continuation_heading
_LEAK_REGEXES = get_prompt_leakage_regexes(default_language())

PROMPT_LEAKAGE_PLAIN_LABEL_PATTERN = _LEAK_REGEXES.plain_label_pattern
PROMPT_LEAKAGE_PLAIN_ANSWER_LABEL_PATTERN = _LEAK_REGEXES.plain_answer_label_pattern
PROMPT_LEAKAGE_HEADING_ONLY_LABEL_PATTERN = _LEAK_REGEXES.heading_only_label_pattern
PROMPT_LEAKAGE_LOOP_RE = _LEAK_REGEXES.loop
PROMPT_OWN_TOKEN_LOOP_RE = _LEAK_REGEXES.own_token_loop
PROMPT_OWN_TOKEN_PREFIX_RE = _LEAK_REGEXES.own_token_prefix
PROMPT_LEAKAGE_SUFFIX_RE = _LEAK_REGEXES.suffix
DANGLING_CLOSING_BRACE_SUFFIX_RE = re.compile(r"(?<=\w)\s*[}\])]{1,}\s*$")
BRACE_ONLY_LINE_RE = re.compile(r"^\s*[}\])]+\s*$")
LIKELY_USER_QUERY_START_RE = _LEAK_REGEXES.likely_user_query_start
PROMPT_LEAKAGE_HEADING_RE = _LEAK_REGEXES.heading
PROMPT_LEAKAGE_INLINE_RE = _LEAK_REGEXES.inline
PROMPT_LEAKAGE_INSTRUCTION_RES = _LEAK_REGEXES.instruction_lines
EXPANDED_EXPLANATION_QUERY_RE = _INTENT_REGEXES.expanded_explanation
SUMMARY_INTENT_QUERY_RE = _INTENT_REGEXES.summary_intent
STRUCTURED_OVERVIEW_QUERY_RE = _INTENT_REGEXES.structured_overview
TENDER_DOCUMENT_QUERY_RE = _INTENT_REGEXES.tender_document
GENERIC_TENDER_DEFINITION_QUERY_RE = _INTENT_REGEXES.generic_tender_definition
GENERIC_TENDER_INDEFINITE_RE = _INTENT_REGEXES.generic_tender_indefinite
GENERIC_TENDER_CONCEPT_RE = _INTENT_REGEXES.generic_tender_concept
RETRIEVAL_INTENT_STRIP_RE = _INTENT_REGEXES.retrieval_intent_strip
RETRIEVAL_STOPWORD_STRIP_RE = _INTENT_REGEXES.retrieval_stopword_strip
TERMINAL_SENTENCE_CHARS = {".", "!", "?", ";", '"', "'", ")", "]", "}", "»"}
INCOMPLETE_SENTENCE_END_TOKENS = set(_INTENT_REGEXES.incomplete_sentence_end_tokens)
MATH_RENDERING_REQUEST_RE = _INTENT_REGEXES.math_rendering_request
LENGTH_META_PARAGRAPH_RE = _INTENT_REGEXES.length_meta_paragraph
APPROX_WORDS_PER_LINE = 8
LONG_FORM_INTERNAL_INITIAL_TOKEN_CAP = 1536
LONG_FORM_INTERNAL_PASS_TOKEN_CAP = 512
LOCAL_CONTEXT_CHAR_BUDGET = 4500
SUMMARY_LOCAL_CONTEXT_CHAR_BUDGET = 12000
BROAD_SUMMARY_TOP_K_FINAL = 10
DETAILED_OVERVIEW_TOP_K_FINAL = 12
DETAILED_OVERVIEW_RETRIEVAL_TOP_K = 30
LONGFORM_TENDER_SYNTHESIS_MIN_WORDS = 800
LONGFORM_TENDER_REQUIRED_COVERAGE_SLOTS = frozenset(
    {"identification", "cig_lots", "amounts", "duration"}
)
BROAD_SUMMARY_DEFAULT_MAX_TOKENS = 768
DETAILED_OVERVIEW_DEFAULT_MAX_TOKENS = 1024
DEANONYMIZED_STREAM_FLUSH_CHARS = 96
DEANONYMIZED_STREAM_FORCE_FLUSH_CHARS = 220
PROMPT_GARBAGE_PREFIX_TOKEN_RE = re.compile(r"\S+")
INLINE_MARKDOWN_SECTION_HEADING_RE = re.compile(r"(\S)(\*\*[A-ZÀ-ÖØ-Þ][^*\n]{2,90}\*\*)")
INLINE_MARKDOWN_SECTION_AFTER_PUNCT_RE = re.compile(r"([.!?;])\s+(\*\*[A-ZÀ-ÖØ-Þ][^*\n]{2,90}\*\*)")
BOLD_SECTION_HEADING_RE = re.compile(r"^\s*\*\*([^*\n]{2,90})\*\*")
NON_LATIN_SCRIPT_NOISE_RE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")
_ENGINE_MESSAGES = get_engine_messages(default_language())
_ENGINE_CONSTRAINTS = get_engine_response_constraints(default_language())
_ENGINE_CLEANUP = get_engine_cleanup_patterns(default_language())
_ENGINE_LANG_MARKERS = get_engine_language_markers(default_language())


def _fact_sheet_protocol_fields(messages) -> tuple[str, ...]:
    return (
        messages.fact_sheet_label_procedure,
        messages.fact_sheet_label_status,
        messages.fact_sheet_label_procedure_id,
        messages.fact_sheet_label_cig,
        messages.fact_sheet_label_critical_days,
        messages.fact_sheet_label_duration,
        messages.fact_sheet_label_amounts,
        messages.fact_sheet_label_locations,
        messages.fact_sheet_label_percentages,
        messages.fact_sheet_label_sources,
        messages.fact_sheet_label_conflicts,
    )


def _build_fact_sheet_field_regex(messages) -> re.Pattern[str]:
    alternation = "|".join(
        re.escape(field) for field in _fact_sheet_protocol_fields(messages)
    )
    return re.compile(rf"^\s*(?:{alternation})\s*:", re.IGNORECASE)


def _build_fact_sheet_heading_regex(messages) -> re.Pattern[str]:
    heading = re.escape(messages.fact_sheet_heading_text)
    start = re.escape(messages.fact_sheet_start_marker)
    return re.compile(rf"^\s*(?:{heading}|{start})\s*$", re.IGNORECASE)


def _build_fact_sheet_end_regex(messages) -> re.Pattern[str]:
    end = re.escape(messages.fact_sheet_end_marker)
    return re.compile(rf"^\s*{end}\s*$", re.IGNORECASE)


GENERATED_FACT_SHEET_HEADING_RE = _build_fact_sheet_heading_regex(_ENGINE_MESSAGES)
GENERATED_FACT_SHEET_FIELD_RE = _build_fact_sheet_field_regex(_ENGINE_MESSAGES)
GENERATED_FACT_SHEET_END_RE = _build_fact_sheet_end_regex(_ENGINE_MESSAGES)
INTEGRITY_PACT_CONTEXT_RE = _INTENT_REGEXES.integrity_pact_context
INTEGRITY_PACT_QUERY_RE = _INTENT_REGEXES.integrity_pact_query
PLURAL_DAY_RE = _INTENT_REGEXES.plural_day
PROMPT_GARBAGE_PREFIX_TOKENS = _INTENT_REGEXES.prompt_garbage_prefix_tokens
PROMPT_GARBAGE_PREFIX_STRIP_CHARS = " \t\r\n:/\\\\|#[](){}<>,.;'\"`*-_!?="


def _resolve_query_language(rag_query: RAGQuery | None) -> str:
    """Pick the localization language for a request.

    Returns the per-request override on ``rag_query.language`` when set and
    supported, otherwise falls back to :func:`default_language`.
    """

    if rag_query is not None:
        candidate = getattr(rag_query, "language", None)
        if candidate:
            normalized = str(candidate).lower().strip()
            if normalized in {"it", "en"}:
                return normalized
    return default_language()


class QueryMode(str, Enum):
    """Different query modes for the RAG pipeline."""

    SEARCH = "search"  # Retrieve only, no generation
    QA = "qa"  # General question answering
    WRITE_SECTION = "write_section"  # Generate a proposal section
    EXEC_SUMMARY = "exec_summary"  # Generate executive summary
    ANALYZE_REQS = "analyze_reqs"  # Analyze tender requirements
    COMPLIANCE = "compliance"  # Check compliance


class LLMRoute(str, Enum):
    """Effective generation route chosen for the query."""

    INTERNAL = "internal"
    EXTERNAL_ANONYMIZED = "external_anonymized"
    INTERNAL_FALLBACK = "internal_fallback"


class AnonymizerUnavailableError(RuntimeError):
    """Raised when the anonymizer cannot be reached or returns an invalid payload."""


@dataclass
class RAGQuery:
    """Input to the RAG pipeline."""

    text: str
    mode: QueryMode = QueryMode.QA
    filters: dict = field(default_factory=dict)
    top_k: int | None = None
    retrieval_top_k: int | None = None
    # Additional context for specific modes
    section_title: str = ""
    instructions: str = ""
    requirements: str = ""
    sections: str = ""
    section_content: str = ""
    document_text: str = ""
    temperature: float = 0.3
    retrievers: dict[str, bool] = field(default_factory=dict)
    fusion_weights: dict[str, float] = field(default_factory=dict)
    stream: bool = False
    anonymizer_enabled_override: bool | None = None
    route_key: str = "tender"
    tender_id: int | None = None
    external_target_url: str | None = None
    external_target_model: str | None = None
    external_target_provider: str | None = None
    external_target_api_key: str | None = None
    external_target_id: int | None = None
    external_target_timeout_ms: int | None = None
    sampler_overrides: dict | None = None
    planning_coverage_config: dict | None = None
    guardrail_config: dict | None = None
    # Per-request localization override. ``None`` falls back to the
    # process-wide default (``settings.default_locale`` or ``"it"``).
    language: str | None = None
    # Active procedure profile ids resolved by the API layer from
    # tenders.profile_id (persistent) with heuristic fallback. Empty tuple =
    # base profile only (universal procurement RAG).
    active_profile_ids: tuple[str, ...] = field(default_factory=tuple)


@dataclass
class RAGResponse:
    """Output from the RAG pipeline."""

    answer: str
    sources: list[dict]
    mode: QueryMode
    generation_result: GenerationResult | None = None
    llm_route: LLMRoute | None = None
    anonymized: bool = False


@dataclass(frozen=True)
class ResponseLengthTarget:
    """Normalized target length extracted from the user's query."""

    requested_value: int
    requested_unit: str
    target_words: int
    approximate: bool = False


@dataclass(frozen=True)
class RetrievedContext:
    """Shared retrieval output reused by sync and streaming flows."""

    context: str
    sources: list[dict]


class HybridRAGEngine:
    """
    Main HybridRAG engine orchestrating the full retrieval + generation pipeline.

    Pipeline:
    1. Query → Dense retriever (Qdrant vector search)
    2. Query → Sparse retriever (BM25 keyword search)
    3. Query → Graph retriever (Neo4j knowledge graph)
    4. Merge results with Reciprocal Rank Fusion
    5. Re-rank top candidates with cross-encoder
    6. Generate response with LLM (Ollama)
    """

    def __init__(self):
        self.embedder: Embedder | None = None
        self.chunker: SemanticChunker | None = None
        self.dense_retriever: DenseRetriever | None = None
        self.sparse_retriever: SparseRetriever | None = None
        self.graph_retriever: GraphRetriever | None = None
        self.fusion: RankFusion | None = None
        self.reranker: Reranker | None = None
        self.generator: Generator | None = None
        self._external_generators: dict[tuple[str, str, int, str, str], Generator] = {}
        self._anonymizer_failure_count = 0
        self._anonymizer_circuit_open_until = 0.0
        self._anonymizer_fallback_events = 0
        self._anonymizer_circuit_open_events = 0
        self._last_anonymizer_error_reason: str | None = None
        self._last_privacy_debug_trace: dict[str, Any] | None = None
        self._initialized = False
        self._init_lock = asyncio.Lock()
        self._initialization_task: asyncio.Task[None] | None = None

    def start_initialization(self) -> asyncio.Task[None]:
        """Kick off initialization in the background if needed."""
        if self._initialized:
            return self._initialization_task  # type: ignore[return-value]

        if self._initialization_task and not self._initialization_task.done():
            return self._initialization_task

        loop = asyncio.get_running_loop()
        self._initialization_task = loop.create_task(self.initialize())
        return self._initialization_task

    async def ensure_initialized(self) -> None:
        """Wait for the engine to become ready, initializing on demand."""
        if self._initialized:
            return

        if self._initialization_task and not self._initialization_task.done():
            await asyncio.shield(self._initialization_task)
            return

        await self.initialize()

    async def initialize(self):
        """Initialize all RAG components."""
        if self._initialized:
            return

        async with self._init_lock:
            if self._initialized:
                return

            self._initialization_task = asyncio.current_task()
            try:
                logger.info(
                    "Initializing HybridRAG Engine...",
                    qdrant_host=settings.qdrant_host,
                    qdrant_port=settings.qdrant_port,
                    neo4j_uri=settings.neo4j_uri,
                )

                # Embedder
                self.embedder = get_embedder()

                # Chunker
                self.chunker = SemanticChunker(
                    embedder=self.embedder,
                    min_chunk_size=settings.chunk_min_size,
                    max_chunk_size=settings.chunk_max_size,
                )

                # Dense retriever (Qdrant)
                self.dense_retriever = DenseRetriever(self.embedder)
                try:
                    await self.dense_retriever.initialize()
                except Exception as e:
                    logger.warning(
                        "Dense retriever init failed (Qdrant may be unavailable)", error=str(e)
                    )

                # Sparse retriever (BM25)
                self.sparse_retriever = SparseRetriever()
                try:
                    self._bootstrap_sparse_retriever()
                except Exception as e:
                    logger.warning("Sparse retriever bootstrap failed", error=str(e))

                # Graph retriever (Neo4j)
                self.graph_retriever = GraphRetriever()
                try:
                    await self.graph_retriever.initialize()
                except Exception as e:
                    logger.warning(
                        "Graph retriever init failed (Neo4j may be unavailable)", error=str(e)
                    )

                # Fusion
                self.fusion = RankFusion()

                # Re-ranker
                self.reranker = Reranker()

                # Generator (Llama Server)
                self.generator = Generator(
                    base_url=settings.llama_server_url,
                    model=settings.llama_model,
                    timeout=settings.llama_timeout,
                )

                self._initialized = True
                logger.info("HybridRAG Engine initialized successfully")
            except Exception:
                self._initialization_task = None
                raise

    def _bootstrap_sparse_retriever(self) -> None:
        """
        Rebuild the in-memory BM25 index from persisted dense-retriever payloads.

        Dense payloads already contain the chunk text and metadata required for
        sparse retrieval, so we can restore BM25 state after a restart without
        adding a second persistence layer.
        """
        if self.sparse_retriever is None:
            return

        if self.dense_retriever is None or getattr(self.dense_retriever, "client", None) is None:
            logger.warning(
                "Skipping sparse retriever bootstrap because dense storage is unavailable"
            )
            return

        texts, metadatas = self.dense_retriever.load_persisted_chunks(collection="documents")
        self.sparse_retriever.build_index(texts, metadatas)
        logger.info("Sparse retriever bootstrapped", chunks=len(texts))

    async def _retrieve_context_and_sources(
        self,
        rag_query: RAGQuery,
    ) -> RetrievedContext:
        retrieval_query = self._query_text_for_retrieval(rag_query.text)
        retrieval_queries = self._retrieval_queries_for(
            rag_query.text,
            primary_query=retrieval_query,
        )
        retrieval_filters = self._build_retrieval_filters(rag_query)
        vector_filters = self._vector_retrieval_filters(retrieval_filters)
        graph_filters = dict(retrieval_filters or {}) or None
        retriever_selection = self._resolve_retriever_selection(rag_query)
        rank_fusion = self._build_rank_fusion_for_query(rag_query)
        retrieval_top_k = self._effective_retrieval_top_k(rag_query)

        dense_results = []
        sparse_results = []
        graph_results = []
        coverage_fact_sheet_items: list[dict[str, Any]] = []

        if retriever_selection["dense"] and self.dense_retriever:
            try:
                raw_dense = self.dense_retriever.search(
                    query=retrieval_query,
                    top_k=retrieval_top_k or settings.rag_top_k_dense,
                    filters=vector_filters,
                )
                dense_results = [
                    {"text": r.text, "score": r.score, "metadata": r.metadata} for r in raw_dense
                ]
            except Exception as e:
                logger.warning("Dense retrieval failed", error=str(e))

        if retriever_selection["sparse"] and self.sparse_retriever:
            try:
                raw_sparse = self.sparse_retriever.search(
                    query=retrieval_query,
                    top_k=retrieval_top_k or settings.rag_top_k_sparse,
                    filters=vector_filters,
                )
                sparse_results = [
                    {"text": r.text, "score": r.score, "metadata": r.metadata} for r in raw_sparse
                ]
            except Exception as e:
                logger.warning("Sparse retrieval failed", error=str(e))

        variant_queries = retrieval_queries[1:]
        variant_top_k = 2
        if variant_queries:
            if retriever_selection["sparse"] and self.sparse_retriever:
                for variant_query in variant_queries:
                    try:
                        raw_sparse_variant = self.sparse_retriever.search(
                            query=variant_query,
                            top_k=variant_top_k,
                            filters=vector_filters,
                        )
                        sparse_results.extend(
                            {
                                "text": r.text,
                                "score": r.score,
                                "metadata": {
                                    **(r.metadata or {}),
                                    "retrieval_variant": variant_query,
                                },
                            }
                            for r in raw_sparse_variant
                        )
                    except Exception as e:
                        logger.warning(
                            "Sparse retrieval variant failed",
                            error=str(e),
                            variant=variant_query,
                        )

            if retriever_selection["dense"] and self.dense_retriever:
                dense_variant_queries = (
                    (variant_queries[0], variant_queries[-1])
                    if len(variant_queries) > 1
                    else variant_queries
                )
                for variant_query in dict.fromkeys(dense_variant_queries):
                    try:
                        raw_dense_variant = self.dense_retriever.search(
                            query=variant_query,
                            top_k=variant_top_k,
                            filters=vector_filters,
                        )
                        dense_results.extend(
                            {
                                "text": r.text,
                                "score": r.score,
                                "metadata": {
                                    **(r.metadata or {}),
                                    "retrieval_variant": variant_query,
                                },
                            }
                            for r in raw_dense_variant
                        )
                    except Exception as e:
                        logger.warning(
                            "Dense retrieval variant failed",
                            error=str(e),
                            variant=variant_query,
                        )

        if retriever_selection["graph"] and self.graph_retriever:
            try:
                raw_graph = await self.graph_retriever.search(
                    query=retrieval_query,
                    top_k=retrieval_top_k or settings.rag_top_k_graph,
                    filters=graph_filters,
                    active_profiles=self._active_profiles_for_query(rag_query.text),
                )
                graph_results = [
                    {"text": r.text, "score": r.score, "metadata": r.metadata} for r in raw_graph
                ]
            except Exception as e:
                logger.warning("Graph retrieval failed", error=str(e))

        if rag_query.mode in {QueryMode.QA, QueryMode.SEARCH}:
            coverage = await run_planning_coverage(
                query=rag_query.text,
                config=self._planning_coverage_config_for_query(rag_query),
                filters=vector_filters,
                graph_filters=graph_filters,
                sparse_retriever=(self.sparse_retriever if retriever_selection["sparse"] else None),
                dense_retriever=(self.dense_retriever if retriever_selection["dense"] else None),
                graph_retriever=(self.graph_retriever if retriever_selection["graph"] else None),
            )
            if coverage.activated:
                for item in coverage.results:
                    retriever = item.get("retriever")
                    payload = {
                        "text": item.get("text", ""),
                        "score": item.get("score", 0),
                        "metadata": item.get("metadata", {}),
                    }
                    if payload["metadata"].get("coverage_slot") in LONGFORM_TENDER_REQUIRED_COVERAGE_SLOTS:
                        coverage_fact_sheet_items.append(payload)
                    if retriever == "sparse":
                        sparse_results.append(payload)
                    elif retriever == "graph":
                        graph_results.append(payload)
                    else:
                        dense_results.append(payload)
                logger.info(
                    "Planning coverage retrieval completed",
                    query_class=coverage.query_class,
                    slots=coverage.slots_triggered,
                    coverage_results=len(coverage.results),
                    latency_ms=coverage.latency_ms,
                )

        top_k_final = self._effective_final_top_k(rag_query)

        fusion_top_k = self._effective_fusion_top_k(
            top_k_final=top_k_final,
            retrieval_top_k=retrieval_top_k,
            retriever_selection=retriever_selection,
        )

        fused = rank_fusion.fuse(
            dense_results=dense_results,
            sparse_results=sparse_results,
            graph_results=graph_results,
            top_k=fusion_top_k,
        )

        reranked = []
        if fused:
            try:
                fused_dicts = [
                    {
                        "text": f.text,
                        "score": f.score,
                        "metadata": f.metadata,
                        "sources": f.sources,
                        "source_scores": f.source_scores,
                    }
                    for f in fused
                ]
                reranked = self.reranker.rerank(
                    query=retrieval_query,
                    results=fused_dicts,
                    top_k=fusion_top_k,
                )
            except Exception as e:
                logger.warning("Re-ranking failed, using fusion order", error=str(e))
                reranked = fused

        context_items = []
        for r in reranked:
            text = r.text if hasattr(r, "text") else r.get("text", "")
            metadata = r.metadata if hasattr(r, "metadata") else r.get("metadata", {})
            retriever_sources = r.sources if hasattr(r, "sources") else r.get("sources", [])
            source_scores = (
                r.source_scores if hasattr(r, "source_scores") else r.get("source_scores", {})
            )
            context_items.append(
                {
                    "text": text,
                    "score": r.score if hasattr(r, "score") else r.get("score", 0),
                    "metadata": metadata,
                    "retriever_sources": retriever_sources,
                    "source_scores": source_scores,
                }
            )

        fact_sheet_context_items = [
            item
            for item in [*coverage_fact_sheet_items, *context_items]
            if not self._should_exclude_longform_context_item(item, rag_query)
        ]
        context_items = [
            item
            for item in context_items
            if not self._should_exclude_longform_context_item(item, rag_query)
        ]
        context_items, _dedup_stats = deduplicate_context_items(context_items)
        context_items = self._select_final_reranked_results(
            context_items,
            top_k=top_k_final,
            retriever_selection=retriever_selection,
        )

        context_texts = []
        sources = []
        should_compress_context = (
            rag_query.mode == QueryMode.QA and self._query_requests_broad_summary(rag_query.text)
        )
        for item in context_items:
            text = str(item.get("text") or "")
            if should_compress_context:
                text = compress_context_block(
                    text,
                    query=rag_query.text,
                    min_chars_to_compress=450,
                )
            context_texts.append(text)
            sources.append(
                {
                    "text": text[:200] + "..." if len(text) > 200 else text,
                    "score": item.get("score", 0),
                    "metadata": item.get("metadata", {}),
                    "retriever_sources": item.get("retriever_sources", []),
                    "source_scores": item.get("source_scores", {}),
                }
            )

        if self._query_uses_procedure_guardrails(rag_query):
            _profiles = self._active_profiles_for_query(rag_query.text)
            fact_sheet = build_fact_sheet(
                fact_sheet_context_items,
                query=rag_query.text,
                active_profiles=_profiles,
            )
            if self._query_requests_longform_tender_synthesis(rag_query):
                fact_sheet = filter_long_form_amounts(fact_sheet)
            for source, context_text in zip(sources, context_texts, strict=False):
                source_procedure = classify_chunk_procedure(
                    context_text, active_profiles=_profiles
                )
                source["metadata"] = {
                    **source.get("metadata", {}),
                    "procedure_label": source_procedure,
                    "fact_sheet_procedure_label": fact_sheet.procedure_label,
                    "fact_sheet_status": fact_sheet.status.value,
                }
            logger.info(
                "RAG guardrail fact sheet built",
                procedure_label=fact_sheet.procedure_label,
                fact_sheet_status=fact_sheet.status.value,
                cigs=len(fact_sheet.cigs),
                procedure_ids=len(fact_sheet.procedure_ids),
                critical_days=len(fact_sheet.critical_days),
                durations=len(fact_sheet.durations),
                amounts=len(fact_sheet.amounts),
                conflicts=fact_sheet.conflicts,
                source_count=len(fact_sheet.source_ids),
            )
            return RetrievedContext(
                context=self._build_context_with_source_envelopes(
                    context_texts,
                    sources,
                    fact_sheet=fact_sheet,
                ),
                sources=sources,
            )

        return RetrievedContext(
            context=self._build_context_with_doc_tags(context_texts, sources),
            sources=sources,
        )

    def _build_context_with_doc_tags(
        self,
        context_texts: list[str],
        sources: list[dict],
    ) -> str:
        """Build context with XML-style doc tags to prevent header re-injection."""
        parts = []
        for i, (text, source) in enumerate(zip(context_texts, sources, strict=False)):
            doc_id = source.get("metadata", {}).get("chunk_index", i)
            page = source.get("metadata", {}).get("page_number", "?")
            text = text.strip()
            text = re.sub(r"^#{1,4}\s+.+\n", "", text, flags=re.MULTILINE)
            text = re.sub(r"^#{1,4}\s+", "", text)
            parts.append(f"<doc id='{doc_id}' page='{page}'>\n{text}\n</doc>")
        return "\n".join(parts)

    def _format_fact_sheet(self, fact_sheet: FactSheet) -> str:
        messages = _ENGINE_MESSAGES
        procedure_ids = self._format_fact_sheet_values(
            fact_sheet.procedure_ids,
            conflict_key="procedure_id",
            conflicts=fact_sheet.conflicts,
        )
        cigs = self._format_fact_sheet_values(
            fact_sheet.cigs,
            conflict_key="cig",
            conflicts=fact_sheet.conflicts,
            prefix="CIG ",
        )
        not_detected = messages.fact_sheet_value_not_detected
        no_conflicts = messages.fact_sheet_value_no_conflicts
        return "\n".join(
            [
                messages.fact_sheet_start_marker,
                f"{messages.fact_sheet_label_procedure}: {fact_sheet.procedure_label}",
                f"{messages.fact_sheet_label_status}: {fact_sheet.status.value}",
                f"{messages.fact_sheet_label_procedure_id}: {procedure_ids}",
                f"{messages.fact_sheet_label_cig}: {cigs}",
                f"{messages.fact_sheet_label_critical_days}: "
                f"{', '.join(fact_sheet.critical_days) or not_detected}",
                f"{messages.fact_sheet_label_duration}: "
                f"{', '.join(fact_sheet.durations) or not_detected}",
                f"{messages.fact_sheet_label_amounts}: "
                f"{', '.join(fact_sheet.amounts) or not_detected}",
                f"{messages.fact_sheet_label_locations}: "
                f"{', '.join(fact_sheet.locations) or not_detected}",
                f"{messages.fact_sheet_label_percentages}: "
                f"{', '.join(fact_sheet.percentages) or not_detected}",
                f"{messages.fact_sheet_label_sources}: "
                f"{', '.join(fact_sheet.source_ids) or not_detected}",
                f"{messages.fact_sheet_label_conflicts}: "
                f"{', '.join(fact_sheet.conflicts) or no_conflicts}",
                messages.fact_sheet_end_marker,
            ]
        )

    def _build_context_with_source_envelopes(
        self,
        context_texts: list[str],
        sources: list[dict],
        *,
        fact_sheet: FactSheet,
    ) -> str:
        """Build guarded context with deterministic fact sheet and source boundaries."""
        parts = [self._format_fact_sheet(fact_sheet)]
        for index, (text, source) in enumerate(zip(context_texts, sources, strict=False)):
            metadata = source.get("metadata", {})
            doc_id = metadata.get("chunk_index", index)
            page = metadata.get("page_number", "?")
            procedure = (
                metadata.get("procedure_label")
                or _ENGINE_MESSAGES.procedure_label_unattributed
            )
            cleaned = str(text or "").strip()
            cleaned = re.sub(r"^#{1,4}\s+.+\n", "", cleaned, flags=re.MULTILINE)
            cleaned = re.sub(r"^#{1,4}\s+", "", cleaned)
            parts.append(
                f"SOURCE_START id={doc_id} page={page} procedure={procedure}\n{cleaned}\nSOURCE_END"
            )
        return "\n\n".join(parts)

    def _build_retrieval_filters(self, rag_query: RAGQuery) -> dict | None:
        filters = dict(rag_query.filters or {})
        if rag_query.tender_id is not None:
            filters.setdefault("tender_id", rag_query.tender_id)
        return filters or None

    def _vector_retrieval_filters(self, filters: dict | None) -> dict | None:
        if not filters:
            return None
        vector_filters = {
            key: value for key, value in filters.items() if not str(key).startswith("graph_")
        }
        return vector_filters or None

    def _resolve_retriever_selection(self, rag_query: RAGQuery) -> dict[str, bool]:
        selection = {
            "dense": True,
            "sparse": True,
            "graph": True,
        }

        for key in selection:
            if key in rag_query.retrievers:
                selection[key] = bool(rag_query.retrievers[key])

        if any(selection.values()):
            return selection

        logger.warning(
            "All retrievers disabled for query; falling back to defaults",
            query_len=len(rag_query.text),
        )
        return {
            "dense": True,
            "sparse": True,
            "graph": True,
        }

    def _resolve_fusion_weights(self, rag_query: RAGQuery) -> dict[str, float]:
        defaults = {
            "dense": settings.rag_dense_weight,
            "sparse": settings.rag_sparse_weight,
            "graph": settings.rag_graph_weight,
        }

        resolved: dict[str, float] = {}
        for key, default_value in defaults.items():
            candidate = rag_query.fusion_weights.get(key)
            if isinstance(candidate, (int, float)) and math.isfinite(candidate):
                resolved[key] = max(0.05, min(2.0, float(candidate)))
            else:
                resolved[key] = default_value

        return resolved

    def _planning_coverage_config_for_query(self, rag_query: RAGQuery) -> dict[str, Any]:
        config = normalize_planning_coverage_config(rag_query.planning_coverage_config)
        if not self._query_requests_longform_tender_synthesis(rag_query):
            return config

        config["enabled"] = True
        config["mode"] = "always_on"
        config["alwaysRunPlanner"] = True
        slots = dict(config["slots"])
        for slot_key in LONGFORM_TENDER_REQUIRED_COVERAGE_SLOTS:
            slots[slot_key] = True
        config["slots"] = slots
        config["topkPerSlot"] = max(int(config["topkPerSlot"]), 2)
        config["maxSourcesPerSlot"] = max(int(config["maxSourcesPerSlot"]), 2)
        config["globalMaxCoverageChunks"] = max(
            int(config["globalMaxCoverageChunks"]),
            len(LONGFORM_TENDER_REQUIRED_COVERAGE_SLOTS) * 2,
        )
        return config

    def _active_profiles_for_query(
        self, query_text: str
    ) -> tuple[ProcedureProfile, ...]:
        from app.rag.procedure_profiles import resolve_active_profiles

        return resolve_active_profiles(
            query_text,
            chunk_texts=(),
            explicit_profile_ids=tuple(getattr(self, "_pending_profile_ids", ())),
        )

    def _query_primary_procedure_label(self, query_text: str) -> str:
        requested = self._requested_procedure_labels_for_retrieval(query_text)
        if len(requested) == 1:
            return next(iter(requested))
        return classify_chunk_procedure(
            query_text, active_profiles=self._active_profiles_for_query(query_text)
        )

    def _query_explicitly_requests_integrity_pact(self, query_text: str) -> bool:
        return bool(INTEGRITY_PACT_QUERY_RE.search(query_text or ""))

    def _should_exclude_longform_context_item(
        self,
        item: dict[str, Any],
        rag_query: RAGQuery,
    ) -> bool:
        if not self._query_requests_longform_tender_synthesis(rag_query):
            return False

        text = str(item.get("text") or "")
        if not text:
            return False

        if (
            INTEGRITY_PACT_CONTEXT_RE.search(text)
            and not self._query_explicitly_requests_integrity_pact(rag_query.text)
        ):
            return True

        profiles = self._active_profiles_for_query(rag_query.text)
        instance = next((p for p in profiles if p.kind == "tender_instance"), None)
        if instance is None:
            return False
        main_label = instance.main_label
        referenced_label = instance.referenced_label
        if self._query_primary_procedure_label(rag_query.text) != main_label:
            return False

        normalized = text.casefold()
        contamination_re = contamination_re_for(profiles)
        identity_re = identity_re_for(profiles)
        contamination_hits = len(contamination_re.findall(text))
        identity_hits = len(identity_re.findall(text))
        if contamination_hits >= 2 and identity_hits < 2:
            return True
        return (
            classify_chunk_procedure(text, active_profiles=profiles) == referenced_label
            and main_label.casefold() not in normalized
            and bool(contamination_re.search(text))
        )

    def _build_rank_fusion_for_query(self, rag_query: RAGQuery) -> RankFusion:
        weights = self._resolve_fusion_weights(rag_query)
        return RankFusion(
            k=settings.rag_rrf_k,
            dense_weight=weights["dense"],
            sparse_weight=weights["sparse"],
            graph_weight=weights["graph"],
        )

    def _effective_fusion_top_k(
        self,
        *,
        top_k_final: int,
        retrieval_top_k: int | None,
        retriever_selection: dict[str, bool],
    ) -> int:
        base_pool = max(top_k_final, retrieval_top_k or settings.rag_top_k_dense)
        if not retriever_selection.get("graph"):
            return base_pool

        if retrieval_top_k is not None:
            depth_by_retriever = {
                "dense": max(0, int(retrieval_top_k)),
                "sparse": max(0, int(retrieval_top_k)),
                "graph": max(0, int(retrieval_top_k)),
            }
        else:
            depth_by_retriever = {
                "dense": settings.rag_top_k_dense,
                "sparse": settings.rag_top_k_sparse,
                "graph": settings.rag_top_k_graph,
            }

        enabled_pool = sum(
            depth
            for retriever, depth in depth_by_retriever.items()
            if retriever_selection.get(retriever)
        )
        return max(base_pool, enabled_pool)

    def _result_retriever_sources(self, result: Any) -> list[str]:
        if hasattr(result, "sources"):
            return list(result.sources or [])
        if isinstance(result, dict):
            return list(result.get("sources") or result.get("retriever_sources") or [])
        return []

    def _select_final_reranked_results(
        self,
        results: list[Any],
        *,
        top_k: int,
        retriever_selection: dict[str, bool],
    ) -> list[Any]:
        if top_k <= 0:
            return []

        selected = list(results[:top_k])
        if not retriever_selection.get("graph"):
            return selected

        if any("graph" in self._result_retriever_sources(result) for result in selected):
            return selected

        graph_candidate = next(
            (result for result in results if "graph" in self._result_retriever_sources(result)),
            None,
        )
        if graph_candidate is None:
            return selected

        if len(selected) < top_k:
            selected.append(graph_candidate)
            return selected

        replace_index = next(
            (
                index
                for index in range(len(selected) - 1, -1, -1)
                if "graph" not in self._result_retriever_sources(selected[index])
            ),
            len(selected) - 1,
        )
        selected[replace_index] = graph_candidate
        return selected

    async def query(self, rag_query: RAGQuery) -> RAGResponse:
        """
        Execute the full HybridRAG pipeline.

        Args:
            rag_query: The query with mode, filters, and additional context.

        Returns:
            RAGResponse with the generated answer and source references.
        """
        await self.ensure_initialized()

        logger.info(
            "RAG query started",
            mode=rag_query.mode.value,
            query_len=len(rag_query.text),
        )
        self._pending_profile_ids = tuple(rag_query.active_profile_ids)
        retrieved = await self._retrieve_context_and_sources(rag_query)
        context = retrieved.context
        sources = retrieved.sources

        # ─── Step 4: Search-only mode ───
        if rag_query.mode == QueryMode.SEARCH:
            return RAGResponse(
                answer="",
                sources=sources,
                mode=rag_query.mode,
                llm_route=None,
                anonymized=False,
            )

        template, variables = self._resolve_template(rag_query, context)
        (
            generator,
            variables,
            llm_route,
            anonymized,
            deanonymize_session_id,
            anonymizer_enabled,
        ) = await self._prepare_generation_route(rag_query, variables)
        logger.info(
            "RAG route selected",
            mode=rag_query.mode.value,
            route_key=rag_query.route_key,
            tender_id=rag_query.tender_id,
            anonymizer_enabled=anonymizer_enabled,
            anonymizer_used=anonymized,
            llm_route=llm_route.value,
            session_token=self._mask_session_token(deanonymize_session_id),
            target_id=rag_query.external_target_id,
            target_provider=rag_query.external_target_provider,
        )

        fitted_context = self._fit_context_for_generator(
            context,
            generator=generator,
            rag_query=rag_query,
        )
        if fitted_context != context:
            context = fitted_context
            variables = {**variables, "context": fitted_context}

        # ─── Step 5: Generate response ───
        try:
            generation_result = await self._generate(
                rag_query,
                context,
                generator=generator,
                template=template,
                variables=variables,
            )
        except Exception as e:
            logger.error(
                "Generation failed",
                mode=rag_query.mode.value,
                anonymizer_used=anonymized,
                llm_route=llm_route.value,
                session_token=self._mask_session_token(deanonymize_session_id),
                error=str(e),
            )
            if rag_query.mode == QueryMode.QA:
                fallback_answer = get_engine_messages(
                    _resolve_query_language(rag_query)
                ).model_unavailable_fallback
                generation_result = GenerationResult(
                    text=fallback_answer,
                    model=self.generator.model if self.generator else "unknown",
                    template_used="fallback_unavailable",
                )
                logger.warning(
                    "RAG query returned fallback answer",
                    mode=rag_query.mode.value,
                    anonymizer_used=anonymized,
                    llm_route=llm_route.value,
                    session_token=self._mask_session_token(deanonymize_session_id),
                )
                return RAGResponse(
                    answer=fallback_answer,
                    sources=sources,
                    mode=rag_query.mode,
                    generation_result=generation_result,
                    llm_route=llm_route,
                    anonymized=anonymized,
                )
            raise

        try:
            generation_result = await self._extend_answer_if_needed(
                rag_query,
                generator=generator,
                context=context,
                variables=variables,
                generation_result=generation_result,
            )
        except Exception as e:
            logger.warning(
                "Answer extension failed, returning initial generation",
                mode=rag_query.mode.value,
                llm_route=llm_route.value,
                error=str(e),
                target_id=rag_query.external_target_id,
                target_provider=rag_query.external_target_provider,
            )

        try:
            trailing_completion = await self._complete_trailing_sentence_if_needed(
                rag_query,
                generator=generator,
                context=context,
                variables=variables,
                current_text=generation_result.text,
            )
        except Exception as e:
            logger.warning(
                "Trailing sentence completion failed, returning current answer",
                mode=rag_query.mode.value,
                llm_route=llm_route.value,
                error=str(e),
            )
            trailing_completion = None

        if trailing_completion:
            generation_result = replace(
                generation_result,
                text=self._merge_sentence_completion_suffix(
                    generation_result.text,
                    trailing_completion.text,
                ),
                completion_tokens=(
                    (generation_result.completion_tokens or 0)
                    + (trailing_completion.completion_tokens or 0)
                )
                or generation_result.completion_tokens,
            )

        raw_guarded_answer = self._apply_generation_guardrails(
            rag_query,
            context=context,
            answer=generation_result.text,
        )
        if raw_guarded_answer.startswith(BLOCKED_OUTPUT_MESSAGE):
            generation_result = replace(generation_result, text=raw_guarded_answer)
        else:
            generation_result = replace(
                generation_result,
                text=self._clean_final_answer_text(
                    self._remove_duplicate_paragraphs(generation_result.text)
                ),
            )

            if deanonymize_session_id:
                generation_result = replace(
                    generation_result,
                    text=await self._deanonymize_text(
                        generation_result.text,
                        deanonymize_session_id,
                    ),
                )

            generation_result = replace(
                generation_result,
                text=self._apply_generation_guardrails(
                    rag_query,
                    context=context,
                    answer=generation_result.text,
                ),
            )

        logger.info(
            "RAG query completed",
            mode=rag_query.mode.value,
            route_key=rag_query.route_key,
            tender_id=rag_query.tender_id,
            anonymizer_used=anonymized,
            llm_route=llm_route.value,
            session_token=self._mask_session_token(deanonymize_session_id),
            source_count=len(sources),
            answer_len=len(generation_result.text),
            target_id=rag_query.external_target_id,
            target_provider=rag_query.external_target_provider,
        )
        return RAGResponse(
            answer=generation_result.text,
            sources=sources,
            mode=rag_query.mode,
            generation_result=generation_result,
            llm_route=llm_route,
            anonymized=anonymized,
        )

    async def query_stream(self, rag_query: RAGQuery) -> AsyncIterator[str]:
        """
        Stream the RAG pipeline response token by token.

        Retrieval + fusion + re-ranking happen first, then generation is streamed.
        """
        if self._should_buffer_stream_for_quality(rag_query):
            result = await self.query(rag_query)
            if result.answer:
                yield result.answer
            return

        await self.ensure_initialized()
        self._pending_profile_ids = tuple(rag_query.active_profile_ids)
        retrieved = await self._retrieve_context_and_sources(rag_query)
        context = retrieved.context
        length_target = self._extract_requested_length_target(rag_query.text)

        # Determine template and variables
        template, variables = self._resolve_template(rag_query, context)
        (
            generator,
            stream_variables,
            llm_route,
            anonymized,
            deanonymize_session_id,
            _anonymizer_enabled,
        ) = await self._prepare_generation_route(rag_query, variables)

        fitted_context = self._fit_context_for_generator(
            context,
            generator=generator,
            rag_query=rag_query,
        )
        if fitted_context != context:
            context = fitted_context
            stream_variables = {**stream_variables, "context": fitted_context}

        target_goal_words = None
        if rag_query.mode == QueryMode.QA and length_target:
            target_goal_words = (
                length_target.target_words
                if self._supports_large_long_form_generation(generator)
                else self._minimum_acceptable_word_count(
                    length_target.target_words,
                    approximate=length_target.approximate,
                )
            )

        current_text = ""
        active_template = template
        active_variables = stream_variables
        using_continuation_template = False
        pass_attempts = (
            self._continuation_attempt_budget(length_target.target_words)
            if rag_query.mode == QueryMode.QA and length_target
            else 1
        )

        for attempt in range(1, pass_attempts + 1):
            max_tokens = self._generation_pass_token_budget(
                length_target,
                generator=generator,
                current_words=self._count_words(current_text),
            )
            if max_tokens is None:
                max_tokens = self._default_generation_pass_token_budget(
                    rag_query,
                    generator=generator,
                )

            raw_pass_text = ""
            emitted_visible_text = current_text
            deanonymized_flush_candidate = ""
            if deanonymize_session_id:
                logger.info(
                    "RAG stream incremental deanonymization enabled",
                    route_key=rag_query.route_key,
                    tender_id=rag_query.tender_id,
                    llm_route=llm_route.value,
                    target_id=rag_query.external_target_id,
                    target_provider=rag_query.external_target_provider,
                    session_token=self._mask_session_token(deanonymize_session_id),
                    attempt=attempt,
                    max_tokens=max_tokens,
                )

            async for token in generator.generate_stream(
                template=active_template,
                variables=active_variables,
                temperature=rag_query.temperature,
                max_tokens=max_tokens,
                language=_resolve_query_language(rag_query),
            ):
                raw_pass_text += token
                if not deanonymize_session_id:
                    visible_pass_text = self._sanitize_continuation_text(
                        current_text,
                        raw_pass_text,
                    )
                    visible_full_text = self._merge_completion_suffix(
                        current_text,
                        visible_pass_text,
                    )
                    visible_delta = self._stream_sanitized_delta(
                        emitted_visible_text,
                        visible_full_text,
                    )
                    if visible_delta:
                        yield visible_delta
                    emitted_visible_text = visible_full_text
                    continue

                deanonymized_flush_candidate += token
                if not self._should_flush_deanonymized_stream_chunk(deanonymized_flush_candidate):
                    continue

                visible_pass_text = self._sanitize_continuation_text(
                    current_text,
                    raw_pass_text,
                )
                visible_full_text = self._merge_completion_suffix(
                    current_text,
                    visible_pass_text,
                )
                visible_delta = self._stream_sanitized_delta(
                    emitted_visible_text,
                    visible_full_text,
                )
                if visible_delta:
                    restored = await self._deanonymize_text(
                        visible_delta,
                        deanonymize_session_id,
                    )
                    if restored:
                        yield restored
                    emitted_visible_text = visible_full_text
                deanonymized_flush_candidate = ""

            pass_text = self._sanitize_continuation_text(current_text, raw_pass_text)
            if not pass_text:
                break

            merged_pass_text = self._merge_completion_suffix(current_text, pass_text)
            if deanonymize_session_id:
                visible_delta = self._stream_sanitized_delta(
                    emitted_visible_text,
                    merged_pass_text,
                )
                if visible_delta:
                    restored = await self._deanonymize_text(
                        visible_delta,
                        deanonymize_session_id,
                    )
                    if restored:
                        yield restored

            current_text = merged_pass_text

            if not (rag_query.mode == QueryMode.QA and length_target and target_goal_words):
                break

            current_words = self._count_words(current_text)
            if current_words >= target_goal_words:
                break

            active_template = get_prompt_template_text(
                "qa-continuation",
                _resolve_query_language(rag_query),
            )
            using_continuation_template = True
            active_variables = {
                "query": stream_variables.get(
                    "query",
                    self._query_text_without_length_request(rag_query.text),
                ),
                "context": stream_variables.get("context", context),
                "current_answer_tail": self._continuation_tail(current_text),
                "target_words": length_target.target_words,
            }

        trailing_completion = await self._complete_trailing_sentence_if_needed(
            rag_query,
            generator=generator,
            context=context,
            variables=(
                active_variables
                if current_text and using_continuation_template
                else stream_variables
            ),
            current_text=current_text,
        )
        if trailing_completion:
            completion_chunk = self._merge_completion_suffix("", trailing_completion.text)
            if deanonymize_session_id:
                restored = await self._deanonymize_text(completion_chunk, deanonymize_session_id)
                if restored:
                    yield restored
            else:
                yield completion_chunk

    def _has_external_llm(self, rag_query: RAGQuery | None = None) -> bool:
        if rag_query and rag_query.external_target_url:
            return True
        return bool(settings.external_llm_url.strip())

    def _mask_session_token(self, session_id: str | None) -> str | None:
        if not session_id:
            return None
        return f"{session_id[:8]}..."

    def _should_flush_deanonymized_stream_chunk(self, text: str) -> bool:
        stripped = (text or "").rstrip()
        if not stripped:
            return False
        if self._has_unclosed_placeholder(stripped):
            return False
        if len(stripped) >= DEANONYMIZED_STREAM_FORCE_FLUSH_CHARS:
            return True
        if len(stripped) < DEANONYMIZED_STREAM_FLUSH_CHARS:
            return False
        last_char = stripped[-1]
        if last_char in ".!?:;\n":
            return True
        if last_char in ",)]}\"'":
            return True
        return last_char.isspace()

    def _has_unclosed_placeholder(self, text: str) -> bool:
        last_open = (text or "").rfind("[")
        if last_open < 0:
            return False
        return (text or "").rfind("]") < last_open

    def _stream_sanitized_delta(self, emitted_text: str, sanitized_text: str) -> str:
        if not sanitized_text:
            return ""
        if not emitted_text:
            return sanitized_text
        if sanitized_text.startswith(emitted_text):
            return sanitized_text[len(emitted_text) :]
        return self._strip_continuation_overlap(emitted_text, sanitized_text)

    def _should_buffer_stream_for_quality(self, rag_query: RAGQuery) -> bool:
        if rag_query.mode != QueryMode.QA:
            return False

        if self._query_uses_procedure_guardrails(rag_query):
            return True

        if self._extract_requested_length_target(rag_query.text):
            return False

        return self._query_requests_broad_summary(rag_query.text) and bool(
            TENDER_DOCUMENT_QUERY_RE.search(rag_query.text or "")
        )

    def _anonymizer_circuit_is_open(self) -> bool:
        return time.monotonic() < self._anonymizer_circuit_open_until

    def _record_anonymizer_success(self) -> None:
        if self._anonymizer_failure_count or self._anonymizer_circuit_open_until:
            logger.info(
                "Anonymizer circuit reset",
                previous_failures=self._anonymizer_failure_count,
            )
        self._anonymizer_failure_count = 0
        self._anonymizer_circuit_open_until = 0.0
        self._last_anonymizer_error_reason = None

    def _record_anonymizer_failure(self, *, reason: str) -> None:
        self._anonymizer_failure_count += 1
        self._last_anonymizer_error_reason = reason
        logger.warning(
            "Anonymizer failure recorded",
            failure_count=self._anonymizer_failure_count,
            reason=reason,
        )
        if self._anonymizer_failure_count >= settings.anonymizer_circuit_breaker_threshold:
            if not self._anonymizer_circuit_is_open():
                self._anonymizer_circuit_open_events += 1
            self._anonymizer_circuit_open_until = (
                time.monotonic() + settings.anonymizer_circuit_open_seconds
            )
            logger.warning(
                "Anonymizer circuit opened",
                failure_count=self._anonymizer_failure_count,
                open_for_seconds=settings.anonymizer_circuit_open_seconds,
                reason=reason,
            )

    def get_anonymizer_runtime_stats(self) -> dict[str, Any]:
        return {
            "fallback_events": self._anonymizer_fallback_events,
            "runtime_failure_count": self._anonymizer_failure_count,
            "circuit_open": self._anonymizer_circuit_is_open(),
            "circuit_open_events": self._anonymizer_circuit_open_events,
            "last_error_reason": self._last_anonymizer_error_reason,
        }

    def get_last_privacy_debug_trace(self) -> dict[str, Any] | None:
        if self._last_privacy_debug_trace is None:
            return None
        return dict(self._last_privacy_debug_trace)

    def _truncate_debug_text(self, value: str, *, limit: int = 4000) -> str:
        if len(value) <= limit:
            return value
        return f"{value[:limit]}..."

    def _set_last_privacy_debug_trace(
        self,
        *,
        rag_query: RAGQuery,
        llm_route: LLMRoute,
        anonymizer_enabled: bool,
        anonymized: bool,
        session_id: str | None,
        prompt_variables: dict[str, Any] | None,
        note: str | None = None,
    ) -> None:
        debug_prompt = None
        if isinstance(prompt_variables, dict):
            debug_prompt = {
                key: self._truncate_debug_text(value)
                for key, value in prompt_variables.items()
                if isinstance(value, str) and value.strip()
            }
        self._last_privacy_debug_trace = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mode": rag_query.mode.value,
            "route_key": rag_query.route_key,
            "tender_id": rag_query.tender_id,
            "llm_route": llm_route.value,
            "anonymizer_enabled": anonymizer_enabled,
            "anonymized": anonymized,
            "session_token": self._mask_session_token(session_id),
            "target_id": rag_query.external_target_id,
            "target_provider": rag_query.external_target_provider,
            "target_base_url": rag_query.external_target_url,
            "anonymized_prompt_variables": debug_prompt,
            "note": note,
        }

    def _anonymizer_headers(self) -> dict[str, str]:
        if not settings.anonymizer_admin_token:
            return {}
        return {"x-anonymizer-admin-token": settings.anonymizer_admin_token}

    def _get_external_generator(self, rag_query: RAGQuery) -> Generator:
        base_url = (rag_query.external_target_url or settings.external_llm_url).strip()
        model = (
            rag_query.external_target_model or settings.external_llm_model or settings.llama_model
        )
        provider = (rag_query.external_target_provider or "llama").strip().lower()
        api_key = (rag_query.external_target_api_key or "").strip()
        timeout = (
            rag_query.external_target_timeout_ms / 1000
            if rag_query.external_target_timeout_ms
            else settings.llama_timeout
        )
        cache_key = (base_url, model, int(timeout), provider, api_key)
        generator = self._external_generators.get(cache_key)
        if generator is None:
            generator = Generator(
                base_url=base_url,
                model=model,
                provider=provider,
                api_key=api_key or None,
                timeout=int(timeout),
            )
            self._external_generators[cache_key] = generator
        return generator

    async def _prepare_generation_route(
        self,
        rag_query: RAGQuery,
        variables: dict[str, Any],
    ) -> tuple[Generator, dict[str, Any], LLMRoute, bool, str | None, bool]:
        generator = self.generator
        llm_route = LLMRoute.INTERNAL
        anonymized = False
        deanonymize_session_id: str | None = None
        anonymizer_enabled = (
            rag_query.anonymizer_enabled_override
            if rag_query.anonymizer_enabled_override is not None
            else settings.anonymizer_enabled
        )

        if anonymizer_enabled and self._has_external_llm(rag_query):
            try:
                (
                    anonymized_variables,
                    deanonymize_session_id,
                ) = await self._anonymize_prompt_variables(variables)
                generator = self._get_external_generator(rag_query)
                variables = anonymized_variables
                llm_route = LLMRoute.EXTERNAL_ANONYMIZED
                anonymized = True
                self._set_last_privacy_debug_trace(
                    rag_query=rag_query,
                    llm_route=llm_route,
                    anonymizer_enabled=anonymizer_enabled,
                    anonymized=True,
                    session_id=deanonymize_session_id,
                    prompt_variables=variables,
                    note="external route uses anonymized prompt variables",
                )
            except AnonymizerUnavailableError as exc:
                logger.warning(
                    "Anonymizer unavailable, falling back to internal LLM",
                    route_key=rag_query.route_key,
                    tender_id=rag_query.tender_id,
                    fallback_event=True,
                    anonymizer_used=False,
                    session_token=self._mask_session_token(deanonymize_session_id),
                    target_id=rag_query.external_target_id,
                    target_provider=rag_query.external_target_provider,
                    error=str(exc),
                )
                self._anonymizer_fallback_events += 1
                llm_route = LLMRoute.INTERNAL_FALLBACK
                self._set_last_privacy_debug_trace(
                    rag_query=rag_query,
                    llm_route=llm_route,
                    anonymizer_enabled=anonymizer_enabled,
                    anonymized=False,
                    session_id=deanonymize_session_id,
                    prompt_variables=None,
                    note=f"fallback to internal because anonymizer failed: {exc}",
                )
        else:
            self._set_last_privacy_debug_trace(
                rag_query=rag_query,
                llm_route=llm_route,
                anonymizer_enabled=anonymizer_enabled,
                anonymized=False,
                session_id=None,
                prompt_variables=None,
                note="internal route used; no anonymized prompt generated",
            )

        return (
            generator,
            variables,
            llm_route,
            anonymized,
            deanonymize_session_id,
            anonymizer_enabled,
        )

    async def _anonymize_prompt_variables(
        self,
        variables: dict[str, Any],
    ) -> tuple[dict[str, Any], str | None]:
        string_items = [
            (key, value)
            for key, value in variables.items()
            if isinstance(value, str) and value.strip()
        ]
        if not string_items:
            return variables, None

        anonymized_chunks, session_id = await self._anonymize_chunks(
            [value for _, value in string_items]
        )
        anonymized_variables = dict(variables)
        for (key, _), anonymized_value in zip(string_items, anonymized_chunks, strict=False):
            anonymized_variables[key] = anonymized_value
        return anonymized_variables, session_id

    async def _anonymize_chunks(self, chunks: list[str]) -> tuple[list[str], str]:
        if not settings.anonymizer_url.strip():
            raise AnonymizerUnavailableError("anonymizer url is not configured")
        if self._anonymizer_circuit_is_open():
            raise AnonymizerUnavailableError("anonymizer circuit is open")

        payload = await self._post_to_anonymizer("/v1/anonymize", {"chunks": chunks})

        anonymized_items = payload.get("chunks")
        session_id = payload.get("session_id")
        if not isinstance(anonymized_items, list) or len(anonymized_items) != len(chunks):
            self._record_anonymizer_failure(reason="invalid_chunks_payload")
            raise AnonymizerUnavailableError("anonymizer response has invalid chunks")
        if not isinstance(session_id, str) or not session_id:
            self._record_anonymizer_failure(reason="missing_session_id")
            raise AnonymizerUnavailableError("anonymizer response has no session id")

        anonymized_chunks: list[str] = []
        for item in anonymized_items:
            if not isinstance(item, dict):
                self._record_anonymizer_failure(reason="invalid_chunk_item")
                raise AnonymizerUnavailableError("anonymizer response has invalid chunk item")
            anonymized_text = item.get("anonymized_text")
            if not isinstance(anonymized_text, str):
                self._record_anonymizer_failure(reason="missing_anonymized_text")
                raise AnonymizerUnavailableError("anonymizer chunk has no anonymized_text")
            anonymized_chunks.append(anonymized_text)
        return anonymized_chunks, session_id

    async def _deanonymize_text(self, text: str, session_id: str) -> str:
        if not text.strip() or not session_id or not settings.anonymizer_url.strip():
            return text
        if self._anonymizer_circuit_is_open():
            logger.warning(
                "Deanonymization skipped because anonymizer circuit is open",
                session_token=self._mask_session_token(session_id),
            )
            return text

        try:
            payload = await self._post_to_anonymizer(
                "/v1/deanonymize",
                {"text": text, "session_id": session_id},
            )
        except AnonymizerUnavailableError as exc:
            logger.warning(
                "Deanonymization failed, returning anonymized answer",
                session_token=self._mask_session_token(session_id),
                error=str(exc),
            )
            return text

        restored_text = payload.get("text")
        if not isinstance(restored_text, str):
            self._record_anonymizer_failure(reason="invalid_deanonymize_payload")
            logger.warning(
                "Deanonymization returned invalid payload, returning anonymized answer",
                session_token=self._mask_session_token(session_id),
            )
            return text
        return restored_text if isinstance(restored_text, str) else text

    async def _post_to_anonymizer(
        self,
        path: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        attempts = max(1, settings.anonymizer_max_retries + 1)
        last_error: Exception | None = None

        for attempt in range(1, attempts + 1):
            try:
                async with httpx.AsyncClient(timeout=settings.anonymizer_timeout) as client:
                    response = await client.post(
                        f"{settings.anonymizer_url.rstrip('/')}{path}",
                        json=payload,
                        headers=self._anonymizer_headers(),
                    )
                    response.raise_for_status()
                    response_payload = response.json()
                self._record_anonymizer_success()
                return response_payload
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code
                retriable = status_code in {502, 503, 504} and attempt < attempts
                logger.warning(
                    "Anonymizer HTTP error",
                    path=path,
                    attempt=attempt,
                    retriable=retriable,
                    status_code=status_code,
                )
                last_error = exc
                if retriable:
                    continue
                self._record_anonymizer_failure(reason=f"http_{status_code}")
                break
            except (httpx.TimeoutException, httpx.TransportError, ValueError) as exc:
                retriable = attempt < attempts
                logger.warning(
                    "Anonymizer transport error",
                    path=path,
                    attempt=attempt,
                    retriable=retriable,
                    error=str(exc),
                )
                last_error = exc
                if retriable:
                    continue
                self._record_anonymizer_failure(reason=type(exc).__name__)
                break

        raise AnonymizerUnavailableError("anonymizer request failed") from last_error

    async def _generate(
        self,
        rag_query: RAGQuery,
        context: str,
        *,
        generator: Generator | None = None,
        template: str | None = None,
        variables: dict[str, Any] | None = None,
    ) -> GenerationResult:
        """Generate LLM response based on the query mode."""
        if template is None or variables is None:
            template, variables = self._resolve_template(rag_query, context)

        active_generator = generator or self.generator
        length_target = self._extract_requested_length_target(rag_query.text)
        max_tokens = self._generation_pass_token_budget(
            length_target,
            generator=active_generator,
        )
        if max_tokens is None:
            max_tokens = self._default_generation_pass_token_budget(
                rag_query,
                generator=active_generator,
            )
        return await active_generator.generate(
            template=template,
            variables=variables,
            temperature=rag_query.temperature,
            max_tokens=max_tokens,
            sampler_overrides=rag_query.sampler_overrides,
            language=_resolve_query_language(rag_query),
        )

    def _extract_requested_length_target(self, query_text: str) -> ResponseLengthTarget | None:
        normalized_query = query_text or ""

        word_match = WORD_COUNT_REQUEST_RE.search(normalized_query)
        if word_match:
            try:
                value = int(word_match.group(1))
            except ValueError:
                value = 0
            if value >= 50:
                return ResponseLengthTarget(
                    requested_value=value,
                    requested_unit="words",
                    target_words=value,
                    approximate=False,
                )

        line_match = LINE_COUNT_REQUEST_RE.search(normalized_query)
        if line_match:
            try:
                value = int(line_match.group(1))
            except ValueError:
                value = 0
            if value >= 20:
                return ResponseLengthTarget(
                    requested_value=value,
                    requested_unit="lines",
                    target_words=max(200, value * APPROX_WORDS_PER_LINE),
                    approximate=True,
                )

        return None

    def _query_text_without_length_request(self, query_text: str) -> str:
        cleaned = WORD_COUNT_REQUEST_RE.sub("", query_text or "", count=1)
        cleaned = LINE_COUNT_REQUEST_RE.sub("", cleaned, count=1)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.;:-")
        return cleaned or (query_text or "").strip()

    def _extract_requested_word_count(self, query_text: str) -> int | None:
        length_target = self._extract_requested_length_target(query_text)
        if not length_target:
            return None
        return length_target.target_words

    def _count_words(self, text: str) -> int:
        return len(WORD_RE.findall(text or ""))

    def _minimum_acceptable_word_count(
        self, target_words: int, *, approximate: bool = False
    ) -> int:
        if approximate:
            if target_words >= 4000:
                return max(1200, int(target_words * 0.2))
            if target_words >= 1500:
                return max(700, int(target_words * 0.35))
            return max(240, int(target_words * 0.6))
        if target_words >= 400:
            return max(200, int(target_words * 0.95))
        return max(80, int(target_words * 0.85))

    def _completion_token_budget_for_words(self, target_words: int | None) -> int | None:
        if not target_words:
            return None

        estimated_tokens = int(target_words * 3)
        estimated_tokens = max(
            estimated_tokens,
            getattr(settings, "llama_max_tokens", 256),
        )

        return min(estimated_tokens, 4096)

    def _supports_large_long_form_generation(self, generator: Generator) -> bool:
        provider = (getattr(generator, "provider", "llama") or "llama").strip().lower()
        return provider in {"openrouter", "openai", "anthropic"}

    def _continuation_attempt_budget(self, target_words: int) -> int:
        if target_words <= 0:
            return 0
        return max(3, min(8, math.ceil(target_words / 1200)))

    def _generation_pass_token_budget(
        self,
        length_target: ResponseLengthTarget | None,
        *,
        generator: Generator,
        current_words: int = 0,
    ) -> int | None:
        if not length_target:
            return None

        remaining_words = max(length_target.target_words - current_words, 0)
        total_budget = self._completion_token_budget_for_words(remaining_words)
        if not total_budget:
            return None

        if self._supports_large_long_form_generation(generator):
            return total_budget

        if length_target.target_words >= 500 or length_target.approximate:
            if current_words <= 0:
                return min(total_budget, LONG_FORM_INTERNAL_INITIAL_TOKEN_CAP)
            return min(total_budget, LONG_FORM_INTERNAL_PASS_TOKEN_CAP)

        return total_budget

    def _default_generation_pass_token_budget(
        self,
        rag_query: RAGQuery,
        *,
        generator: Generator,
    ) -> int | None:
        if rag_query.mode != QueryMode.QA:
            return None

        if self._query_requests_structured_tender_overview(rag_query.text):
            if self._supports_large_long_form_generation(generator):
                return max(DETAILED_OVERVIEW_DEFAULT_MAX_TOKENS, 1536)
            return DETAILED_OVERVIEW_DEFAULT_MAX_TOKENS

        if self._query_requests_broad_summary(rag_query.text):
            if self._supports_large_long_form_generation(generator):
                return max(BROAD_SUMMARY_DEFAULT_MAX_TOKENS, 1024)
            return BROAD_SUMMARY_DEFAULT_MAX_TOKENS

        return None

    def _continuation_tail(self, text: str, *, limit: int = 1600) -> str:
        normalized = (text or "").strip()
        if len(normalized) <= limit:
            return normalized
        return normalized[-limit:].lstrip()

    def _normalize_duplicate_block(self, text: str) -> str:
        normalized = re.sub(r"\s+", " ", (text or "").strip().lower())
        return normalized.strip(" ,.;:-")

    def _looks_like_answer_start(self, text: str) -> bool:
        candidate = (text or "").lstrip()
        if not candidate:
            return False
        return not LIKELY_USER_QUERY_START_RE.match(candidate)

    def _strip_prompt_garbage_prefix(self, text: str) -> tuple[str, bool]:
        candidate = (text or "").lstrip()
        if not candidate:
            return "", False

        garbage_count = 0
        for match in PROMPT_GARBAGE_PREFIX_TOKEN_RE.finditer(candidate):
            raw_token = match.group(0)
            normalized = raw_token.strip(PROMPT_GARBAGE_PREFIX_STRIP_CHARS).lower()
            normalized = normalized.replace("’", "'").replace("'s", "s")
            normalized = re.sub(r"[^a-zà-ÿ]+", "", normalized)
            if not normalized or normalized in PROMPT_GARBAGE_PREFIX_TOKENS:
                garbage_count += 1
                continue

            if garbage_count >= 3:
                remainder = candidate[match.start() :].lstrip()
                if self._looks_like_answer_start(remainder):
                    return remainder, True
                return "", True
            return candidate, False

        if garbage_count >= 3:
            return "", True
        return candidate, False

    def _strip_prompt_leakage(self, text: str) -> str:
        cleaned = (text or "").strip()
        cleaned_lines: list[str] = []
        for line in cleaned.splitlines():
            candidate = line.rstrip()
            raw_stripped = candidate.strip()
            if not raw_stripped:
                if cleaned_lines and cleaned_lines[-1]:
                    cleaned_lines.append("")
                continue
            if PROMPT_LEAKAGE_HEADING_RE.match(raw_stripped):
                continue
            if PROMPT_LEAKAGE_LOOP_RE.match(raw_stripped):
                continue
            if PROMPT_OWN_TOKEN_LOOP_RE.match(raw_stripped):
                continue
            if BRACE_ONLY_LINE_RE.match(raw_stripped):
                continue
            if any(pattern.match(raw_stripped) for pattern in PROMPT_LEAKAGE_INSTRUCTION_RES):
                continue

            suffix_trimmed = False
            brace_trimmed = False
            inline_match = PROMPT_LEAKAGE_INLINE_RE.search(candidate)
            if inline_match:
                candidate = candidate[: inline_match.start()].rstrip()
            suffix_match = PROMPT_LEAKAGE_SUFFIX_RE.search(candidate)
            if suffix_match:
                candidate = candidate[: suffix_match.start()].rstrip()
                suffix_trimmed = True
            own_prefix_match = PROMPT_OWN_TOKEN_PREFIX_RE.match(candidate)
            if own_prefix_match:
                candidate = candidate[own_prefix_match.end() :].lstrip()
                suffix_trimmed = True
            brace_suffix_match = DANGLING_CLOSING_BRACE_SUFFIX_RE.search(candidate)
            if brace_suffix_match:
                candidate = candidate[: brace_suffix_match.start()].rstrip()
                brace_trimmed = True
            candidate, garbage_prefix_trimmed = self._strip_prompt_garbage_prefix(candidate)
            if garbage_prefix_trimmed:
                suffix_trimmed = True

            stripped = candidate.strip()
            if not stripped:
                continue
            if (
                (suffix_trimmed or brace_trimmed)
                and candidate[-1] not in TERMINAL_SENTENCE_CHARS
                and self._count_words(candidate) >= 3
            ):
                candidate = f"{candidate.rstrip(' ,;:-')}."

            cleaned_lines.append(candidate)
        return "\n".join(cleaned_lines).strip()

    def _strip_continuation_overlap(self, base_text: str, continuation_text: str) -> str:
        base_tail = self._continuation_tail(base_text, limit=2400)
        continuation = (continuation_text or "").lstrip()
        if not base_tail or not continuation:
            return continuation

        max_overlap = min(len(base_tail), len(continuation), 800)
        for overlap in range(max_overlap, 59, -1):
            if base_tail[-overlap:] == continuation[:overlap]:
                return continuation[overlap:].lstrip()

        return continuation

    def _remove_redundant_continuation_blocks(self, base_text: str, continuation_text: str) -> str:
        recent_blocks = [
            self._normalize_duplicate_block(block)
            for block in re.split(r"\n\s*\n", self._continuation_tail(base_text, limit=3200))
            if self._normalize_duplicate_block(block)
        ]

        kept_blocks: list[str] = []
        for block in re.split(r"\n\s*\n", (continuation_text or "").strip()):
            stripped = block.strip()
            normalized = self._normalize_duplicate_block(stripped)
            if not normalized:
                continue

            duplicate = False
            for existing in recent_blocks:
                if (
                    normalized == existing
                    or normalized in existing
                    or existing in normalized
                    or SequenceMatcher(None, normalized, existing).ratio() >= 0.92
                ):
                    duplicate = True
                    break

            if duplicate:
                continue

            kept_blocks.append(stripped)
            recent_blocks.append(normalized)

        return "\n\n".join(kept_blocks).strip()

    def _remove_length_meta_blocks(self, text: str) -> str:
        kept_blocks: list[str] = []
        for block in re.split(r"\n\s*\n", (text or "").strip()):
            stripped = block.strip()
            if not stripped:
                continue
            if LENGTH_META_PARAGRAPH_RE.search(stripped):
                continue
            kept_blocks.append(stripped)
        return "\n\n".join(kept_blocks).strip()

    def _separate_inline_markdown_sections(self, text: str) -> str:
        separated = INLINE_MARKDOWN_SECTION_AFTER_PUNCT_RE.sub(r"\1\n\n\2", text or "")
        return INLINE_MARKDOWN_SECTION_HEADING_RE.sub(r"\1\n\n\2", separated)

    def _section_heading_key(self, block: str) -> str | None:
        match = BOLD_SECTION_HEADING_RE.match(block or "")
        if not match:
            return None
        heading = re.sub(r"\s+", " ", match.group(1).casefold()).strip(" :.")
        return heading or None

    def _deduplicate_restarted_sections(self, text: str) -> str:
        kept_blocks: list[str] = []
        heading_indexes: dict[str, int] = {}

        for block in re.split(r"\n\s*\n", (text or "").strip()):
            stripped = block.strip()
            if not stripped:
                continue

            heading_key = self._section_heading_key(stripped)
            if not heading_key:
                kept_blocks.append(stripped)
                continue

            previous_index = heading_indexes.get(heading_key)
            if previous_index is None:
                heading_indexes[heading_key] = len(kept_blocks)
                kept_blocks.append(stripped)
                continue

            if len(self._normalize_duplicate_block(stripped)) > len(
                self._normalize_duplicate_block(kept_blocks[previous_index])
            ):
                kept_blocks[previous_index] = stripped

        return "\n\n".join(kept_blocks).strip()

    def _strip_generated_fact_sheet_leakage(self, text: str) -> str:
        lines = (text or "").splitlines()
        first_content_index = next(
            (index for index, line in enumerate(lines) if line.strip()),
            None,
        )
        if first_content_index is None:
            return ""

        first_line = lines[first_content_index].strip()
        if GENERATED_FACT_SHEET_HEADING_RE.match(first_line):
            start_index = first_content_index
            index = first_content_index + 1
        elif GENERATED_FACT_SHEET_FIELD_RE.match(first_line):
            start_index = first_content_index
            index = first_content_index
        else:
            return text

        saw_field = False
        while index < len(lines):
            stripped = lines[index].strip()
            if GENERATED_FACT_SHEET_FIELD_RE.match(stripped):
                saw_field = True
                index += 1
                continue
            if GENERATED_FACT_SHEET_END_RE.match(stripped):
                index += 1
                break
            if not stripped and saw_field:
                index += 1
                break
            if not stripped:
                index += 1
                continue
            break

        if not saw_field:
            return text
        return "\n".join(lines[:start_index] + lines[index:]).strip()

    def _clean_generation_artifacts(self, text: str) -> str:
        cleaned = NON_LATIN_SCRIPT_NOISE_RE.sub("", text or "")
        cleaned = PLURAL_DAY_RE.sub(r"\1 giorni", cleaned)
        for pattern, replacement in _ENGINE_CLEANUP.ocr_replacements:
            cleaned = pattern.sub(replacement, cleaned)
        return re.sub(r"[ \t]{2,}", " ", cleaned).strip()

    def _deduplicate_repeated_paragraphs(self, text: str) -> str:
        return self._remove_redundant_continuation_blocks("", text)

    def _sanitize_continuation_text(self, base_text: str, continuation_text: str) -> str:
        cleaned = self._clean_continuation_text(continuation_text)
        cleaned = self._strip_prompt_leakage(cleaned)
        cleaned = self._separate_inline_markdown_sections(cleaned)
        cleaned = self._deduplicate_restarted_sections(cleaned)
        cleaned = self._remove_length_meta_blocks(cleaned)
        cleaned = self._strip_continuation_overlap(base_text, cleaned)
        cleaned = self._remove_redundant_continuation_blocks(base_text, cleaned)
        return cleaned.strip()

    def _query_requests_math_rendering(self, query_text: str) -> bool:
        return bool(MATH_RENDERING_REQUEST_RE.search(query_text or ""))

    def _fit_context_for_generator(
        self,
        context: str,
        *,
        generator: Generator,
        rag_query: RAGQuery | None = None,
    ) -> str:
        if self._supports_large_long_form_generation(generator):
            return context

        normalized = (context or "").strip()
        context_budget = (
            SUMMARY_LOCAL_CONTEXT_CHAR_BUDGET
            if rag_query and self._query_requests_broad_summary(rag_query.text)
            else LOCAL_CONTEXT_CHAR_BUDGET
        )
        if len(normalized) <= context_budget:
            return normalized

        parts = [part.strip() for part in normalized.split("\n\n---\n\n") if part.strip()]
        if not parts:
            return normalized[:context_budget].rstrip()

        kept_parts: list[str] = []
        current_len = 0
        separator_len = len("\n\n---\n\n")

        for part in parts:
            additional = len(part) if not kept_parts else separator_len + len(part)
            if current_len + additional > context_budget:
                remaining = context_budget - current_len
                if not kept_parts and remaining > 120:
                    kept_parts.append(part[:remaining].rstrip())
                break

            kept_parts.append(part)
            current_len += additional

        fitted = "\n\n---\n\n".join(kept_parts).strip()
        return fitted or normalized[:context_budget].rstrip()

    def _clean_continuation_text(self, text: str) -> str:
        lines = (text or "").strip().splitlines()
        cleaned_lines: list[str] = []
        skipping_meta = True

        for line in lines:
            stripped = line.strip()
            if PROMPT_LEAKAGE_HEADING_RE.match(stripped):
                break
            if PROMPT_LEAKAGE_LOOP_RE.match(stripped):
                break
            if PROMPT_OWN_TOKEN_LOOP_RE.match(stripped):
                break
            if BRACE_ONLY_LINE_RE.match(stripped):
                break
            if skipping_meta and not stripped:
                continue
            if skipping_meta and CONTINUATION_HEADING_RE.match(stripped):
                continue
            if skipping_meta and any(
                stripped.lower().startswith(prefix)
                for prefix in _ENGINE_CLEANUP.continuation_skip_prefixes
            ):
                continue
            skipping_meta = False
            cleaned_lines.append(line)

        return "\n".join(cleaned_lines).strip()

    def _clean_final_answer_text(self, text: str) -> str:
        text = self._strip_prompt_leakage(text)
        text = self._strip_generated_fact_sheet_leakage(text)
        text = self._separate_inline_markdown_sections(text)
        text = self._deduplicate_restarted_sections(text)
        text = self._clean_generation_artifacts(text)
        text = self._remove_length_meta_blocks(text)
        text = self._deduplicate_repeated_paragraphs(text)
        lines = [
            line
            for line in (text or "").strip().splitlines()
            if not CONTINUATION_HEADING_RE.match(line.strip())
            and not PROMPT_LEAKAGE_HEADING_RE.match(line.strip())
        ]
        while lines:
            stripped = lines[-1].strip()
            if not stripped:
                lines.pop()
                continue

            normalized = stripped.lstrip("#").strip()
            if PROMPT_LEAKAGE_LOOP_RE.match(stripped):
                lines.pop()
                continue
            if PROMPT_OWN_TOKEN_LOOP_RE.match(stripped):
                lines.pop()
                continue
            if BRACE_ONLY_LINE_RE.match(stripped):
                lines.pop()
                continue
            if stripped.startswith("#") and len(normalized.split()) <= 8:
                lines.pop()
                continue

            if stripped[-1] not in TERMINAL_SENTENCE_CHARS and not stripped.startswith(
                ("-", "*", "$")
            ):
                lines.pop()
                continue

            break

        return "\n".join(lines).strip()

    def _ends_with_incomplete_sentence_fragment(self, text: str) -> bool:
        normalized = (text or "").rstrip()
        if not normalized:
            return False

        last_line = normalized.splitlines()[-1].strip()
        if (
            not last_line
            or CONTINUATION_HEADING_RE.match(last_line)
            or last_line.startswith(("#", "-", "*", "$"))
        ):
            return False

        trimmed = last_line.rstrip("".join(TERMINAL_SENTENCE_CHARS))
        words = WORD_RE.findall(trimmed.lower())
        if len(words) < 3:
            return False

        return words[-1] in INCOMPLETE_SENTENCE_END_TOKENS

    def _needs_sentence_completion(self, text: str) -> bool:
        normalized = (text or "").rstrip()
        if not normalized:
            return False

        last_line = normalized.splitlines()[-1].strip()
        if not last_line:
            return False
        if CONTINUATION_HEADING_RE.match(last_line):
            return False
        if last_line.startswith(("#", "-", "*", "$")):
            return False
        if last_line[-1] in TERMINAL_SENTENCE_CHARS:
            return self._ends_with_incomplete_sentence_fragment(normalized)

        return len(last_line.split()) >= 3

    def _clean_sentence_completion_text(self, text: str) -> str:
        cleaned = self._clean_continuation_text(text).strip()
        cleaned = self._strip_prompt_leakage(cleaned)
        cleaned = self._remove_length_meta_blocks(cleaned)
        cleaned = cleaned.lstrip(" ,;:-")
        if cleaned and cleaned[-1] not in TERMINAL_SENTENCE_CHARS:
            cleaned = f"{cleaned}."
        return cleaned

    def _merge_completion_suffix(self, base_text: str, suffix: str) -> str:
        base = (base_text or "").rstrip()
        extra = (suffix or "").lstrip()
        if not base:
            return extra
        if not extra:
            return base

        if base.endswith((" ", "\n", "\t", "-", "/", "(", "[", "{", '"', "'")):
            return f"{base}{extra}"
        if re.match(r"^[,.;:!?)}\]»]", extra):
            return f"{base}{extra}"
        return f"{base} {extra}"

    def _merge_sentence_completion_suffix(self, base_text: str, suffix: str) -> str:
        base = (base_text or "").rstrip()
        if self._ends_with_incomplete_sentence_fragment(base):
            base = base.rstrip("".join(TERMINAL_SENTENCE_CHARS)).rstrip()
        return self._merge_completion_suffix(base, suffix)

    async def _complete_trailing_sentence_if_needed(
        self,
        rag_query: RAGQuery,
        *,
        generator: Generator,
        context: str,
        variables: dict[str, Any],
        current_text: str,
    ) -> GenerationResult | None:
        if rag_query.mode != QueryMode.QA or not self._needs_sentence_completion(current_text):
            return None

        logger.info(
            "Completing trailing sentence after long-form generation",
            mode=rag_query.mode.value,
            current_words=self._count_words(current_text),
        )

        completion_result = await generator.generate(
            template=get_prompt_template_text(
                "qa-sentence-closure",
                _resolve_query_language(rag_query),
            ),
            variables={
                "query": variables.get(
                    "query", self._query_text_without_length_request(rag_query.text)
                ),
                "context": variables.get("context", context),
                "current_answer_tail": self._continuation_tail(current_text, limit=1200),
            },
            temperature=min(rag_query.temperature, 0.2),
            max_tokens=96,
            sampler_overrides=rag_query.sampler_overrides,
            language=_resolve_query_language(rag_query),
        )

        cleaned_text = self._clean_sentence_completion_text(completion_result.text)
        if not cleaned_text:
            return None

        return replace(completion_result, text=cleaned_text)

    def _query_requests_expanded_explanation(self, query_text: str) -> bool:
        return bool(EXPANDED_EXPLANATION_QUERY_RE.search(query_text or ""))

    def _query_requests_broad_summary(self, query_text: str) -> bool:
        normalized_query = self._query_text_without_length_request(query_text or "")
        if GENERIC_TENDER_DEFINITION_QUERY_RE.search(
            normalized_query
        ) and GENERIC_TENDER_INDEFINITE_RE.search(normalized_query):
            return False
        if GENERIC_TENDER_CONCEPT_RE.search(normalized_query):
            return False
        return bool(
            (
                SUMMARY_INTENT_QUERY_RE.search(normalized_query)
                or STRUCTURED_OVERVIEW_QUERY_RE.search(normalized_query)
            )
            and TENDER_DOCUMENT_QUERY_RE.search(normalized_query)
        )

    def _query_requests_structured_tender_overview(self, query_text: str) -> bool:
        normalized_query = self._query_text_without_length_request(query_text or "")
        return bool(
            STRUCTURED_OVERVIEW_QUERY_RE.search(normalized_query)
            and TENDER_DOCUMENT_QUERY_RE.search(normalized_query)
        )

    def _query_requests_longform_tender_synthesis(self, rag_query: RAGQuery) -> bool:
        if rag_query.mode != QueryMode.QA:
            return False
        length_target = self._extract_requested_length_target(rag_query.text)
        if not length_target or length_target.target_words < LONGFORM_TENDER_SYNTHESIS_MIN_WORDS:
            return False
        return self._query_requests_broad_summary(rag_query.text)

    def _query_uses_procedure_guardrails(self, rag_query: RAGQuery) -> bool:
        cfg = normalize_guardrail_config(rag_query.guardrail_config)
        if not cfg["enabled"]:
            return False
        if rag_query.mode != QueryMode.QA:
            return False
        if cfg["onlyTenderOverview"]:
            return self._query_requests_broad_summary(rag_query.text)
        return bool(TENDER_DOCUMENT_QUERY_RE.search(rag_query.text or ""))

    def _apply_generation_guardrails(
        self,
        rag_query: RAGQuery,
        *,
        context: str,
        answer: str,
    ) -> str:
        if not self._query_uses_procedure_guardrails(rag_query):
            return answer

        fact_sheet = fact_sheet_from_guarded_context(context)
        if fact_sheet is None:
            return answer

        missing_slots = fact_sheet_missing_critical_slots(fact_sheet)
        if missing_slots:
            logger.warning(
                "RAG fact sheet missing critical slots",
                missing_slots=missing_slots,
                procedure_label=fact_sheet.procedure_label,
            )

        active_profiles = self._active_profiles_for_query(rag_query.text)
        result = validate_guarded_answer(
            answer=answer,
            fact_sheet=fact_sheet,
            guarded=True,
            query=rag_query.text,
            config=rag_query.guardrail_config,
            allowed_procedure_labels=source_procedure_labels_from_guarded_context(context),
            active_profiles=active_profiles,
        )
        if result.status in {"AUDIT", "BLOCK"}:
            logger.warning(
                "RAG guarded answer validation failed",
                status=result.status,
                failures=result.failures,
                procedure_label=fact_sheet.procedure_label,
            )
        if result.status == "BLOCK":
            repaired_answer = repair_unsupported_protected_facts(answer, fact_sheet)
            if repaired_answer != answer:
                repaired_result = validate_guarded_answer(
                    answer=repaired_answer,
                    fact_sheet=fact_sheet,
                    guarded=True,
                    query=rag_query.text,
                    config=rag_query.guardrail_config,
                    allowed_procedure_labels=source_procedure_labels_from_guarded_context(context),
                    active_profiles=active_profiles,
                )
                if repaired_result.status != "BLOCK":
                    logger.warning(
                        "RAG guarded answer repaired",
                        original_failures=result.failures,
                        repaired_status=repaired_result.status,
                        procedure_label=fact_sheet.procedure_label,
                    )
                    return repaired_result.safe_answer
                critical, soft = classify_guardrail_failures(repaired_result.failures)
                if not critical and soft:
                    logger.warning(
                        "RAG guarded answer soft-failure fallback",
                        original_failures=result.failures,
                        repaired_failures=repaired_result.failures,
                        procedure_label=fact_sheet.procedure_label,
                    )
                    return self._append_guardrail_soft_warning(
                        repaired_answer,
                        language=_resolve_query_language(rag_query),
                    )
                logger.warning(
                    "RAG guarded answer repair still failed",
                    original_failures=result.failures,
                    repaired_failures=repaired_result.failures,
                    repaired_issue_snippets=guardrail_issue_snippets(repaired_answer),
                    procedure_label=fact_sheet.procedure_label,
                )
            else:
                critical, soft = classify_guardrail_failures(result.failures)
                if not critical and soft:
                    logger.warning(
                        "RAG guarded answer soft-failure fallback (no repair changes)",
                        failures=result.failures,
                        procedure_label=fact_sheet.procedure_label,
                    )
                    return self._append_guardrail_soft_warning(
                        answer,
                        language=_resolve_query_language(rag_query),
                    )
                logger.warning(
                    "RAG guarded answer repair made no changes",
                    failures=result.failures,
                    issue_snippets=guardrail_issue_snippets(answer),
                    procedure_label=fact_sheet.procedure_label,
                )
            return self._build_guardrail_blocked_answer(
                fact_sheet,
                language=_resolve_query_language(rag_query),
            )
        return result.safe_answer

    @staticmethod
    def _append_guardrail_soft_warning(
        answer: str,
        *,
        language: str | None = None,
    ) -> str:
        warning = get_guardrail_messages(language).soft_warning
        text = (answer or "").rstrip()
        if not text:
            return warning
        if warning in text:
            return text
        return f"{text}\n\n{warning}"

    def _build_guardrail_blocked_answer(
        self,
        fact_sheet: FactSheet,
        *,
        language: str | None = None,
    ) -> str:
        messages = get_guardrail_messages(language)

        def values_or_missing(
            values: tuple[str, ...],
            *,
            conflict_key: str | None = None,
            prefix: str = "",
        ) -> str:
            if conflict_key and conflict_key in fact_sheet.conflicts:
                return messages.conflict_detected
            if not values:
                return messages.not_detected
            return ", ".join(f"{prefix}{value}" for value in values)

        return "\n".join(
            [
                BLOCKED_OUTPUT_MESSAGE,
                "",
                messages.blocked_intro,
                "",
                messages.fact_sheet_heading,
                f"- {messages.procedure_label}: "
                f"{fact_sheet.procedure_label or messages.not_detected}",
                f"- {messages.procedure_id_label}: "
                f"{values_or_missing(fact_sheet.procedure_ids, conflict_key='procedure_id')}",
                f"- {messages.cig_label}: "
                f"{values_or_missing(fact_sheet.cigs, conflict_key='cig', prefix='CIG ')}",
                f"- {messages.critical_days_label}: "
                f"{values_or_missing(fact_sheet.critical_days)}",
                f"- {messages.duration_label}: "
                f"{values_or_missing(fact_sheet.durations)}",
                f"- {messages.amounts_label}: "
                f"{values_or_missing(fact_sheet.amounts)}",
                f"- {messages.locations_label}: "
                f"{values_or_missing(fact_sheet.locations)}",
                f"- {messages.percentages_label}: "
                f"{values_or_missing(fact_sheet.percentages)}",
                f"- {messages.sources_label}: "
                f"{values_or_missing(fact_sheet.source_ids)}",
            ]
        )

    def _format_fact_sheet_values(
        self,
        values: tuple[str, ...],
        *,
        conflict_key: str | None,
        conflicts: tuple[str, ...],
        prefix: str = "",
    ) -> str:
        if conflict_key and conflict_key in conflicts:
            return _ENGINE_MESSAGES.fact_sheet_value_conflict_detected
        if not values:
            return _ENGINE_MESSAGES.fact_sheet_value_not_detected
        return ", ".join(f"{prefix}{value}" for value in values)

    def _effective_final_top_k(self, rag_query: RAGQuery) -> int:
        requested_top_k = rag_query.top_k or settings.rag_top_k_final
        if rag_query.mode in {
            QueryMode.QA,
            QueryMode.SEARCH,
        } and self._query_requests_structured_tender_overview(rag_query.text):
            return max(requested_top_k, DETAILED_OVERVIEW_TOP_K_FINAL)
        if rag_query.mode in {
            QueryMode.QA,
            QueryMode.SEARCH,
        } and self._query_requests_broad_summary(rag_query.text):
            return max(requested_top_k, BROAD_SUMMARY_TOP_K_FINAL)
        return requested_top_k

    def _effective_retrieval_top_k(self, rag_query: RAGQuery) -> int | None:
        requested_retrieval_top_k = rag_query.retrieval_top_k
        if rag_query.mode in {
            QueryMode.QA,
            QueryMode.SEARCH,
        } and self._query_requests_structured_tender_overview(rag_query.text):
            base_top_k = requested_retrieval_top_k or settings.rag_top_k_dense
            return max(base_top_k, DETAILED_OVERVIEW_RETRIEVAL_TOP_K)
        if requested_retrieval_top_k is not None:
            return requested_retrieval_top_k
        return None

    def _query_text_for_retrieval(self, query_text: str) -> str:
        normalized_query = self._query_text_without_length_request(query_text or "")
        if not self._query_requests_broad_summary(normalized_query):
            return normalized_query

        stripped = RETRIEVAL_INTENT_STRIP_RE.sub(" ", normalized_query)
        stripped = RETRIEVAL_STOPWORD_STRIP_RE.sub(" ", stripped)
        stripped = re.sub(r"\s+", " ", stripped).strip(" ,.;:-")
        return stripped or normalized_query

    def _retrieval_variant_language_for(self, query_text: str) -> str:
        normalized_query = self._query_text_without_length_request(query_text or "").casefold()
        markers = _ENGINE_LANG_MARKERS
        english_score = sum(
            1 for marker in markers.english_markers if marker in normalized_query
        )
        italian_score = sum(
            1 for marker in markers.italian_markers if marker in normalized_query
        )
        return "en" if english_score > italian_score else "it"

    def _requested_procedure_labels_for_retrieval(self, query_text: str) -> set[str]:
        normalized_query = self._query_text_without_length_request(query_text or "").casefold()
        requested: set[str] = set()
        for label, anchors in PROCEDURE_ANCHORS.items():
            markers = (label, *anchors)
            if any(str(marker or "").casefold() in normalized_query for marker in markers):
                requested.add(label)
        return requested

    def _retrieval_variant_procedure_labels(self, variant: str) -> set[str]:
        normalized_variant = str(variant or "").casefold()
        return {label for label in PROCEDURE_ANCHORS if label.casefold() in normalized_variant}

    def _retrieval_queries_for(
        self,
        query_text: str,
        *,
        primary_query: str | None = None,
        active_profiles: tuple[ProcedureProfile, ...] | None = None,
    ) -> tuple[str, ...]:
        primary = primary_query or self._query_text_for_retrieval(query_text)
        queries = [primary]
        seen = {primary.casefold()}

        if not self._query_requests_broad_summary(query_text):
            return tuple(queries)

        language = self._retrieval_variant_language_for(query_text)
        try:
            variants = list(
                load_retrieval_query_variants(
                    "retrieval-critical-coverage", language=language
                )
            )
        except Exception as e:  # noqa: BLE001 — asset optional
            logger.warning("Critical retrieval prompt asset unavailable", error=str(e))
            variants = []

        from app.rag.procedure_profiles import (
            active_critical_coverage_queries,
            resolve_active_profiles,
        )

        profiles = active_profiles
        if profiles is None:
            profiles = resolve_active_profiles(
                query_text,
                chunk_texts=(),
                explicit_profile_ids=tuple(getattr(self, "_pending_profile_ids", ())),
            )
        variants.extend(active_critical_coverage_queries(profiles, language=language))

        for variant in variants:
            normalized = variant.casefold()
            if normalized in seen:
                continue
            seen.add(normalized)
            queries.append(variant)
        return tuple(queries)

    def _build_response_constraints(self, rag_query: RAGQuery) -> str:
        length_target = self._extract_requested_length_target(rag_query.text)
        language = _resolve_query_language(rag_query)
        templates = get_engine_response_constraints(language)
        unit_messages = get_engine_messages(language)
        constraints: list[str] = list(templates.general)

        if length_target:
            min_words = self._minimum_acceptable_word_count(
                length_target.target_words,
                approximate=length_target.approximate,
            )
            max_words = max(
                length_target.target_words + 100,
                int(length_target.target_words * 1.1),
            )
            unit_label = (
                unit_messages.length_unit_lines
                if length_target.requested_unit == "lines"
                else unit_messages.length_unit_words
            )
            requested_label = f"{length_target.requested_value} {unit_label}"
            constraints.extend(
                template.format(
                    requested_label=requested_label,
                    min_words=min_words,
                    max_words=max_words,
                    target_words=length_target.target_words,
                )
                for template in templates.length_target_templates
            )
            if length_target.requested_unit == "lines":
                constraints.extend(templates.lines_mode)
        else:
            constraints.extend(templates.no_length_target)
        if self._query_requests_expanded_explanation(rag_query.text):
            constraints.extend(templates.expanded_explanation)
        if self._query_requests_broad_summary(rag_query.text):
            constraints.extend(templates.broad_summary)
        if self._query_requests_structured_tender_overview(rag_query.text):
            heading = templates.structured_overview_heading[0]
            sections_block = "\n".join(templates.structured_overview_sections)
            constraints.append(f"{heading}\n{sections_block}")
            constraints.extend(templates.structured_overview)

        if self._query_requests_math_rendering(rag_query.text):
            constraints.extend(templates.math_rendering)

        return "\n".join(f"- {constraint}" for constraint in constraints)

    async def _extend_answer_if_needed(
        self,
        rag_query: RAGQuery,
        *,
        generator: Generator,
        context: str,
        variables: dict[str, Any],
        generation_result: GenerationResult,
    ) -> GenerationResult:
        if rag_query.mode != QueryMode.QA:
            return generation_result

        length_target = self._extract_requested_length_target(rag_query.text)
        if not length_target:
            return generation_result

        goal_words = (
            length_target.target_words
            if self._supports_large_long_form_generation(generator)
            else self._minimum_acceptable_word_count(
                length_target.target_words,
                approximate=length_target.approximate,
            )
        )
        current_text = self._deduplicate_repeated_paragraphs(
            self._strip_prompt_leakage(generation_result.text)
        ).strip()
        if current_text != generation_result.text:
            generation_result = replace(generation_result, text=current_text)
        current_words = self._count_words(current_text)
        if current_words >= goal_words:
            return generation_result

        logger.info(
            "Extending QA answer to satisfy requested length",
            requested_unit=length_target.requested_unit,
            requested_value=length_target.requested_value,
            target_words=length_target.target_words,
            current_words=current_words,
            goal_words=goal_words,
        )

        for attempt in range(1, self._continuation_attempt_budget(length_target.target_words) + 1):
            remaining_words = max(goal_words - current_words, 0)
            if remaining_words <= 0:
                break

            continuation_result = await generator.generate(
                template=get_prompt_template_text(
                    "qa-continuation",
                    _resolve_query_language(rag_query),
                ),
                variables={
                    "query": variables.get("query", rag_query.text),
                    "context": variables.get("context", context),
                    "current_answer_tail": self._continuation_tail(current_text),
                    "target_words": length_target.target_words,
                },
                temperature=rag_query.temperature,
                max_tokens=self._generation_pass_token_budget(
                    length_target,
                    generator=generator,
                    current_words=current_words,
                ),
                sampler_overrides=rag_query.sampler_overrides,
                language=_resolve_query_language(rag_query),
            )

            continuation_text = self._sanitize_continuation_text(
                current_text,
                continuation_result.text,
            )
            if not continuation_text:
                break

            current_text = f"{current_text}\n\n{continuation_text}".strip()
            current_words = self._count_words(current_text)

            logger.info(
                "QA answer extension complete",
                attempt=attempt,
                current_words=current_words,
                target_words=length_target.target_words,
            )

            generation_result = replace(
                generation_result,
                text=current_text,
                completion_tokens=(
                    (generation_result.completion_tokens or 0)
                    + (continuation_result.completion_tokens or 0)
                )
                or generation_result.completion_tokens,
            )

            if current_words >= goal_words:
                break

        return generation_result

    def _resolve_template(self, rag_query: RAGQuery, context: str) -> tuple[str, dict]:
        """Resolve the prompt template and variables for a given query mode."""
        mode = rag_query.mode

        if mode == QueryMode.QA:
            query_text = self._query_text_without_length_request(rag_query.text)
            if self._query_requests_longform_tender_synthesis(rag_query):
                return "tender_longform_synthesis", {
                    "context": context,
                    "query": query_text,
                    "response_constraints": self._build_response_constraints(rag_query),
                }
            if self._query_uses_procedure_guardrails(rag_query):
                return "tender_overview", {
                    "context": context,
                    "query": query_text,
                    "response_constraints": self._build_response_constraints(rag_query),
                }
            return "general_qa", {
                "context": context,
                "query": query_text,
                "response_constraints": self._build_response_constraints(rag_query),
            }

        elif mode == QueryMode.WRITE_SECTION:
            return "proposal_section", {
                "context": context,
                "section_title": rag_query.section_title,
                "instructions": rag_query.instructions or rag_query.text,
                "requirements": rag_query.requirements,
            }

        elif mode == QueryMode.EXEC_SUMMARY:
            return "executive_summary", {
                "sections": rag_query.sections,
                "context": context,
                "requirements": rag_query.requirements,
            }

        elif mode == QueryMode.ANALYZE_REQS:
            return "requirement_analyzer", {
                "document_text": rag_query.document_text or rag_query.text,
            }

        elif mode == QueryMode.COMPLIANCE:
            return "compliance_checker", {
                "requirement": rag_query.requirements,
                "section_content": rag_query.section_content,
                "context": context,
            }

        else:
            return "general_qa", {
                "context": context,
                "query": self._query_text_without_length_request(rag_query.text),
                "response_constraints": self._build_response_constraints(rag_query),
            }

    # ──────────────────────────────────────────────
    # Ingestion helpers
    # ──────────────────────────────────────────────

    def chunk_and_embed(
        self,
        text: str,
        metadata: ChunkMetadata | None = None,
    ) -> list[TextChunk]:
        """Chunk a document and prepare it for indexing."""
        if not self._initialized or not self.chunker:
            raise RuntimeError("HybridRAG Engine not initialized yet.")
        return self.chunker.chunk_text(text, metadata)

    def index_chunks(
        self,
        chunks: list[TextChunk],
        collection: str = "documents",
    ) -> list[str]:
        """Index chunks into the dense retriever (Qdrant)."""
        if not self._initialized or not self.dense_retriever or not self.sparse_retriever:
            raise RuntimeError("HybridRAG Engine not initialized yet.")
        texts = [c.text for c in chunks]
        metadatas = [c.metadata.__dict__ for c in chunks]

        # Index in dense retriever
        point_ids = self.dense_retriever.index_chunks(texts, metadatas, collection)

        # Add to sparse retriever
        self.sparse_retriever.add_chunks(texts, metadatas)

        return point_ids

    async def shutdown(self):
        """Gracefully shutdown all components."""
        logger.info("Shutting down HybridRAG Engine...")
        if self.dense_retriever:
            await self.dense_retriever.shutdown()
        if self.graph_retriever:
            await self.graph_retriever.shutdown()
        self._initialized = False
        logger.info("HybridRAG Engine shut down")

    BROKEN_NUMERIC_PATTERNS = _ENGINE_CLEANUP.broken_numeric_patterns
    CRITICAL_NUMERIC_PATTERNS = _ENGINE_CLEANUP.critical_numeric_patterns

    def _pin_critical_chunks(
        self,
        chunks: list[dict],
    ) -> tuple[list[dict], list[dict]]:
        """Separate pinned (critical data) chunks from MMR candidates."""
        pinned, candidates = [], []
        for chunk in chunks:
            text = chunk.get("text", "")
            is_critical = any(
                pattern.search(text) for pattern in self.CRITICAL_NUMERIC_PATTERNS
            )
            if is_critical:
                pinned.append(chunk)
            else:
                candidates.append(chunk)
        return pinned, candidates

    def _remove_duplicate_paragraphs(
        self,
        text: str,
        similarity_threshold: float = 0.85,
    ) -> str:
        """Remove near-duplicate paragraphs using Jaccard similarity."""
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        unique = []
        for para in paragraphs:
            tokens_new = set(para.lower().split())
            is_duplicate = False
            for accepted in unique:
                tokens_acc = set(accepted.lower().split())
                intersection = tokens_new & tokens_acc
                union = tokens_new | tokens_acc
                if union and len(intersection) / len(union) >= similarity_threshold:
                    is_duplicate = True
                    break
            if not is_duplicate:
                unique.append(para)
        return "\n\n".join(unique)

    def _has_broken_numeric_patterns(self, text: str) -> bool:
        return any(pattern.search(text) for pattern in self.BROKEN_NUMERIC_PATTERNS)
