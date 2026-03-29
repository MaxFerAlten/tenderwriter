"""Helpers to migrate the legacy KPI SQLite store into the configured primary database."""

from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Any

from app.store import SqliteStore

_MIGRATION_TABLE_ORDER = [
    'kpi_model_versions',
    'kpi_tenders',
    'kpi_domain_events',
    'kpi_document_contexts',
    'kpi_analysis_jobs',
    'kpi_snapshots',
    'kpi_findings',
    'kpi_phase_transitions',
]
_SEQUENCE_TABLES = [
    'kpi_domain_events',
    'kpi_document_contexts',
    'kpi_analysis_jobs',
    'kpi_model_versions',
    'kpi_snapshots',
    'kpi_findings',
    'kpi_phase_transitions',
]


def _source_exists(source_path: str | None) -> bool:
    if not source_path:
        return False
    return Path(source_path).exists()


def migrate_legacy_sqlite_to_store(source_path: str | None, target_store: SqliteStore) -> dict[str, Any]:
    if not _source_exists(source_path):
        return {
            'status': 'skipped',
            'reason': 'legacy_source_missing',
            'source_path': source_path,
            'migrated_tables': {},
        }

    if target_store.has_persisted_data():
        return {
            'status': 'skipped',
            'reason': 'target_store_not_empty',
            'source_path': source_path,
            'migrated_tables': {},
        }

    source = sqlite3.connect(str(source_path))
    source.row_factory = sqlite3.Row
    migrated_tables: dict[str, int] = {}

    try:
        target_connection = target_store._require_connection()
        for table_name in _MIGRATION_TABLE_ORDER:
            rows = source.execute(f'SELECT * FROM {table_name} ORDER BY 1 ASC').fetchall()
            migrated_tables[table_name] = len(rows)
            if not rows:
                continue

            columns = list(rows[0].keys())
            insert_sql = (
                f"INSERT INTO {table_name} ({', '.join(columns)}) "
                f"VALUES ({', '.join(['?'] * len(columns))})"
            )
            for row in rows:
                target_connection.execute(insert_sql, tuple(row[column] for column in columns))

        target_connection.commit()
        _sync_postgres_sequences(target_store)

        version_row = source.execute('SELECT version_num FROM alembic_version LIMIT 1').fetchone()
        return {
            'status': 'completed',
            'reason': None,
            'source_path': source_path,
            'source_schema_version': (None if version_row is None else version_row['version_num']),
            'migrated_tables': migrated_tables,
        }
    finally:
        source.close()


def validate_legacy_sqlite_counts(source_path: str | None, target_store: SqliteStore) -> dict[str, Any]:
    if not _source_exists(source_path):
        return {
            'status': 'skipped',
            'reason': 'legacy_source_missing',
            'counts': {},
        }

    source = sqlite3.connect(str(source_path))
    try:
        counts: dict[str, dict[str, Any]] = {}
        all_matched = True
        for table_name in _MIGRATION_TABLE_ORDER:
            source_count = int(source.execute(f'SELECT COUNT(*) FROM {table_name}').fetchone()[0] or 0)
            target_count = target_store.table_row_count(table_name)
            matched = source_count == target_count
            all_matched = all_matched and matched
            counts[table_name] = {
                'source_count': source_count,
                'target_count': target_count,
                'matched': matched,
            }

        return {
            'status': 'completed' if all_matched else 'mismatch',
            'reason': None if all_matched else 'row_count_mismatch',
            'counts': counts,
        }
    finally:
        source.close()


def _sync_postgres_sequences(target_store: SqliteStore) -> None:
    connection = target_store._require_connection()
    if connection.backend_name != 'postgresql':
        return

    schema_prefix = f'{target_store.schema_name}.' if target_store.schema_name else ''
    for table_name in _SEQUENCE_TABLES:
        connection.execute(
            """
            SELECT setval(
                pg_get_serial_sequence(?, 'id'),
                COALESCE((SELECT MAX(id) FROM """ + schema_prefix + table_name + """), 1),
                COALESCE((SELECT MAX(id) FROM """ + schema_prefix + table_name + """), 0) > 0
            )
            """,
            (f'{schema_prefix}{table_name}',),
        )
    connection.commit()
