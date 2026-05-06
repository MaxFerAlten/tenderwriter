"""Unit tests for staged requirement candidate query helpers."""

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
_SERVICE_MODULE = load_service_test_module("app.services.requirement_candidates")

RequirementCandidate = _MODELS.RequirementCandidate
RequirementExtractionRun = _MODELS.RequirementExtractionRun
list_staged_requirement_candidate_runs = _SERVICE_MODULE.list_staged_requirement_candidate_runs


class _FakeExecuteResult:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def scalars(self) -> _FakeExecuteResult:
        return self

    def all(self) -> list[object]:
        return list(self._rows)


class _FakeAsyncSession:
    def __init__(self, rows: list[object]) -> None:
        self.rows = rows
        self.statement = None

    async def execute(self, statement):
        self.statement = statement
        return _FakeExecuteResult(self.rows)


class RequirementCandidateQueryTests(unittest.IsolatedAsyncioTestCase):
    async def test_list_staged_requirement_candidate_runs_orders_candidates_and_clamps_limit(
        self,
    ) -> None:
        run = RequirementExtractionRun(
            id=5,
            tender_id=21,
            extraction_method="heuristic_v1",
            candidate_count=2,
        )
        run.candidates = [
            RequirementCandidate(
                id=9,
                tender_id=21,
                extraction_run_id=5,
                candidate_position=2,
                summary_text="Second item",
                normalized_text="second item",
                priority="medium",
            ),
            RequirementCandidate(
                id=8,
                tender_id=21,
                extraction_run_id=5,
                candidate_position=1,
                summary_text="First item",
                normalized_text="first item",
                priority="high",
            ),
        ]
        db = _FakeAsyncSession([run])

        runs = await list_staged_requirement_candidate_runs(
            db,
            tender_id=21,
            limit_runs=99,
        )

        self.assertEqual(
            [candidate.summary_text for candidate in runs[0].candidates],
            ["First item", "Second item"],
        )
        self.assertIsNotNone(db.statement)
        self.assertEqual(db.statement._limit_clause.value, 20)


if __name__ == "__main__":
    unittest.main()
