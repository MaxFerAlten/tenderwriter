"""Regression tests for the KPI rehearsal_summary publish path.

Covers ``TenderRehearsalService._publish_rehearsal_summary`` semantics
introduced as part of the MiroFish finishing pass:

* the publish call is flag-gated (``rehearsal_summary_publish_enabled``)
* a missing local summary is reported as ``no_summary``
* a delivered HTTP response yields ``delivered``
* an HTTP non-2xx response yields ``undelivered`` without raising
* an exception inside the client is swallowed and reported as ``failed``

These guarantees are load-bearing: KPI sync failures must never flip a
completed rehearsal run to FAILED.
"""

from __future__ import annotations

import os
import unittest
from unittest.mock import AsyncMock, patch

from test_module_loaders import load_service_test_module

_TEST_ENV = {
    "APP_SECRET_KEY": "alpha-key-123456789012345678901234567890",
    "ADMIN_PASSWORD": "test-admin-password-1234567890",
    "DATABASE_URL": "postgresql+asyncpg://tester:securepass@localhost:5432/tenderwriter",
    "NEO4J_PASSWORD": "test-neo4j-password-1234567890",
    "MINIO_SECRET_KEY": "test-minio-password-1234567890",
    "ONLYOFFICE_JWT_SECRET": "office-jwt-token-12345678901234567890",
}
for _key, _value in _TEST_ENV.items():
    os.environ.setdefault(_key, _value)


_SERVICE = load_service_test_module("app.intelligence.rehearsal")
_KPI_CLIENT = load_service_test_module("app.services.kpi_reason_engine")


class _StubClientResult:
    def __init__(self, *, delivered: bool, status_code: int = 200, error: str | None = None):
        self.delivered = delivered
        self.status_code = status_code
        self.error_message = error


class PublishRehearsalSummaryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.service = _SERVICE.TenderRehearsalService(registry=object())

    async def test_disabled_flag_short_circuits_without_client_call(self) -> None:
        client_factory = AsyncMock()
        with (
            patch.object(_SERVICE.settings, "rehearsal_summary_publish_enabled", False),
            patch.object(_KPI_CLIENT, "KpiReasonEngineClient", client_factory),
        ):
            status = await self.service._publish_rehearsal_summary(
                db=object(), tender_id=10, proposal_id=7
            )
        self.assertEqual(status, "disabled")
        client_factory.assert_not_called()

    async def test_no_local_summary_returns_no_summary(self) -> None:
        with (
            patch.object(_SERVICE.settings, "rehearsal_summary_publish_enabled", True),
            patch.object(
                _SERVICE,
                "build_rehearsal_summary",
                AsyncMock(return_value=None),
            ),
        ):
            status = await self.service._publish_rehearsal_summary(
                db=object(), tender_id=10, proposal_id=None
            )
        self.assertEqual(status, "no_summary")

    async def test_delivered_response_returns_delivered(self) -> None:
        put_mock = AsyncMock(return_value=_StubClientResult(delivered=True))
        client_instance = type("StubClient", (), {"put_rehearsal_summary": put_mock})()

        with (
            patch.object(_SERVICE.settings, "rehearsal_summary_publish_enabled", True),
            patch.object(
                _SERVICE,
                "build_rehearsal_summary",
                AsyncMock(return_value={"run_id": 42, "tender_id": 10}),
            ),
            patch.object(
                _KPI_CLIENT,
                "KpiReasonEngineClient",
                lambda *a, **kw: client_instance,
            ),
        ):
            status = await self.service._publish_rehearsal_summary(
                db=object(), tender_id=10, proposal_id=7
            )
        self.assertEqual(status, "delivered")
        put_mock.assert_awaited_once()
        called_args = put_mock.await_args
        self.assertEqual(called_args.args[0], "10")
        self.assertEqual(called_args.args[1]["run_id"], 42)

    async def test_undelivered_response_does_not_raise(self) -> None:
        put_mock = AsyncMock(
            return_value=_StubClientResult(delivered=False, status_code=503, error="upstream down")
        )
        client_instance = type("StubClient", (), {"put_rehearsal_summary": put_mock})()

        with (
            patch.object(_SERVICE.settings, "rehearsal_summary_publish_enabled", True),
            patch.object(
                _SERVICE,
                "build_rehearsal_summary",
                AsyncMock(return_value={"run_id": 42}),
            ),
            patch.object(
                _KPI_CLIENT,
                "KpiReasonEngineClient",
                lambda *a, **kw: client_instance,
            ),
        ):
            status = await self.service._publish_rehearsal_summary(
                db=object(), tender_id=10, proposal_id=None
            )
        self.assertEqual(status, "undelivered")

    async def test_client_exception_is_swallowed_and_reported_failed(self) -> None:
        put_mock = AsyncMock(side_effect=RuntimeError("network unreachable"))
        client_instance = type("StubClient", (), {"put_rehearsal_summary": put_mock})()

        with (
            patch.object(_SERVICE.settings, "rehearsal_summary_publish_enabled", True),
            patch.object(
                _SERVICE,
                "build_rehearsal_summary",
                AsyncMock(return_value={"run_id": 42}),
            ),
            patch.object(
                _KPI_CLIENT,
                "KpiReasonEngineClient",
                lambda *a, **kw: client_instance,
            ),
        ):
            status = await self.service._publish_rehearsal_summary(
                db=object(), tender_id=10, proposal_id=None
            )
        self.assertEqual(status, "failed")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
