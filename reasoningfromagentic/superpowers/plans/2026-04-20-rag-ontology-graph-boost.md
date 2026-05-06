# RAG Ontology Graph Boost Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-enable graph for retrieval evaluation as a safe, ontology-aware signal that cannot dominate dense/sparse retrieval with generic unscoped nodes.

**Architecture:** Keep dense+sparse as the default baseline. When graph is explicitly enabled, pass a graph-only ontology filter derived from each evaluation case. Strip graph-only filters before dense/sparse calls. Make `GraphRetriever` classify requirements with `TenderOntologyService`, filter by ontology domain, return ontology metadata, and use low graph fusion weights from the baseline CLI.

**Tech Stack:** FastAPI backend Python 3.11, Neo4j graph retriever, HybridRAG engine, deterministic `app.intelligence.ontology`, unittest, Ruff.

---

### Task 1: Graph-only ontology filter plumbing

**Files:**
- Modify: `backend/app/rag/engine.py`
- Modify: `backend/app/services/rag_retrieval_evaluation.py`
- Test: `backend/tests/test_rag_scope_filters.py`
- Test: `backend/tests/test_rag_retrieval_evaluation.py`

- [ ] Add failing tests proving `graph_ontology_domain` reaches graph only.
- [ ] Implement vector filter stripping for keys prefixed by `graph_`.
- [ ] Add per-case `graph_ontology_domain` when graph is enabled in retrieval evaluation.
- [ ] Run focused tests.

### Task 2: Ontology-aware graph requirement search

**Files:**
- Modify: `backend/app/rag/graph_retriever.py`
- Modify: `backend/app/services/tender_requirements.py`
- Test: `backend/tests/test_rag_scope_filters.py`
- Test: `backend/tests/test_tender_requirement_materialization.py`

- [ ] Add failing tests for gold-domain mapping, on-the-fly requirement ontology tagging, and sync payload ontology.
- [ ] Store ontology fields when adding requirements.
- [ ] Filter requirement graph results by ontology domain when requested.
- [ ] Include ontology/provenance metadata in graph results.
- [ ] Run focused tests.

### Task 3: Safe graph baseline mode

**Files:**
- Modify: `backend/app/utils/recall_cli.py`
- Modify: `backend/app/services/rag_retrieval_evaluation.py`
- Test: `backend/tests/test_recall_cli.py`
- Test: `backend/tests/test_rag_retrieval_evaluation.py`

- [ ] Add failing tests for low graph fusion weights when graph is opt-in.
- [ ] Add `fusion_weights` support to evaluator.
- [ ] Add CLI defaults `dense=0.45`, `sparse=0.35`, `graph=0.15` for graph-enabled baseline.
- [ ] Run baseline `dense,sparse,graph` and compare with dense+sparse.

### Task 4: Verification

**Files:**
- Generated: `backend/reports/rag-retrieval-baseline-graph-safe.json`

- [ ] Run focused unittest suite.
- [ ] Run Ruff on touched files.
- [ ] Run live dense+sparse baseline to confirm no regression.
- [ ] Run live dense+sparse+graph baseline to measure impact.
