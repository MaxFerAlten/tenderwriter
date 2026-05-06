# RAG Procedure Fact Guardrails Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent RAG answers from mixing distinct tender procedures, inventing or truncating protected numeric facts, and emitting duplicated long-form tender analyses.

**Architecture:** Keep the existing HybridRAG pipeline: dense + BM25 + graph + RRF + reranker + planning coverage. Add a deterministic guardrail layer after retrieval and before generation to segment source chunks by procedure, build a fact sheet for protected fields, inject that fact sheet into tender overview prompts, then validate the generated answer before it is returned. Generic non-tender queries remain unchanged.

**Tech Stack:** FastAPI backend, Python 3.11+, existing HybridRAG engine, existing `AppSettings` runtime configuration, unittest/pytest, Vitest for frontend contract tests if UI controls are added.

---

## Current Diagnosis

`/home/tendermachine/Documenti/Obsidian Vault/RAG-fix-7.md` identifies four concrete defects:

- Long tender overview answers repeat entire sections and restart from the opening paragraph.
- The model mixes facts from two procedures present in the same corpus, especially OSCAT and SCT.
- Protected fields such as CIG, procedure id, days, amounts, addresses, subjects, and phase names are inferred or truncated.
- The current output can look fluent even when it contains unsupported facts, so prompt-only mitigation is insufficient.

Relevant code reality:

- `backend/app/rag/engine.py` already centralizes retrieval, context construction, generation, streaming, and final cleanup.
- `backend/app/rag/planningcoverage.py` already adds slot-specific retrieval candidates and metadata such as `coverage_slot`.
- `backend/app/rag/context_quality.py` already deduplicates context items and compresses broad tender context.
- `backend/app/services/rag_answer_quality_evaluation.py` already evaluates duplicates, unsupported entities, and numeric coverage for offline fixtures, but it is not part of the live RAG response path.
- The current context envelope is `<doc id='...' page='...'>...</doc>`; `RAG-fix-7.md` asks for stable source delimiters and source attribution.

## Target Behavior

- A broad tender query involving a single procedure returns a fact table first, then narrative analysis.
- A query whose retrieved context clearly contains multiple procedures is either separated by procedure label or blocked if the user did not ask for comparison.
- Any CIG, procedure id, day count, amount, percentage, address, or subject in the final answer must exist in the fact sheet.
- If a protected field has conflicting values, return exactly `output bloccato: conflitto o dato non verificato` and still return the retrieved sources.
- Streamed tender overview answers use the same guardrail path as non-streamed answers.
- Generic RAG questions that are not tender overview questions do not run the new blocking gate.

## File Map

- Create `backend/app/rag/procedure_guardrails.py`: procedure labels, anchors, fact sheet dataclasses, deterministic protected-field extraction, validation result types, answer validation.
- Modify `backend/app/rag/engine.py`: build guardrail context after rerank/dedup, inject fact sheet into prompt variables, run validation after generation, and reuse full buffered query path for guarded streaming.
- Modify `backend/app/rag/generator.py`: update `tender_overview` template to require fact table before narrative and forbid facts outside the fact sheet.
- Modify `backend/app/api/rag.py`: optionally include guardrail config load from `AppSettings.data["rag_guardrails"]`; default only runs on structured tender overview queries.
- Create `backend/tests/test_rag_procedure_guardrails.py`: unit tests for segmentation, fact extraction, conflict detection, numeric validation, duplicate validation.
- Update `backend/tests/test_rag_prompt_leakage_loop.py`: regression tests for guarded streaming and final cleanup compatibility.
- Update `backend/tests/test_rag_anonymizer_routing.py`: prompt contract tests for the `tender_overview` template and response constraints.
- Optional later UI task: extend `frontend/src/pages/PlanningCoverage.tsx` and `frontend/src/api/client.ts` with guardrail mode controls.

## Target Gates

- `test_rag_procedure_guardrails.py`: all unit tests pass.
- Existing targeted tests keep passing:
  - `backend/tests/test_planningcoverage.py`
  - `backend/tests/test_rag_critical_coverage.py`
  - `backend/tests/test_rag_prompt_leakage_loop.py`
  - `backend/tests/test_rag_tender_overview_longform.py`
- Frontend is unchanged unless the optional UI task is implemented.
- Block message is exact and stable: `output bloccato: conflitto o dato non verificato`.

---

### Task 1: Add Regression Tests For Procedure Mixing And Protected Facts

**Files:**
- Create: `backend/tests/test_rag_procedure_guardrails.py`

- [ ] **Step 1: Write failing unit tests**

Create `backend/tests/test_rag_procedure_guardrails.py` with these tests:

```python
# ruff: noqa: E402
"""Tests for deterministic RAG procedure guardrails."""

from __future__ import annotations

import unittest

from app.rag.procedure_guardrails import (
    BLOCKED_OUTPUT_MESSAGE,
    FactStatus,
    build_fact_sheet,
    classify_chunk_procedure,
    validate_guarded_answer,
)


class RagProcedureGuardrailsTests(unittest.TestCase):
    def test_classifies_oscat_and_sct_chunks_by_anchors(self) -> None:
        self.assertEqual(
            classify_chunk_procedure(
                "Servizi GitLab, Sonar, Nexus, Vulnerability Assessment, SME, MAM e STS."
            ),
            "OSCAT",
        )
        self.assertEqual(
            classify_chunk_procedure(
                "RTPC, CCTT, fase transitoria, qualificazione ACN e Via San Piero a Quaracchi."
            ),
            "SCT",
        )

    def test_build_fact_sheet_extracts_protected_fields_with_sources(self) -> None:
        items = [
            {
                "text": (
                    "Procedura OSCAT 012942/2025 per CI/CD. "
                    "CIG B123456789. Sono previsti 180 giorni e 48 mesi."
                ),
                "metadata": {"chunk_index": 7, "page_number": 3},
            }
        ]

        sheet = build_fact_sheet(items, query="descrivimi la gara OSCAT")

        self.assertEqual(sheet.procedure_label, "OSCAT")
        self.assertIn("012942/2025", sheet.procedure_ids)
        self.assertIn("B123456789", sheet.cigs)
        self.assertIn("180 giorni", sheet.critical_days)
        self.assertIn("48 mesi", sheet.durations)
        self.assertEqual(sheet.status, FactStatus.VERIFIED)
        self.assertIn("chunk:7", sheet.source_ids)

    def test_conflicting_cigs_block_fact_sheet(self) -> None:
        sheet = build_fact_sheet(
            [
                {"text": "Gara OSCAT con CIG B123456789.", "metadata": {"chunk_index": 1}},
                {"text": "Gara OSCAT con CIG C987654321.", "metadata": {"chunk_index": 2}},
            ],
            query="descrivimi la gara OSCAT",
        )

        self.assertEqual(sheet.status, FactStatus.CONFLICT)
        self.assertIn("cig", sheet.conflicts)

    def test_answer_with_unverified_number_is_blocked(self) -> None:
        sheet = build_fact_sheet(
            [{"text": "Gara OSCAT con CIG B123456789 e durata 48 mesi.", "metadata": {}}],
            query="descrivimi la gara OSCAT",
        )

        result = validate_guarded_answer(
            answer="La gara OSCAT dura 48 mesi e include una fase da 270 giorni.",
            fact_sheet=sheet,
            guarded=True,
        )

        self.assertEqual(result.status, "BLOCK")
        self.assertEqual(result.safe_answer, BLOCKED_OUTPUT_MESSAGE)
        self.assertIn("unverified_number:270", result.failures)

    def test_answer_mixing_oscat_and_sct_without_comparison_is_blocked(self) -> None:
        sheet = build_fact_sheet(
            [{"text": "OSCAT usa GitLab, Sonar, Nexus e Vulnerability Assessment.", "metadata": {}}],
            query="descrivimi la gara OSCAT",
        )

        result = validate_guarded_answer(
            answer="OSCAT usa GitLab. SCT richiede RTPC e qualificazione ACN.",
            fact_sheet=sheet,
            guarded=True,
        )

        self.assertEqual(result.status, "BLOCK")
        self.assertIn("cross_procedure_mixing", result.failures)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
cd backend
PYTHONPATH=. uv run --no-project --with pytest --with pydantic-settings --with pydantic pytest -q tests/test_rag_procedure_guardrails.py -q
```

Expected: fail with `ModuleNotFoundError: No module named 'app.rag.procedure_guardrails'`.

- [ ] **Step 3: Commit tests**

```bash
git add backend/tests/test_rag_procedure_guardrails.py
git commit -m "test rag procedure guardrails"
```

---

### Task 2: Implement Procedure Segmentation And Fact Sheet Extraction

**Files:**
- Create: `backend/app/rag/procedure_guardrails.py`
- Test: `backend/tests/test_rag_procedure_guardrails.py`

- [ ] **Step 1: Add dataclasses, anchors, and extraction helpers**

Create `backend/app/rag/procedure_guardrails.py`:

```python
"""Deterministic guardrails for tender procedure-aware RAG answers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
import re
from typing import Any

BLOCKED_OUTPUT_MESSAGE = "output bloccato: conflitto o dato non verificato"


class FactStatus(StrEnum):
    VERIFIED = "verificato"
    NOT_DETECTED = "non_rilevato"
    CONFLICT = "conflitto"


ProcedureLabel = str

PROCEDURE_ANCHORS: dict[ProcedureLabel, tuple[str, ...]] = {
    "OSCAT": (
        "gitlab",
        "sonar",
        "nexus",
        "vulnerability assessment",
        "dpa",
        "gpa",
        "gva",
        "sme",
        "mam",
        "sts",
        "devsecops",
        "oscat",
    ),
    "SCT": (
        "cctt",
        "rtpc",
        "presa in carico",
        "fase transitoria",
        "qualificazione acn",
        "tix",
        "via san piero a quaracchi",
        "sistema cloud toscana",
        "sistema cloud toscano",
    ),
}

_CIG_RE = re.compile(r"\bCIG\s*[:\-]?\s*([A-Z0-9]{8,12})\b", re.IGNORECASE)
_PROCEDURE_ID_RE = re.compile(r"\b(?:procedura|gara)\s*(?:n\.?|numero)?\s*([0-9]{5,6}/20[0-9]{2})\b", re.IGNORECASE)
_DAY_RE = re.compile(r"\b([1-9][0-9]{1,3})\s+giorni\b", re.IGNORECASE)
_MONTH_RE = re.compile(r"\b([1-9][0-9]{0,2})\s+mesi\b", re.IGNORECASE)
_MONEY_RE = re.compile(r"(?:€|\beuro\b)\s*[\d.]+(?:,\d{2})?", re.IGNORECASE)
_ADDRESS_RE = re.compile(r"\bvia\s+san\s+piero\s+a\s+quaracchi\s+\d+\b", re.IGNORECASE)
_NUMBER_RE = re.compile(r"\b\d+(?:[.,]\d+)*\b")


@dataclass(frozen=True)
class FactSheet:
    procedure_label: ProcedureLabel
    procedure_ids: tuple[str, ...] = ()
    cigs: tuple[str, ...] = ()
    critical_days: tuple[str, ...] = ()
    durations: tuple[str, ...] = ()
    amounts: tuple[str, ...] = ()
    locations: tuple[str, ...] = ()
    source_ids: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    status: FactStatus = FactStatus.NOT_DETECTED

    def protected_values(self) -> set[str]:
        values: set[str] = set()
        for group in (
            self.procedure_ids,
            self.cigs,
            self.critical_days,
            self.durations,
            self.amounts,
            self.locations,
        ):
            values.update(group)
        return values

    def protected_numbers(self) -> set[str]:
        numbers: set[str] = set()
        for value in self.protected_values():
            numbers.update(_NUMBER_RE.findall(value))
        return numbers


@dataclass(frozen=True)
class GuardrailValidationResult:
    status: str
    safe_answer: str
    failures: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


def _normalize(text: str) -> str:
    return " ".join(str(text or "").casefold().split())


def _unique(values: Sequence[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = " ".join(str(value or "").strip().split())
        if not cleaned:
            continue
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(cleaned)
    return tuple(result)


def classify_chunk_procedure(text: str) -> ProcedureLabel:
    normalized = _normalize(text)
    scores = {
        label: sum(1 for anchor in anchors if anchor in normalized)
        for label, anchors in PROCEDURE_ANCHORS.items()
    }
    best_label, best_score = max(scores.items(), key=lambda item: item[1])
    if best_score <= 0:
        return "non_attribuibile"
    tied = [label for label, score in scores.items() if score == best_score]
    return best_label if len(tied) == 1 else "non_attribuibile"


def _source_id(item: Mapping[str, Any], index: int) -> str:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), Mapping) else {}
    chunk_id = metadata.get("chunk_index") or metadata.get("chunk_id") or index
    return f"chunk:{chunk_id}"


def _extract_all(pattern: re.Pattern[str], text: str) -> tuple[str, ...]:
    values: list[str] = []
    for match in pattern.finditer(text):
        value = match.group(1) if match.groups() else match.group(0)
        values.append(value)
    return _unique(values)


def _extract_day_values(text: str) -> tuple[str, ...]:
    return _unique([f"{value} giorni" for value in _extract_all(_DAY_RE, text)])


def _extract_month_values(text: str) -> tuple[str, ...]:
    return _unique([f"{value} mesi" for value in _extract_all(_MONTH_RE, text)])


def _detect_conflicts(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    return (field_name,) if len(values) > 1 else ()


def build_fact_sheet(
    context_items: Sequence[Mapping[str, Any]],
    *,
    query: str,
) -> FactSheet:
    labels = [
        label
        for item in context_items
        if (label := classify_chunk_procedure(str(item.get("text") or ""))) != "non_attribuibile"
    ]
    query_label = classify_chunk_procedure(query)
    if query_label != "non_attribuibile":
        labels.insert(0, query_label)

    procedure_label = _unique(labels)[0] if labels else "non_attribuibile"
    source_ids: list[str] = []
    procedure_ids: list[str] = []
    cigs: list[str] = []
    critical_days: list[str] = []
    durations: list[str] = []
    amounts: list[str] = []
    locations: list[str] = []

    for index, item in enumerate(context_items):
        text = str(item.get("text") or "")
        if not text:
            continue
        source_ids.append(_source_id(item, index))
        procedure_ids.extend(_extract_all(_PROCEDURE_ID_RE, text))
        cigs.extend(_extract_all(_CIG_RE, text))
        critical_days.extend(_extract_day_values(text))
        durations.extend(_extract_month_values(text))
        amounts.extend(_extract_all(_MONEY_RE, text))
        locations.extend(_extract_all(_ADDRESS_RE, text))

    normalized_procedure_ids = _unique(procedure_ids)
    normalized_cigs = _unique(cigs)
    normalized_days = _unique(critical_days)
    normalized_durations = _unique(durations)
    normalized_amounts = _unique(amounts)
    normalized_locations = _unique(locations)
    conflicts = (
        *_detect_conflicts(normalized_cigs, "cig"),
        *_detect_conflicts(normalized_procedure_ids, "procedure_id"),
    )
    has_values = any(
        (
            normalized_procedure_ids,
            normalized_cigs,
            normalized_days,
            normalized_durations,
            normalized_amounts,
            normalized_locations,
        )
    )
    status = FactStatus.CONFLICT if conflicts else (
        FactStatus.VERIFIED if has_values else FactStatus.NOT_DETECTED
    )

    return FactSheet(
        procedure_label=procedure_label,
        procedure_ids=normalized_procedure_ids,
        cigs=normalized_cigs,
        critical_days=normalized_days,
        durations=normalized_durations,
        amounts=normalized_amounts,
        locations=normalized_locations,
        source_ids=_unique(source_ids),
        conflicts=tuple(conflicts),
        status=status,
    )
```

- [ ] **Step 2: Run tests**

Run:

```bash
cd backend
PYTHONPATH=. uv run --no-project --with pytest --with pydantic-settings --with pydantic pytest -q tests/test_rag_procedure_guardrails.py -q
```

Expected: segmentation and extraction tests pass; validation tests still fail because `validate_guarded_answer` is not implemented.

- [ ] **Step 3: Commit implementation**

```bash
git add backend/app/rag/procedure_guardrails.py backend/tests/test_rag_procedure_guardrails.py
git commit -m "add rag procedure fact sheet extraction"
```

---

### Task 3: Implement Blocking Answer Validation

**Files:**
- Modify: `backend/app/rag/procedure_guardrails.py`
- Test: `backend/tests/test_rag_procedure_guardrails.py`

- [ ] **Step 1: Add validator functions**

Append this code to `backend/app/rag/procedure_guardrails.py`:

```python
_PLACEHOLDER_RE = re.compile(
    r"\b(?:entro|fino a|non oltre)\s+giorni\b|\bCIG\s+[A-Z0-9]{0,7}\b",
    re.IGNORECASE,
)
_PARAGRAPH_SPLIT_RE = re.compile(r"\n\s*\n+")


def _answer_procedure_labels(answer: str) -> set[ProcedureLabel]:
    normalized = _normalize(answer)
    return {
        label
        for label, anchors in PROCEDURE_ANCHORS.items()
        if any(anchor in normalized for anchor in anchors)
    }


def _allows_comparison(answer: str) -> bool:
    normalized = _normalize(answer)
    return any(term in normalized for term in ("confront", "compar", "distingu", "separ"))


def _duplicate_paragraph_failures(answer: str) -> tuple[str, ...]:
    seen: set[str] = set()
    failures: list[str] = []
    for block in _PARAGRAPH_SPLIT_RE.split(str(answer or "").strip()):
        normalized = _normalize(block)
        if not normalized:
            continue
        if normalized in seen:
            failures.append("duplicate_paragraph")
            break
        seen.add(normalized)
    return tuple(failures)


def _unverified_number_failures(answer: str, fact_sheet: FactSheet) -> tuple[str, ...]:
    allowed = fact_sheet.protected_numbers()
    failures: list[str] = []
    for number in _NUMBER_RE.findall(answer):
        normalized_number = number.replace(".", "").replace(",", "")
        allowed_normalized = {value.replace(".", "").replace(",", "") for value in allowed}
        if normalized_number not in allowed_normalized:
            failures.append(f"unverified_number:{number}")
    return tuple(failures)


def validate_guarded_answer(
    *,
    answer: str,
    fact_sheet: FactSheet,
    guarded: bool,
) -> GuardrailValidationResult:
    if not guarded:
        return GuardrailValidationResult(status="PASS", safe_answer=answer)

    failures: list[str] = []
    if fact_sheet.status == FactStatus.CONFLICT:
        failures.append("fact_sheet_conflict")
    if _PLACEHOLDER_RE.search(answer):
        failures.append("numeric_placeholder")
    failures.extend(_duplicate_paragraph_failures(answer))
    failures.extend(_unverified_number_failures(answer, fact_sheet))

    labels = _answer_procedure_labels(answer)
    if len(labels) > 1 and not _allows_comparison(answer):
        failures.append("cross_procedure_mixing")
    if fact_sheet.procedure_label in {"OSCAT", "SCT"}:
        other_labels = labels - {fact_sheet.procedure_label}
        if other_labels and not _allows_comparison(answer):
            failures.append("wrong_procedure_label")

    if failures:
        return GuardrailValidationResult(
            status="BLOCK",
            safe_answer=BLOCKED_OUTPUT_MESSAGE,
            failures=_unique(failures),
        )
    return GuardrailValidationResult(status="PASS", safe_answer=answer)
```

- [ ] **Step 2: Run tests**

Run:

```bash
cd backend
PYTHONPATH=. uv run --no-project --with pytest --with pydantic-settings --with pydantic pytest -q tests/test_rag_procedure_guardrails.py -q
```

Expected: all tests in `test_rag_procedure_guardrails.py` pass.

- [ ] **Step 3: Commit validator**

```bash
git add backend/app/rag/procedure_guardrails.py backend/tests/test_rag_procedure_guardrails.py
git commit -m "add rag guarded answer validation"
```

---

### Task 4: Build Guarded Context And Fact Table In The Engine

**Files:**
- Modify: `backend/app/rag/engine.py`
- Test: `backend/tests/test_rag_procedure_guardrails.py`

- [ ] **Step 1: Add engine-level tests**

Append these tests to `backend/tests/test_rag_procedure_guardrails.py`:

```python
from types import SimpleNamespace

from app.rag.engine import HybridRAGEngine, QueryMode, RAGQuery


class RagEngineGuardrailContextTests(unittest.IsolatedAsyncioTestCase):
    async def test_retrieved_context_contains_fact_sheet_for_tender_overview(self) -> None:
        engine = HybridRAGEngine()
        engine.dense_retriever = SimpleNamespace(
            search=lambda **kwargs: [
                SimpleNamespace(
                    text="OSCAT usa GitLab, Sonar, Nexus. CIG B123456789. Durata 48 mesi.",
                    score=0.91,
                    metadata={"chunk_index": 11, "page_number": 4},
                )
            ]
        )
        engine.sparse_retriever = None
        engine.graph_retriever = None
        engine.reranker = SimpleNamespace(rerank=lambda **kwargs: kwargs["results"])

        retrieved = await engine._retrieve_context_and_sources(
            RAGQuery(
                text="descrivimi la gara OSCAT evidenzia punti critici",
                mode=QueryMode.QA,
                retrievers={"dense": True, "sparse": False, "graph": False},
            )
        )

        self.assertIn("FACT_SHEET_START", retrieved.context)
        self.assertIn("procedura: OSCAT", retrieved.context)
        self.assertIn("CIG B123456789", retrieved.context)
        self.assertIn("48 mesi", retrieved.context)
        self.assertIn("SOURCE_START", retrieved.context)
```

- [ ] **Step 2: Import guardrail helpers in `engine.py`**

Add imports near other RAG imports:

```python
from app.rag.procedure_guardrails import (
    FactSheet,
    build_fact_sheet,
)
```

- [ ] **Step 3: Add context formatting helpers to `HybridRAGEngine`**

Add these methods near `_build_context_with_doc_tags`:

```python
    def _query_uses_procedure_guardrails(self, rag_query: RAGQuery) -> bool:
        return rag_query.mode == QueryMode.QA and self._query_requests_structured_tender_overview(
            rag_query.text
        )

    def _format_fact_sheet(self, fact_sheet: FactSheet) -> str:
        return "\n".join(
            [
                "FACT_SHEET_START",
                f"procedura: {fact_sheet.procedure_label}",
                f"stato_verifica: {fact_sheet.status.value}",
                f"procedure_id: {', '.join(fact_sheet.procedure_ids) or 'non_rilevato'}",
                f"cig: {', '.join(f'CIG {value}' for value in fact_sheet.cigs) or 'non_rilevato'}",
                f"giorni_critici: {', '.join(fact_sheet.critical_days) or 'non_rilevato'}",
                f"durata: {', '.join(fact_sheet.durations) or 'non_rilevato'}",
                f"importi: {', '.join(fact_sheet.amounts) or 'non_rilevato'}",
                f"sedi_luoghi: {', '.join(fact_sheet.locations) or 'non_rilevato'}",
                f"fonti: {', '.join(fact_sheet.source_ids) or 'non_rilevato'}",
                f"conflitti: {', '.join(fact_sheet.conflicts) or 'nessuno'}",
                "FACT_SHEET_END",
            ]
        )

    def _build_context_with_source_envelopes(
        self,
        context_texts: list[str],
        sources: list[dict],
        *,
        fact_sheet: FactSheet | None,
    ) -> str:
        parts: list[str] = []
        if fact_sheet is not None:
            parts.append(self._format_fact_sheet(fact_sheet))
        for index, (text, source) in enumerate(zip(context_texts, sources, strict=False)):
            metadata = source.get("metadata", {})
            doc_id = metadata.get("chunk_index", index)
            page = metadata.get("page_number", "?")
            procedure = metadata.get("procedure_label") or "non_attribuibile"
            cleaned = str(text or "").strip()
            cleaned = re.sub(r"^#{1,4}\s+.+\n", "", cleaned, flags=re.MULTILINE)
            parts.append(
                f"SOURCE_START id={doc_id} page={page} procedure={procedure}\n"
                f"{cleaned}\n"
                "SOURCE_END"
            )
        return "\n\n".join(parts)
```

- [ ] **Step 4: Build the fact sheet inside `_retrieve_context_and_sources`**

Replace the final `return RetrievedContext(...)` block with:

```python
        fact_sheet = None
        if self._query_uses_procedure_guardrails(rag_query):
            fact_sheet = build_fact_sheet(context_items, query=rag_query.text)
            for source in sources:
                source["metadata"] = {
                    **source.get("metadata", {}),
                    "procedure_label": fact_sheet.procedure_label,
                    "fact_sheet_status": fact_sheet.status.value,
                }

        return RetrievedContext(
            context=self._build_context_with_source_envelopes(
                context_texts,
                sources,
                fact_sheet=fact_sheet,
            ),
            sources=sources,
        )
```

- [ ] **Step 5: Run tests**

Run:

```bash
cd backend
PYTHONPATH=. uv run --no-project --with pytest --with fastapi --with httpx --with pydantic-settings --with pydantic --with sqlalchemy --with asyncpg --with structlog --with qdrant-client --with rank-bm25 --with numpy --with neo4j --with python-jose --with passlib --with email-validator --with slowapi pytest -q tests/test_rag_procedure_guardrails.py -q
```

Expected: guardrail context test passes.

- [ ] **Step 6: Commit engine context changes**

```bash
git add backend/app/rag/engine.py backend/tests/test_rag_procedure_guardrails.py
git commit -m "add guarded fact sheet context"
```

---

### Task 5: Update Tender Overview Prompt Contract

**Files:**
- Modify: `backend/app/rag/generator.py`
- Modify: `backend/tests/test_rag_anonymizer_routing.py`

- [ ] **Step 1: Add prompt contract test**

Add this test near other prompt template tests in `backend/tests/test_rag_anonymizer_routing.py`:

```python
def test_tender_overview_prompt_requires_fact_sheet_before_narrative(self) -> None:
    template = PROMPT_TEMPLATES["tender_overview"]

    self.assertIn("FACT_SHEET_START", template)
    self.assertIn("Fatti verificati", template)
    self.assertIn("Non usare numeri, CIG, importi, indirizzi o soggetti assenti dalla fact sheet", template)
    self.assertIn("Se stato_verifica e conflitto", template)
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
cd backend
PYTHONPATH=. uv run --no-project --with pytest --with fastapi --with httpx --with pydantic-settings --with pydantic --with sqlalchemy --with asyncpg --with structlog --with qdrant-client --with rank-bm25 --with numpy --with neo4j --with python-jose --with passlib --with email-validator --with slowapi pytest -q tests/test_rag_anonymizer_routing.py::RAGAnonymizerRoutingTests::test_tender_overview_prompt_requires_fact_sheet_before_narrative -q
```

Expected: fail until template is changed.

- [ ] **Step 3: Replace `tender_overview` template rules**

In `backend/app/rag/generator.py`, update the start of `PROMPT_TEMPLATES["tender_overview"]` so it contains:

```python
    "tender_overview": """[SYSTEM RULES - CRITICAL FOR TENDER RESPONSE PREPARATION]

Usa SOLO il contesto recuperato. Il contesto contiene una sezione FACT_SHEET_START / FACT_SHEET_END e poi una serie di SOURCE_START / SOURCE_END.

Regole obbligatorie:
- Prima produci una sezione "Fatti verificati" con i campi presenti nella fact sheet.
- Poi produci la sezione narrativa richiesta dall'utente.
- Non usare numeri, CIG, importi, indirizzi o soggetti assenti dalla fact sheet.
- Non unire OSCAT e SCT se la domanda non chiede esplicitamente un confronto.
- Se stato_verifica e conflitto, rispondi solo: output bloccato: conflitto o dato non verificato.
- Se un dato e indicato come non_rilevato, scrivi non rilevato e non inferire.
- Non ripetere paragrafi o introduzioni.

Rispondi nella STESSA LINGUA della domanda.
[END RULES]

Contesto recuperato:
{context}

Domanda:
{query}

{response_constraints}

Risposta strutturata:
""",
```

- [ ] **Step 4: Run prompt tests**

Run:

```bash
cd backend
PYTHONPATH=. uv run --no-project --with pytest --with fastapi --with httpx --with pydantic-settings --with pydantic --with sqlalchemy --with asyncpg --with structlog --with qdrant-client --with rank-bm25 --with numpy --with neo4j --with python-jose --with passlib --with email-validator --with slowapi pytest -q tests/test_rag_anonymizer_routing.py tests/test_rag_prompt_leakage_loop.py -q
```

Expected: pass or only fail on older assertions that contradict the new fact-sheet-first contract; update those assertions to the new wording if needed.

- [ ] **Step 5: Commit prompt contract**

```bash
git add backend/app/rag/generator.py backend/tests/test_rag_anonymizer_routing.py
git commit -m "tighten tender overview fact sheet prompt"
```

---

### Task 6: Wire Blocking Validation Into Non-Streamed And Streamed RAG

**Files:**
- Modify: `backend/app/rag/engine.py`
- Test: `backend/tests/test_rag_procedure_guardrails.py`
- Test: `backend/tests/test_rag_prompt_leakage_loop.py`

- [ ] **Step 1: Add tests for final blocking**

Append this test to `backend/tests/test_rag_procedure_guardrails.py`:

```python
class RagEngineGuardrailValidationTests(unittest.IsolatedAsyncioTestCase):
    async def test_query_blocks_answer_with_unverified_number_after_generation(self) -> None:
        engine = HybridRAGEngine()
        engine.ensure_initialized = AsyncMock()
        engine._retrieve_context_and_sources = AsyncMock(
            return_value=SimpleNamespace(
                context=(
                    "FACT_SHEET_START\n"
                    "procedura: OSCAT\n"
                    "stato_verifica: verificato\n"
                    "cig: CIG B123456789\n"
                    "durata: 48 mesi\n"
                    "FACT_SHEET_END\n"
                    "SOURCE_START id=1 page=1 procedure=OSCAT\n"
                    "OSCAT usa GitLab. CIG B123456789. Durata 48 mesi.\n"
                    "SOURCE_END"
                ),
                sources=[],
            )
        )
        engine._prepare_generation_route = AsyncMock(
            return_value=(
                SimpleNamespace(provider="llama"),
                {"context": "", "query": "descrivimi la gara OSCAT"},
                SimpleNamespace(value="internal"),
                False,
                None,
                False,
            )
        )
        engine._generate = AsyncMock(
            return_value=SimpleNamespace(
                text="La gara OSCAT dura 48 mesi e include una fase da 270 giorni.",
                model="test",
                completion_tokens=20,
            )
        )

        response = await engine.query(
            RAGQuery(
                text="descrivimi la gara OSCAT evidenzia punti critici",
                mode=QueryMode.QA,
            )
        )

        self.assertEqual(response.answer, BLOCKED_OUTPUT_MESSAGE)
```

Add imports at the top of the test file:

```python
from unittest.mock import AsyncMock
from app.rag.procedure_guardrails import BLOCKED_OUTPUT_MESSAGE
```

- [ ] **Step 2: Add validation extraction helpers to `engine.py`**

Import:

```python
from app.rag.procedure_guardrails import (
    BLOCKED_OUTPUT_MESSAGE,
    FactSheet,
    FactStatus,
    build_fact_sheet,
    validate_guarded_answer,
)
```

Add methods:

```python
    def _fact_sheet_from_context(self, context: str) -> FactSheet | None:
        match = re.search(r"FACT_SHEET_START\n(?P<body>.*?)\nFACT_SHEET_END", context, re.DOTALL)
        if not match:
            return None
        body = match.group("body")
        values: dict[str, str] = {}
        for line in body.splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            values[key.strip()] = value.strip()

        def split_values(key: str, prefix: str = "") -> tuple[str, ...]:
            raw = values.get(key, "")
            if raw in {"", "non_rilevato", "nessuno"}:
                return ()
            items = tuple(part.strip() for part in raw.split(",") if part.strip())
            if prefix:
                return tuple(item.removeprefix(prefix).strip() for item in items)
            return items

        status_value = values.get("stato_verifica", FactStatus.NOT_DETECTED.value)
        status = FactStatus(status_value) if status_value in FactStatus._value2member_map_ else FactStatus.NOT_DETECTED
        return FactSheet(
            procedure_label=values.get("procedura", "non_attribuibile"),
            procedure_ids=split_values("procedure_id"),
            cigs=split_values("cig", "CIG "),
            critical_days=split_values("giorni_critici"),
            durations=split_values("durata"),
            amounts=split_values("importi"),
            locations=split_values("sedi_luoghi"),
            source_ids=split_values("fonti"),
            conflicts=split_values("conflitti"),
            status=status,
        )

    def _apply_generation_guardrails(
        self,
        rag_query: RAGQuery,
        *,
        context: str,
        answer: str,
    ) -> str:
        if not self._query_uses_procedure_guardrails(rag_query):
            return answer
        fact_sheet = self._fact_sheet_from_context(context)
        if fact_sheet is None:
            return answer
        result = validate_guarded_answer(
            answer=answer,
            fact_sheet=fact_sheet,
            guarded=True,
        )
        if result.status == "BLOCK":
            logger.warning(
                "RAG guarded answer blocked",
                failures=result.failures,
                procedure_label=fact_sheet.procedure_label,
            )
        return result.safe_answer
```

- [ ] **Step 3: Apply validation after final cleanup**

In `query`, after final cleanup and deanonymization handling, apply:

```python
        generation_result = replace(
            generation_result,
            text=self._apply_generation_guardrails(
                rag_query,
                context=context,
                answer=generation_result.text,
            ),
        )
```

Place this after `_clean_final_answer_text(...)` and after deanonymization if deanonymized values can introduce protected facts. If anonymizer redaction changes values, place it after deanonymization.

- [ ] **Step 4: Ensure streamed guarded queries use full query path**

Update `_should_buffer_stream_for_quality`:

```python
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
```

- [ ] **Step 5: Run validation tests**

Run:

```bash
cd backend
PYTHONPATH=. uv run --no-project --with pytest --with fastapi --with httpx --with pydantic-settings --with pydantic --with sqlalchemy --with asyncpg --with structlog --with qdrant-client --with rank-bm25 --with numpy --with neo4j --with python-jose --with passlib --with email-validator --with slowapi pytest -q tests/test_rag_procedure_guardrails.py tests/test_rag_prompt_leakage_loop.py -q
```

Expected: pass.

- [ ] **Step 6: Commit validation wiring**

```bash
git add backend/app/rag/engine.py backend/tests/test_rag_procedure_guardrails.py backend/tests/test_rag_prompt_leakage_loop.py
git commit -m "block unverified guarded rag answers"
```

---

### Task 7: Add Runtime Configuration In AppSettings

**Files:**
- Modify: `backend/app/api/rag.py`
- Modify: `backend/app/rag/engine.py`
- Test: `backend/tests/test_rag_procedure_guardrails.py`

- [ ] **Step 1: Add config dataclass in `procedure_guardrails.py`**

Add:

```python
GUARDRAIL_SETTINGS_KEY = "rag_guardrails"

DEFAULT_GUARDRAIL_CONFIG: dict[str, Any] = {
    "enabled": True,
    "mode": "block",
    "onlyTenderOverview": True,
    "blockOnConflict": True,
    "blockOnUnverifiedNumbers": True,
    "blockOnCrossProcedureMixing": True,
}


def normalize_guardrail_config(raw: Mapping[str, Any] | None) -> dict[str, Any]:
    incoming = dict(raw or {})
    mode = str(incoming.get("mode", DEFAULT_GUARDRAIL_CONFIG["mode"]))
    return {
        "enabled": bool(incoming.get("enabled", DEFAULT_GUARDRAIL_CONFIG["enabled"])),
        "mode": mode if mode in {"audit", "block"} else "block",
        "onlyTenderOverview": bool(
            incoming.get("onlyTenderOverview", DEFAULT_GUARDRAIL_CONFIG["onlyTenderOverview"])
        ),
        "blockOnConflict": bool(
            incoming.get("blockOnConflict", DEFAULT_GUARDRAIL_CONFIG["blockOnConflict"])
        ),
        "blockOnUnverifiedNumbers": bool(
            incoming.get(
                "blockOnUnverifiedNumbers",
                DEFAULT_GUARDRAIL_CONFIG["blockOnUnverifiedNumbers"],
            )
        ),
        "blockOnCrossProcedureMixing": bool(
            incoming.get(
                "blockOnCrossProcedureMixing",
                DEFAULT_GUARDRAIL_CONFIG["blockOnCrossProcedureMixing"],
            )
        ),
    }
```

- [ ] **Step 2: Add `guardrail_config` to `RAGQuery`**

In `backend/app/rag/engine.py` dataclass `RAGQuery`, add:

```python
    guardrail_config: dict | None = None
```

- [ ] **Step 3: Use config in `_query_uses_procedure_guardrails`**

Replace method with:

```python
    def _query_uses_procedure_guardrails(self, rag_query: RAGQuery) -> bool:
        from app.rag.procedure_guardrails import normalize_guardrail_config

        cfg = normalize_guardrail_config(rag_query.guardrail_config)
        if not cfg["enabled"]:
            return False
        if cfg["onlyTenderOverview"]:
            return rag_query.mode == QueryMode.QA and self._query_requests_structured_tender_overview(
                rag_query.text
            )
        return rag_query.mode == QueryMode.QA and self._query_requests_broad_summary(rag_query.text)
```

- [ ] **Step 4: Load config in `backend/app/api/rag.py`**

Import:

```python
from app.rag.procedure_guardrails import (
    GUARDRAIL_SETTINGS_KEY,
    normalize_guardrail_config,
)
```

Add loader:

```python
async def _load_guardrail_config(db: AsyncSession) -> dict:
    result = await db.execute(select(AppSettings).limit(1))
    row = result.scalar_one_or_none()
    if row and isinstance(row.data, dict):
        return normalize_guardrail_config(row.data.get(GUARDRAIL_SETTINGS_KEY))
    return normalize_guardrail_config(None)
```

In the `RAGQuery(...)` constructor in `rag_query`, add:

```python
        guardrail_config=await _load_guardrail_config(db),
```

- [ ] **Step 5: Add config tests**

Add tests to `backend/tests/test_rag_procedure_guardrails.py`:

```python
from app.rag.procedure_guardrails import normalize_guardrail_config


class RagGuardrailConfigTests(unittest.TestCase):
    def test_default_config_blocks_only_tender_overviews(self) -> None:
        cfg = normalize_guardrail_config(None)

        self.assertTrue(cfg["enabled"])
        self.assertEqual(cfg["mode"], "block")
        self.assertTrue(cfg["onlyTenderOverview"])

    def test_invalid_mode_falls_back_to_block(self) -> None:
        cfg = normalize_guardrail_config({"mode": "loose"})

        self.assertEqual(cfg["mode"], "block")
```

- [ ] **Step 6: Run tests and commit**

Run:

```bash
cd backend
PYTHONPATH=. uv run --no-project --with pytest --with fastapi --with httpx --with pydantic-settings --with pydantic --with sqlalchemy --with asyncpg --with structlog --with qdrant-client --with rank-bm25 --with numpy --with neo4j --with python-jose --with passlib --with email-validator --with slowapi pytest -q tests/test_rag_procedure_guardrails.py tests/test_planningcoverage.py -q
```

Commit:

```bash
git add backend/app/api/rag.py backend/app/rag/engine.py backend/app/rag/procedure_guardrails.py backend/tests/test_rag_procedure_guardrails.py
git commit -m "add runtime rag guardrail config"
```

---

### Task 8: Add Observability And Metrics Logs

**Files:**
- Modify: `backend/app/rag/engine.py`
- Test: `backend/tests/test_rag_procedure_guardrails.py`

- [ ] **Step 1: Add log assertions using a simple monkeypatch**

Add this test:

```python
def test_validation_result_exposes_failure_codes_for_logging(self) -> None:
    sheet = build_fact_sheet(
        [{"text": "OSCAT con CIG B123456789.", "metadata": {}}],
        query="OSCAT",
    )

    result = validate_guarded_answer(
        answer="OSCAT con CIG B123456789 e fase da 270 giorni.",
        fact_sheet=sheet,
        guarded=True,
    )

    self.assertEqual(result.status, "BLOCK")
    self.assertIn("unverified_number:270", result.failures)
```

- [ ] **Step 2: Add structured logs**

In `_retrieve_context_and_sources`, after building `fact_sheet`, log:

```python
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
```

In `_apply_generation_guardrails`, keep:

```python
            logger.warning(
                "RAG guarded answer blocked",
                failures=result.failures,
                procedure_label=fact_sheet.procedure_label,
            )
```

- [ ] **Step 3: Run tests**

Run:

```bash
cd backend
PYTHONPATH=. uv run --no-project --with pytest --with fastapi --with httpx --with pydantic-settings --with pydantic --with sqlalchemy --with asyncpg --with structlog --with qdrant-client --with rank-bm25 --with numpy --with neo4j --with python-jose --with passlib --with email-validator --with slowapi pytest -q tests/test_rag_procedure_guardrails.py -q
```

Expected: pass.

- [ ] **Step 4: Commit logs**

```bash
git add backend/app/rag/engine.py backend/tests/test_rag_procedure_guardrails.py
git commit -m "log rag guardrail outcomes"
```

---

### Task 9: Optional Admin Controls In Planning Coverage Page

**Files:**
- Modify: `backend/app/api/planningcoverage.py`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/pages/PlanningCoverage.tsx`
- Test: `frontend/src/api/client.test.ts`

Use this only after backend guardrails are stable. It exposes `rag_guardrails` settings next to Planning Coverage so admins can choose `audit` or `block`.

- [ ] **Step 1: Add frontend API tests**

Add to `frontend/src/api/client.test.ts`:

```ts
it('updates RAG guardrail config through planning coverage admin endpoint', async () => {
    fetchMock.mockResolvedValue(
        new Response(JSON.stringify({ enabled: true, mode: 'block', onlyTenderOverview: true }), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
        })
    );

    const result = await planningCoverageApi.updateGuardrails({
        enabled: true,
        mode: 'block',
        onlyTenderOverview: true,
    });

    expect(result.mode).toBe('block');
    expect(fetchMock).toHaveBeenCalledWith(
        '/api/planningcoverage/guardrails',
        expect.objectContaining({ method: 'POST' })
    );
});
```

- [ ] **Step 2: Add backend endpoint**

In `backend/app/api/planningcoverage.py`, add `GET/POST /guardrails` using `GUARDRAIL_SETTINGS_KEY` and `normalize_guardrail_config`.

- [ ] **Step 3: Add UI controls**

In `PlanningCoverage.tsx`, add a separate section with:

- checkbox `Enable answer guardrails`
- select `Mode` with `audit` and `block`
- checkbox `Only tender overview`

- [ ] **Step 4: Run frontend tests**

```bash
cd frontend
npm test -- client.test.ts --run
```

- [ ] **Step 5: Commit UI controls**

```bash
git add backend/app/api/planningcoverage.py frontend/src/api/client.ts frontend/src/api/client.test.ts frontend/src/pages/PlanningCoverage.tsx
git commit -m "add admin controls for rag guardrails"
```

---

## Verification Matrix

Run these before claiming completion:

```bash
cd backend
PYTHONPATH=. uv run --no-project --with pytest --with fastapi --with httpx --with pydantic-settings --with pydantic --with sqlalchemy --with asyncpg --with structlog --with qdrant-client --with rank-bm25 --with numpy --with neo4j --with python-jose --with passlib --with email-validator --with slowapi pytest -q \
  tests/test_rag_procedure_guardrails.py \
  tests/test_planningcoverage.py \
  tests/test_rag_critical_coverage.py \
  tests/test_rag_prompt_leakage_loop.py \
  tests/test_rag_tender_overview_longform.py -q
```

```bash
cd backend
PYTHONPATH=. uv run --no-project --with fastapi --with pydantic-settings --with pydantic --with sqlalchemy --with asyncpg --with structlog --with qdrant-client --with rank-bm25 --with numpy --with neo4j --with httpx --with python-jose --with passlib --with email-validator --with slowapi python -m compileall -q app/rag/procedure_guardrails.py app/rag/engine.py app/rag/generator.py app/api/rag.py
```

If Task 9 is implemented:

```bash
cd frontend
npm test -- client.test.ts --run
npm run build
```

## Rollout Notes

- Start with `mode=block` only for structured tender overview queries. This is narrow enough to avoid regressions on normal search, proposal generation, compliance check, and requirement extraction.
- Keep the blocked answer exact and short so frontend and user support can identify the condition.
- Log failures with structured codes; use these codes to decide later whether to relax `unverified_number` for harmless page numbers.
- Do not normalize known real tender values in cleanup functions. Values such as CIG must come from the fact sheet, not from hard-coded corrections.

## Self-Review

- Spec coverage: segmentation, deduplication, fact sheet, prompt guardrails, final blocking gate, and observability are each mapped to a task.
- Placeholder scan: no task relies on unspecified implementation; each code step has concrete file paths and snippets.
- Type consistency: `FactSheet`, `FactStatus`, `GuardrailValidationResult`, `build_fact_sheet`, and `validate_guarded_answer` are introduced before engine integration uses them.

