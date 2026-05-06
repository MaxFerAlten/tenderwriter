import inspect
import os
import sys
import unittest
from contextlib import contextmanager
from importlib import import_module
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import APIRouter

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


def _router_module(*paths: str, extras: dict | None = None) -> ModuleType:
    module = ModuleType("fake_router_module")
    router = APIRouter()

    for index, path in enumerate(paths):

        async def _handler(_path=path):
            return {"path": _path}

        router.add_api_route(path, _handler, methods=["GET"], name=f"handler_{index}")

    module.router = router
    for key, value in (extras or {}).items():
        setattr(module, key, value)
    return module


def _build_main_test_modules() -> tuple[dict[str, object], type]:
    fake_config = ModuleType("app.config")
    fake_config.settings = SimpleNamespace(
        app_name="TenderWriter Test",
        app_version="test-version",
        app_debug=False,
        cors_origins="http://localhost",
        admin_username="admin@test.local",
        admin_password="admin-password",
        admin_enabled=False,
    )

    fake_slowapi = ModuleType("slowapi")
    fake_slowapi._rate_limit_exceeded_handler = lambda *args, **kwargs: None

    fake_slowapi_errors = ModuleType("slowapi.errors")

    class _FakeRateLimitExceededError(Exception):
        pass

    fake_slowapi_errors.RateLimitExceeded = _FakeRateLimitExceededError

    fake_sqlalchemy = ModuleType("sqlalchemy")

    class _FakeSelect:
        def where(self, *args, **kwargs):
            return self

    fake_sqlalchemy.select = lambda *args, **kwargs: _FakeSelect()

    fake_models = ModuleType("app.models")

    class _FakeUser:
        email = "email"

    fake_models.User = _FakeUser

    class _FakeScalarResult:
        def scalar_one_or_none(self):
            return None

    class _FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def execute(self, query):
            return _FakeScalarResult()

        async def commit(self):
            return None

        def add(self, row):
            return None

    fake_db_database = ModuleType("app.db.database")
    fake_db_database.async_session_factory = lambda: _FakeSession()
    fake_db_database.init_db = AsyncMock()
    fake_db_database.close_db = AsyncMock()

    fake_db_redis = ModuleType("app.db.redis")
    fake_db_redis.close_redis = AsyncMock()

    fake_auth = _router_module(
        extras={
            "limiter": object(),
            "hash_password": lambda password: f"hashed:{password}",
        }
    )
    fake_admin = _router_module()
    fake_chat = _router_module()
    fake_content_library = _router_module()
    fake_data_explorer = _router_module()
    fake_gateway_admin = _router_module()
    fake_kpi_admin = _router_module()
    fake_mattermost = _router_module()
    fake_onlyoffice = _router_module()
    fake_rag = _router_module()
    fake_planningcoverage = _router_module("/config", "/test")

    fake_anonymizer_admin = _router_module("/config", "/stats", "/test")
    fake_system = _router_module("/capabilities")
    fake_proposals = _router_module(
        "/{proposal_id}/draft-ready",
        "/{proposal_id}/submission-status",
    )
    fake_observability = _router_module(
        "/{tender_id}/observability/workspace",
        "/{tender_id}/observability/summary",
        "/{tender_id}/observability/contributions",
    )
    fake_tenders = _router_module(
        "/{tender_id}/decision",
        "/{tender_id}/bid-plan",
        "/{tender_id}/contribution-wave",
        "/{tender_id}/coordination-risk",
        "/{tender_id}/coordination-recovery",
        "/{tender_id}/gate-rework",
        "/{tender_id}/gate-stop",
        "/{tender_id}/outcome",
        "/{tender_id}/clarifications",
        "/{tender_id}/clarifications/{clarification_id}/submit",
    )
    fake_tasks = _router_module()
    fake_ingestions = _router_module()
    fake_intelligence = _router_module(
        "/tools",
        "/tools/coverage-analyzer",
        "/tools/evidence-auditor",
        "/tools/compliance-panorama",
        "/tools/graph-path-explainer",
        "/tools/contradiction-finder",
        "/query",
    )
    fake_lifecycle_projector = ModuleType("app.intelligence.lifecycle_projector")
    fake_lifecycle_projector.set_active_rag_engine = lambda rag_engine: None

    fake_rag_engine = ModuleType("app.rag.engine")

    class FakeHybridRAGEngine:
        instances: list["FakeHybridRAGEngine"] = []

        def __init__(self):
            self.initialize_calls = 0
            self.shutdown_calls = 0
            type(self).instances.append(self)

        async def initialize(self):
            self.initialize_calls += 1

        async def shutdown(self):
            self.shutdown_calls += 1

    fake_rag_engine.HybridRAGEngine = FakeHybridRAGEngine

    modules = {
        "app.config": fake_config,
        "slowapi": fake_slowapi,
        "slowapi.errors": fake_slowapi_errors,
        "sqlalchemy": fake_sqlalchemy,
        "app.models": fake_models,
        "app.db.database": fake_db_database,
        "app.db.redis": fake_db_redis,
        "app.api.admin": fake_admin,
        "app.api.anonymizer_admin": fake_anonymizer_admin,
        "app.api.auth": fake_auth,
        "app.api.chat": fake_chat,
        "app.api.content_library": fake_content_library,
        "app.api.data_explorer": fake_data_explorer,
        "app.api.gateway_admin": fake_gateway_admin,
        "app.api.kpi_admin": fake_kpi_admin,
        "app.api.mattermost": fake_mattermost,
        "app.api.observability": fake_observability,
        "app.api.onlyoffice": fake_onlyoffice,
        "app.api.planningcoverage": fake_planningcoverage,
        "app.api.proposals": fake_proposals,
        "app.api.rag": fake_rag,
        "app.api.system": fake_system,
        "app.api.tenders": fake_tenders,
        "app.api.tasks": fake_tasks,
        "app.api.ingestions": fake_ingestions,
        "app.api.intelligence": fake_intelligence,
        "app.intelligence.lifecycle_projector": fake_lifecycle_projector,
        "app.rag.engine": fake_rag_engine,
    }
    return modules, FakeHybridRAGEngine


@contextmanager
def _load_main_module():
    from unittest.mock import patch

    modules, fake_engine_cls = _build_main_test_modules()
    with patch.dict(sys.modules, modules):
        sys.modules.pop("app.main", None)
        main_module = import_module("app.main")
        try:
            yield main_module, fake_engine_cls
        finally:
            sys.modules.pop("app.main", None)
            fake_engine_cls.instances.clear()


class RouteRegistrationTests(unittest.IsolatedAsyncioTestCase):
    def test_observability_routes_are_registered_under_api_tenders(self) -> None:
        with _load_main_module() as (main_module, _):
            app = main_module.create_app()
            paths = {route.path for route in app.routes}

        self.assertIn("/api/tenders/{tender_id}/observability/workspace", paths)
        self.assertIn("/api/tenders/{tender_id}/observability/summary", paths)
        self.assertIn("/api/tenders/{tender_id}/observability/contributions", paths)

    def test_sprint_18_lifecycle_routes_are_registered(self) -> None:
        with _load_main_module() as (main_module, _):
            app = main_module.create_app()
            paths = {route.path for route in app.routes}

        self.assertIn("/api/tenders/{tender_id}/decision", paths)
        self.assertIn("/api/tenders/{tender_id}/bid-plan", paths)
        self.assertIn("/api/tenders/{tender_id}/contribution-wave", paths)
        self.assertIn("/api/tenders/{tender_id}/coordination-risk", paths)
        self.assertIn("/api/tenders/{tender_id}/coordination-recovery", paths)
        self.assertIn("/api/tenders/{tender_id}/gate-rework", paths)
        self.assertIn("/api/tenders/{tender_id}/gate-stop", paths)
        self.assertIn("/api/tenders/{tender_id}/outcome", paths)
        self.assertIn("/api/tenders/{tender_id}/clarifications", paths)
        self.assertIn("/api/tenders/{tender_id}/clarifications/{clarification_id}/submit", paths)
        self.assertIn("/api/proposals/{proposal_id}/draft-ready", paths)
        self.assertIn("/api/proposals/{proposal_id}/submission-status", paths)
        self.assertIn("/api/system/capabilities", paths)
        self.assertIn("/api/anonymizer/config", paths)
        self.assertIn("/api/anonymizer/stats", paths)
        self.assertIn("/api/anonymizer/test", paths)

    def test_intelligence_routes_are_registered(self) -> None:
        with _load_main_module() as (main_module, _):
            app = main_module.create_app()
            paths = {route.path for route in app.routes}

        self.assertIn("/api/intelligence/tools", paths)
        self.assertIn("/api/intelligence/tools/coverage-analyzer", paths)
        self.assertIn("/api/intelligence/tools/evidence-auditor", paths)
        self.assertIn("/api/intelligence/tools/compliance-panorama", paths)
        self.assertIn("/api/intelligence/tools/graph-path-explainer", paths)
        self.assertIn("/api/intelligence/tools/contradiction-finder", paths)
        self.assertIn("/api/intelligence/query", paths)

    def test_planning_coverage_routes_are_registered(self) -> None:
        with _load_main_module() as (main_module, _):
            app = main_module.create_app()
            paths = {route.path for route in app.routes}

        self.assertIn("/api/planningcoverage/config", paths)
        self.assertIn("/api/planningcoverage/test", paths)

    def test_lifespan_configures_lazy_rag_initialization(self) -> None:
        with _load_main_module() as (main_module, _):
            source = inspect.getsource(main_module.lifespan)

        self.assertIn("app.state.rag_engine = HybridRAGEngine()", source)
        self.assertIn("app.state.rag_engine_initialization_task = None", source)
        self.assertNotIn("asyncio.create_task", source)
        self.assertNotIn("await app.state.rag_engine.initialize()", source)

    async def test_lifespan_creates_engine_without_eager_initialization(self) -> None:
        with _load_main_module() as (main_module, fake_engine_cls):
            app = SimpleNamespace(state=SimpleNamespace())

            async with main_module.lifespan(app):
                self.assertIsInstance(app.state.rag_engine, fake_engine_cls)
                self.assertIsNone(app.state.rag_engine_initialization_task)
                self.assertEqual(app.state.rag_engine.initialize_calls, 0)

            self.assertEqual(fake_engine_cls.instances[0].shutdown_calls, 1)


if __name__ == "__main__":
    unittest.main()
