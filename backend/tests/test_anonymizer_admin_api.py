import os
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

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

from app.api.anonymizer_admin import router
from app.api.auth import UserResponse, get_current_user


class AnonymizerAdminApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        app = FastAPI()
        app.include_router(router, prefix="/anonymizer")
        app.dependency_overrides[get_current_user] = lambda: UserResponse(
            id=1,
            email="admin@test.local",
            name="Admin",
            role="admin",
        )
        cls.client = TestClient(app)

    def test_get_config_proxies_to_anonymizer_service(self) -> None:
        with patch(
            "app.api.anonymizer_admin._proxy_anonymizer",
            AsyncMock(return_value={"entities": ["PERSON"], "ttl_seconds": 3600}),
        ) as proxy_mock:
            response = self.client.get("/anonymizer/config")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["entities"], ["PERSON"])
        proxy_mock.assert_awaited_once_with("GET", "/v1/config")

    def test_test_endpoint_passes_payload_to_anonymizer(self) -> None:
        with patch(
            "app.api.anonymizer_admin._proxy_anonymizer",
            AsyncMock(return_value={"session_id": "sess-1", "chunks": []}),
        ) as proxy_mock:
            response = self.client.post(
                "/anonymizer/test",
                json={"text": "Mario Rossi", "config": {"entities": ["PERSON"]}},
            )

        self.assertEqual(response.status_code, 200)
        proxy_mock.assert_awaited_once_with(
            "POST",
            "/v1/anonymize",
            {"text": "Mario Rossi", "config": {"entities": ["PERSON"]}},
        )


if __name__ == "__main__":
    unittest.main()
