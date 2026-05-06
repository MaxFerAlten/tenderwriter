"""Unit tests for consolidated requirement review helpers."""

from __future__ import annotations

import os
import unittest

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
_SERVICE_MODULE = load_service_test_module("app.services.requirement_review")

ConsolidatedRequirement = _MODELS.ConsolidatedRequirement
RequirementReview = _MODELS.RequirementReview
apply_requirement_review = _SERVICE_MODULE.apply_requirement_review
list_consolidated_requirements_for_review = (
    _SERVICE_MODULE.list_consolidated_requirements_for_review
)


class _FakeExecuteResult:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def scalars(self) -> _FakeExecuteResult:
        return self

    def all(self) -> list[object]:
        return list(self._rows)


class _FakeAsyncSession:
    def __init__(self, rows: list[object] | None = None) -> None:
        self.rows = list(rows or [])
        self.statement = None
        self.added: list[object] = []
        self.flush_count = 0
        self._next_id = 1

    async def execute(self, statement):
        self.statement = statement
        return _FakeExecuteResult(self.rows)

    def add(self, instance: object) -> None:
        self.added.append(instance)

    async def flush(self) -> None:
        self.flush_count += 1
        for instance in self.added:
            if getattr(instance, "id", None) is None:
                instance.id = self._next_id
                self._next_id += 1


class RequirementReviewTests(unittest.IsolatedAsyncioTestCase):
    async def test_list_consolidated_requirements_for_review_orders_by_priority_and_confidence(
        self,
    ) -> None:
        db = _FakeAsyncSession(
            rows=[
                ConsolidatedRequirement(
                    id=1,
                    tender_id=61,
                    canonical_text="Medium confidence medium priority",
                    normalized_text="medium confidence medium priority",
                    priority="medium",
                    confidence=0.45,
                    source_count=1,
                    consolidation_method="staging_v1",
                    review_state="pending",
                    graph_state="active",
                ),
                ConsolidatedRequirement(
                    id=2,
                    tender_id=61,
                    canonical_text="High priority lower confidence",
                    normalized_text="high priority lower confidence",
                    priority="high",
                    confidence=0.32,
                    source_count=1,
                    consolidation_method="staging_v1",
                    review_state="pending",
                    graph_state="active",
                ),
                ConsolidatedRequirement(
                    id=3,
                    tender_id=61,
                    canonical_text="High priority higher confidence",
                    normalized_text="high priority higher confidence",
                    priority="high",
                    confidence=0.91,
                    source_count=1,
                    consolidation_method="staging_v1",
                    review_state="pending",
                    graph_state="active",
                ),
            ]
        )

        requirements = await list_consolidated_requirements_for_review(
            db,
            tender_id=61,
            review_state="pending",
            limit=2,
        )

        self.assertEqual(
            [item.canonical_text for item in requirements],
            ["High priority lower confidence", "High priority higher confidence"],
        )
        self.assertIsNotNone(db.statement)
        self.assertIn("graph_state", str(db.statement))
        self.assertIn(":graph_state_1", str(db.statement))

    async def test_apply_requirement_review_updates_state_and_creates_audit_row(self) -> None:
        db = _FakeAsyncSession()
        requirement = ConsolidatedRequirement(
            id=14,
            tender_id=62,
            canonical_text="Provide signed annex A.",
            normalized_text="provide signed annex a",
            priority="high",
            source_count=2,
            consolidation_method="staging_v1",
            review_state="pending",
            graph_state="active",
            metadata_json={"sources": [{"candidate_id": 1}]},
        )

        updated_requirement, review = await apply_requirement_review(
            db,
            requirement=requirement,
            actor_id=7,
            action="approve",
            notes="Supported by two matching sources.",
        )

        self.assertIs(updated_requirement, requirement)
        self.assertEqual(updated_requirement.review_state, "approved")
        self.assertEqual(updated_requirement.metadata_json["review_count"], 1)
        self.assertEqual(updated_requirement.metadata_json["latest_review"]["action"], "approve")
        self.assertIsInstance(review, RequirementReview)
        self.assertEqual(review.actor_id, 7)
        self.assertEqual(review.previous_review_state, "pending")
        self.assertEqual(review.new_review_state, "approved")
        self.assertEqual(review.notes, "Supported by two matching sources.")
        self.assertGreaterEqual(db.flush_count, 1)

    async def test_apply_requirement_review_rejects_unknown_actions(self) -> None:
        db = _FakeAsyncSession()
        requirement = ConsolidatedRequirement(
            id=15,
            tender_id=63,
            canonical_text="Provide insurance certificate.",
            normalized_text="provide insurance certificate",
            priority="medium",
            source_count=1,
            consolidation_method="staging_v1",
            review_state="pending",
            graph_state="active",
        )

        with self.assertRaises(ValueError):
            await apply_requirement_review(
                db,
                requirement=requirement,
                actor_id=8,
                action="archive",
            )

    async def test_apply_requirement_review_edits_text_and_graph_v2_fields_with_audit(self) -> None:
        db = _FakeAsyncSession()
        requirement = ConsolidatedRequirement(
            id=16,
            tender_id=64,
            canonical_text="Provide old insurance certificate.",
            normalized_text="provide old insurance certificate",
            category="risk",
            priority="medium",
            source_count=1,
            consolidation_method="staging_v1",
            review_state="approved",
            graph_state="active",
            metadata_json={"review_count": 1},
        )

        updated_requirement, review = await apply_requirement_review(
            db,
            requirement=requirement,
            actor_id=9,
            action="edit",
            notes="Cleaned up the extracted requirement.",
            edit_payload={
                "canonical_text": "Provide updated cyber insurance certificate.",
                "priority": "high",
                "conditions": ["Before contract signature"],
                "exceptions": ["Optional modules excluded"],
                "applicability": {"lot": "1"},
            },
        )

        self.assertIs(updated_requirement, requirement)
        self.assertEqual(requirement.review_state, "pending")
        self.assertEqual(requirement.graph_state, "active")
        self.assertEqual(requirement.canonical_text, "Provide updated cyber insurance certificate.")
        self.assertEqual(
            requirement.normalized_text, "provide updated cyber insurance certificate."
        )
        self.assertEqual(requirement.priority, "high")
        self.assertEqual(requirement.conditions, ["Before contract signature"])
        self.assertEqual(requirement.exceptions, ["Optional modules excluded"])
        self.assertEqual(requirement.applicability, {"lot": "1"})
        self.assertEqual(review.action, "edit")
        self.assertEqual(review.previous_review_state, "approved")
        self.assertEqual(review.new_review_state, "pending")
        self.assertEqual(
            review.metadata_json["edit"]["before"]["canonical_text"],
            "Provide old insurance certificate.",
        )
        self.assertEqual(review.metadata_json["edit"]["after"]["priority"], "high")

    async def test_apply_requirement_review_dismiss_marks_requirement_obsolete_without_deleting_audit(
        self,
    ) -> None:
        db = _FakeAsyncSession()
        requirement = ConsolidatedRequirement(
            id=17,
            tender_id=65,
            canonical_text="Dismiss noisy candidate.",
            normalized_text="dismiss noisy candidate",
            priority="low",
            source_count=1,
            consolidation_method="staging_v1",
            review_state="pending",
            graph_state="active",
            metadata_json={"sources": [{"candidate_id": 4}]},
        )

        updated_requirement, review = await apply_requirement_review(
            db,
            requirement=requirement,
            actor_id=10,
            action="dismiss",
            notes="False positive.",
        )

        self.assertIs(updated_requirement, requirement)
        self.assertEqual(requirement.review_state, "dismissed")
        self.assertEqual(requirement.graph_state, "obsolete")
        self.assertEqual(requirement.metadata_json["lifecycle"]["reason"], "manual_dismissed")
        self.assertEqual(requirement.metadata_json["sources"], [{"candidate_id": 4}])
        self.assertEqual(review.action, "dismiss")
        self.assertEqual(review.metadata_json["previous_graph_state"], "active")

    async def test_apply_requirement_review_merge_marks_source_obsolete_and_updates_target_metadata(
        self,
    ) -> None:
        db = _FakeAsyncSession()
        source = ConsolidatedRequirement(
            id=18,
            tender_id=66,
            canonical_text="Provide insurance.",
            normalized_text="provide insurance",
            priority="medium",
            source_count=2,
            consolidation_method="staging_v1",
            review_state="pending",
            graph_state="active",
        )
        target = ConsolidatedRequirement(
            id=19,
            tender_id=66,
            canonical_text="Provide cyber insurance certificate.",
            normalized_text="provide cyber insurance certificate",
            priority="high",
            source_count=1,
            consolidation_method="staging_v1",
            review_state="pending",
            graph_state="active",
            metadata_json={},
        )

        updated_requirement, review = await apply_requirement_review(
            db,
            requirement=source,
            actor_id=11,
            action="merge",
            notes="Duplicate of the stronger insurance requirement.",
            target_requirement=target,
        )

        self.assertIs(updated_requirement, source)
        self.assertEqual(source.review_state, "merged")
        self.assertEqual(source.graph_state, "obsolete")
        self.assertEqual(source.metadata_json["lifecycle"]["reason"], "manual_merged")
        self.assertEqual(target.source_count, 3)
        self.assertEqual(target.metadata_json["manual_merges"][0]["source_requirement_id"], 18)
        self.assertEqual(review.metadata_json["merge_target"]["id"], 19)

    async def test_apply_requirement_review_split_creates_pending_children_and_obsoletes_source(
        self,
    ) -> None:
        db = _FakeAsyncSession()
        requirement = ConsolidatedRequirement(
            id=20,
            tender_id=67,
            canonical_text="Provide ISO 27001 and cyber insurance.",
            normalized_text="provide iso 27001 and cyber insurance",
            category="technical",
            priority="high",
            source_count=1,
            consolidation_method="staging_v1",
            review_state="pending",
            graph_state="active",
        )

        updated_requirement, review = await apply_requirement_review(
            db,
            requirement=requirement,
            actor_id=12,
            action="split",
            notes="Two atomic requirements.",
            split_payloads=[
                {"canonical_text": "Provide ISO 27001 certification.", "category": "security"},
                {"canonical_text": "Provide cyber insurance certificate.", "category": "risk"},
            ],
        )

        created_children = [item for item in db.added if isinstance(item, ConsolidatedRequirement)]
        self.assertIs(updated_requirement, requirement)
        self.assertEqual(requirement.review_state, "split")
        self.assertEqual(requirement.graph_state, "obsolete")
        self.assertEqual(requirement.metadata_json["lifecycle"]["reason"], "manual_split")
        self.assertEqual(
            [item.canonical_text for item in created_children],
            [
                "Provide ISO 27001 certification.",
                "Provide cyber insurance certificate.",
            ],
        )
        self.assertTrue(all(item.review_state == "pending" for item in created_children))
        self.assertEqual(review.metadata_json["split_children"][0]["id"], created_children[0].id)


if __name__ == "__main__":
    unittest.main()
