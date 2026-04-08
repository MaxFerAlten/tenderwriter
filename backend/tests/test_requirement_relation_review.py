"""Unit tests for inferred requirement relation review helpers."""

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
_SERVICE_MODULE = load_service_test_module("app.services.requirement_relation_review")

RequirementRelation = _MODELS.RequirementRelation
RequirementRelationReview = _MODELS.RequirementRelationReview
apply_requirement_relation_review = _SERVICE_MODULE.apply_requirement_relation_review
list_requirement_relations_for_review = _SERVICE_MODULE.list_requirement_relations_for_review


class _FakeExecuteResult:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def scalars(self) -> "_FakeExecuteResult":
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
                setattr(instance, "id", self._next_id)
                self._next_id += 1


class RequirementRelationReviewTests(unittest.IsolatedAsyncioTestCase):
    async def test_list_requirement_relations_for_review_orders_overrides_before_dependencies(self) -> None:
        db = _FakeAsyncSession(
            rows=[
                RequirementRelation(
                    id=1,
                    tender_id=81,
                    source_requirement_id=501,
                    target_requirement_id=502,
                    relation_type="depends_on",
                    confidence=0.21,
                    review_state="pending",
                    graph_state="active",
                ),
                RequirementRelation(
                    id=2,
                    tender_id=81,
                    source_requirement_id=503,
                    target_requirement_id=504,
                    relation_type="overrides",
                    confidence=0.34,
                    review_state="pending",
                    graph_state="active",
                ),
                RequirementRelation(
                    id=3,
                    tender_id=81,
                    source_requirement_id=505,
                    target_requirement_id=506,
                    relation_type="overrides",
                    confidence=0.72,
                    review_state="pending",
                    graph_state="active",
                ),
            ]
        )

        relations = await list_requirement_relations_for_review(
            db,
            tender_id=81,
            review_state="pending",
            limit=2,
        )

        self.assertEqual(
            [item.id for item in relations],
            [2, 3],
        )
        self.assertIsNotNone(db.statement)
        self.assertIn("graph_state", str(db.statement))
        self.assertIn(":graph_state_1", str(db.statement))

    async def test_apply_requirement_relation_review_updates_state_and_creates_audit_row(self) -> None:
        db = _FakeAsyncSession()
        relation = RequirementRelation(
            id=41,
            tender_id=82,
            source_requirement_id=601,
            target_requirement_id=602,
            relation_type="depends_on",
            confidence=0.63,
            review_state="pending",
            graph_state="active",
            metadata_json={"inference_method": "dependency_clause_v1"},
        )

        updated_relation, review = await apply_requirement_relation_review(
            db,
            relation=relation,
            actor_id=19,
            action="approve",
            notes="Clause clearly links the prerequisite.",
        )

        self.assertIs(updated_relation, relation)
        self.assertEqual(updated_relation.review_state, "approved")
        self.assertEqual(updated_relation.metadata_json["review_count"], 1)
        self.assertEqual(updated_relation.metadata_json["latest_review"]["action"], "approve")
        self.assertIsInstance(review, RequirementRelationReview)
        self.assertEqual(review.actor_id, 19)
        self.assertEqual(review.previous_review_state, "pending")
        self.assertEqual(review.new_review_state, "approved")
        self.assertEqual(review.notes, "Clause clearly links the prerequisite.")
        self.assertGreaterEqual(db.flush_count, 1)

    async def test_apply_requirement_relation_review_rejects_unknown_actions(self) -> None:
        db = _FakeAsyncSession()
        relation = RequirementRelation(
            id=42,
            tender_id=83,
            source_requirement_id=701,
            target_requirement_id=702,
            relation_type="overrides",
            confidence=0.88,
            review_state="pending",
            graph_state="active",
        )

        with self.assertRaises(ValueError):
            await apply_requirement_relation_review(
                db,
                relation=relation,
                actor_id=20,
                action="archive",
            )


if __name__ == "__main__":
    unittest.main()
