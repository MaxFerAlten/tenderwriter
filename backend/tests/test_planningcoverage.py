# ruff: noqa: E402
"""Tests for tender planning coverage retrieval."""

from __future__ import annotations

import os
import unittest
from types import SimpleNamespace

_TEST_ENV = {
    "APP_SECRET_KEY": "alpha-key-123456789012345678901234567890",
    "ADMIN_PASSWORD": "test-admin-password-1234567890",
    "DATABASE_URL": "postgresql+asyncpg://tester:securepass@localhost:5432/tenderwriter",
    "NEO4J_PASSWORD": "test-neo4j-password-1234567890",
    "MINIO_SECRET_KEY": "test-minio-password-1234567890",
    "ONLYOFFICE_JWT_SECRET": "office-jwt-token-12345678901234567890",
}
for key, value in _TEST_ENV.items():
    os.environ.setdefault(key, value)

from app.api.planningcoverage import (
    PlanningCoverageConfigPayload,
    PlanningCoverageTestResponse,
)
from app.rag.engine import HybridRAGEngine, QueryMode, RAGQuery
from app.rag.planningcoverage import (
    DEFAULT_PLANNING_COVERAGE_CONFIG,
    classify_query_for_coverage,
    run_planning_coverage,
)


class _FakeReranker:
    def rerank(self, *, query, results, top_k):
        del query
        return results[:top_k]


class _RecordingRetriever:
    def __init__(self, *, marker: str, metadata: dict | None = None) -> None:
        self.marker = marker
        self.metadata = metadata or {}
        self.queries: list[str] = []

    def search(self, query: str, top_k: int | None = None, filters: dict | None = None):
        self.queries.append(query)
        normalized = query.casefold()
        if not any(token in normalized for token in ("cig", "importo", "base asta", "base d'asta")):
            return []
        return [
            SimpleNamespace(
                text=(
                    f"{self.marker}: Lotto 1 - CIG B123456789 - "
                    "importo base d'asta Euro 1.250.000 IVA esclusa."
                ),
                score=3.5,
                metadata={"page_number": 12, **self.metadata},
            )
        ][: top_k or 1]


class _LongformCoverageRetriever:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def search(self, query: str, top_k: int | None = None, filters: dict | None = None):
        del top_k, filters
        self.queries.append(query)
        normalized = query.casefold()
        if "stazione appaltante" in normalized or "procedura" in normalized:
            return [
                SimpleNamespace(
                    text=(
                        "OSCAT per servizi CI/CD. Stazione appaltante Regione Toscana. "
                        "Procedura 012942/2025."
                    ),
                    score=2.8,
                    metadata={"chunk_index": 101, "page_number": 1},
                )
            ]
        if "cig" in normalized:
            return [
                SimpleNamespace(
                    text="OSCAT servizi GitLab, Sonar e Nexus. CIG B123456789.",
                    score=2.7,
                    metadata={"chunk_index": 102, "page_number": 2},
                )
            ]
        if "importo" in normalized or "base d'asta" in normalized or "euro" in normalized:
            return [
                SimpleNamespace(
                    text=(
                        "OSCAT importo a base di gara pari a 5.999.723,60 euro. "
                        "Valore globale stimato pari a 11.172.582,96 euro."
                    ),
                    score=2.6,
                    metadata={"chunk_index": 103, "page_number": 3},
                )
            ]
        if "durata" in normalized or "mesi" in normalized:
            return [
                SimpleNamespace(
                    text="OSCAT durata dell'accordo quadro pari a 48 mesi.",
                    score=2.5,
                    metadata={"chunk_index": 104, "page_number": 4},
                )
            ]
        return [
            SimpleNamespace(
                text="OSCAT usa GitLab, Sonar, Nexus e Vulnerability Assessment.",
                score=3.0,
                metadata={"chunk_index": 100, "page_number": 1},
            )
        ]


class _FirstOnlyReranker:
    def rerank(self, *, query, results, top_k):
        del query, top_k
        return results[:1]


class _StaticRetriever:
    def __init__(self, results: list[SimpleNamespace]) -> None:
        self.results = results

    def search(self, query: str, top_k: int | None = None, filters: dict | None = None):
        del query, filters
        return self.results[: top_k or len(self.results)]


class PlanningCoverageTests(unittest.IsolatedAsyncioTestCase):
    def _enabled_config(self) -> dict:
        config = {
            **DEFAULT_PLANNING_COVERAGE_CONFIG,
            "enabled": True,
            "alwaysRunPlanner": True,
            "globalMaxCoverageChunks": 6,
            "maxSourcesPerSlot": 1,
            "retrievers": {"sparse": True, "dense": True, "graph": False},
        }
        config["slots"] = {
            key: key in {"cig_lots", "amounts"} for key in DEFAULT_PLANNING_COVERAGE_CONFIG["slots"]
        }
        return config

    def test_classifier_runs_all_enabled_slots_for_broad_tender_overview(self) -> None:
        plan = classify_query_for_coverage(
            "Analizza questa gara e recupera i dettagli principali",
            self._enabled_config(),
        )

        self.assertTrue(plan.activated)
        self.assertEqual(plan.query_class, "tender_structured")
        self.assertIn("cig_lots", plan.slots_triggered)
        self.assertIn("amounts", plan.slots_triggered)
        self.assertNotIn("duration", plan.slots_triggered)
        self.assertTrue(any("CIG" in query for query in plan.generated_queries["cig_lots"]))

    def test_default_config_keeps_planner_disabled(self) -> None:
        plan = classify_query_for_coverage(
            "Analizza questa gara e recupera CIG e importi",
            DEFAULT_PLANNING_COVERAGE_CONFIG,
        )

        self.assertFalse(plan.activated)
        self.assertEqual(plan.slots_triggered, [])

    def test_api_payload_preserves_camel_case_contract(self) -> None:
        payload = PlanningCoverageConfigPayload(
            enabled=True,
            topkPerSlot=3,
            maxSourcesPerSlot=2,
            globalMaxCoverageChunks=9,
            minScore=0.4,
            onlyTenderQueries=True,
            alwaysRunPlanner=False,
        )
        dumped = payload.model_dump(by_alias=True)

        self.assertEqual(dumped["topkPerSlot"], 3)
        self.assertEqual(dumped["maxSourcesPerSlot"], 2)
        self.assertEqual(dumped["globalMaxCoverageChunks"], 9)
        self.assertEqual(dumped["minScore"], 0.4)
        self.assertFalse(dumped["alwaysRunPlanner"])

        response = PlanningCoverageTestResponse(
            query_class="tender_structured",
            activated=True,
            slots_triggered=["cig_lots"],
            generated_queries={"cig_lots": ["CIG lotto gara"]},
            notes=[],
        ).model_dump(by_alias=True)

        self.assertEqual(response["queryClass"], "tender_structured")
        self.assertEqual(response["slotsTriggered"], ["cig_lots"])
        self.assertIn("generatedQueries", response)

    async def test_run_planning_coverage_collects_strong_sparse_and_dense_matches(self) -> None:
        sparse = _RecordingRetriever(marker="sparse", metadata={"source": "sparse-fixture"})
        dense = _RecordingRetriever(marker="dense", metadata={"source": "dense-fixture"})

        result = await run_planning_coverage(
            query="Analizza questa gara",
            config=self._enabled_config(),
            filters={"tender_id": 42},
            sparse_retriever=sparse,
            dense_retriever=dense,
        )

        self.assertTrue(result.activated)
        self.assertGreaterEqual(len(result.results), 2)
        self.assertTrue(any("CIG" in query for query in sparse.queries))
        self.assertTrue(any("importo" in query.casefold() for query in dense.queries))
        metadata = result.results[0]["metadata"]
        self.assertTrue(metadata["planning_coverage"])
        self.assertIn(metadata["coverage_slot"], {"cig_lots", "amounts"})
        self.assertIn(metadata["coverage_retriever"], {"sparse", "dense"})
        self.assertEqual(metadata["tender_id"], 42)

    async def test_engine_injects_planning_coverage_sources_only_when_config_enabled(self) -> None:
        engine = HybridRAGEngine()
        engine.dense_retriever = _RecordingRetriever(marker="dense")
        engine.sparse_retriever = _RecordingRetriever(marker="sparse")
        engine.graph_retriever = None
        engine.reranker = _FakeReranker()

        disabled = await engine._retrieve_context_and_sources(
            RAGQuery(
                text="Analizza questa gara",
                mode=QueryMode.SEARCH,
                top_k=5,
                planning_coverage_config=DEFAULT_PLANNING_COVERAGE_CONFIG,
            )
        )
        # The PLANNING-COVERAGE injector is config-gated and must NOT run when
        # disabled: no source may carry a planning-coverage slot provenance
        # (`coverage_slot`/`coverage_slot_label`/`planning_coverage`).
        #
        # Critical-coverage broad-summary retrieval variants are a SEPARATE,
        # independently-gated feature. Post-decontamination the generic base
        # variant "identificativo procedura CIG RUP stazione appaltante"
        # legitimately matches the test corpus and is tagged with
        # `retrieval_variant` (NOT a planning-coverage slot). Tolerating those
        # while still proving the planning-coverage feature stayed off keeps
        # this a real regression guard.
        planning_slot_sources = [
            source
            for source in disabled.sources
            if any(
                key in (source.get("metadata") or {})
                for key in (
                    "coverage_slot",
                    "coverage_slot_label",
                    "planning_coverage",
                )
            )
        ]
        self.assertEqual(
            planning_slot_sources,
            [],
            msg=(
                "planning-coverage injection ran while the config was "
                "disabled (sources carry planning-coverage slot provenance)"
            ),
        )
        # Every disabled-config source that DID surface must be a
        # critical-coverage retrieval variant, never a planning-coverage slot.
        for source in disabled.sources:
            self.assertIn(
                "retrieval_variant",
                source.get("metadata") or {},
                msg=(
                    "unexpected non-retrieval-variant source surfaced with "
                    f"planning-coverage disabled: {source!r}"
                ),
            )

        enabled = await engine._retrieve_context_and_sources(
            RAGQuery(
                text="Analizza questa gara",
                mode=QueryMode.SEARCH,
                top_k=5,
                planning_coverage_config=self._enabled_config(),
            )
        )

        self.assertGreaterEqual(len(enabled.sources), 1)
        self.assertTrue(
            any(source["metadata"].get("coverage_slot") == "cig_lots" for source in enabled.sources)
        )

    async def test_longform_tender_forces_critical_coverage_into_fact_sheet(self) -> None:
        engine = HybridRAGEngine()
        retriever = _LongformCoverageRetriever()
        engine.dense_retriever = retriever
        engine.sparse_retriever = retriever
        engine.graph_retriever = None
        engine.reranker = _FirstOnlyReranker()

        retrieved = await engine._retrieve_context_and_sources(
            RAGQuery(
                text=(
                    "descrivimi dettagliatamente ogni aspetto della gara OSCAT "
                    "della regione toscana in 1500 parole"
                ),
                mode=QueryMode.QA,
                top_k=1,
                retrievers={"dense": True, "sparse": True, "graph": False},
                planning_coverage_config=DEFAULT_PLANNING_COVERAGE_CONFIG,
            )
        )

        self.assertIn("procedure_id: 012942/2025", retrieved.context)
        self.assertIn("durata: 48 mesi", retrieved.context)
        self.assertIn("5.999.723,60 euro", retrieved.context)
        self.assertIn("11.172.582,96 euro", retrieved.context)
        self.assertTrue(any("base d'asta" in query.casefold() for query in retriever.queries))

    async def test_longform_tender_filters_unrequested_integrity_pact_noise(self) -> None:
        engine = HybridRAGEngine()
        engine.dense_retriever = _StaticRetriever(
            [
                SimpleNamespace(
                    text=(
                        "OSCAT usa GitLab, Sonar, Nexus e Vulnerability Assessment. "
                        "Procedura 012942/2025."
                    ),
                    score=3.0,
                    metadata={"chunk_index": 201, "page_number": 1},
                ),
                SimpleNamespace(
                    text=(
                        "Patto di Integrità: soglie economiche, obblighi anticorruzione "
                        "e importi amministrativi eterogenei."
                    ),
                    score=2.9,
                    metadata={"chunk_index": 202, "page_number": 12},
                ),
                SimpleNamespace(
                    text=(
                        "SCT-Tix CCTT ESTAR monitoraggio impianti industriali per il "
                        "Sistema Cloud Toscana."
                    ),
                    score=2.8,
                    metadata={"chunk_index": 203, "page_number": 13},
                ),
            ]
        )
        engine.sparse_retriever = None
        engine.graph_retriever = None
        engine.reranker = _FakeReranker()

        retrieved = await engine._retrieve_context_and_sources(
            RAGQuery(
                text=(
                    "descrivimi dettagliatamente ogni aspetto della gara OSCAT "
                    "della regione toscana in 1500 parole"
                ),
                mode=QueryMode.QA,
                retrievers={"dense": True, "sparse": False, "graph": False},
                planning_coverage_config=DEFAULT_PLANNING_COVERAGE_CONFIG,
            )
        )

        self.assertIn("procedura: OSCAT", retrieved.context)
        self.assertNotIn("Patto di Integrità", retrieved.context)
        self.assertNotIn("SCT-Tix", retrieved.context)
        self.assertNotIn("ESTAR", retrieved.context)

    async def test_longform_tender_keeps_integrity_pact_when_requested(self) -> None:
        engine = HybridRAGEngine()
        engine.dense_retriever = _StaticRetriever(
            [
                SimpleNamespace(
                    text="OSCAT usa GitLab, Sonar, Nexus. Procedura 012942/2025.",
                    score=3.0,
                    metadata={"chunk_index": 301, "page_number": 1},
                ),
                SimpleNamespace(
                    text=(
                        "Patto di Integrità: obblighi anticorruzione applicabili alla "
                        "documentazione amministrativa della gara."
                    ),
                    score=2.9,
                    metadata={"chunk_index": 302, "page_number": 12},
                ),
            ]
        )
        engine.sparse_retriever = None
        engine.graph_retriever = None
        engine.reranker = _FakeReranker()

        retrieved = await engine._retrieve_context_and_sources(
            RAGQuery(
                text=(
                    "descrivimi il Patto di Integrità della gara OSCAT "
                    "della regione toscana in 1000 parole"
                ),
                mode=QueryMode.QA,
                retrievers={"dense": True, "sparse": False, "graph": False},
                planning_coverage_config=DEFAULT_PLANNING_COVERAGE_CONFIG,
            )
        )

        self.assertIn("Patto di Integrità", retrieved.context)


# NOTE on structure: planning-coverage.md has a single `## Messages` section
# parsed as `key: value` pairs (load_localized_messages), NOT `## Header` + `- item`
# bullet groups. So load_keyword_group does not apply here; the decontamination
# guard binds to the parsed slot tuples via get_planning_coverage_messages. The
# "conceptual groups" in the plan map to slot keys: duration, scoring, platform,
# certifications.
class PlanningCoverageDecontaminationTests(unittest.TestCase):
    # Real slot keys (from app/rag/localization._SLOT_KEYS) whose query/trigger/
    # evidence tuples previously pinned Toscana/benchmark-specific literals.
    REAL_SLOTS = ("duration", "scoring", "platform", "certifications")

    FORBIDDEN = (
        "36 mesi",
        '"70"',
        '"80"',
        "sardegnacat",
        "iso/iec 27001",
        "iso/iec 27017",
        "iso/iec 27018",
        "uni/pdr 125",
        "sa 8000",
        "iso 26000",
        "qualificazione acn",
    )

    def test_planning_coverage_base_queries_do_not_force_specific_values(self) -> None:
        from app.rag.localization import get_planning_coverage_messages

        for lang in ("it", "en"):
            get_planning_coverage_messages.cache_clear()
            msgs = get_planning_coverage_messages(lang)
            for slot in self.REAL_SLOTS:
                flat = " ".join(
                    (
                        *msgs.slot_triggers.get(slot, ()),
                        *msgs.slot_queries.get(slot, ()),
                        *msgs.slot_evidence.get(slot, ()),
                    )
                ).casefold()
                for forbidden in self.FORBIDDEN:
                    self.assertNotIn(
                        forbidden,
                        flat,
                        msg=f"{lang}/{slot} still has {forbidden!r}",
                    )

    def test_planning_coverage_still_triggers_duration_scoring_platform_certs(
        self,
    ) -> None:
        # Decontamination must keep the slots meaningful: each genericized slot
        # still fires on its concept and still emits generic tokens.
        from app.rag.localization import get_planning_coverage_messages

        expected_generic = {
            "it": {
                "duration": ("durata", "mesi", "giorni"),
                "scoring": ("punteggio", "offerta tecnica", "criteri"),
                "platform": ("piattaforma", "portale", "spid"),
                "certifications": ("certificazione", "iso", "qualificazione"),
            },
            "en": {
                "duration": ("duration", "months", "days"),
                "scoring": ("score", "technical bid", "criteria"),
                "platform": ("platform", "portal", "spid"),
                "certifications": ("certification", "iso", "qualification"),
            },
        }
        for lang in ("it", "en"):
            get_planning_coverage_messages.cache_clear()
            msgs = get_planning_coverage_messages(lang)
            for slot, tokens in expected_generic[lang].items():
                self.assertTrue(
                    msgs.slot_triggers.get(slot),
                    msg=f"{lang}/{slot} lost its trigger terms",
                )
                self.assertTrue(
                    msgs.slot_queries.get(slot),
                    msg=f"{lang}/{slot} lost its generated queries",
                )
                flat = " ".join(
                    (
                        *msgs.slot_triggers[slot],
                        *msgs.slot_queries[slot],
                        *msgs.slot_evidence.get(slot, ()),
                    )
                ).casefold()
                self.assertTrue(
                    any(tok in flat for tok in tokens),
                    msg=f"{lang}/{slot} dropped all generic tokens {tokens!r}",
                )
        get_planning_coverage_messages.cache_clear()


if __name__ == "__main__":
    unittest.main()
