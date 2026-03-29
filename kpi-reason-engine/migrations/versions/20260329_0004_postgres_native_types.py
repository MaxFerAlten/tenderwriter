"""promote postgres columns to native jsonb and timestamptz

Revision ID: 20260329_0004
Revises: 20260315_0003
Create Date: 2026-03-29 19:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260329_0004"
down_revision = "20260315_0003"
branch_labels = None
depends_on = None


def _schema_name() -> str | None:
    normalized = str(op.get_context().config.get_main_option("kpi.schema") or "").strip()
    return normalized or None


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _jsonb_type() -> postgresql.JSONB:
    return postgresql.JSONB(astext_type=sa.Text())


def _promote_json_column(
    table_name: str,
    column_name: str,
    *,
    empty_literal: str,
    nullable: bool,
    server_default: str | None = None,
) -> None:
    schema_name = _schema_name()
    if server_default is not None:
        op.alter_column(
            table_name,
            column_name,
            schema=schema_name,
            existing_type=sa.Text(),
            existing_nullable=nullable,
            server_default=None,
        )
    using_expression = (
        f"CASE "
        f"WHEN {column_name} IS NULL OR btrim({column_name}) = '' THEN '{empty_literal}'::jsonb "
        f"ELSE {column_name}::jsonb "
        f"END"
    )
    op.alter_column(
        table_name,
        column_name,
        schema=schema_name,
        existing_type=sa.Text(),
        type_=_jsonb_type(),
        existing_nullable=nullable,
        postgresql_using=using_expression,
    )
    op.alter_column(
        table_name,
        column_name,
        schema=schema_name,
        existing_type=_jsonb_type(),
        existing_nullable=nullable,
        server_default=None if server_default is None else sa.text(server_default),
    )


def _promote_timestamp_column(table_name: str, column_name: str, *, nullable: bool) -> None:
    schema_name = _schema_name()
    using_expression = f"NULLIF({column_name}, '')::timestamptz"
    op.alter_column(
        table_name,
        column_name,
        schema=schema_name,
        existing_type=sa.Text(),
        type_=sa.DateTime(timezone=True),
        existing_nullable=nullable,
        postgresql_using=using_expression,
    )


def _demote_json_column(
    table_name: str,
    column_name: str,
    *,
    nullable: bool,
    server_default: str | None = None,
) -> None:
    schema_name = _schema_name()
    if server_default is not None:
        op.alter_column(
            table_name,
            column_name,
            schema=schema_name,
            existing_type=_jsonb_type(),
            existing_nullable=nullable,
            server_default=None,
        )
    op.alter_column(
        table_name,
        column_name,
        schema=schema_name,
        existing_type=_jsonb_type(),
        type_=sa.Text(),
        existing_nullable=nullable,
        postgresql_using=f"{column_name}::text",
    )
    if server_default is not None:
        op.alter_column(
            table_name,
            column_name,
            schema=schema_name,
            existing_type=sa.Text(),
            existing_nullable=nullable,
            server_default=server_default,
        )


def _demote_timestamp_column(table_name: str, column_name: str, *, nullable: bool) -> None:
    schema_name = _schema_name()
    op.alter_column(
        table_name,
        column_name,
        schema=schema_name,
        existing_type=sa.DateTime(timezone=True),
        type_=sa.Text(),
        existing_nullable=nullable,
        postgresql_using=f"{column_name}::text",
    )


def upgrade() -> None:
    if not _is_postgresql():
        return

    _promote_json_column("kpi_tenders", "departments_json", empty_literal="[]", nullable=False, server_default="'[]'::jsonb")
    _promote_json_column(
        "kpi_tenders",
        "requirement_contexts_json",
        empty_literal="[]",
        nullable=False,
        server_default="'[]'::jsonb",
    )
    _promote_json_column(
        "kpi_tenders",
        "section_contexts_json",
        empty_literal="[]",
        nullable=False,
        server_default="'[]'::jsonb",
    )
    _promote_json_column("kpi_tenders", "metadata_json", empty_literal="{}", nullable=False, server_default="'{}'::jsonb")
    _promote_timestamp_column("kpi_tenders", "due_at", nullable=True)
    _promote_timestamp_column("kpi_tenders", "created_at", nullable=False)
    _promote_timestamp_column("kpi_tenders", "updated_at", nullable=False)
    _promote_timestamp_column("kpi_tenders", "last_synced_at", nullable=False)

    _promote_timestamp_column("kpi_domain_events", "occurred_at", nullable=False)
    _promote_json_column("kpi_domain_events", "payload_json", empty_literal="{}", nullable=False)
    _promote_timestamp_column("kpi_domain_events", "created_at", nullable=False)

    _promote_json_column("kpi_document_contexts", "metadata_json", empty_literal="{}", nullable=False, server_default="'{}'::jsonb")
    _promote_timestamp_column("kpi_document_contexts", "created_at", nullable=False)

    _promote_json_column("kpi_analysis_jobs", "metadata_json", empty_literal="{}", nullable=False, server_default="'{}'::jsonb")
    _promote_timestamp_column("kpi_analysis_jobs", "created_at", nullable=False)
    _promote_timestamp_column("kpi_analysis_jobs", "started_at", nullable=True)
    _promote_timestamp_column("kpi_analysis_jobs", "completed_at", nullable=True)
    _promote_timestamp_column("kpi_analysis_jobs", "updated_at", nullable=True)

    _promote_json_column("kpi_model_versions", "descriptor_json", empty_literal="{}", nullable=False, server_default="'{}'::jsonb")
    _promote_timestamp_column("kpi_model_versions", "created_at", nullable=False)

    _promote_json_column("kpi_snapshots", "kpis_json", empty_literal="[]", nullable=False)
    _promote_json_column("kpi_snapshots", "notes_json", empty_literal="[]", nullable=False, server_default="'[]'::jsonb")
    _promote_json_column(
        "kpi_snapshots",
        "analysis_metadata_json",
        empty_literal="{}",
        nullable=False,
        server_default="'{}'::jsonb",
    )
    _promote_timestamp_column("kpi_snapshots", "generated_at", nullable=False)
    _promote_timestamp_column("kpi_snapshots", "created_at", nullable=False)

    _promote_timestamp_column("kpi_findings", "created_at", nullable=False)

    _promote_timestamp_column("kpi_phase_transitions", "occurred_at", nullable=True)
    _promote_timestamp_column("kpi_phase_transitions", "created_at", nullable=False)


def downgrade() -> None:
    if not _is_postgresql():
        return

    _demote_timestamp_column("kpi_phase_transitions", "created_at", nullable=False)
    _demote_timestamp_column("kpi_phase_transitions", "occurred_at", nullable=True)

    _demote_timestamp_column("kpi_findings", "created_at", nullable=False)

    _demote_timestamp_column("kpi_snapshots", "created_at", nullable=False)
    _demote_timestamp_column("kpi_snapshots", "generated_at", nullable=False)
    _demote_json_column("kpi_snapshots", "analysis_metadata_json", nullable=False, server_default="'{}'")
    _demote_json_column("kpi_snapshots", "notes_json", nullable=False, server_default="'[]'")
    _demote_json_column("kpi_snapshots", "kpis_json", nullable=False)

    _demote_timestamp_column("kpi_model_versions", "created_at", nullable=False)
    _demote_json_column("kpi_model_versions", "descriptor_json", nullable=False, server_default="'{}'")

    _demote_timestamp_column("kpi_analysis_jobs", "updated_at", nullable=True)
    _demote_timestamp_column("kpi_analysis_jobs", "completed_at", nullable=True)
    _demote_timestamp_column("kpi_analysis_jobs", "started_at", nullable=True)
    _demote_timestamp_column("kpi_analysis_jobs", "created_at", nullable=False)
    _demote_json_column("kpi_analysis_jobs", "metadata_json", nullable=False, server_default="'{}'")

    _demote_timestamp_column("kpi_document_contexts", "created_at", nullable=False)
    _demote_json_column("kpi_document_contexts", "metadata_json", nullable=False, server_default="'{}'")

    _demote_timestamp_column("kpi_domain_events", "created_at", nullable=False)
    _demote_json_column("kpi_domain_events", "payload_json", nullable=False)
    _demote_timestamp_column("kpi_domain_events", "occurred_at", nullable=False)

    _demote_timestamp_column("kpi_tenders", "last_synced_at", nullable=False)
    _demote_timestamp_column("kpi_tenders", "updated_at", nullable=False)
    _demote_timestamp_column("kpi_tenders", "created_at", nullable=False)
    _demote_timestamp_column("kpi_tenders", "due_at", nullable=True)
    _demote_json_column("kpi_tenders", "metadata_json", nullable=False, server_default="'{}'")
    _demote_json_column("kpi_tenders", "section_contexts_json", nullable=False, server_default="'[]'")
    _demote_json_column("kpi_tenders", "requirement_contexts_json", nullable=False, server_default="'[]'")
    _demote_json_column("kpi_tenders", "departments_json", nullable=False, server_default="'[]'")
