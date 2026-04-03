import os
import unittest
from unittest.mock import Mock, patch

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

with patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=Mock(name="engine")):
    from app.models import AIGatewayTarget, AppSettings
    from app.privacy_policy import resolve_effective_privacy_policy


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _SequenceResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return iter(self._values)


class _FakeDb:
    def __init__(self, *, settings_row: AppSettings, targets: list[AIGatewayTarget]):
        self.settings_row = settings_row
        self.targets = targets

    async def execute(self, stmt):
        stmt_str = str(stmt)
        if "ai_gateway_targets" in stmt_str:
            return _SequenceResult(self.targets)
        return _ScalarResult(self.settings_row)


class PrivacyPolicyResolverTests(unittest.IsolatedAsyncioTestCase):
    async def test_external_target_is_selected_when_policy_allows_anonymized_external(self) -> None:
        db = _FakeDb(
            settings_row=AppSettings(
                data={
                    "anonymizer_enabled": True,
                    "anonymizer_policy": {"default": {"mode": "external_anonymized"}},
                }
            ),
            targets=[
                AIGatewayTarget(
                    id=7,
                    route_key="tender",
                    target_kind="cloud",
                    provider="openai",
                    base_url="https://llm.example.com/v1",
                    model_name="gpt-tender",
                    enabled=True,
                    priority=1,
                    timeout_ms=12000,
                    use_anonymizer=True,
                )
            ],
        )

        policy = await resolve_effective_privacy_policy(db, route_key="tender", tender_id=42)

        self.assertEqual(policy.mode, "external_anonymized")
        self.assertTrue(policy.anonymizer_enabled)
        self.assertEqual(policy.target_id, 7)
        self.assertEqual(policy.target_provider, "openai")

    async def test_tender_override_can_force_internal_only(self) -> None:
        db = _FakeDb(
            settings_row=AppSettings(
                data={
                    "anonymizer_enabled": True,
                    "anonymizer_policy": {
                        "default": {"mode": "external_anonymized"},
                        "tenders": {"99": {"mode": "internal_only"}},
                    },
                }
            ),
            targets=[
                AIGatewayTarget(
                    id=8,
                    route_key="tender",
                    target_kind="cloud",
                    provider="openai",
                    base_url="https://llm.example.com/v1",
                    model_name="gpt-tender",
                    enabled=True,
                    priority=1,
                    timeout_ms=12000,
                    use_anonymizer=True,
                )
            ],
        )

        policy = await resolve_effective_privacy_policy(db, route_key="tender", tender_id=99)

        self.assertEqual(policy.mode, "internal_only")
        self.assertEqual(policy.target_id, 8)


if __name__ == "__main__":
    unittest.main()
