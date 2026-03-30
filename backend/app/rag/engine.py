"""
TenderWriter — HybridRAG Engine Orchestrator

The main engine that coordinates all retrieval strategies (dense, sparse, graph),
fuses results, re-ranks them, and generates responses using a local LLM.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
import math
import re
import time
from typing import Any, AsyncIterator

import httpx
import structlog

from app.config import settings
from app.rag.chunker import SemanticChunker, ChunkMetadata, TextChunk
from app.rag.dense_retriever import DenseRetriever
from app.rag.embedder import Embedder, get_embedder
from app.rag.fusion import RankFusion
from app.rag.generator import Generator, GenerationResult
from app.rag.graph_retriever import GraphRetriever
from app.rag.reranker import Reranker
from app.rag.sparse_retriever import SparseRetriever

logger = structlog.get_logger()

WORD_COUNT_REQUEST_RE = re.compile(
    r"\b(\d{2,5})\s+(?:parole|words|palabras)\b",
    re.IGNORECASE,
)
LINE_COUNT_REQUEST_RE = re.compile(
    r"\b(\d{2,5})\s+(?:righe|riga|linee|line|lines|lineas|líneas)\b",
    re.IGNORECASE,
)
WORD_RE = re.compile(r"\b[\wÀ-ÿ]+\b", re.UNICODE)
CONTINUATION_HEADING_RE = re.compile(
    r"^\s*(?:#{1,6}\s*)?(?:continuazione|continuation|proseguimento)\b.*$",
    re.IGNORECASE,
)
APPROX_WORDS_PER_LINE = 8
LONG_FORM_PASS_TOKEN_CAP = 768

QA_CONTINUATION_PROMPT = """ISTRUZIONI IMPORTANTI:
- Devi rispondere nella STESSA LINGUA della domanda dell'utente.
- Stai continuando una risposta gia iniziata.
- Non ricominciare dall'inizio.
- Non ripetere sezioni o frasi gia scritte.
- Non commentare la lunghezza della risposta.
- Non scrivere titoli o frasi come "Continuazione della risposta".
- {length_instruction}

## User Question
{query}

## Retrieved Context
{context}

## Draft Ending
{current_answer_tail}

## Task
Scrivi solo la continuazione della risposta, iniziando direttamente con il contenuto mancante in modo fluido e coerente con il draft gia presente.
"""


class QueryMode(str, Enum):
    """Different query modes for the RAG pipeline."""
    SEARCH = "search"                  # Retrieve only, no generation
    QA = "qa"                          # General question answering
    WRITE_SECTION = "write_section"    # Generate a proposal section
    EXEC_SUMMARY = "exec_summary"     # Generate executive summary
    ANALYZE_REQS = "analyze_reqs"     # Analyze tender requirements
    COMPLIANCE = "compliance"          # Check compliance


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
    # Additional context for specific modes
    section_title: str = ""
    instructions: str = ""
    requirements: str = ""
    sections: str = ""
    section_content: str = ""
    document_text: str = ""
    temperature: float = 0.3
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
    """Normalized user-requested answer length."""

    requested_value: int
    requested_unit: str
    target_words: int
    approximate: bool = False


@dataclass(frozen=True)
class RetrievedContext:
    """Shared retrieval payload used by sync and streaming flows."""

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
                    logger.warning("Dense retriever init failed (Qdrant may be unavailable)", error=str(e))

                # Sparse retriever (BM25)
                self.sparse_retriever = SparseRetriever()

                # Graph retriever (Neo4j)
                self.graph_retriever = GraphRetriever()
                try:
                    await self.graph_retriever.initialize()
                except Exception as e:
                    logger.warning("Graph retriever init failed (Neo4j may be unavailable)", error=str(e))

                # Fusion
                self.fusion = RankFusion()

                # Re-ranker
                self.reranker = Reranker()

                # Generator (Llama Server)
                self.generator = Generator(
                    base_url=settings.llama_server_url,
                    model=settings.llama_model,
                    timeout=settings.llama_timeout
                )

                self._initialized = True
                logger.info("HybridRAG Engine initialized successfully")
            except Exception:
                self._initialization_task = None
                raise

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
                fallback_answer = "Il modello e temporaneamente non disponibile. Mostro solo le fonti recuperate."
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

        generation_result = replace(
            generation_result,
            text=self._clean_final_answer_text(generation_result.text),
        )

        if deanonymize_session_id:
            generation_result = replace(
                generation_result,
                text=await self._deanonymize_text(
                    generation_result.text,
                    deanonymize_session_id,
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
        await self.ensure_initialized()
        retrieved = await self._retrieve_context_and_sources(rag_query)
        context = retrieved.context
        length_target = self._extract_requested_length_target(rag_query.text)
        stream_max_tokens = self._generation_pass_token_budget(length_target)

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

        if llm_route == LLMRoute.EXTERNAL_ANONYMIZED and deanonymize_session_id:
            logger.info(
                "RAG stream buffered for deanonymization",
                route_key=rag_query.route_key,
                tender_id=rag_query.tender_id,
                llm_route=llm_route.value,
                target_id=rag_query.external_target_id,
                target_provider=rag_query.external_target_provider,
                session_token=self._mask_session_token(deanonymize_session_id),
            )
            buffered_tokens: list[str] = []
            async for token in generator.generate_stream(
                template=template,
                variables=stream_variables,
                temperature=rag_query.temperature,
                max_tokens=stream_max_tokens,
            ):
                buffered_tokens.append(token)
            restored = await self._deanonymize_text("".join(buffered_tokens), deanonymize_session_id)
            if restored:
                yield restored
            return

        async for token in generator.generate_stream(
            template=template,
            variables=stream_variables,
            temperature=rag_query.temperature,
            max_tokens=stream_max_tokens,
        ):
            yield token

    async def _retrieve_context_and_sources(
        self,
        rag_query: RAGQuery,
    ) -> RetrievedContext:
        retrieval_query = self._query_text_without_length_request(rag_query.text)

        dense_results = []
        sparse_results = []
        graph_results = []

        try:
            raw_dense = self.dense_retriever.search(
                query=retrieval_query,
                top_k=rag_query.top_k or settings.rag_top_k_dense,
                filters=rag_query.filters,
            )
            dense_results = [
                {"text": r.text, "score": r.score, "metadata": r.metadata}
                for r in raw_dense
            ]
        except Exception as e:
            logger.warning("Dense retrieval failed", error=str(e))

        try:
            raw_sparse = self.sparse_retriever.search(
                query=retrieval_query,
                top_k=rag_query.top_k or settings.rag_top_k_sparse,
                filters=rag_query.filters,
            )
            sparse_results = [
                {"text": r.text, "score": r.score, "metadata": r.metadata}
                for r in raw_sparse
            ]
        except Exception as e:
            logger.warning("Sparse retrieval failed", error=str(e))

        try:
            raw_graph = await self.graph_retriever.search(
                query=retrieval_query,
                top_k=rag_query.top_k or settings.rag_top_k_graph,
                filters=rag_query.filters,
            )
            graph_results = [
                {"text": r.text, "score": r.score, "metadata": r.metadata}
                for r in raw_graph
            ]
        except Exception as e:
            logger.warning("Graph retrieval failed", error=str(e))

        fused = self.fusion.fuse(
            dense_results=dense_results,
            sparse_results=sparse_results,
            graph_results=graph_results,
            top_k=20,
        )

        top_k_final = rag_query.top_k or settings.rag_top_k_final
        reranked = []
        if fused:
            try:
                fused_dicts = [
                    {"text": f.text, "score": f.score, "metadata": f.metadata, "sources": f.sources}
                    for f in fused
                ]
                reranked = self.reranker.rerank(
                    query=retrieval_query,
                    results=fused_dicts,
                    top_k=top_k_final,
                )
            except Exception as e:
                logger.warning("Re-ranking failed, using fusion order", error=str(e))
                reranked = fused[:top_k_final]

        context_texts = []
        sources = []
        for r in reranked:
            text = r.text if hasattr(r, "text") else r.get("text", "")
            metadata = r.metadata if hasattr(r, "metadata") else r.get("metadata", {})
            context_texts.append(text)
            sources.append({
                "text": text[:200] + "..." if len(text) > 200 else text,
                "score": r.score if hasattr(r, "score") else r.get("score", 0),
                "metadata": metadata,
            })

        return RetrievedContext(
            context="\n\n---\n\n".join(context_texts),
            sources=sources,
        )

    def _has_external_llm(self, rag_query: RAGQuery | None = None) -> bool:
        if rag_query and rag_query.external_target_url:
            return True
        return bool(settings.external_llm_url.strip())

    def _mask_session_token(self, session_id: str | None) -> str | None:
        if not session_id:
            return None
        return f"{session_id[:8]}..."

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
        if (
            self._anonymizer_failure_count
            >= settings.anonymizer_circuit_breaker_threshold
        ):
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
        model = rag_query.external_target_model or settings.external_llm_model or settings.llama_model
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
                anonymized_variables, deanonymize_session_id = await self._anonymize_prompt_variables(
                    variables
                )
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
        for (key, _), anonymized_value in zip(string_items, anonymized_chunks):
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
        return await active_generator.generate(
            template=template,
            variables=variables,
            temperature=rag_query.temperature,
            max_tokens=self._generation_pass_token_budget(length_target),
        )

    def _extract_requested_length_target(
        self,
        query_text: str,
    ) -> ResponseLengthTarget | None:
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
                    target_words=max(50, value * APPROX_WORDS_PER_LINE),
                    approximate=True,
                )

        return None

    def _extract_requested_word_count(self, query_text: str) -> int | None:
        length_target = self._extract_requested_length_target(query_text)
        return length_target.target_words if length_target else None

    def _length_target_requested_label(self, length_target: ResponseLengthTarget) -> str:
        if length_target.requested_unit == "lines":
            return f"{length_target.requested_value} righe"
        return f"{length_target.requested_value} parole"

    def _length_target_instruction(self, length_target: ResponseLengthTarget) -> str:
        if length_target.requested_unit == "lines":
            return (
                "Continua finche la risposta diventa il piu estesa e dettagliata possibile, "
                f"avvicinandoti al target di circa {length_target.requested_value} righe "
                f"(equivalenti a circa {length_target.target_words} parole)."
            )
        return (
            "Continua fino a raggiungere complessivamente circa "
            f"{length_target.target_words} parole."
        )

    def _query_text_without_length_request(self, query_text: str) -> str:
        cleaned = WORD_COUNT_REQUEST_RE.sub("", query_text or "", count=1)
        cleaned = LINE_COUNT_REQUEST_RE.sub("", cleaned, count=1)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.;:-")
        return cleaned or (query_text or "").strip()

    def _count_words(self, text: str) -> int:
        return len(WORD_RE.findall(text or ""))

    def _minimum_acceptable_word_count(
        self,
        target_words: int,
        *,
        approximate: bool = False,
    ) -> int:
        if approximate:
            if target_words >= 4000:
                return max(800, int(target_words * 0.1))
            if target_words >= 1500:
                return max(600, int(target_words * 0.25))
            return max(160, int(target_words * 0.6))
        if target_words >= 400:
            return max(200, int(target_words * 0.95))
        return max(80, int(target_words * 0.85))

    def _continuation_attempt_budget(self, target_words: int) -> int:
        if target_words <= 0:
            return 0
        return max(3, min(8, math.ceil(target_words / 1200)))

    def _completion_token_budget_for_words(self, target_words: int | None) -> int | None:
        if not target_words:
            return None

        estimated_tokens = int(target_words * 3)
        if target_words >= 800:
            estimated_tokens = max(estimated_tokens, 3072)
        elif target_words >= 500:
            estimated_tokens = max(estimated_tokens, 2048)
        elif target_words >= 250:
            estimated_tokens = max(estimated_tokens, 1024)
        else:
            estimated_tokens = max(
                estimated_tokens,
                getattr(settings, "llama_max_tokens", 256),
            )

        return min(estimated_tokens, 4096)

    def _generation_pass_token_budget(
        self,
        length_target: ResponseLengthTarget | None,
        *,
        current_words: int = 0,
    ) -> int | None:
        if not length_target:
            return None

        remaining_words = max(length_target.target_words - current_words, 0)
        total_budget = self._completion_token_budget_for_words(remaining_words)
        if not total_budget:
            return None

        if length_target.target_words >= 500 or length_target.approximate:
            return min(total_budget, LONG_FORM_PASS_TOKEN_CAP)

        return total_budget

    def _continuation_tail(self, text: str, *, limit: int = 1600) -> str:
        normalized = (text or "").strip()
        if len(normalized) <= limit:
            return normalized
        return normalized[-limit:].lstrip()

    def _clean_continuation_text(self, text: str) -> str:
        lines = (text or "").strip().splitlines()
        cleaned_lines: list[str] = []
        skipping_meta = True

        for line in lines:
            stripped = line.strip()
            if skipping_meta and not stripped:
                continue
            if skipping_meta and CONTINUATION_HEADING_RE.match(stripped):
                continue
            if skipping_meta and stripped.lower().startswith("ecco la continuazione"):
                continue
            skipping_meta = False
            cleaned_lines.append(line)

        return "\n".join(cleaned_lines).strip()

    def _clean_final_answer_text(self, text: str) -> str:
        lines = [
            line
            for line in (text or "").strip().splitlines()
            if not CONTINUATION_HEADING_RE.match(line.strip())
        ]
        terminal_chars = {".", "!", "?", ":", ";", '"', "'", ")", "]", "}"}
        while lines:
            stripped = lines[-1].strip()
            if not stripped:
                lines.pop()
                continue

            normalized = stripped.lstrip("#").strip()
            if stripped.startswith("#") and len(normalized.split()) <= 8:
                lines.pop()
                continue

            if (
                stripped[-1] not in terminal_chars
                and not stripped.startswith(("-", "*", "$"))
            ):
                lines.pop()
                continue

            break

        return "\n".join(lines).strip()

    def _build_response_constraints(self, rag_query: RAGQuery) -> str:
        length_target = self._extract_requested_length_target(rag_query.text)
        constraints = [
            "Rispondi direttamente alla domanda dell'utente senza preamboli meta.",
            "Non limitarti a contare o commentare la lunghezza della tua risposta.",
        ]

        if length_target:
            min_words = self._minimum_acceptable_word_count(
                length_target.target_words,
                approximate=length_target.approximate,
            )
            max_words = max(
                length_target.target_words + 100,
                int(length_target.target_words * 1.1),
            )
            constraints.append(
                f"L'utente ha richiesto circa {self._length_target_requested_label(length_target)}."
            )
            if length_target.requested_unit == "lines":
                constraints.extend([
                    f"Tratta questo obiettivo come una risposta molto estesa, equivalente a circa {length_target.target_words} parole.",
                    "Non discutere la fattibilita del numero di righe richiesto e non scusarti per la lunghezza: rispondi subito nel merito.",
                    f"Scrivi una risposta completa di almeno {min_words} parole circa, usando tutto lo spazio disponibile prima di fermarti.",
                    "Organizza la spiegazione in sezioni sostanziali, esempi e passaggi logici, senza riempitivi o ripetizioni.",
                ])
            else:
                constraints.extend([
                    f"Scrivi una risposta completa compresa tra {min_words} e {max_words} parole circa.",
                    f"Avvicinati il piu possibile al target di {length_target.target_words} parole senza fermarti molto prima.",
                    "Se serve, amplia con spiegazioni, esempi e passaggi logici utili, senza riempitivi o ripetizioni.",
                ])
        else:
            constraints.append("Mantieni la risposta proporzionata alla richiesta.")

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

        minimum_words = self._minimum_acceptable_word_count(
            length_target.target_words,
            approximate=length_target.approximate,
        )
        current_text = generation_result.text.strip()
        current_words = self._count_words(current_text)
        if length_target.approximate:
            logger.info(
                "Skipping iterative extension for approximate requested length",
                requested_unit=length_target.requested_unit,
                requested_value=length_target.requested_value,
                target_words=length_target.target_words,
                current_words=current_words,
            )
            return generation_result
        if current_words >= minimum_words:
            return generation_result

        logger.info(
            "Extending QA answer to satisfy requested length",
            requested_unit=length_target.requested_unit,
            requested_value=length_target.requested_value,
            target_words=length_target.target_words,
            current_words=current_words,
            minimum_words=minimum_words,
        )

        for attempt in range(1, self._continuation_attempt_budget(length_target.target_words) + 1):
            remaining_words = max(length_target.target_words - current_words, 0)
            if remaining_words <= 0:
                break

            continuation_result = await generator.generate(
                template=QA_CONTINUATION_PROMPT,
                variables={
                    "query": variables.get("query", rag_query.text),
                    "context": variables.get("context", context),
                    "current_answer_tail": self._continuation_tail(current_text),
                    "length_instruction": self._length_target_instruction(length_target),
                },
                temperature=rag_query.temperature,
                max_tokens=self._generation_pass_token_budget(
                    length_target,
                    current_words=current_words,
                ),
            )

            continuation_text = self._clean_continuation_text(continuation_result.text)
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
                ) or generation_result.completion_tokens,
            )

            if current_words >= minimum_words:
                break

        return generation_result

    def _resolve_template(self, rag_query: RAGQuery, context: str) -> tuple[str, dict]:
        """Resolve the prompt template and variables for a given query mode."""
        mode = rag_query.mode

        if mode == QueryMode.QA:
            return "general_qa", {
                "context": context,
                "query": self._query_text_without_length_request(rag_query.text),
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
        if (
            not self._initialized
            or not self.dense_retriever
            or not self.sparse_retriever
        ):
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
