"""Regression and introduction tests for tender requirement candidate APIs."""

from __future__ import annotations

import os
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from test_module_loaders import load_tenders_test_modules

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

_TENDERS_MODULES = load_tenders_test_modules()
_TENDERS_MODULE = _TENDERS_MODULES.tenders

get_tender = _TENDERS_MODULE.get_tender
get_tender_requirement_candidates = _TENDERS_MODULE.get_tender_requirement_candidates
get_tender_consolidated_requirements = _TENDERS_MODULE.get_tender_consolidated_requirements
get_tender_consolidated_requirement_relations = _TENDERS_MODULE.get_tender_consolidated_requirement_relations
get_tender_consolidated_requirement_relation_review_queue = _TENDERS_MODULE.get_tender_consolidated_requirement_relation_review_queue
get_tender_consolidated_requirement_review_queue = _TENDERS_MODULE.get_tender_consolidated_requirement_review_queue
rebuild_tender_consolidated_requirements = _TENDERS_MODULE.rebuild_tender_consolidated_requirements
review_tender_consolidated_requirement_relation = _TENDERS_MODULE.review_tender_consolidated_requirement_relation
review_tender_consolidated_requirement = _TENDERS_MODULE.review_tender_consolidated_requirement

ComplianceStatus = _TENDERS_MODULES.models.ComplianceStatus
ConsolidatedRequirement = _TENDERS_MODULES.models.ConsolidatedRequirement
RequirementCandidate = _TENDERS_MODULES.models.RequirementCandidate
RequirementExtractionRun = _TENDERS_MODULES.models.RequirementExtractionRun
RequirementReview = _TENDERS_MODULES.models.RequirementReview
RequirementRelation = _TENDERS_MODULES.models.RequirementRelation
RequirementRelationReview = _TENDERS_MODULES.models.RequirementRelationReview
Tender = _TENDERS_MODULES.models.Tender
TenderRequirement = _TENDERS_MODULES.models.TenderRequirement
TenderStatus = _TENDERS_MODULES.models.TenderStatus


class TenderRequirementCandidateApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_tender_keeps_materialized_requirements_only(self) -> None:
        tender = Tender(id=31, title="Framework Tender", status=TenderStatus.ACTIVE)
        tender.requirements = [
            TenderRequirement(
                id=4,
                requirement_text="Provide signed annex A",
                category="Section 1",
                priority="high",
                compliance_status=ComplianceStatus.NOT_ADDRESSED,
            )
        ]
        extraction_run = RequirementExtractionRun(
            id=14,
            tender_id=31,
            extraction_method="heuristic_v1",
            candidate_count=1,
        )
        extraction_run.candidates = [
            RequirementCandidate(
                id=17,
                tender_id=31,
                extraction_run_id=14,
                candidate_position=1,
                summary_text="Staged candidate only",
                normalized_text="staged candidate only",
                priority="medium",
            )
        ]
        tender.requirement_extraction_runs = [extraction_run]
        tender.requirement_candidates = list(extraction_run.candidates)
        current_user = SimpleNamespace(id=7, role="admin")

        with patch.object(_TENDERS_MODULE, "check_tender_access", AsyncMock(return_value=tender)):
            response = await get_tender(
                tender_id=31,
                current_user=current_user,
                db=SimpleNamespace(),
            )

        payload = response.model_dump()
        self.assertEqual(len(response.requirements), 1)
        self.assertEqual(response.requirements[0].requirement_text, "Provide signed annex A")
        self.assertNotIn("requirement_candidates", payload)
        self.assertNotIn("requirement_extraction_runs", payload)

    async def test_get_tender_requirement_candidates_keeps_staged_contract_when_consolidated_rows_exist(self) -> None:
        tender = Tender(id=33, title="Services Tender", status=TenderStatus.ACTIVE)
        tender.consolidated_requirements = [
            ConsolidatedRequirement(
                id=71,
                tender_id=33,
                canonical_text="Persisted consolidated row",
                normalized_text="persisted consolidated row",
                priority="medium",
                source_count=1,
                consolidation_method="staging_v1",
                review_state="pending",
            )
        ]
        current_user = SimpleNamespace(id=10, role="admin")
        extraction_run = RequirementExtractionRun(
            id=19,
            tender_id=33,
            source_document_ref="tenders/33/rfp.pdf",
            filename="rfp.pdf",
            extraction_method="heuristic_v1",
            candidate_count=1,
        )
        extraction_run.candidates = [
            RequirementCandidate(
                id=24,
                tender_id=33,
                extraction_run_id=19,
                candidate_position=1,
                source_document_ref="tenders/33/rfp.pdf",
                source_reference="Section 1",
                summary_text="First staged requirement",
                normalized_text="first staged requirement",
                priority="high",
            )
        ]

        with (
            patch.object(_TENDERS_MODULE, "check_tender_access", AsyncMock(return_value=tender)),
            patch.object(
                _TENDERS_MODULE,
                "list_staged_requirement_candidate_runs",
                AsyncMock(return_value=[extraction_run]),
            ),
        ):
            response = await get_tender_requirement_candidates(
                tender_id=33,
                limit_runs=5,
                current_user=current_user,
                db=SimpleNamespace(),
            )

        payload = response.model_dump()
        self.assertEqual(response.total_runs, 1)
        self.assertEqual(response.items[0].candidates[0].summary_text, "First staged requirement")
        self.assertNotIn("consolidated_requirements", payload)
        self.assertNotIn("canonical_text", payload["items"][0]["candidates"][0])

    async def test_get_tender_requirement_candidates_returns_staged_runs(self) -> None:
        tender = Tender(id=32, title="Services Tender", status=TenderStatus.ACTIVE)
        current_user = SimpleNamespace(id=9, role="admin")
        extraction_run = RequirementExtractionRun(
            id=18,
            tender_id=32,
            source_document_ref="tenders/32/rfp.pdf",
            filename="rfp.pdf",
            extraction_method="heuristic_v1",
            candidate_count=2,
            metadata_json={"staged_candidate_count": 2},
            created_at=datetime(2026, 4, 4, 9, 30, tzinfo=timezone.utc),
        )
        extraction_run.candidates = [
            RequirementCandidate(
                id=23,
                tender_id=32,
                extraction_run_id=18,
                candidate_position=2,
                source_document_ref="tenders/32/rfp.pdf",
                source_reference="Section 2",
                summary_text="Second requirement",
                normalized_text="second requirement",
                priority="medium",
                confidence=0.73,
            ),
            RequirementCandidate(
                id=22,
                tender_id=32,
                extraction_run_id=18,
                candidate_position=1,
                source_document_ref="tenders/32/rfp.pdf",
                source_reference="Section 1",
                summary_text="First requirement",
                normalized_text="first requirement",
                priority="high",
                confidence=0.94,
            ),
        ]

        with (
            patch.object(_TENDERS_MODULE, "check_tender_access", AsyncMock(return_value=tender)),
            patch.object(
                _TENDERS_MODULE,
                "list_staged_requirement_candidate_runs",
                AsyncMock(return_value=[extraction_run]),
            ) as list_mock,
        ):
            response = await get_tender_requirement_candidates(
                tender_id=32,
                limit_runs=5,
                current_user=current_user,
                db=SimpleNamespace(),
            )

        list_mock.assert_awaited_once()
        self.assertEqual(response.total_runs, 1)
        self.assertEqual(len(response.items), 1)
        self.assertEqual(response.items[0].filename, "rfp.pdf")
        self.assertEqual(response.items[0].metadata_json["staged_candidate_count"], 2)
        self.assertEqual(
            [candidate.summary_text for candidate in response.items[0].candidates],
            ["First requirement", "Second requirement"],
        )
        self.assertEqual(response.items[0].candidates[0].source_reference, "Section 1")
        self.assertAlmostEqual(response.items[0].candidates[0].confidence or 0.0, 0.94)

    async def test_get_tender_consolidated_requirements_returns_materialized_rows(self) -> None:
        tender = Tender(id=34, title="Complex Tender", status=TenderStatus.ACTIVE)
        current_user = SimpleNamespace(id=11, role="admin")
        fake_db = SimpleNamespace()
        consolidated_row = ConsolidatedRequirement(
            id=81,
            tender_id=34,
            canonical_text="Provide ISO 27001 certificate.",
            normalized_text="provide iso 27001 certificate",
            category="Mandatory Requirements",
            priority="high",
            confidence=0.97,
            source_count=2,
            consolidation_method="staging_v1",
            review_state="pending",
            metadata_json={
                "sources": [{"candidate_id": 1}, {"candidate_id": 2}],
                "primary_source": {"candidate_id": 2, "document_role": "clarification"},
                "source_document_roles": ["clarification", "disciplinare"],
                "precedence_policy": "document_role_v1",
            },
            created_at=datetime(2026, 4, 4, 11, 0, tzinfo=timezone.utc),
        )
        consolidated_row.reviews = [
            RequirementReview(
                id=301,
                tender_id=34,
                consolidated_requirement_id=81,
                actor_id=11,
                action="approve",
                previous_review_state="pending",
                new_review_state="approved",
                notes="Historical review",
            )
        ]

        with (
            patch.object(_TENDERS_MODULE, "check_tender_access", AsyncMock(return_value=tender)),
            patch.object(
                _TENDERS_MODULE,
                "list_consolidated_requirements",
                AsyncMock(return_value=[consolidated_row]),
            ) as list_mock,
        ):
            response = await get_tender_consolidated_requirements(
                tender_id=34,
                current_user=current_user,
                db=fake_db,
            )

        list_mock.assert_awaited_once_with(fake_db, tender_id=34, graph_state="active")
        self.assertEqual(response.total_items, 1)
        self.assertEqual(response.items[0].canonical_text, "Provide ISO 27001 certificate.")
        self.assertEqual(response.items[0].source_count, 2)
        self.assertEqual(response.items[0].graph_state, "active")
        self.assertEqual(len(response.items[0].metadata_json["sources"]), 2)
        self.assertEqual(response.items[0].metadata_json["primary_source"]["document_role"], "clarification")
        self.assertEqual(response.items[0].metadata_json["precedence_policy"], "document_role_v1")
        self.assertNotIn("reviews", response.model_dump()["items"][0])
        self.assertNotIn("relations", response.model_dump()["items"][0])

    async def test_get_tender_consolidated_requirements_can_return_obsolete_rows(self) -> None:
        tender = Tender(id=43, title="Complex Tender", status=TenderStatus.ACTIVE)
        current_user = SimpleNamespace(id=22, role="admin")
        fake_db = SimpleNamespace()
        obsolete_row = ConsolidatedRequirement(
            id=181,
            tender_id=43,
            canonical_text="Legacy requirement no longer present.",
            normalized_text="legacy requirement no longer present",
            category="Historical",
            priority="low",
            confidence=0.42,
            source_count=1,
            consolidation_method="staging_v1",
            review_state="approved",
            graph_state="obsolete",
            metadata_json={"lifecycle": {"graph_state": "obsolete", "reason": "missing_from_latest_rebuild"}},
            created_at=datetime(2026, 4, 8, 9, 0, tzinfo=timezone.utc),
        )

        with (
            patch.object(_TENDERS_MODULE, "check_tender_access", AsyncMock(return_value=tender)),
            patch.object(
                _TENDERS_MODULE,
                "list_consolidated_requirements",
                AsyncMock(return_value=[obsolete_row]),
            ) as list_mock,
        ):
            response = await get_tender_consolidated_requirements(
                tender_id=43,
                graph_state="obsolete",
                current_user=current_user,
                db=fake_db,
            )

        list_mock.assert_awaited_once_with(fake_db, tender_id=43, graph_state="obsolete")
        self.assertEqual(response.total_items, 1)
        self.assertEqual(response.items[0].graph_state, "obsolete")
        self.assertEqual(response.items[0].metadata_json["lifecycle"]["reason"], "missing_from_latest_rebuild")

    async def test_get_tender_consolidated_requirement_relations_returns_inferred_edges(self) -> None:
        tender = Tender(id=39, title="Complex Tender", status=TenderStatus.ACTIVE)
        current_user = SimpleNamespace(id=16, role="admin")
        fake_db = SimpleNamespace()
        source_requirement = ConsolidatedRequirement(
            id=121,
            tender_id=39,
            canonical_text="Provide signed annex A with wet signature.",
            normalized_text="provide signed annex a with wet signature",
            priority="high",
            source_count=1,
            consolidation_method="staging_v1",
            review_state="pending",
        )
        target_requirement = ConsolidatedRequirement(
            id=122,
            tender_id=39,
            canonical_text="Provide signed annex A.",
            normalized_text="provide signed annex a",
            priority="medium",
            source_count=1,
            consolidation_method="staging_v1",
            review_state="pending",
        )
        relation = RequirementRelation(
            id=501,
            tender_id=39,
            source_requirement_id=121,
            target_requirement_id=122,
            relation_type="overrides",
            confidence=0.91,
            metadata_json={
                "inference_method": "lexical_override_v1",
                "shared_terms": ["provide", "signed", "annex"],
            },
        )
        relation.source_requirement = source_requirement
        relation.target_requirement = target_requirement

        with (
            patch.object(_TENDERS_MODULE, "check_tender_access", AsyncMock(return_value=tender)),
            patch.object(
                _TENDERS_MODULE,
                "list_requirement_relations",
                AsyncMock(return_value=[relation]),
            ) as list_mock,
        ):
            response = await get_tender_consolidated_requirement_relations(
                tender_id=39,
                relation_type="overrides",
                current_user=current_user,
                db=fake_db,
            )

        list_mock.assert_awaited_once_with(
            fake_db,
            tender_id=39,
            relation_type="overrides",
            graph_state="active",
        )
        self.assertEqual(response.total_items, 1)
        self.assertEqual(response.items[0].relation_type, "overrides")
        self.assertEqual(response.items[0].source_requirement_text, "Provide signed annex A with wet signature.")
        self.assertEqual(response.items[0].target_requirement_text, "Provide signed annex A.")
        self.assertEqual(response.items[0].review_state, "pending")
        self.assertEqual(response.items[0].graph_state, "active")
        self.assertEqual(response.items[0].metadata_json["inference_method"], "lexical_override_v1")

    async def test_get_tender_consolidated_requirement_relations_filters_depends_on_edges(self) -> None:
        tender = Tender(id=40, title="Complex Tender", status=TenderStatus.ACTIVE)
        current_user = SimpleNamespace(id=17, role="admin")
        fake_db = SimpleNamespace()
        source_requirement = ConsolidatedRequirement(
            id=131,
            tender_id=40,
            canonical_text="Submit the final commercial offer after presenting the technical plan.",
            normalized_text="submit the final commercial offer after presenting the technical plan",
            priority="high",
            source_count=1,
            consolidation_method="staging_v1",
            review_state="pending",
        )
        target_requirement = ConsolidatedRequirement(
            id=132,
            tender_id=40,
            canonical_text="Present the technical plan.",
            normalized_text="present the technical plan",
            priority="medium",
            source_count=1,
            consolidation_method="staging_v1",
            review_state="pending",
        )
        relation = RequirementRelation(
            id=502,
            tender_id=40,
            source_requirement_id=131,
            target_requirement_id=132,
            relation_type="depends_on",
            confidence=0.77,
            metadata_json={
                "inference_method": "dependency_clause_v1",
                "matched_clause": "presenting the technical plan",
            },
        )
        relation.source_requirement = source_requirement
        relation.target_requirement = target_requirement

        with (
            patch.object(_TENDERS_MODULE, "check_tender_access", AsyncMock(return_value=tender)),
            patch.object(
                _TENDERS_MODULE,
                "list_requirement_relations",
                AsyncMock(return_value=[relation]),
            ) as list_mock,
        ):
            response = await get_tender_consolidated_requirement_relations(
                tender_id=40,
                relation_type="depends_on",
                current_user=current_user,
                db=fake_db,
            )

        list_mock.assert_awaited_once_with(
            fake_db,
            tender_id=40,
            relation_type="depends_on",
            graph_state="active",
        )
        self.assertEqual(response.total_items, 1)
        self.assertEqual(response.items[0].relation_type, "depends_on")
        self.assertEqual(response.items[0].source_requirement_id, 131)
        self.assertEqual(response.items[0].target_requirement_id, 132)
        self.assertEqual(response.items[0].review_state, "pending")
        self.assertEqual(response.items[0].graph_state, "active")
        self.assertEqual(response.items[0].metadata_json["inference_method"], "dependency_clause_v1")

    async def test_get_tender_consolidated_requirement_relations_can_return_obsolete_edges(self) -> None:
        tender = Tender(id=44, title="Complex Tender", status=TenderStatus.ACTIVE)
        current_user = SimpleNamespace(id=23, role="admin")
        fake_db = SimpleNamespace()
        source_requirement = ConsolidatedRequirement(
            id=191,
            tender_id=44,
            canonical_text="Legacy source requirement.",
            normalized_text="legacy source requirement",
            priority="low",
            source_count=1,
            consolidation_method="staging_v1",
            review_state="approved",
            graph_state="obsolete",
        )
        target_requirement = ConsolidatedRequirement(
            id=192,
            tender_id=44,
            canonical_text="Legacy target requirement.",
            normalized_text="legacy target requirement",
            priority="low",
            source_count=1,
            consolidation_method="staging_v1",
            review_state="approved",
            graph_state="obsolete",
        )
        relation = RequirementRelation(
            id=801,
            tender_id=44,
            source_requirement_id=191,
            target_requirement_id=192,
            relation_type="overrides",
            confidence=0.52,
            review_state="approved",
            graph_state="obsolete",
            metadata_json={"lifecycle": {"graph_state": "obsolete", "reason": "missing_from_latest_rebuild"}},
        )
        relation.source_requirement = source_requirement
        relation.target_requirement = target_requirement

        with (
            patch.object(_TENDERS_MODULE, "check_tender_access", AsyncMock(return_value=tender)),
            patch.object(
                _TENDERS_MODULE,
                "list_requirement_relations",
                AsyncMock(return_value=[relation]),
            ) as list_mock,
        ):
            response = await get_tender_consolidated_requirement_relations(
                tender_id=44,
                relation_type="overrides",
                graph_state="obsolete",
                current_user=current_user,
                db=fake_db,
            )

        list_mock.assert_awaited_once_with(
            fake_db,
            tender_id=44,
            relation_type="overrides",
            graph_state="obsolete",
        )
        self.assertEqual(response.total_items, 1)
        self.assertEqual(response.items[0].graph_state, "obsolete")
        self.assertEqual(response.items[0].metadata_json["lifecycle"]["reason"], "missing_from_latest_rebuild")

    async def test_get_tender_consolidated_requirement_relation_review_queue_returns_triaged_edges(self) -> None:
        tender = Tender(id=41, title="Complex Tender", status=TenderStatus.ACTIVE)
        current_user = SimpleNamespace(id=18, role="admin")
        fake_db = SimpleNamespace()
        relation = RequirementRelation(
            id=503,
            tender_id=41,
            source_requirement_id=141,
            target_requirement_id=142,
            relation_type="overrides",
            confidence=0.54,
            review_state="pending",
            metadata_json={"inference_method": "lexical_override_v1"},
        )
        relation.source_requirement = ConsolidatedRequirement(
            id=141,
            tender_id=41,
            canonical_text="Provide signed annex A with wet signature.",
            normalized_text="provide signed annex a with wet signature",
            priority="high",
            source_count=1,
            consolidation_method="staging_v1",
            review_state="pending",
        )
        relation.target_requirement = ConsolidatedRequirement(
            id=142,
            tender_id=41,
            canonical_text="Provide signed annex A.",
            normalized_text="provide signed annex a",
            priority="medium",
            source_count=1,
            consolidation_method="staging_v1",
            review_state="pending",
        )

        with (
            patch.object(_TENDERS_MODULE, "check_tender_access", AsyncMock(return_value=tender)),
            patch.object(
                _TENDERS_MODULE,
                "list_requirement_relations_for_review",
                AsyncMock(return_value=[relation]),
            ) as queue_mock,
        ):
            response = await get_tender_consolidated_requirement_relation_review_queue(
                tender_id=41,
                review_state="pending",
                relation_type="overrides",
                limit=15,
                current_user=current_user,
                db=fake_db,
            )

        queue_mock.assert_awaited_once_with(
            fake_db,
            tender_id=41,
            review_state="pending",
            relation_type="overrides",
            limit=15,
        )
        self.assertEqual(response.total_items, 1)
        self.assertEqual(response.items[0].relation_type, "overrides")
        self.assertEqual(response.items[0].review_state, "pending")
        self.assertEqual(response.items[0].source_requirement_text, "Provide signed annex A with wet signature.")

    async def test_get_tender_consolidated_requirement_review_queue_returns_triaged_rows(self) -> None:
        tender = Tender(id=36, title="Complex Tender", status=TenderStatus.ACTIVE)
        current_user = SimpleNamespace(id=13, role="admin")
        fake_db = SimpleNamespace()
        pending_row = ConsolidatedRequirement(
            id=101,
            tender_id=36,
            canonical_text="Pending review item",
            normalized_text="pending review item",
            priority="high",
            confidence=0.41,
            source_count=1,
            consolidation_method="staging_v1",
            review_state="pending",
        )

        with (
            patch.object(_TENDERS_MODULE, "check_tender_access", AsyncMock(return_value=tender)),
            patch.object(
                _TENDERS_MODULE,
                "list_consolidated_requirements_for_review",
                AsyncMock(return_value=[pending_row]),
            ) as queue_mock,
        ):
            response = await get_tender_consolidated_requirement_review_queue(
                tender_id=36,
                review_state="pending",
                limit=25,
                current_user=current_user,
                db=fake_db,
            )

        queue_mock.assert_awaited_once_with(
            fake_db,
            tender_id=36,
            review_state="pending",
            limit=25,
        )
        self.assertEqual(response.total_items, 1)
        self.assertEqual(response.items[0].canonical_text, "Pending review item")
        self.assertEqual(response.items[0].review_state, "pending")

    async def test_rebuild_tender_consolidated_requirements_returns_rebuilt_rows(self) -> None:
        tender = Tender(id=35, title="Complex Tender", status=TenderStatus.ACTIVE)
        current_user = SimpleNamespace(id=12, role="admin")
        rebuilt_row = ConsolidatedRequirement(
            id=91,
            tender_id=35,
            canonical_text="Submit insurance certificate.",
            normalized_text="submit insurance certificate",
            priority="high",
            confidence=0.83,
            source_count=1,
            consolidation_method="staging_v1",
            review_state="pending",
            metadata_json={"sources": [{"candidate_id": 201}]},
        )
        fake_db = SimpleNamespace()

        with (
            patch.object(_TENDERS_MODULE, "check_tender_access", AsyncMock(return_value=tender)),
            patch.object(
                _TENDERS_MODULE,
                "rebuild_consolidated_requirements_from_staging",
                AsyncMock(return_value=[rebuilt_row]),
            ) as rebuild_mock,
        ):
            response = await rebuild_tender_consolidated_requirements(
                tender_id=35,
                limit_runs=3,
                current_user=current_user,
                db=fake_db,
            )

        rebuild_mock.assert_awaited_once_with(fake_db, tender_id=35, limit_runs=3)
        self.assertEqual(response.total_items, 1)
        self.assertEqual(response.items[0].canonical_text, "Submit insurance certificate.")
        self.assertEqual(response.items[0].priority, "high")

    async def test_review_tender_consolidated_requirement_returns_updated_requirement_and_review(self) -> None:
        tender = Tender(id=37, title="Complex Tender", status=TenderStatus.ACTIVE)
        current_user = SimpleNamespace(id=14, role="admin")
        fake_db = SimpleNamespace()
        requirement = ConsolidatedRequirement(
            id=110,
            tender_id=37,
            canonical_text="Provide cyber insurance certificate.",
            normalized_text="provide cyber insurance certificate",
            priority="high",
            source_count=1,
            consolidation_method="staging_v1",
            review_state="approved",
            metadata_json={"review_count": 1},
        )
        review = RequirementReview(
            id=401,
            tender_id=37,
            consolidated_requirement_id=110,
            actor_id=14,
            action="approve",
            previous_review_state="pending",
            new_review_state="approved",
            notes="Verified manually.",
            metadata_json={},
        )

        with (
            patch.object(_TENDERS_MODULE, "check_tender_access", AsyncMock(return_value=tender)),
            patch.object(
                _TENDERS_MODULE,
                "get_consolidated_requirement_for_tender",
                AsyncMock(return_value=requirement),
            ) as load_mock,
            patch.object(
                _TENDERS_MODULE,
                "apply_requirement_review",
                AsyncMock(return_value=(requirement, review)),
            ) as review_mock,
        ):
            response = await review_tender_consolidated_requirement(
                tender_id=37,
                requirement_id=110,
                data=_TENDERS_MODULE.ConsolidatedRequirementReviewRequest(
                    action="approve",
                    notes="Verified manually.",
                ),
                current_user=current_user,
                db=fake_db,
            )

        load_mock.assert_awaited_once_with(
            fake_db,
            tender_id=37,
            requirement_id=110,
        )
        review_mock.assert_awaited_once_with(
            fake_db,
            requirement=requirement,
            actor_id=14,
            action="approve",
            notes="Verified manually.",
        )
        self.assertEqual(response.requirement.review_state, "approved")
        self.assertEqual(response.review.new_review_state, "approved")
        self.assertEqual(response.review.notes, "Verified manually.")

    async def test_review_tender_consolidated_requirement_relation_returns_updated_relation_and_review(self) -> None:
        tender = Tender(id=42, title="Complex Tender", status=TenderStatus.ACTIVE)
        current_user = SimpleNamespace(id=21, role="admin")
        fake_db = SimpleNamespace()
        relation = RequirementRelation(
            id=601,
            tender_id=42,
            source_requirement_id=151,
            target_requirement_id=152,
            relation_type="depends_on",
            confidence=0.66,
            review_state="approved",
            metadata_json={"review_count": 1},
        )
        relation.source_requirement = ConsolidatedRequirement(
            id=151,
            tender_id=42,
            canonical_text="Submit the final commercial offer after presenting the technical plan.",
            normalized_text="submit the final commercial offer after presenting the technical plan",
            priority="high",
            source_count=1,
            consolidation_method="staging_v1",
            review_state="pending",
        )
        relation.target_requirement = ConsolidatedRequirement(
            id=152,
            tender_id=42,
            canonical_text="Present the technical plan.",
            normalized_text="present the technical plan",
            priority="medium",
            source_count=1,
            consolidation_method="staging_v1",
            review_state="pending",
        )
        review = RequirementRelationReview(
            id=701,
            tender_id=42,
            requirement_relation_id=601,
            actor_id=21,
            action="approve",
            previous_review_state="pending",
            new_review_state="approved",
            notes="Dependency confirmed manually.",
            metadata_json={},
        )

        with (
            patch.object(_TENDERS_MODULE, "check_tender_access", AsyncMock(return_value=tender)),
            patch.object(
                _TENDERS_MODULE,
                "get_requirement_relation_for_tender",
                AsyncMock(return_value=relation),
            ) as load_mock,
            patch.object(
                _TENDERS_MODULE,
                "apply_requirement_relation_review",
                AsyncMock(return_value=(relation, review)),
            ) as review_mock,
        ):
            response = await review_tender_consolidated_requirement_relation(
                tender_id=42,
                relation_id=601,
                data=_TENDERS_MODULE.RequirementRelationReviewRequest(
                    action="approve",
                    notes="Dependency confirmed manually.",
                ),
                current_user=current_user,
                db=fake_db,
            )

        load_mock.assert_awaited_once_with(
            fake_db,
            tender_id=42,
            relation_id=601,
        )
        review_mock.assert_awaited_once_with(
            fake_db,
            relation=relation,
            actor_id=21,
            action="approve",
            notes="Dependency confirmed manually.",
        )
        self.assertEqual(response.relation.id, 601)
        self.assertEqual(response.relation.review_state, "approved")
        self.assertEqual(response.review.new_review_state, "approved")
        self.assertEqual(response.review.notes, "Dependency confirmed manually.")

    async def test_review_tender_consolidated_requirement_rejects_missing_row(self) -> None:
        tender = Tender(id=38, title="Complex Tender", status=TenderStatus.ACTIVE)
        current_user = SimpleNamespace(id=15, role="admin")
        fake_db = SimpleNamespace()

        with (
            patch.object(_TENDERS_MODULE, "check_tender_access", AsyncMock(return_value=tender)),
            patch.object(
                _TENDERS_MODULE,
                "get_consolidated_requirement_for_tender",
                AsyncMock(return_value=None),
            ),
        ):
            with self.assertRaises(_TENDERS_MODULE.HTTPException) as exc:
                await review_tender_consolidated_requirement(
                    tender_id=38,
                    requirement_id=999,
                    data=_TENDERS_MODULE.ConsolidatedRequirementReviewRequest(action="approve"),
                    current_user=current_user,
                    db=fake_db,
                )

        self.assertEqual(exc.exception.status_code, 404)
        self.assertEqual(exc.exception.detail, "Consolidated requirement not found")


if __name__ == "__main__":
    unittest.main()
