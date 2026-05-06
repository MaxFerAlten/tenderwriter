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
        self.assertEqual(disabled.sources, [])

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


if __name__ == "__main__":
    unittest.main()
