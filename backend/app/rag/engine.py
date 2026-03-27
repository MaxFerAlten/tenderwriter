"""
TenderWriter — HybridRAG Engine Orchestrator

The main engine that coordinates all retrieval strategies (dense, sparse, graph),
fuses results, re-ranks them, and generates responses using a local LLM.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
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


@dataclass
class RAGResponse:
    """Output from the RAG pipeline."""
    answer: str
    sources: list[dict]
    mode: QueryMode
    generation_result: GenerationResult | None = None
    llm_route: LLMRoute | None = None
    anonymized: bool = False


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
        self._external_generator: Generator | None = None
        self._anonymizer_failure_count = 0
        self._anonymizer_circuit_open_until = 0.0
        self._initialized = False

    async def initialize(self):
        """Initialize all RAG components."""
        logger.info("Initializing HybridRAG Engine...", 
                    qdrant_host=settings.qdrant_host, 
                    qdrant_port=settings.qdrant_port,
                    neo4j_uri=settings.neo4j_uri)

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

    async def query(self, rag_query: RAGQuery) -> RAGResponse:
        """
        Execute the full HybridRAG pipeline.

        Args:
            rag_query: The query with mode, filters, and additional context.

        Returns:
            RAGResponse with the generated answer and source references.
        """
        if not self._initialized:
            raise RuntimeError("HybridRAG Engine not initialized. Call initialize() first.")

        logger.info(
            "RAG query started",
            mode=rag_query.mode.value,
            query_len=len(rag_query.text),
        )

        # ─── Step 1: Retrieve from all sources ───
        dense_results = []
        sparse_results = []
        graph_results = []

        # Dense retrieval
        try:
            raw_dense = self.dense_retriever.search(
                query=rag_query.text,
                top_k=rag_query.top_k or settings.rag_top_k_dense,
                filters=rag_query.filters,
            )
            dense_results = [
                {"text": r.text, "score": r.score, "metadata": r.metadata}
                for r in raw_dense
            ]
        except Exception as e:
            logger.warning("Dense retrieval failed", error=str(e))

        # Sparse retrieval
        try:
            raw_sparse = self.sparse_retriever.search(
                query=rag_query.text,
                top_k=rag_query.top_k or settings.rag_top_k_sparse,
                filters=rag_query.filters,
            )
            sparse_results = [
                {"text": r.text, "score": r.score, "metadata": r.metadata}
                for r in raw_sparse
            ]
        except Exception as e:
            logger.warning("Sparse retrieval failed", error=str(e))

        # Graph retrieval
        try:
            raw_graph = await self.graph_retriever.search(
                query=rag_query.text,
                top_k=rag_query.top_k or settings.rag_top_k_graph,
                filters=rag_query.filters,
            )
            graph_results = [
                {"text": r.text, "score": r.score, "metadata": r.metadata}
                for r in raw_graph
            ]
        except Exception as e:
            logger.warning("Graph retrieval failed", error=str(e))

        # ─── Step 2: Fuse results ───
        fused = self.fusion.fuse(
            dense_results=dense_results,
            sparse_results=sparse_results,
            graph_results=graph_results,
            top_k=20,  # Send top 20 to re-ranker
        )

        # ─── Step 3: Re-rank ───
        top_k_final = rag_query.top_k or settings.rag_top_k_final
        reranked = []
        if fused:
            try:
                fused_dicts = [
                    {"text": f.text, "score": f.score, "metadata": f.metadata, "sources": f.sources}
                    for f in fused
                ]
                reranked = self.reranker.rerank(
                    query=rag_query.text,
                    results=fused_dicts,
                    top_k=top_k_final,
                )
            except Exception as e:
                logger.warning("Re-ranking failed, using fusion order", error=str(e))
                # Fallback: use fusion results directly
                reranked = fused[:top_k_final]

        # Build context from top results
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

        context = "\n\n---\n\n".join(context_texts)

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
        generator = self.generator
        llm_route = LLMRoute.INTERNAL
        anonymized = False
        deanonymize_session_id: str | None = None

        if settings.anonymizer_enabled and self._has_external_llm():
            try:
                variables, deanonymize_session_id = await self._anonymize_prompt_variables(
                    variables
                )
                generator = self._get_external_generator()
                llm_route = LLMRoute.EXTERNAL_ANONYMIZED
                anonymized = True
            except AnonymizerUnavailableError as exc:
                logger.warning(
                    "Anonymizer unavailable, falling back to internal LLM",
                    fallback_event=True,
                    anonymizer_used=False,
                    session_token=self._mask_session_token(deanonymize_session_id),
                    error=str(exc),
                )
                llm_route = LLMRoute.INTERNAL_FALLBACK
        logger.info(
            "RAG route selected",
            mode=rag_query.mode.value,
            anonymizer_enabled=settings.anonymizer_enabled,
            anonymizer_used=anonymized,
            llm_route=llm_route.value,
            session_token=self._mask_session_token(deanonymize_session_id),
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
            if deanonymize_session_id:
                generation_result = replace(
                    generation_result,
                    text=await self._deanonymize_text(
                        generation_result.text,
                        deanonymize_session_id,
                    ),
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

        logger.info(
            "RAG query completed",
            mode=rag_query.mode.value,
            anonymizer_used=anonymized,
            llm_route=llm_route.value,
            session_token=self._mask_session_token(deanonymize_session_id),
            source_count=len(sources),
            answer_len=len(generation_result.text),
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
        if settings.anonymizer_enabled and self._has_external_llm():
            logger.info(
                "RAG stream forced to internal route",
                reason="v1_streaming_not_supported",
                anonymizer_enabled=True,
                anonymizer_used=False,
                llm_route=LLMRoute.INTERNAL.value,
            )

        # Run retrieval pipeline (same as query, but stream the generation)
        # For brevity, we reuse the query method's retrieval logic
        rag_query_copy = RAGQuery(
            text=rag_query.text,
            mode=QueryMode.SEARCH,
            filters=rag_query.filters,
            top_k=rag_query.top_k,
        )
        search_result = await self.query(rag_query_copy)
        context = "\n\n---\n\n".join(s["text"] for s in search_result.sources)

        # Determine template and variables
        template, variables = self._resolve_template(rag_query, context)

        # Stream generation
        async for token in self.generator.generate_stream(
            template=template,
            variables=variables,
            temperature=rag_query.temperature,
        ):
            yield token

    def _has_external_llm(self) -> bool:
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

    def _record_anonymizer_failure(self, *, reason: str) -> None:
        self._anonymizer_failure_count += 1
        logger.warning(
            "Anonymizer failure recorded",
            failure_count=self._anonymizer_failure_count,
            reason=reason,
        )
        if (
            self._anonymizer_failure_count
            >= settings.anonymizer_circuit_breaker_threshold
        ):
            self._anonymizer_circuit_open_until = (
                time.monotonic() + settings.anonymizer_circuit_open_seconds
            )
            logger.warning(
                "Anonymizer circuit opened",
                failure_count=self._anonymizer_failure_count,
                open_for_seconds=settings.anonymizer_circuit_open_seconds,
                reason=reason,
            )

    def _get_external_generator(self) -> Generator:
        if self._external_generator is None:
            self._external_generator = Generator(
                base_url=settings.external_llm_url,
                model=settings.external_llm_model or settings.llama_model,
                timeout=settings.llama_timeout,
            )
        return self._external_generator

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
        return await active_generator.generate(
            template=template,
            variables=variables,
            temperature=rag_query.temperature,
        )

    def _resolve_template(self, rag_query: RAGQuery, context: str) -> tuple[str, dict]:
        """Resolve the prompt template and variables for a given query mode."""
        mode = rag_query.mode

        if mode == QueryMode.QA:
            return "general_qa", {
                "context": context,
                "query": rag_query.text,
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
                "query": rag_query.text,
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
        return self.chunker.chunk_text(text, metadata)

    def index_chunks(
        self,
        chunks: list[TextChunk],
        collection: str = "documents",
    ) -> list[str]:
        """Index chunks into the dense retriever (Qdrant)."""
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
