"""Schema inventory tests used to prepare controlled Alembic migration work."""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
import warnings
from importlib import import_module
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

import sqlalchemy as sa
from test_module_loaders import load_models_test_module


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


def _close_default_event_loop() -> None:
    try:
        loop = asyncio.get_event_loop_policy().get_event_loop()
    except RuntimeError:
        return
    if loop.is_running() or loop.is_closed():
        return
    loop.close()
    asyncio.set_event_loop(None)


def _load_schema_inventory_module():
    load_models_test_module()

    fake_config = ModuleType("app.config")
    fake_config.settings = SimpleNamespace(
        database_url=_TEST_ENV["DATABASE_URL"],
        app_debug=False,
    )

    with (
        patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=Mock()),
        patch.dict(sys.modules, {"app.config": fake_config}),
    ):
        for module_name in list(sys.modules):
            if module_name == "app.db.database" or module_name == "app.db.schema_inventory":
                sys.modules.pop(module_name, None)
            elif module_name == "app.models" or module_name.startswith("app.models."):
                sys.modules.pop(module_name, None)
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="The GenericFunction .* is already registered and is going to be overridden.",
                category=sa.exc.SAWarning,
            )
            warnings.filterwarnings(
                "ignore",
                message="The GenericFunction '.*' is already registered and is going to be overridden.",
                category=sa.exc.SAWarning,
            )
            module = import_module("app.db.schema_inventory")
    _close_default_event_loop()
    return module


def _load_baseline_revision_module():
    revision_path = (
        Path(__file__).resolve().parents[1]
        / "migrations"
        / "versions"
        / "20260403_0001_backend_schema_baseline.py"
    )
    spec = importlib.util.spec_from_file_location("test_backend_schema_baseline", revision_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="The GenericFunction .* is already registered and is going to be overridden.",
            category=sa.exc.SAWarning,
        )
        warnings.filterwarnings(
            "ignore",
            message="The GenericFunction '.*' is already registered and is going to be overridden.",
            category=sa.exc.SAWarning,
        )
        warnings.filterwarnings(
            "ignore",
            message="The GenericFunction 'hstore.*' is already registered and is going to be overridden.",
            category=sa.exc.SAWarning,
        )
        warnings.filterwarnings(
            "ignore",
            message="The GenericFunction '.*' is already registered and is going to be overridden.",
            category=sa.exc.SAWarning,
        )
        spec.loader.exec_module(module)
    _close_default_event_loop()
    return module


def test_schema_inventory_captures_compatibility_columns() -> None:
    """The metadata inventory should expose the legacy compatibility columns explicitly."""

    schema_inventory = _load_schema_inventory_module()

    inventory = schema_inventory.build_schema_inventory()
    users_columns = {column["name"] for column in inventory["tables"]["users"]["columns"]}
    gateway_columns = {
        column["name"] for column in inventory["tables"]["ai_gateway_targets"]["columns"]
    }

    assert inventory["table_count"] > 0
    assert {"is_active", "is_verified"} <= users_columns
    assert {"connection_method", "api_key"} <= gateway_columns
    assert inventory["compatibility_columns"] == {
        "users": {"is_active": True, "is_verified": True},
        "ai_gateway_targets": {"connection_method": True, "api_key": True},
    }


def test_baseline_revision_covers_schema_inventory_tables() -> None:
    """The baseline revision should cover the same tables exposed by the inventory snapshot."""

    schema_inventory = _load_schema_inventory_module()
    baseline_revision = _load_baseline_revision_module()

    inventory = schema_inventory.build_schema_inventory()

    assert set(baseline_revision.BASELINE_TABLES) == set(inventory["tables"])
    assert baseline_revision.revision == "20260403_0001"
    assert baseline_revision.down_revision is None
