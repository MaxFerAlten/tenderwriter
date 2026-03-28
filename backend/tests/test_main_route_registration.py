import os
import inspect
import unittest

_TEST_ENV = {
    "APP_SECRET_KEY": "alpha-key-123456789012345678901234567890",
    "ADMIN_PASSWORD": "test-admin-password-1234567890",
    "DATABASE_URL": "postgresql+asyncpg://tester:securepass@localhost:5432/tenderwriter",
    "NEO4J_PASSWORD": "test-neo4j-password-1234567890",
    "MINIO_SECRET_KEY": "test-minio-password-1234567890",
    "ONLYOFFICE_JWT_SECRET": "office-jwt-token-12345678901234567890",
    "KPI_REASON_ENGINE_BASE_URL": "http://kpi-service.test",
    "KPI_REASON_ENGINE_SERVICE_TOKEN": "service-token-123",
}
for key, value in _TEST_ENV.items():
    os.environ.setdefault(key, value)

from app.main import create_app, lifespan


class RouteRegistrationTests(unittest.TestCase):
    def test_observability_routes_are_registered_under_api_tenders(self) -> None:
        app = create_app()
        paths = {route.path for route in app.routes}

        self.assertIn("/api/tenders/{tender_id}/observability/workspace", paths)
        self.assertIn("/api/tenders/{tender_id}/observability/summary", paths)
        self.assertIn("/api/tenders/{tender_id}/observability/contributions", paths)

    def test_sprint_18_lifecycle_routes_are_registered(self) -> None:
        app = create_app()
        paths = {route.path for route in app.routes}

        self.assertIn("/api/tenders/{tender_id}/decision", paths)
        self.assertIn("/api/tenders/{tender_id}/bid-plan", paths)
        self.assertIn("/api/tenders/{tender_id}/contribution-wave", paths)
        self.assertIn("/api/tenders/{tender_id}/outcome", paths)
        self.assertIn("/api/tenders/{tender_id}/clarifications", paths)
        self.assertIn("/api/tenders/{tender_id}/clarifications/{clarification_id}/submit", paths)
        self.assertIn("/api/proposals/{proposal_id}/draft-ready", paths)
        self.assertIn("/api/proposals/{proposal_id}/submission-status", paths)
        self.assertIn("/api/system/capabilities", paths)
        self.assertIn("/api/anonymizer/config", paths)
        self.assertIn("/api/anonymizer/stats", paths)
        self.assertIn("/api/anonymizer/test", paths)

    def test_lifespan_schedules_rag_initialization_in_background(self) -> None:
        source = inspect.getsource(lifespan)

        self.assertIn("app.state.rag_engine_initialization_task = asyncio.create_task", source)
        self.assertIn("await app.state.rag_engine.initialize()", source)


if __name__ == "__main__":
    unittest.main()
