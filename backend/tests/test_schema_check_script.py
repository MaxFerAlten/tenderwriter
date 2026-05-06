"""Guardrails for the manual schema verification script."""

from __future__ import annotations

from pathlib import Path


def test_check_db_schema_reports_alembic_state_and_gateway_columns() -> None:
    """The manual verification script should expose the key post-migration signals."""

    source = (Path(__file__).resolve().parents[1] / "app" / "check_db_schema.py").read_text(
        encoding="utf-8"
    )

    assert "BOOTSTRAP_MODE_CONFIG" in source
    assert "ALEMBIC_VERSION_TABLE" in source
    assert "ALEMBIC_VERSION:" in source
    assert "AI_GATEWAY_TARGET_COLUMNS" in source
    assert "PUBLIC_TABLE_COUNT" in source
