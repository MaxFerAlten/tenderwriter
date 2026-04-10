"""Unit tests for requirement graph backfill operations."""

from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, call, patch

from test_module_loaders import load_service_test_module

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

_SERVICE_MODULE = load_service_test_module("app.services.requirement_graph_backfill")
_CLI_MODULE = load_service_test_module("app.backfill_requirement_graphs")


class _ScalarResult:
    def __init__(self, values: list[int]) -> None:
        self._values = values

    def scalars(self):
        return self

    def all(self) -> list[int]:
        return self._values


class _FakeAsyncSession:
    def __init__(self, tender_ids: list[int] | None = None) -> None:
        self.tender_ids = tender_ids or []
        self.executed: list[object] = []

    async def execute(self, statement):
        self.executed.append(statement)
        return _ScalarResult(self.tender_ids)


class RequirementGraphBackfillTests(unittest.IsolatedAsyncioTestCase):
    async def test_explicit_tender_ids_are_deduplicated_without_discovery_query(self) -> None:
        db = _FakeAsyncSession(tender_ids=[999])

        tender_ids = await _SERVICE_MODULE.list_requirement_graph_backfill_tender_ids(
            db,
            tender_ids=[12, 12, 14],
        )

        self.assertEqual(tender_ids, [12, 14])
        self.assertEqual(db.executed, [])

    async def test_backfill_requirement_graphs_rebuilds_discovered_tenders(self) -> None:
        db = _FakeAsyncSession(tender_ids=[41, 42, 42])

        with patch.object(
            _SERVICE_MODULE,
            "list_staged_requirement_candidate_runs",
            AsyncMock(return_value=[SimpleNamespace(id=7)]),
        ), patch.object(
            _SERVICE_MODULE,
            "rebuild_consolidated_requirements_from_staging",
            AsyncMock(
                side_effect=[
                    [SimpleNamespace(id=1)],
                    [SimpleNamespace(id=2), SimpleNamespace(id=3)],
                ]
            ),
        ) as rebuild_mock:
            summary = await _SERVICE_MODULE.backfill_requirement_graphs(
                db,
                limit_runs=3,
            )

        self.assertEqual(summary.tender_count, 2)
        self.assertEqual(summary.rebuilt_count, 2)
        self.assertEqual([item.consolidated_count for item in summary.results], [1, 2])
        self.assertEqual([item.source for item in summary.results], ["staging", "staging"])
        rebuild_mock.assert_has_awaits(
            [
                call(db, tender_id=41, limit_runs=3),
                call(db, tender_id=42, limit_runs=3),
            ]
        )

    async def test_backfill_requirement_graphs_dry_run_does_not_rebuild(self) -> None:
        db = _FakeAsyncSession(tender_ids=[51])

        with patch.object(
            _SERVICE_MODULE,
            "rebuild_consolidated_requirements_from_staging",
            AsyncMock(return_value=[SimpleNamespace(id=1)]),
        ) as rebuild_mock:
            summary = await _SERVICE_MODULE.backfill_requirement_graphs(
                db,
                limit_runs=2,
                dry_run=True,
            )

        self.assertTrue(summary.dry_run)
        self.assertEqual(summary.planned_count, 1)
        self.assertEqual(summary.results[0].status, "planned")
        rebuild_mock.assert_not_awaited()

    async def test_backfill_requirement_graphs_falls_back_to_legacy_requirements_without_staged_runs(self) -> None:
        db = _FakeAsyncSession(tender_ids=[61])

        with patch.object(
            _SERVICE_MODULE,
            "list_staged_requirement_candidate_runs",
            AsyncMock(return_value=[]),
        ), patch.object(
            _SERVICE_MODULE,
            "rebuild_consolidated_requirements_from_staging",
            AsyncMock(return_value=[SimpleNamespace(id=99)]),
        ) as staged_rebuild_mock, patch.object(
            _SERVICE_MODULE,
            "rebuild_consolidated_requirements_from_legacy",
            AsyncMock(return_value=[SimpleNamespace(id=601), SimpleNamespace(id=602)]),
        ) as legacy_rebuild_mock:
            summary = await _SERVICE_MODULE.backfill_requirement_graphs(
                db,
                limit_runs=4,
            )

        self.assertEqual(summary.tender_count, 1)
        self.assertEqual(summary.rebuilt_count, 1)
        self.assertEqual(summary.results[0].source, "legacy")
        self.assertEqual(summary.results[0].consolidated_count, 2)
        staged_rebuild_mock.assert_not_awaited()
        legacy_rebuild_mock.assert_awaited_once_with(db, tender_id=61)

    def test_backfill_cli_parses_scoped_dry_run_options(self) -> None:
        args = _CLI_MODULE.build_parser().parse_args(
            ["--dry-run", "--tender-id", "12", "--tender-id", "14", "--limit-runs", "2"]
        )

        self.assertTrue(args.dry_run)
        self.assertEqual(args.tender_ids, [12, 14])
        self.assertEqual(args.limit_runs, 2)


if __name__ == "__main__":
    unittest.main()
