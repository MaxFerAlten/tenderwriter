"""Unit tests for staged requirement consolidation."""

from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from test_module_loaders import load_models_test_module, load_service_test_module

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

_MODELS = load_models_test_module()
_SERVICE_MODULE = load_service_test_module("app.services.requirement_consolidation")

RequirementCandidate = _MODELS.RequirementCandidate
RequirementExtractionRun = _MODELS.RequirementExtractionRun
build_consolidated_requirement_payloads = _SERVICE_MODULE.build_consolidated_requirement_payloads
rebuild_consolidated_requirements_from_staging = _SERVICE_MODULE.rebuild_consolidated_requirements_from_staging
build_requirement_relation_payloads = _SERVICE_MODULE.build_requirement_relation_payloads
replace_consolidated_requirements = _SERVICE_MODULE.replace_consolidated_requirements
replace_requirement_relations = _SERVICE_MODULE.replace_requirement_relations


class _FakeAsyncSession:
    def __init__(self) -> None:
        self.executed: list[object] = []
        self.added: list[object] = []
        self.flush_count = 0
        self._next_id = 1

    async def execute(self, statement):
        self.executed.append(statement)
        return SimpleNamespace(
            scalars=lambda: SimpleNamespace(all=lambda: []),
        )

    def add(self, instance: object) -> None:
        self.added.append(instance)

    async def flush(self) -> None:
        self.flush_count += 1
        for instance in self.added:
            if getattr(instance, "id", None) is None:
                setattr(instance, "id", self._next_id)
                self._next_id += 1


class RequirementConsolidationTests(unittest.IsolatedAsyncioTestCase):
    async def test_build_consolidated_requirement_payloads_merges_duplicates_and_aggregates_sources(self) -> None:
        latest_run = RequirementExtractionRun(id=12, tender_id=51, extraction_method="heuristic_v1", filename="latest.pdf")
        latest_run.candidates = [
            RequirementCandidate(
                id=101,
                tender_id=51,
                extraction_run_id=12,
                candidate_position=1,
                source_document_ref="tenders/51/latest.pdf",
                source_reference="Section 1",
                summary_text="Provide signed annex A.",
                normalized_text="provide signed annex a",
                priority="high",
                confidence=0.92,
            ),
            RequirementCandidate(
                id=102,
                tender_id=51,
                extraction_run_id=12,
                candidate_position=2,
                source_document_ref="tenders/51/latest.pdf",
                source_reference="Section 2",
                summary_text="Include an implementation plan.",
                normalized_text="include an implementation plan",
                priority="medium",
                confidence=0.61,
            ),
        ]

        older_run = RequirementExtractionRun(id=11, tender_id=51, extraction_method="heuristic_v1", filename="older.pdf")
        older_run.candidates = [
            RequirementCandidate(
                id=91,
                tender_id=51,
                extraction_run_id=11,
                candidate_position=1,
                source_document_ref="tenders/51/older.pdf",
                source_reference="Annex B",
                summary_text="Provide signed annex A.",
                normalized_text="provide signed annex a",
                priority="medium",
                confidence=0.45,
            )
        ]

        payloads = build_consolidated_requirement_payloads([latest_run, older_run])

        self.assertEqual(len(payloads), 2)
        self.assertEqual(payloads[0]["canonical_text"], "Provide signed annex A.")
        self.assertEqual(payloads[0]["priority"], "high")
        self.assertAlmostEqual(payloads[0]["confidence"] or 0.0, 0.92)
        self.assertEqual(payloads[0]["source_count"], 2)
        self.assertEqual(len(payloads[0]["metadata_json"]["sources"]), 2)
        self.assertEqual(set(payloads[0]["metadata_json"]["extraction_run_ids"]), {11, 12})
        self.assertEqual(payloads[0]["metadata_json"]["primary_source"]["candidate_id"], 101)
        self.assertEqual(payloads[0]["metadata_json"]["precedence_policy"], "document_role_v1")
        self.assertEqual(payloads[0]["metadata_json"]["merge_kind"], "cross_document_duplicate")

    async def test_build_consolidated_requirement_payloads_promotes_highest_precedence_document_source(self) -> None:
        base_run = RequirementExtractionRun(
            id=31,
            tender_id=77,
            extraction_method="heuristic_v1",
            filename="disciplinare.pdf",
            source_document_ref="tenders/77/disciplinare.pdf",
        )
        base_run.candidates = [
            RequirementCandidate(
                id=301,
                tender_id=77,
                extraction_run_id=31,
                candidate_position=1,
                source_document_ref="tenders/77/disciplinare.pdf",
                source_reference="Art. 12",
                summary_text="Provide signed annex A.",
                normalized_text="provide signed annex a",
                category="Art. 12",
                priority="medium",
                confidence=0.62,
            )
        ]

        clarification_run = RequirementExtractionRun(
            id=32,
            tender_id=77,
            extraction_method="heuristic_v1",
            filename="chiarimenti-01.pdf",
            source_document_ref="tenders/77/chiarimenti-01.pdf",
        )
        clarification_run.candidates = [
            RequirementCandidate(
                id=302,
                tender_id=77,
                extraction_run_id=32,
                candidate_position=1,
                source_document_ref="tenders/77/chiarimenti-01.pdf",
                source_reference="FAQ 7",
                summary_text="Provide signed annex A with wet signature.",
                normalized_text="provide signed annex a",
                category="FAQ 7",
                priority="high",
                confidence=0.58,
            )
        ]

        payloads = build_consolidated_requirement_payloads([base_run, clarification_run])

        self.assertEqual(len(payloads), 1)
        self.assertEqual(payloads[0]["canonical_text"], "Provide signed annex A with wet signature.")
        self.assertEqual(payloads[0]["priority"], "high")
        self.assertEqual(payloads[0]["category"], "FAQ 7")
        self.assertEqual(payloads[0]["metadata_json"]["primary_source"]["document_role"], "clarification")
        self.assertEqual(
            payloads[0]["metadata_json"]["source_document_roles"],
            ["clarification", "disciplinare"],
        )
        self.assertTrue(payloads[0]["metadata_json"]["cross_document"])

    async def test_build_requirement_relation_payloads_infers_override_from_clarification(self) -> None:
        base_requirement = _MODELS.ConsolidatedRequirement(
            id=401,
            tender_id=77,
            canonical_text="Provide signed annex A.",
            normalized_text="provide signed annex a",
            priority="medium",
            source_count=1,
            consolidation_method="staging_v1",
            review_state="pending",
            metadata_json={
                "primary_source": {
                    "document_role": "disciplinare",
                    "precedence_rank": 50,
                }
            },
        )
        clarification_requirement = _MODELS.ConsolidatedRequirement(
            id=402,
            tender_id=77,
            canonical_text="Provide signed annex A with wet signature.",
            normalized_text="provide signed annex a with wet signature",
            priority="high",
            source_count=1,
            consolidation_method="staging_v1",
            review_state="pending",
            metadata_json={
                "primary_source": {
                    "document_role": "clarification",
                    "precedence_rank": 60,
                }
            },
        )
        unrelated_requirement = _MODELS.ConsolidatedRequirement(
            id=403,
            tender_id=77,
            canonical_text="Submit cyber insurance certificate.",
            normalized_text="submit cyber insurance certificate",
            priority="high",
            source_count=1,
            consolidation_method="staging_v1",
            review_state="pending",
            metadata_json={
                "primary_source": {
                    "document_role": "capitolato",
                    "precedence_rank": 40,
                }
            },
        )

        relation_payloads = build_requirement_relation_payloads(
            [base_requirement, clarification_requirement, unrelated_requirement]
        )

        self.assertEqual(len(relation_payloads), 1)
        self.assertEqual(relation_payloads[0]["relation_type"], "overrides")
        self.assertEqual(relation_payloads[0]["source_requirement_id"], 402)
        self.assertEqual(relation_payloads[0]["target_requirement_id"], 401)
        self.assertGreaterEqual(relation_payloads[0]["confidence"], 0.8)
        self.assertEqual(
            relation_payloads[0]["metadata_json"]["inference_method"],
            "lexical_override_v1",
        )
        self.assertIn("annex", relation_payloads[0]["metadata_json"]["shared_terms"])

    async def test_build_requirement_relation_payloads_infers_depends_on_from_explicit_clause(self) -> None:
        dependency_requirement = _MODELS.ConsolidatedRequirement(
            id=451,
            tender_id=79,
            canonical_text="Submit the final commercial offer after presenting the technical plan.",
            normalized_text="submit the final commercial offer after presenting the technical plan",
            priority="high",
            source_count=1,
            consolidation_method="staging_v1",
            review_state="pending",
            metadata_json={
                "primary_source": {
                    "document_role": "disciplinare",
                    "precedence_rank": 50,
                }
            },
        )
        prerequisite_requirement = _MODELS.ConsolidatedRequirement(
            id=452,
            tender_id=79,
            canonical_text="Present the technical plan.",
            normalized_text="present the technical plan",
            priority="medium",
            source_count=1,
            consolidation_method="staging_v1",
            review_state="pending",
            metadata_json={
                "primary_source": {
                    "document_role": "disciplinare",
                    "precedence_rank": 50,
                }
            },
        )
        unrelated_requirement = _MODELS.ConsolidatedRequirement(
            id=453,
            tender_id=79,
            canonical_text="Provide the signed declaration of absence of conflict.",
            normalized_text="provide the signed declaration of absence of conflict",
            priority="medium",
            source_count=1,
            consolidation_method="staging_v1",
            review_state="pending",
            metadata_json={
                "primary_source": {
                    "document_role": "disciplinare",
                    "precedence_rank": 50,
                }
            },
        )

        relation_payloads = build_requirement_relation_payloads(
            [dependency_requirement, prerequisite_requirement, unrelated_requirement]
        )

        depends_on_payloads = [
            item for item in relation_payloads if item["relation_type"] == "depends_on"
        ]
        self.assertEqual(len(depends_on_payloads), 1)
        self.assertEqual(depends_on_payloads[0]["source_requirement_id"], 451)
        self.assertEqual(depends_on_payloads[0]["target_requirement_id"], 452)
        self.assertGreaterEqual(depends_on_payloads[0]["confidence"], 0.6)
        self.assertEqual(
            depends_on_payloads[0]["metadata_json"]["inference_method"],
            "dependency_clause_v1",
        )
        self.assertIn("technical", depends_on_payloads[0]["metadata_json"]["shared_terms"])
        self.assertIn("technical plan", depends_on_payloads[0]["metadata_json"]["matched_clause"])

    async def test_rebuild_consolidated_requirements_from_staging_replaces_rows(self) -> None:
        db = _FakeAsyncSession()
        extraction_run = RequirementExtractionRun(id=22, tender_id=52, extraction_method="heuristic_v1", filename="rfp.pdf")
        extraction_run.candidates = [
            RequirementCandidate(
                id=201,
                tender_id=52,
                extraction_run_id=22,
                candidate_position=1,
                source_document_ref="tenders/52/rfp.pdf",
                source_reference="Section 7",
                summary_text="Submit insurance certificate.",
                normalized_text="submit insurance certificate",
                priority="high",
                confidence=0.83,
            )
        ]

        with patch.object(
            _SERVICE_MODULE,
            "list_staged_requirement_candidate_runs",
            AsyncMock(return_value=[extraction_run]),
        ) as list_mock, patch.object(
            _SERVICE_MODULE,
            "_load_existing_consolidated_requirements",
            AsyncMock(return_value=[]),
        ), patch.object(
            _SERVICE_MODULE,
            "_load_existing_requirement_relations",
            AsyncMock(return_value=[]),
        ):
            rows = await rebuild_consolidated_requirements_from_staging(
                db,
                tender_id=52,
                limit_runs=3,
            )

        list_mock.assert_awaited_once_with(db, tender_id=52, limit_runs=3)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].tender_id, 52)
        self.assertEqual(rows[0].canonical_text, "Submit insurance certificate.")
        self.assertEqual(rows[0].priority, "high")
        self.assertEqual(rows[0].source_count, 1)
        self.assertEqual(rows[0].consolidation_method, "staging_v1")
        self.assertEqual(rows[0].graph_state, "active")
        self.assertEqual(rows[0].metadata_json["primary_source"]["document_role"], "other")
        relation_rows = [item for item in db.added if item.__class__.__name__ == "RequirementRelation"]
        self.assertEqual(len(relation_rows), 0)
        self.assertGreaterEqual(db.flush_count, 1)

    async def test_replace_consolidated_requirements_preserves_review_state_and_obsoletes_missing_rows(self) -> None:
        db = _FakeAsyncSession()
        existing_row = _MODELS.ConsolidatedRequirement(
            id=610,
            tender_id=88,
            canonical_text="Provide signed annex A.",
            normalized_text="provide signed annex a",
            priority="medium",
            source_count=1,
            consolidation_method="staging_v1",
            review_state="approved",
            graph_state="active",
            metadata_json={
                "review_count": 2,
                "latest_review": {"action": "approve"},
                "manual_tag": "keep",
            },
        )
        missing_row = _MODELS.ConsolidatedRequirement(
            id=611,
            tender_id=88,
            canonical_text="Legacy requirement.",
            normalized_text="legacy requirement",
            priority="low",
            source_count=1,
            consolidation_method="staging_v1",
            review_state="changes_requested",
            graph_state="active",
            metadata_json={"review_count": 1},
        )

        with patch.object(
            _SERVICE_MODULE,
            "_load_existing_consolidated_requirements",
            AsyncMock(return_value=[existing_row, missing_row]),
        ):
            rows = await replace_consolidated_requirements(
                db,
                tender_id=88,
                consolidated_items=[
                    {
                        "canonical_text": "Provide signed annex A with wet signature.",
                        "normalized_text": "provide signed annex a",
                        "category": "FAQ 7",
                        "priority": "high",
                        "confidence": 0.88,
                        "source_count": 2,
                        "consolidation_method": "staging_v1",
                        "review_state": "pending",
                        "metadata_json": {
                            "primary_source": {"document_role": "clarification"},
                        },
                    }
                ],
            )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].id, 610)
        self.assertEqual(rows[0].canonical_text, "Provide signed annex A with wet signature.")
        self.assertEqual(rows[0].review_state, "approved")
        self.assertEqual(rows[0].graph_state, "active")
        self.assertEqual(rows[0].metadata_json["review_count"], 2)
        self.assertEqual(rows[0].metadata_json["manual_tag"], "keep")
        self.assertEqual(rows[0].metadata_json["lifecycle"]["graph_state"], "active")
        self.assertEqual(missing_row.graph_state, "obsolete")
        self.assertEqual(missing_row.metadata_json["lifecycle"]["graph_state"], "obsolete")
        self.assertEqual(missing_row.metadata_json["lifecycle"]["reason"], "missing_from_latest_rebuild")

    async def test_replace_requirement_relations_preserves_review_state_and_obsoletes_missing_rows(self) -> None:
        db = _FakeAsyncSession()
        existing_relation = _MODELS.RequirementRelation(
            id=710,
            tender_id=89,
            source_requirement_id=801,
            target_requirement_id=802,
            relation_type="depends_on",
            confidence=0.61,
            review_state="approved",
            graph_state="active",
            metadata_json={
                "review_count": 1,
                "latest_review": {"action": "approve"},
                "manual_tag": "keep",
            },
        )
        missing_relation = _MODELS.RequirementRelation(
            id=711,
            tender_id=89,
            source_requirement_id=803,
            target_requirement_id=804,
            relation_type="overrides",
            confidence=0.83,
            review_state="pending",
            graph_state="active",
            metadata_json={"review_count": 1},
        )

        with patch.object(
            _SERVICE_MODULE,
            "_load_existing_requirement_relations",
            AsyncMock(return_value=[existing_relation, missing_relation]),
        ):
            rows = await replace_requirement_relations(
                db,
                tender_id=89,
                relation_items=[
                    {
                        "source_requirement_id": 801,
                        "target_requirement_id": 802,
                        "relation_type": "depends_on",
                        "confidence": 0.77,
                        "review_state": "pending",
                        "metadata_json": {
                            "inference_method": "dependency_clause_v1",
                        },
                    }
                ],
            )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].id, 710)
        self.assertEqual(rows[0].confidence, 0.77)
        self.assertEqual(rows[0].review_state, "approved")
        self.assertEqual(rows[0].graph_state, "active")
        self.assertEqual(rows[0].metadata_json["review_count"], 1)
        self.assertEqual(rows[0].metadata_json["manual_tag"], "keep")
        self.assertEqual(rows[0].metadata_json["lifecycle"]["graph_state"], "active")
        self.assertEqual(missing_relation.graph_state, "obsolete")
        self.assertEqual(missing_relation.metadata_json["lifecycle"]["graph_state"], "obsolete")

    async def test_list_consolidated_requirements_defaults_to_active_graph_state(self) -> None:
        db = _FakeAsyncSession()

        await _SERVICE_MODULE.list_consolidated_requirements(
            db,
            tender_id=90,
        )

        self.assertEqual(len(db.executed), 1)
        self.assertIn("graph_state", str(db.executed[0]))
        self.assertIn(":graph_state_1", str(db.executed[0]))

    async def test_list_requirement_relations_can_load_obsolete_graph_state(self) -> None:
        db = _FakeAsyncSession()

        await _SERVICE_MODULE.list_requirement_relations(
            db,
            tender_id=91,
            graph_state="obsolete",
        )

        self.assertEqual(len(db.executed), 1)
        self.assertIn("graph_state", str(db.executed[0]))
        self.assertIn(":graph_state_1", str(db.executed[0]))


if __name__ == "__main__":
    unittest.main()
