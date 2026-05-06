# RAG Quality Score Lift Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Raise retrieval and generated-answer quality scores for tender analysis by removing duplicated context, improving coverage of critical tender facts, preserving numeric evidence, and measuring answer-level defects.

**Architecture:** Keep the current HybridRAG shape: dense + sparse + optional graph + RRF + reranker. Add deterministic quality gates around it: a pre-prompt context hygiene layer, critical-fact query expansion for broad tender questions, numeric integrity metadata during ingestion, and an answer-level evaluator aligned with the five user criteria from `resoningfromagentic/ultimate/RAG-refine.md`.

**Tech Stack:** FastAPI backend Python 3.11, Qdrant dense retrieval, in-memory BM25 sparse retrieval, Neo4j graph retriever, existing cross-encoder reranker, unittest, Ruff.

---

## Current Diagnosis

`RAG-refine.md` identifies five score blockers:

- Duplicated paragraphs in generated answers.
- Numeric text corruption such as `entro giorni`.
- Unsupported facts/entities such as `Consorzio Metis`.
- Missing critical tender facts: ACN, CCTT, CO-LO-KW, START, 48 mesi, 180/210/270 giorni, penali, art. 1456 c.c.
- No systematic answer-level evaluation for the five qualitative criteria: aderenza alla gara, correttezza fattuale, aspetti tecnologici, punti critici, qualita redazionale.

Codebase reality:

- BM25 already exists in `backend/app/rag/sparse_retriever.py`.
- PDF parsing already uses `unstructured.partition.pdf.partition_pdf(strategy="hi_res")`, with PyMuPDF fallback in `backend/app/ingestion/pipeline.py`.
- There is final answer dedup in `HybridRAGEngine._deduplicate_repeated_paragraphs`, but no pre-prompt context dedup.
- Retrieval evaluation exists in `backend/app/services/rag_retrieval_evaluation.py`, but it measures source keyword recall, not generated answer quality.
- Current verified benchmark after graph-safe fix:
  - dense+sparse: Recall@5 56.00%, Precision@3 23.37%, PageHit 8.00%.
  - dense+sparse+graph safe: Recall@5 68.00%, Precision@3 24.59%, PageHit 12.00%.
  - graph-only: Recall@5 8.00%, so graph is not strong enough as a standalone retriever.

## Internal Prompting Policy

All prompts, prompt fragments, query-expansion texts, critical-fact lists, or any other
text that specializes retrieval fit MUST live outside Python classes and modules. They
belong under:

- `internalprompting/it/`
- `internalprompting/en/`

Every retrieval-specialization asset must have both an Italian and an English Markdown
version. Python code may load, parse, and validate these files, but must not embed the
specialized prompt/query text directly in class bodies or constants.

For this phase, scope is intentionally narrow: create and load only the Markdown files
needed by the information retrieval engine. Generation prompts, proposal-writing prompts,
and non-retrieval agent prompts are out of scope unless a retrieval task explicitly needs
them.

## Target Gates

- Retrieval: graph-safe Recall@5 >= 72%, with dense+sparse no regression below 56%.
- Retrieval: PageHit >= 16% on the current 50-case evaluation set.
- Quality: duplicate paragraph ratio <= 0.08 on answer fixtures.
- Quality: no unsupported capitalized organization/entity names in answer fixtures unless present in retrieved context.
- Quality: numeric fact coverage >= 0.80 for critical numeric fixtures.
- Redaction: generated tender overview has all required sections once and no repeated paragraph blocks.

## File Map

- Create `backend/app/rag/context_quality.py`: deterministic context normalization, duplicate detection, query-focused sentence compression, critical fact term utilities.
- Modify `backend/app/rag/engine.py`: call context dedup/compression before prompt construction, add critical query expansion for broad tender overviews, preserve aligned sources.
- Create `internalprompting/it/retrieval-critical-coverage.md`: Italian retrieval terms and critical tender coverage prompts for the retrieve engine only.
- Create `internalprompting/en/retrieval-critical-coverage.md`: English equivalent of the retrieval coverage asset.
- Create `backend/app/rag/internal_prompting.py`: safe loader/parser for `internalprompting/{it,en}` Markdown assets.
- Modify `backend/app/rag/dense_retriever.py`: optional wider dense fetch for broad tender overview; optionally expose client-side MMR in a later task.
- Modify `backend/app/rag/sparse_retriever.py`: improve Italian/domain tokenization for legal and technical acronyms.
- Create `backend/app/ingestion/document_quality.py`: numeric pattern extraction and broken numeric-fragment detection.
- Modify `backend/app/ingestion/pipeline.py`: attach numeric evidence metadata to chunk inputs and report parse warnings.
- Modify `backend/app/rag/generator.py`: tighten `general_qa` prompt for tender overview mode without adding a new template surface.
- Create `backend/app/services/rag_answer_quality_evaluation.py`: answer-level evaluator for duplication, required fact coverage, unsupported entity hints, and numeric evidence coverage.
- Modify `backend/app/utils/recall_cli.py`: keep retrieval baseline unchanged, optionally include quality-summary path only when explicitly requested.
- Create `backend/app/utils/rag_quality_cli.py`: CLI for answer-level fixtures and quality gates.
- Create tests:
  - `backend/tests/test_rag_context_quality.py`
  - `backend/tests/test_rag_critical_coverage.py`
  - `backend/tests/test_ingestion_document_quality.py`
  - `backend/tests/test_rag_answer_quality_evaluation.py`
  - Update `backend/tests/test_rag_scope_filters.py`
  - Update `backend/tests/test_rag_prompt_leakage_loop.py`

---

### Task 1: Add Answer-Level Quality Metrics

**Files:**
- Create: `backend/app/services/rag_answer_quality_evaluation.py`
- Create: `backend/tests/test_rag_answer_quality_evaluation.py`
- Create: `backend/app/utils/rag_quality_cli.py`

- [x] Write failing tests for duplicate ratio, required fact coverage, numeric coverage, and unsupported entity detection.

Test cases to create:

```python
def test_duplicate_ratio_detects_repeated_paragraphs():
    text = "A. La gara richiede ACN.\n\nA. La gara richiede ACN.\n\nB. Sono previsti 180 giorni."
    metrics = evaluate_answer_quality(
        answer=text,
        context="La gara richiede ACN. Sono previsti 180 giorni.",
        required_facts=("ACN", "180 giorni"),
    )
    assert metrics.duplicate_block_ratio == 0.3333
    assert "duplicate_blocks" in metrics.failures
```

```python
def test_unsupported_entity_detection_flags_entity_absent_from_context():
    metrics = evaluate_answer_quality(
        answer="Il Consorzio Metis gestisce la gara.",
        context="Regione Toscana e ESTAR sono soggetti coinvolti.",
        required_facts=(),
    )
    assert "Consorzio Metis" in metrics.unsupported_entities
    assert "unsupported_entities" in metrics.failures
```

- [x] Implement dataclasses:

```python
@dataclass(frozen=True)
class AnswerQualityMetrics:
    duplicate_block_ratio: float
    required_fact_coverage: float
    numeric_fact_coverage: float
    unsupported_entities: tuple[str, ...]
    failures: tuple[str, ...]
```

- [x] Implement `evaluate_answer_quality(answer, context, required_facts, numeric_facts=())`.

Rules:

- Split answer into paragraph blocks by blank lines.
- Normalize by lowercasing, removing repeated whitespace, and stripping punctuation.
- Duplicate block ratio = duplicate block count / total non-empty block count.
- Required fact coverage = facts present in answer / facts requested.
- Numeric fact coverage = numeric facts present in answer and context / numeric facts requested.
- Unsupported entities: capitalized multi-token entities in answer that are absent from context.

- [x] Implement `backend/app/utils/rag_quality_cli.py` with JSON fixture input:

```json
[
  {
    "id": "overview-oscat",
    "question": "Analizza la gara OSCAT",
    "answer": "...",
    "context": "...",
    "required_facts": ["ACN", "CCTT", "CO-LO-KW", "START", "180 giorni"],
    "numeric_facts": ["180 giorni", "270 giorni", "48 mesi"]
  }
]
```

- [x] Run:

```bash
cd backend
python3 -m unittest tests.test_rag_answer_quality_evaluation
```

Expected: pass after implementation.

### Task 2: Deduplicate Context Before Prompt Construction

**Files:**
- Create: `backend/app/rag/context_quality.py`
- Modify: `backend/app/rag/engine.py`
- Test: `backend/tests/test_rag_context_quality.py`
- Update: `backend/tests/test_rag_scope_filters.py`

- [x] Write failing tests for exact and near duplicate context blocks.

```python
def test_deduplicate_context_blocks_keeps_best_source_score():
    items = [
        {"text": "La gara richiede qualificazione ACN entro 210 giorni.", "score": 0.2},
        {"text": "La gara richiede qualificazione ACN entro 210 giorni.", "score": 0.9},
    ]
    deduped, stats = deduplicate_context_items(items)
    assert len(deduped) == 1
    assert deduped[0]["score"] == 0.9
    assert stats["removed"] == 1
```

```python
def test_near_duplicate_context_blocks_are_removed():
    items = [
        {"text": "Il Fornitore deve completare la Fase 1 entro 180 giorni solari."},
        {"text": "Il fornitore deve completare la fase 1 entro 180 giorni solari continuativi."},
    ]
    deduped, stats = deduplicate_context_items(items, similarity_threshold=0.88)
    assert len(deduped) == 1
    assert stats["removed"] == 1
```

- [x] Implement `context_quality.py`:

```python
def normalize_context_text(text: str) -> str:
    return " ".join(str(text or "").casefold().split())
```

```python
def deduplicate_context_items(
    items: Sequence[Mapping[str, Any]],
    *,
    similarity_threshold: float = 0.92,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    ...
```

Use `difflib.SequenceMatcher` for near duplicates. Keep the item with higher score. Preserve metadata and `source_scores`.

- [x] Integrate in `HybridRAGEngine._retrieve_context_and_sources` after reranking and before building `context_texts`.

Expected behavior:

- `sources` and `context_texts` remain aligned.
- Removed duplicates do not reach the prompt.
- Source metadata can include `context_dedup_removed_count` only in diagnostics, not in user-facing text.

- [x] Run:

```bash
cd backend
python3 -m unittest tests.test_rag_context_quality tests.test_rag_scope_filters
```

### Task 3: Add Critical Tender Coverage Retrieval for Broad Tender Questions

**Files:**
- Create: `internalprompting/it/retrieval-critical-coverage.md`
- Create: `internalprompting/en/retrieval-critical-coverage.md`
- Create: `backend/app/rag/internal_prompting.py`
- Modify: `backend/app/rag/engine.py`
- Create: `backend/tests/test_rag_critical_coverage.py`

- [x] Add failing tests proving broad tender overview queries load extra lexical query variants from Markdown assets, not from Python constants.

```python
def test_structured_tender_overview_expands_retrieval_queries():
    engine = HybridRAGEngine()
    queries = engine._retrieval_queries_for("Analizza questa gara e dimmi punti critici")
    assert any("qualificazione ACN" in query for query in queries)
    assert any("CCTT" in query for query in queries)
    assert any("CO-LO-KW" in query for query in queries)
    assert any("art. 1456" in query for query in queries)
```

- [x] Create the Italian retrieval asset at `internalprompting/it/retrieval-critical-coverage.md`:

```markdown
# Retrieval Critical Coverage

Scopo: espandere il retrieval delle panoramiche di gara con termini critici esatti.
Ambito: solo retrieval. Non usare questo file come prompt di generazione.

## Query Variants

- qualificazione ACN QC1 QC2 AI1 AI2 Decreto direttoriale ACN
- CCTT Community Cloud Territoriale Toscana infrastruttura nodi rack LAN
- CO-LO-KW PUN PUE canone energetico voltura utenze elettriche
- START piattaforma telematica negoziazione gara
- 180 giorni 210 giorni 270 giorni 48 mesi affiancamento migrazione
- penali 100 euro giorno 10% risoluzione art. 1456 c.c.
```

- [x] Create the English retrieval asset at `internalprompting/en/retrieval-critical-coverage.md`:

```markdown
# Retrieval Critical Coverage

Purpose: expand broad tender overview retrieval with exact tender-critical terms.
Scope: retrieval only. Do not use this file as a generation prompt.

## Query Variants

- ACN qualification QC1 QC2 AI1 AI2 ACN director decree
- CCTT Tuscany Territorial Community Cloud infrastructure nodes rack LAN
- CO-LO-KW PUN PUE energy fee electricity contract transfer
- START electronic procurement platform tender negotiation
- 180 days 210 days 270 days 48 months transition migration
- penalties 100 euro per day 10% termination article 1456 civil code
```

- [x] Implement `backend/app/rag/internal_prompting.py` with a deterministic Markdown loader:

```python
from __future__ import annotations

from pathlib import Path

INTERNAL_PROMPTING_ROOT = Path(__file__).resolve().parents[3] / "internalprompting"


def load_retrieval_query_variants(asset_name: str, *, language: str = "it") -> tuple[str, ...]:
    if language not in {"it", "en"}:
        raise ValueError("language must be 'it' or 'en'")
    path = INTERNAL_PROMPTING_ROOT / language / f"{asset_name}.md"
    text = path.read_text(encoding="utf-8")
    variants: list[str] = []
    inside_variants = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line == "## Query Variants":
            inside_variants = True
            continue
        if inside_variants and line.startswith("## "):
            break
        if inside_variants and line.startswith("- "):
            value = line[2:].strip()
            if value:
                variants.append(value)
    if not variants:
        raise ValueError(f"No query variants found in {path}")
    return tuple(variants)
```

- [x] Implement deterministic query expansion only for broad tender overview questions by loading `retrieval-critical-coverage.md`. Do not embed the specialized query text in `HybridRAGEngine`, `DenseRetriever`, `SparseRetriever`, or any other Python class.

- [x] In `_retrieve_context_and_sources`, for broad overview only:

1. Run current dense/sparse/graph retrieval for the original query.
2. Run sparse retrieval for each critical variant with `top_k=2`.
3. Run dense retrieval for at most the top 2 broad variants: ACN/CCTT and numeric/penalties.
4. Append these candidates before fusion with metadata field `retrieval_variant`.

- [x] Keep the standard 50-case `Recall.py` path stable unless the query matches overview intent.

- [x] Run:

```bash
cd backend
python3 -m unittest tests.test_rag_critical_coverage tests.test_rag_scope_filters
```

### Task 4: Add Query-Focused Context Compression

**Files:**
- Modify: `backend/app/rag/context_quality.py`
- Modify: `backend/app/rag/engine.py`
- Test: `backend/tests/test_rag_context_quality.py`

- [x] Write failing test that irrelevant repeated sentences are removed while numeric/legal evidence is preserved.

```python
def test_compress_context_preserves_numeric_and_query_sentences():
    text = (
        "La procedura contiene premesse generiche. "
        "Il Fornitore deve conseguire qualificazione ACN entro 210 giorni. "
        "Altra premessa generica ripetuta."
    )
    compressed = compress_context_block(text, query="Quale qualificazione ACN e richiesta?")
    assert "qualificazione ACN entro 210 giorni" in compressed
    assert "premesse generiche" not in compressed
```

- [x] Implement deterministic sentence extraction:

- Split by sentence boundaries and newlines.
- Keep sentences matching query terms, critical tender terms, legal/numeric regex, or source headings.
- For short blocks under 450 characters, keep original text.
- Never rewrite content; only select existing sentences.

- [x] Apply compression after dedup and before prompt fitting, only for QA mode and broad tender overview mode first.

- [x] Run:

```bash
cd backend
python3 -m unittest tests.test_rag_context_quality
```

### Task 5: Strengthen Prompt Constraints for the Five Evaluation Criteria

**Files:**
- Modify: `backend/app/rag/engine.py`
- Modify: `backend/app/rag/generator.py`
- Test: `backend/tests/test_rag_prompt_leakage_loop.py`

- [x] Add failing test that structured tender overview constraints include the five required sections.

Expected section names:

- Oggetto e perimetro
- Architettura tecnologica
- Fasi operative critiche
- Punti di rischio contrattuale
- Governance multi-soggetto

- [x] Extend `_build_response_constraints` for structured tender overview:

```text
Organizza la risposta in queste sezioni esatte:
1. Oggetto e perimetro
2. Architettura tecnologica
3. Fasi operative critiche
4. Punti di rischio contrattuale
5. Governance multi-soggetto
```

- [x] Add rules:

- Do not repeat the same paragraph or concept in multiple sections.
- Every numeric value must appear exactly as found in context.
- If a subject, organization, platform, penalty, or deadline is not in context, say `non disponibile nei documenti forniti`.
- Do not introduce names absent from retrieved context.

- [x] Keep the existing prompt-leakage protections unchanged.

- [x] Run:

```bash
cd backend
python3 -m unittest tests.test_rag_prompt_leakage_loop
```

### Task 6: Preserve Numeric Evidence During Ingestion

**Files:**
- Create: `backend/app/ingestion/document_quality.py`
- Modify: `backend/app/ingestion/pipeline.py`
- Test: `backend/tests/test_ingestion_document_quality.py`
- Update: `backend/tests/test_ingestion_chunk_scope.py`

- [x] Write failing tests for numeric fact extraction and broken numeric fragments.

```python
def test_extract_numeric_mentions_finds_giorni_euro_percentuali_and_articles():
    mentions = extract_numeric_mentions(
        "entro 180 giorni, penale Euro 100/giorno, massimo 10%, art. 1456 c.c."
    )
    assert "180 giorni" in mentions
    assert "Euro 100" in mentions
    assert "10%" in mentions
    assert "art. 1456 c.c." in mentions
```

```python
def test_detect_broken_numeric_fragment_flags_missing_number():
    assert has_broken_numeric_fragment("la fase deve concludersi entro giorni")
    assert not has_broken_numeric_fragment("la fase deve concludersi entro 180 giorni")
```

- [x] Implement regex helpers:

```python
NUMERIC_MENTION_PATTERNS = (
    r"\b\d{1,4}\s+(?:giorni|mesi|anni)\b",
    r"\bEuro\s*[\d.,]+",
    r"\b\d{1,3}\s*%",
    r"\bart\.?\s*\d+[^\s,.;)]*(?:\s*c\.c\.)?",
)
```

- [x] In `_build_chunk_inputs`, attach `extra["numeric_mentions"]` and `extra["parse_warnings"]` to each `ChunkMetadata`.

- [x] If a chunk has a broken numeric fragment and previous/next element is same page, merge neighboring text before chunking instead of indexing the broken fragment alone.

- [x] Do not add `pdfplumber` yet. Current dependencies already include `unstructured[pdf,docx]` and `pymupdf`; add `pdfplumber` only if the numeric warning rate remains high after this task.

- [x] Run:

```bash
cd backend
python3 -m unittest tests.test_ingestion_document_quality tests.test_ingestion_chunk_scope
```

### Task 7: Tune Sparse/Dense/Graph Weights With a Grid Search CLI

**Files:**
- Create: `backend/app/utils/tune_retrieval_weights.py`
- Test: `backend/tests/test_recall_cli.py`

- [x] Add failing test for deterministic candidate grid generation.

```python
def test_candidate_weight_grid_includes_safe_graph_profiles():
    grid = build_candidate_grid()
    assert {"dense": 0.45, "sparse": 0.35, "graph": 0.15} in grid
    assert any(item["sparse"] >= 0.45 for item in grid)
```

- [x] Implement CLI that runs `evaluate_retrieval_baseline` over:

- retrievers: `dense,sparse`, `dense,sparse,graph`
- retrieval_top_k: 5, 8, 10, 15
- fusion weights:
  - dense 0.45 / sparse 0.35 / graph 0.15
  - dense 0.35 / sparse 0.50 / graph 0.10
  - dense 0.40 / sparse 0.45 / graph 0.10
  - dense 0.50 / sparse 0.40 / graph 0.05

- [x] Sort by:

1. Recall@5 descending.
2. PageHit descending.
3. Precision@3 descending.
4. Latency ascending.

- [x] Output JSON to `backend/reports/rag-retrieval-tuning.json`.

- [x] Run:

```bash
cd backend
python3 -m unittest tests.test_recall_cli
```

### Task 8: Full Verification and Acceptance

**Files:**
- Generated reports:
  - `backend/reports/rag-retrieval-baseline.json`
  - `backend/reports/rag-retrieval-baseline-graph-safe.json`
  - `backend/reports/rag-retrieval-tuning.json`
  - `backend/reports/rag-answer-quality.json`

- Verification snapshot, 2026-04-20:
  - Focused Docker unittest suite: 39 tests passed.
  - New modules/tests Ruff: passed.
  - Historical touched modules with pre-existing Ruff debt: `py_compile` passed for
    `app/rag/engine.py`, `app/rag/generator.py`, and `app/ingestion/pipeline.py`.
  - Answer-quality smoke fixture: duplicate ratio 0.0000, required fact coverage 1.0000,
    numeric fact coverage 1.0000, unsupported entity count 0.
  - dense+sparse baseline: Recall@5 56.00%, Precision@3 23.37%, PageHit 8.00%.
  - dense+sparse+graph safe baseline: Recall@5 68.00%, Precision@3 24.59%, PageHit 12.00%.
  - best tuning candidate: dense+sparse, `retrieval_top_k=15`, weights
    dense 0.40 / sparse 0.45 / graph 0.10, Recall@5 76.00%, Precision@3 25.89%,
    PageHit 14.00%, average latency 334.29 ms.

- [x] Run focused tests:

```bash
docker run --rm \
  -v /home/tendermachine/tender/tenderwriter/backend:/work \
  -v /home/tendermachine/tender/tenderwriter/internalprompting:/work/internalprompting \
  -w /work tenderwriter-backend python3 -m unittest \
  tests.test_rag_context_quality \
  tests.test_rag_critical_coverage \
  tests.test_ingestion_document_quality \
  tests.test_rag_answer_quality_evaluation \
  tests.test_rag_scope_filters \
  tests.test_recall_cli \
  tests.test_ingestion_chunk_scope \
  tests.test_rag_prompt_leakage_loop
```

- [x] Run Ruff on touched files:

```bash
cd backend
uv run --no-project ruff check \
  app/rag/context_quality.py \
  app/rag/engine.py \
  app/rag/dense_retriever.py \
  app/rag/sparse_retriever.py \
  app/ingestion/document_quality.py \
  app/ingestion/pipeline.py \
  app/rag/generator.py \
  app/services/rag_answer_quality_evaluation.py \
  app/utils/rag_quality_cli.py \
  app/utils/tune_retrieval_weights.py \
  tests/test_rag_context_quality.py \
  tests/test_rag_critical_coverage.py \
  tests/test_ingestion_document_quality.py \
  tests/test_rag_answer_quality_evaluation.py
```

If full Ruff on `app/rag/engine.py` reports pre-existing unrelated debt, run `python3 -m py_compile app/rag/engine.py` and Ruff the new modules/tests.

- [x] Run live retrieval baselines:

```bash
docker run --rm --network tenderwriter_default --env-file .env \
  -v /home/tendermachine/tender/tenderwriter/backend:/work \
  -v /home/tendermachine/tender/tenderwriter/internalprompting:/work/internalprompting \
  -w /work \
  tenderwriter-backend python3 -m app.utils.recall_cli \
  --report-file reports/rag-retrieval-baseline.json
```

```bash
docker run --rm --network tenderwriter_default --env-file .env \
  -v /home/tendermachine/tender/tenderwriter/backend:/work \
  -v /home/tendermachine/tender/tenderwriter/internalprompting:/work/internalprompting \
  -w /work \
  tenderwriter-backend python3 -m app.utils.recall_cli \
  --retrievers dense,sparse,graph \
  --report-file reports/rag-retrieval-baseline-graph-safe.json
```

- [x] Run retrieval tuning:

```bash
docker run --rm --network tenderwriter_default --env-file .env \
  -v /home/tendermachine/tender/tenderwriter/backend:/work \
  -v /home/tendermachine/tender/tenderwriter/internalprompting:/work/internalprompting \
  -w /work \
  tenderwriter-backend python3 -m app.utils.tune_retrieval_weights \
  --report-file reports/rag-retrieval-tuning.json
```

- [x] Run answer-quality fixtures:

```bash
docker run --rm --network tenderwriter_default --env-file .env \
  -v /home/tendermachine/tender/tenderwriter/backend:/work -w /work \
  tenderwriter-backend python3 -m app.utils.rag_quality_cli \
  --fixtures app/utils/rag_quality_fixtures.json \
  --report-file reports/rag-answer-quality.json
```

- [ ] Acceptance gate status: partial. Recall and quality gates pass; PageHit remains below target.

- dense+sparse Recall@5 >= 56.00%.
- graph-safe Recall@5 >= 72.00% or tuning report explains why not.
  - Raw graph-safe Recall@5 is 68.00%, but the best tuned dense+sparse candidate reaches 76.00%.
- PageHit >= 16.00% or tuning report explains which cases remain page-mismatched.
  - Current best PageHit is 14.00%. There are 43/50 page-mismatched cases, concentrated in
    TECNICO (10), AMMINISTRATIVO (9), SLA_PENALITA (8), CERTIFICAZIONI (5), and
    ECONOMICO_FINANZIARIO (5). This points to page anchoring and chunk/source-page calibration
    as the next lift, not another graph boost.
- duplicate paragraph ratio <= 0.08.
- unsupported entity count == 0 on fixtures.
- numeric fact coverage >= 0.80.

## Recommended Execution Order

1. Task 1: measure answer defects first, so improvements are visible.
2. Task 2: pre-prompt context dedup. This is the quickest path to removing redaction failures.
3. Task 3: critical coverage retrieval. This targets aderenza, tecnologia, and punti critici.
4. Task 5: structured prompt. This improves the five-criteria score without changing retrieval.
5. Task 4: deterministic context compression. This reduces prompt noise after coverage expands.
6. Task 6: numeric ingestion integrity. This stabilizes correctness over re-ingestion.
7. Task 7: weight tuning. This is optimization after quality controls are in place.
8. Task 8: full verification and report comparison.

## Explicit Non-Goals

- Do not make graph-only the default. Current graph-only Recall@5 is 8.00%.
- Do not add `pdfplumber` before proving current `unstructured` + PyMuPDF path cannot meet numeric gates.
- Do not rely on LLM context compression for the first pass; deterministic extraction is cheaper, testable, and easier to gate.
- Do not hide hallucinations with post-generation rewriting. Prefer stronger context, stronger prompt constraints, and measurable unsupported-entity detection.
