"""
TenderWriter — HybridRAG Engine Orchestrator

The main engine that coordinates all retrieval strategies (dense, sparse, graph),
fuses results, re-ranks them, and generates responses using a local LLM.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from difflib import SequenceMatcher
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
    r"\b(\d{2,5})\s+(?:righe|lines|lineas)\b",
    re.IGNORECASE,
)
WORD_RE = re.compile(r"\b[\wÀ-ÿ]+\b", re.UNICODE)
CONTINUATION_HEADING_RE = re.compile(
    r"^\s*(?:#{1,6}\s*)?(?:continuazione|continuation|proseguimento)\b.*$",
    re.IGNORECASE,
)
PROMPT_LEAKAGE_PLAIN_LABEL_PATTERN = (
    r"(?:draft ending|(?:task|compito)(?=\s*:|$)|retrieved context|user question|response constraints|istruzioni importanti|domanda utente|contesto recuperato|parte finale gia scritta(?:\s*\([^)]*\))?)"
)
PROMPT_LEAKAGE_HEADING_ONLY_LABEL_PATTERN = r"(?:answer(?:\s*\([^)]*\))?)"
PROMPT_LEAKAGE_HEADING_RE = re.compile(
    rf"^\s*(?:(?:#{{1,6}}\s*)(?:{PROMPT_LEAKAGE_PLAIN_LABEL_PATTERN}|{PROMPT_LEAKAGE_HEADING_ONLY_LABEL_PATTERN})(?:\s|:|$)|(?:{PROMPT_LEAKAGE_PLAIN_LABEL_PATTERN})(?:\s|:|$)).*$",
    re.IGNORECASE,
)
PROMPT_LEAKAGE_INLINE_RE = re.compile(
    rf"\s+(?:#{{1,6}}\s*(?:{PROMPT_LEAKAGE_PLAIN_LABEL_PATTERN}|{PROMPT_LEAKAGE_HEADING_ONLY_LABEL_PATTERN})(?:\s|:|$)|(?:compito|task|domanda utente|contesto recuperato|parte finale gia scritta(?:\s*\([^)]*\))?|retrieved context|user question|response constraints|istruzioni importanti)\s*:).*$",
    re.IGNORECASE,
)
PROMPT_LEAKAGE_INSTRUCTION_RES = (
    re.compile(
        r"^scrivi solo il seguito naturale della risposta, iniziando direttamente dal contenuto mancante\.?$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^continua solo quanto basta per chiudere in modo naturale l'ultima frase o l'ultimo concetto rimasto interrotto\. inizia direttamente con il testo mancante\.?$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^provide a helpful, accurate answer based on the available context\.?$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^if the context doesn't contain enough information, say so clearly\.?$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^ricorda: rispondi nella stessa lingua della domanda sopra!?$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^inizia direttamente con la risposta finale, senza copiare intestazioni o sezioni del prompt\.?$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^ora continua direttamente dal punto in cui la risposta si e interrotta\.?$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^ora completa solo quanto basta per chiudere in modo naturale l'ultima frase o l'ultimo concetto rimasto interrotto\.?$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^inizia direttamente con il testo mancante\.?$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^- devi rispondere nella stessa lingua della domanda dell'utente\.?$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^- stai continuando una risposta gia iniziata\.?$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^- devi completare solo la frase o il concetto finale rimasto interrotto\.?$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^- non ricominciare dall'inizio\.?$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^- non ripetere (?:sezioni o frasi gia scritte|il testo gia scritto)\.?$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^- non commentare il numero di parole\.?$",
        re.IGNORECASE,
    ),
    re.compile(
        r'^- non scrivere titoli o frasi come "continuazione della risposta"\.?$',
        re.IGNORECASE,
    ),
    re.compile(
        r"^- non citare o copiare etichette interne del prompt\.?$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^- aggiungi solo contenuto nuovo, sostanziale e coerente con quanto gia scritto\.?$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^- non iniziare un nuovo paragrafo, una nuova sezione o un nuovo argomento\.?$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^- scrivi al massimo 60 parole\.?$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^- chiudi con una frase completa e coerente\.?$",
        re.IGNORECASE,
    ),
)
EXPANDED_EXPLANATION_QUERY_RE = re.compile(
    r"\b(?:riassum\w*|spiega\w*|descriv\w*|sintetizza\w*|summari[sz]\w*|explain\w*|describe\w*)\b",
    re.IGNORECASE,
)
SUMMARY_INTENT_QUERY_RE = re.compile(
    r"\b(?:riassum\w*|sintetizza\w*|summari[sz]\w*|overview|panoramica|spiega\w*|descriv\w*)\b",
    re.IGNORECASE,
)
STRUCTURED_OVERVIEW_QUERY_RE = re.compile(
    r"\b(?:elenco|lista|punti?\s+chiave|dettagliat\w*|complet\w*|strutturat\w*)\b",
    re.IGNORECASE,
)
TENDER_DOCUMENT_QUERY_RE = re.compile(
    r"\b(?:gara|bando|capitolato|disciplinare|documentazione|procedura|lotto|tender|rfp|avviso)\b",
    re.IGNORECASE,
)
RETRIEVAL_INTENT_STRIP_RE = re.compile(
    r"\b(?:fai|fammi|dammi|fornisci|scrivi|prepara|genera|riassum\w*|sintetizza\w*|summari[sz]\w*|overview|panoramica|spiega\w*|descriv\w*|elenco|lista|punti?\s+chiave|dettagliat\w*|complet\w*|strutturat\w*)\b",
    re.IGNORECASE,
)
RETRIEVAL_STOPWORD_STRIP_RE = re.compile(
    r"\b(?:un|una|uno|del|della|delle|dei|degli|dello|di|da|dei|della)\b",
    re.IGNORECASE,
)
TERMINAL_SENTENCE_CHARS = {".", "!", "?", ";", '"', "'", ")", "]", "}", "»"}
INCOMPLETE_SENTENCE_END_TOKENS = {
    "a",
    "ad",
    "al",
    "alla",
    "allo",
    "an",
    "and",
    "as",
    "con",
    "da",
    "de",
    "del",
    "della",
    "di",
    "e",
    "for",
    "fra",
    "from",
    "il",
    "in",
    "into",
    "la",
    "le",
    "lo",
    "nel",
    "nella",
    "of",
    "o",
    "on",
    "or",
    "per",
    "su",
    "the",
    "to",
    "tra",
    "un",
    "una",
    "uno",
    "verso",
    "with",
    "y",
}
MATH_RENDERING_REQUEST_RE = re.compile(
    r"\b(?:latex|la\s*tex|formula|formule|equation|equazioni|matematica|matematiche|simboli matematici|math)\b",
    re.IGNORECASE,
)
LENGTH_META_PARAGRAPH_RE = re.compile(
    r"\b(?:parole|words|righe|lines)\b.*\b(?:sufficienti|insufficienti|troppo pochi|troppo poche|too few|enough|conteggio|numero di parole)\b",
    re.IGNORECASE,
)
APPROX_WORDS_PER_LINE = 8
LONG_FORM_INTERNAL_PASS_TOKEN_CAP = 512
LOCAL_CONTEXT_CHAR_BUDGET = 4500
SUMMARY_LOCAL_CONTEXT_CHAR_BUDGET = 12000
BROAD_SUMMARY_TOP_K_FINAL = 10
DETAILED_OVERVIEW_TOP_K_FINAL = 12
DETAILED_OVERVIEW_RETRIEVAL_TOP_K = 30
BROAD_SUMMARY_DEFAULT_MAX_TOKENS = 768
DETAILED_OVERVIEW_DEFAULT_MAX_TOKENS = 1024
DEANONYMIZED_STREAM_FLUSH_CHARS = 96
DEANONYMIZED_STREAM_FORCE_FLUSH_CHARS = 220

QA_CONTINUATION_PROMPT = """ISTRUZIONI IMPORTANTI:
- Devi rispondere nella STESSA LINGUA della domanda dell'utente.
- Stai continuando una risposta gia iniziata.
- Non ricominciare dall'inizio.
- Non ripetere sezioni o frasi gia scritte.
- Non commentare il numero di parole.
- Non scrivere titoli o frasi come "Continuazione della risposta".
- Non citare o copiare etichette interne del prompt.
- Se nel draft trovi formule OCR rovinate o simboli incompleti, non copiarli alla cieca: riscrivi il passaggio in forma corretta oppure spiegalo in prosa accurata.
- Aggiungi solo contenuto nuovo, sostanziale e coerente con quanto gia scritto.

DOMANDA UTENTE:
{query}

CONTESTO RECUPERATO:
{context}

PARTE FINALE GIA SCRITTA (solo riferimento, non copiarla):
{current_answer_tail}

Ora continua direttamente dal punto in cui la risposta si e interrotta.
Scrivi solo il seguito naturale della risposta, iniziando direttamente dal contenuto mancante.
"""

QA_SENTENCE_CLOSURE_PROMPT = """ISTRUZIONI IMPORTANTI:
- Devi rispondere nella STESSA LINGUA della domanda dell'utente.
- Devi completare solo la frase o il concetto finale rimasto interrotto.
- Non iniziare un nuovo paragrafo, una nuova sezione o un nuovo argomento.
- Non ripetere il testo gia scritto.
- Scrivi al massimo 60 parole.
- Chiudi con una frase completa e coerente.
- Non citare o copiare etichette interne del prompt.

DOMANDA UTENTE:
{query}

CONTESTO RECUPERATO:
{context}

PARTE FINALE GIA SCRITTA (solo riferimento, non copiarla):
{current_answer_tail}

Ora completa solo quanto basta per chiudere in modo naturale l'ultima frase o l'ultimo concetto rimasto interrotto.
Inizia direttamente con il testo mancante.
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
                    logger.warning("Dense retriever init failed (Qdrant may be unavailable)", error=str(e))

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
            logger.warning("Skipping sparse retriever bootstrap because dense storage is unavailable")
            return

        texts, metadatas = self.dense_retriever.load_persisted_chunks(collection="documents")
        self.sparse_retriever.build_index(texts, metadatas)
        logger.info("Sparse retriever bootstrapped", chunks=len(texts))

    async def _retrieve_context_and_sources(
        self,
        rag_query: RAGQuery,
    ) -> RetrievedContext:
        retrieval_query = self._query_text_for_retrieval(rag_query.text)
        retriever_selection = self._resolve_retriever_selection(rag_query)
        rank_fusion = self._build_rank_fusion_for_query(rag_query)
        retrieval_top_k = self._effective_retrieval_top_k(rag_query)

        dense_results = []
        sparse_results = []
        graph_results = []

        if retriever_selection["dense"] and self.dense_retriever:
            try:
                raw_dense = self.dense_retriever.search(
                    query=retrieval_query,
                    top_k=retrieval_top_k or settings.rag_top_k_dense,
                    filters=rag_query.filters,
                )
                dense_results = [
                    {"text": r.text, "score": r.score, "metadata": r.metadata}
                    for r in raw_dense
                ]
            except Exception as e:
                logger.warning("Dense retrieval failed", error=str(e))

        if retriever_selection["sparse"] and self.sparse_retriever:
            try:
                raw_sparse = self.sparse_retriever.search(
                    query=retrieval_query,
                    top_k=retrieval_top_k or settings.rag_top_k_sparse,
                    filters=rag_query.filters,
                )
                sparse_results = [
                    {"text": r.text, "score": r.score, "metadata": r.metadata}
                    for r in raw_sparse
                ]
            except Exception as e:
                logger.warning("Sparse retrieval failed", error=str(e))

        if retriever_selection["graph"] and self.graph_retriever:
            try:
                raw_graph = await self.graph_retriever.search(
                    query=retrieval_query,
                    top_k=retrieval_top_k or settings.rag_top_k_graph,
                    filters=rag_query.filters,
                )
                graph_results = [
                    {"text": r.text, "score": r.score, "metadata": r.metadata}
                    for r in raw_graph
                ]
            except Exception as e:
                logger.warning("Graph retrieval failed", error=str(e))

        top_k_final = self._effective_final_top_k(rag_query)

        fused = rank_fusion.fuse(
            dense_results=dense_results,
            sparse_results=sparse_results,
            graph_results=graph_results,
            top_k=max(
                top_k_final,
                retrieval_top_k or settings.rag_top_k_dense,
            ),
        )

        reranked = []
        if fused:
            try:
                fused_dicts = [
                    {"text": f.text, "score": f.score, "metadata": f.metadata, "sources": f.sources, "source_scores": f.source_scores}
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
            retriever_sources = r.sources if hasattr(r, "sources") else r.get("sources", [])
            source_scores = r.source_scores if hasattr(r, "source_scores") else r.get("source_scores", {})
            context_texts.append(text)
            sources.append({
                "text": text[:200] + "..." if len(text) > 200 else text,
                "score": r.score if hasattr(r, "score") else r.get("score", 0),
                "metadata": metadata,
                "retriever_sources": retriever_sources,
                "source_scores": source_scores,
            })

        return RetrievedContext(
            context="\n\n---\n\n".join(context_texts),
            sources=sources,
        )

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

    def _build_rank_fusion_for_query(self, rag_query: RAGQuery) -> RankFusion:
        weights = self._resolve_fusion_weights(rag_query)
        return RankFusion(
            k=settings.rag_rrf_k,
            dense_weight=weights["dense"],
            sparse_weight=weights["sparse"],
            graph_weight=weights["graph"],
        )

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
                ) or generation_result.completion_tokens,
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

            first_token_in_attempt = True
            async for token in generator.generate_stream(
                template=active_template,
                variables=active_variables,
                temperature=rag_query.temperature,
                max_tokens=max_tokens,
            ):
                raw_pass_text += token
                if not deanonymize_session_id:
                    if first_token_in_attempt and current_text:
                        joined_token = self._merge_completion_suffix(current_text, token)
                        token = self._stream_sanitized_delta(current_text, joined_token)
                    if token:
                        yield token
                    first_token_in_attempt = False
                    continue

                deanonymized_flush_candidate += token
                if not self._should_flush_deanonymized_stream_chunk(
                    deanonymized_flush_candidate
                ):
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

            active_template = QA_CONTINUATION_PROMPT
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
                if current_text and active_template == QA_CONTINUATION_PROMPT
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
            max_tokens=self._generation_pass_token_budget(
                length_target,
                generator=active_generator,
            ),
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

    def _minimum_acceptable_word_count(self, target_words: int, *, approximate: bool = False) -> int:
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
            return min(total_budget, LONG_FORM_INTERNAL_PASS_TOKEN_CAP)

        return total_budget

    def _continuation_tail(self, text: str, *, limit: int = 1600) -> str:
        normalized = (text or "").strip()
        if len(normalized) <= limit:
            return normalized
        return normalized[-limit:].lstrip()

    def _normalize_duplicate_block(self, text: str) -> str:
        normalized = re.sub(r"\s+", " ", (text or "").strip().lower())
        return normalized.strip(" ,.;:-")

    def _strip_prompt_leakage(self, text: str) -> str:
        cleaned = (text or "").strip()
        cleaned_lines: list[str] = []
        for line in cleaned.splitlines():
            candidate = line.rstrip()
            inline_match = PROMPT_LEAKAGE_INLINE_RE.search(candidate)
            if inline_match:
                candidate = candidate[:inline_match.start()].rstrip()

            stripped = candidate.strip()
            if not stripped:
                if cleaned_lines and cleaned_lines[-1]:
                    cleaned_lines.append("")
                continue

            if PROMPT_LEAKAGE_HEADING_RE.match(stripped):
                continue
            if any(pattern.match(stripped) for pattern in PROMPT_LEAKAGE_INSTRUCTION_RES):
                continue

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

    def _deduplicate_repeated_paragraphs(self, text: str) -> str:
        return self._remove_redundant_continuation_blocks("", text)

    def _sanitize_continuation_text(self, base_text: str, continuation_text: str) -> str:
        cleaned = self._clean_continuation_text(continuation_text)
        cleaned = self._strip_prompt_leakage(cleaned)
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
            if skipping_meta and not stripped:
                continue
            if skipping_meta and CONTINUATION_HEADING_RE.match(stripped):
                continue
            if skipping_meta and stripped.lower().startswith("ecco la continuazione"):
                continue
            if skipping_meta and stripped.lower().startswith("continuo la risposta"):
                continue
            skipping_meta = False
            cleaned_lines.append(line)

        return "\n".join(cleaned_lines).strip()

    def _clean_final_answer_text(self, text: str) -> str:
        text = self._strip_prompt_leakage(text)
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
            if stripped.startswith("#") and len(normalized.split()) <= 8:
                lines.pop()
                continue

            if (
                stripped[-1] not in TERMINAL_SENTENCE_CHARS
                and not stripped.startswith(("-", "*", "$"))
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
            template=QA_SENTENCE_CLOSURE_PROMPT,
            variables={
                "query": variables.get("query", self._query_text_without_length_request(rag_query.text)),
                "context": variables.get("context", context),
                "current_answer_tail": self._continuation_tail(current_text, limit=1200),
            },
            temperature=min(rag_query.temperature, 0.2),
            max_tokens=96,
        )

        cleaned_text = self._clean_sentence_completion_text(completion_result.text)
        if not cleaned_text:
            return None

        return replace(completion_result, text=cleaned_text)

    def _query_requests_expanded_explanation(self, query_text: str) -> bool:
        return bool(EXPANDED_EXPLANATION_QUERY_RE.search(query_text or ""))

    def _query_requests_broad_summary(self, query_text: str) -> bool:
        normalized_query = self._query_text_without_length_request(query_text or "")
        return bool(
            (SUMMARY_INTENT_QUERY_RE.search(normalized_query) or STRUCTURED_OVERVIEW_QUERY_RE.search(normalized_query))
            and TENDER_DOCUMENT_QUERY_RE.search(normalized_query)
        )

    def _query_requests_structured_tender_overview(self, query_text: str) -> bool:
        normalized_query = self._query_text_without_length_request(query_text or "")
        return bool(
            STRUCTURED_OVERVIEW_QUERY_RE.search(normalized_query)
            and TENDER_DOCUMENT_QUERY_RE.search(normalized_query)
        )

    def _effective_final_top_k(self, rag_query: RAGQuery) -> int:
        requested_top_k = rag_query.top_k or settings.rag_top_k_final
        if rag_query.mode in {QueryMode.QA, QueryMode.SEARCH} and self._query_requests_structured_tender_overview(
            rag_query.text
        ):
            return max(requested_top_k, DETAILED_OVERVIEW_TOP_K_FINAL)
        if rag_query.mode in {QueryMode.QA, QueryMode.SEARCH} and self._query_requests_broad_summary(
            rag_query.text
        ):
            return max(requested_top_k, BROAD_SUMMARY_TOP_K_FINAL)
        return requested_top_k

    def _effective_retrieval_top_k(self, rag_query: RAGQuery) -> int | None:
        requested_retrieval_top_k = rag_query.retrieval_top_k
        if requested_retrieval_top_k is not None:
            return requested_retrieval_top_k
        if rag_query.mode in {QueryMode.QA, QueryMode.SEARCH} and self._query_requests_structured_tender_overview(
            rag_query.text
        ):
            return max(settings.rag_top_k_dense, DETAILED_OVERVIEW_RETRIEVAL_TOP_K)
        return None

    def _query_text_for_retrieval(self, query_text: str) -> str:
        normalized_query = self._query_text_without_length_request(query_text or "")
        if not self._query_requests_broad_summary(normalized_query):
            return normalized_query

        stripped = RETRIEVAL_INTENT_STRIP_RE.sub(" ", normalized_query)
        stripped = RETRIEVAL_STOPWORD_STRIP_RE.sub(" ", stripped)
        stripped = re.sub(r"\s+", " ", stripped).strip(" ,.;:-")
        return stripped or normalized_query

    def _build_response_constraints(self, rag_query: RAGQuery) -> str:
        length_target = self._extract_requested_length_target(rag_query.text)
        constraints = [
            "Rispondi direttamente alla domanda dell'utente senza preamboli meta.",
            "Non limitarti a contare o commentare il numero di parole della tua risposta.",
            "Se percepisci di essere vicino al limite di output, chiudi sempre la frase o il concetto in corso prima di terminare.",
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
            requested_label = (
                f"{length_target.requested_value} righe"
                if length_target.requested_unit == "lines"
                else f"{length_target.requested_value} parole"
            )
            constraints.extend([
                f"L'utente ha richiesto circa {requested_label}.",
                f"Scrivi una risposta completa compresa tra {min_words} e {max_words} parole circa.",
                f"Avvicinati il piu possibile al target di {length_target.target_words} parole senza fermarti molto prima.",
                "Se serve, amplia con spiegazioni, esempi e passaggi logici utili, senza riempitivi o ripetizioni.",
            ])
            if length_target.requested_unit == "lines":
                constraints.append(
                    "Interpreta la richiesta in righe come una risposta molto estesa e dettagliata, senza discutere la fattibilita del numero richiesto."
                )
        else:
            constraints.append("Mantieni la risposta proporzionata alla richiesta.")
            if self._query_requests_expanded_explanation(rag_query.text):
                constraints.append(
                    "Se il contesto lo consente, sviluppa una risposta un po' piu completa del minimo, coprendo definizione, contesto e punti chiave invece di fermarti a una sola frase breve."
                )
            if self._query_requests_broad_summary(rag_query.text):
                constraints.append(
                    "Se il contesto recuperato copre solo una parte della gara, fornisci comunque la migliore sintesi possibile dei punti emersi e aggiungi solo alla fine una breve nota sugli aspetti non coperti, invece di fermarti a dire soltanto che il contesto e insufficiente."
                )
            if self._query_requests_structured_tender_overview(rag_query.text):
                constraints.extend([
                    "Organizza la risposta come elenco strutturato della gara, privilegiando: oggetto, stazione appaltante, procedura, criterio di aggiudicazione, durata, documenti citati, requisiti o obblighi principali emersi dal contesto.",
                    "Non copiare segnaposto, slash isolati, date incomplete o frammenti OCR palesemente rotti.",
                    "Se un dettaglio non e abbastanza chiaro nel contesto, omettilo oppure segnalalo in modo breve come dato non chiaramente emerso, senza inventarlo.",
                ])

        if self._query_requests_math_rendering(rag_query.text):
            constraints.extend([
                "Quando riporti formule o simboli matematici, riscrivili in notazione matematica leggibile e coerente.",
                "Non copiare frammenti OCR corrotti, pseudo-LaTeX incompleto o formule palesemente spezzate dal contesto.",
                "Se il contesto contiene una formula danneggiata, spiega il significato matematico corretto invece di inventare simboli.",
            ])

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
                template=QA_CONTINUATION_PROMPT,
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
                ) or generation_result.completion_tokens,
            )

            if current_words >= goal_words:
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
