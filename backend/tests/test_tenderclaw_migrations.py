"""Tests for migrations system."""

import json
import tempfile
from pathlib import Path

import pytest

from backend.migrations.registry import MigrationRegistry, Migration
from backend.migrations.runner import (
    load_migrations_state,
    save_migrations_state,
    run_all_pending,
    get_migration_status,
    MIGRATIONS_STATE_FILE,
)


@pytest.fixture(autouse=True)
def reset_registry():
    """Reset migration registry before each test."""
    MigrationRegistry._migrations.clear()
    MigrationRegistry._applied.clear()
    yield
    MigrationRegistry._migrations.clear()
    MigrationRegistry._applied.clear()


@pytest.fixture
def temp_migrations_file(monkeypatch):
    """Create a temporary migrations state file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        temp_file = Path(tmpdir) / "migrations.json"
        monkeypatch.setattr("backend.migrations.runner.MIGRATIONS_STATE_FILE", temp_file)
        yield temp_file


class TestMigrationRegistry:
    def test_register(self):
        """Test registering a migration."""
        def migrate_fn():
            pass
        
        MigrationRegistry.register(
            "test_001",
            "Test migration",
            migrate=migrate_fn,
            rollback=None,
        )
        
        assert "test_001" in MigrationRegistry._migrations
        migration = MigrationRegistry._migrations["test_001"]
        assert migration.id == "test_001"
        assert migration.description == "Test migration"
        assert migration.migrate == migrate_fn

    def test_get_pending(self):
        """Test getting pending migrations."""
        def migrate_fn():
            pass
        
        MigrationRegistry.register("test_001", "Test 1", migrate=migrate_fn)
        MigrationRegistry.register("test_002", "Test 2", migrate=migrate_fn)
        
        pending = MigrationRegistry.get_pending()
        assert len(pending) == 2
        assert {m.id for m in pending} == {"test_001", "test_002"}

    def test_mark_applied(self):
        """Test marking migration as applied."""
        def migrate_fn():
            pass
        
        MigrationRegistry.register("test_001", "Test", migrate=migrate_fn)
        MigrationRegistry.mark_applied("test_001")
        
        pending = MigrationRegistry.get_pending()
        applied = MigrationRegistry.get_applied()
        
        assert len(pending) == 0
        assert len(applied) == 1
        assert applied[0].id == "test_001"

    def test_run_pending(self):
        """Test running pending migrations."""
        run_count = {"value": 0}
        
        def migrate_fn():
            run_count["value"] += 1
        
        MigrationRegistry.register("test_001", "Test", migrate=migrate_fn)
        MigrationRegistry.register("test_002", "Test", migrate=migrate_fn)
        
        run_ids = MigrationRegistry.run_pending()
        
        assert run_ids == ["test_001", "test_002"]
        assert run_count["value"] == 2
        assert len(MigrationRegistry.get_pending()) == 0

    def test_run_pending_with_failure(self):
        """Test that migration failure raises exception."""
        def bad_migrate():
            raise ValueError("Migration failed")
        
        MigrationRegistry.register("test_001", "Test", migrate=bad_migrate)
        
        with pytest.raises(RuntimeError, match="Migration test_001 failed"):
            MigrationRegistry.run_pending()


class TestRunner:
    def test_save_and_load_state(self, temp_migrations_file):
        """Test saving and loading migration state."""
        state = {"test_001": "2024-01-01T00:00:00", "test_002": "2024-01-02T00:00:00"}
        
        save_migrations_state(state)
        loaded = load_migrations_state()
        
        assert loaded == state

    def test_run_all_pending(self, temp_migrations_file):
        """Test running all pending migrations."""
        def migrate_fn():
            pass
        
        MigrationRegistry.register("test_001", "Test", migrate=migrate_fn)
        
        run_ids = run_all_pending()
        
        assert run_ids == ["test_001"]
        assert "test_001" in load_migrations_state()

    def test_get_migration_status(self, temp_migrations_file):
        """Test getting migration status."""
        def migrate_fn():
            pass
        
        MigrationRegistry.register("test_001", "Test 1", migrate=migrate_fn)
        MigrationRegistry.register("test_002", "Test 2", migrate=migrate_fn)
        MigrationRegistry.mark_applied("test_001")
        
        status = get_migration_status()
        
        assert status["total"] == 2
        assert status["applied"] == 1
        assert status["pending"] == 1
        assert len(status["migrations"]) == 2
