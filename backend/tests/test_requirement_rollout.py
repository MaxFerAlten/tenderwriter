"""Unit tests for requirement pipeline rollout controls."""

from __future__ import annotations

import os
import unittest
from types import SimpleNamespace

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

_SERVICE_MODULE = load_service_test_module("app.services.requirement_rollout")


class RequirementRolloutTests(unittest.TestCase):
    def test_llm_v2_rollout_keeps_global_flag_disabled_as_hard_stop(self) -> None:
        settings = SimpleNamespace(
            requirement_extraction_llm_v2_enabled=False,
            requirement_extraction_llm_v2_rollout_percent=100,
            requirement_extraction_llm_v2_tender_ids="12",
            requirement_extraction_llm_v2_blocked_tender_ids="",
        )

        self.assertFalse(
            _SERVICE_MODULE.should_use_requirement_extraction_llm_v2(
                settings,
                tender_id=12,
            )
        )

    def test_llm_v2_rollout_preserves_full_enablement_when_percent_is_default(self) -> None:
        settings = SimpleNamespace(
            requirement_extraction_llm_v2_enabled=True,
            requirement_extraction_llm_v2_rollout_percent=100,
            requirement_extraction_llm_v2_tender_ids="",
            requirement_extraction_llm_v2_blocked_tender_ids="",
        )

        self.assertTrue(
            _SERVICE_MODULE.should_use_requirement_extraction_llm_v2(
                settings,
                tender_id=None,
            )
        )
        self.assertTrue(
            _SERVICE_MODULE.should_use_requirement_extraction_llm_v2(
                settings,
                tender_id=91,
            )
        )

    def test_llm_v2_rollout_supports_allowlist_and_blocklist(self) -> None:
        settings = SimpleNamespace(
            requirement_extraction_llm_v2_enabled=True,
            requirement_extraction_llm_v2_rollout_percent=0,
            requirement_extraction_llm_v2_tender_ids="12, 14",
            requirement_extraction_llm_v2_blocked_tender_ids="14",
        )

        self.assertTrue(
            _SERVICE_MODULE.should_use_requirement_extraction_llm_v2(
                settings,
                tender_id=12,
            )
        )
        self.assertFalse(
            _SERVICE_MODULE.should_use_requirement_extraction_llm_v2(
                settings,
                tender_id=14,
            )
        )
        self.assertFalse(
            _SERVICE_MODULE.should_use_requirement_extraction_llm_v2(
                settings,
                tender_id=99,
            )
        )

    def test_llm_v2_rollout_uses_stable_percentage_bucket(self) -> None:
        tender_id = 77
        bucket = _SERVICE_MODULE.requirement_rollout_bucket(tender_id)
        settings = SimpleNamespace(
            requirement_extraction_llm_v2_enabled=True,
            requirement_extraction_llm_v2_rollout_percent=bucket + 1,
            requirement_extraction_llm_v2_tender_ids="",
            requirement_extraction_llm_v2_blocked_tender_ids="",
        )

        self.assertTrue(
            _SERVICE_MODULE.should_use_requirement_extraction_llm_v2(
                settings,
                tender_id=tender_id,
            )
        )
        settings.requirement_extraction_llm_v2_rollout_percent = bucket
        self.assertFalse(
            _SERVICE_MODULE.should_use_requirement_extraction_llm_v2(
                settings,
                tender_id=tender_id,
            )
        )


if __name__ == "__main__":
    unittest.main()
