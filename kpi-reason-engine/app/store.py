"""SQLite-backed persistence for tw-kpi-reason-engine."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.analytics import AnalysisSnapshot
from app.transition_diagnostics import TransitionSnapshot

_REQUIRED_TABLES = {
    'alembic_version',
    'kpi_tenders',
    'kpi_domain_events',
    'kpi_document_contexts',
    'kpi_analysis_jobs',
    'kpi_model_versions',
    'kpi_snapshots',
    'kpi_findings',
    'kpi_phase_transitions',
}

def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_json(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, sort_keys=True)


def _to_json_list(value: Any) -> str:
    return json.dumps(value if value is not None else [], ensure_ascii=False, sort_keys=True)


class SqliteStore:
    """Persistent repository layer for the KPI service."""

    def __init__(self, database_path: str) -> None:
        self.database_path = Path(database_path)
        self._lock = threading.RLock()
        self._connection: sqlite3.Connection | None = None

    def open(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.database_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        with self._lock:
            self._connection.execute('PRAGMA journal_mode=WAL;')
            self._connection.execute('PRAGMA foreign_keys=ON;')
            self._connection.execute('PRAGMA synchronous=NORMAL;')
            self._validate_schema()

    def close(self) -> None:
        if self._connection is None:
            return
        with self._lock:
            self._connection.close()
            self._connection = None

    def clear_all(self) -> None:
        with self._lock:
            connection = self._require_connection()
            connection.execute('DELETE FROM kpi_phase_transitions')
            connection.execute('DELETE FROM kpi_findings')
            connection.execute('DELETE FROM kpi_snapshots')
            connection.execute('DELETE FROM kpi_analysis_jobs')
            connection.execute('DELETE FROM kpi_document_contexts')
            connection.execute('DELETE FROM kpi_domain_events')
            connection.execute('DELETE FROM kpi_model_versions')
            connection.execute('DELETE FROM kpi_tenders')
            connection.commit()

    def upsert_tender(self, payload: dict[str, Any]) -> None:
        now = _utcnow_iso()
        with self._lock:
            connection = self._require_connection()
            connection.execute(
                """
                INSERT INTO kpi_tenders (
                    external_tender_id,
                    title,
                    customer_name,
                    due_at,
                    current_status,
                    departments_json,
                    requirement_contexts_json,
                    section_contexts_json,
                    metadata_json,
                    health,
                    analytical_phase,
                    created_at,
                    updated_at,
                    last_synced_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(external_tender_id) DO UPDATE SET
                    title = excluded.title,
                    customer_name = excluded.customer_name,
                    due_at = excluded.due_at,
                    current_status = excluded.current_status,
                    departments_json = excluded.departments_json,
                    requirement_contexts_json = excluded.requirement_contexts_json,
                    section_contexts_json = excluded.section_contexts_json,
                    metadata_json = excluded.metadata_json,
                    updated_at = excluded.updated_at,
                    last_synced_at = excluded.last_synced_at
                """,
                (
                    payload['external_tender_id'],
                    payload['title'],
                    payload.get('customer_name'),
                    payload.get('due_at'),
                    payload.get('current_status'),
                    _to_json_list(payload.get('departments', [])),
                    _to_json_list(payload.get('requirement_contexts', [])),
                    _to_json_list(payload.get('section_contexts', [])),
                    _to_json(payload.get('metadata', {})),
                    'unknown',
                    None,
                    now,
                    now,
                    now,
                ),
            )
            connection.commit()

    def insert_domain_event(self, external_tender_id: str, payload: dict[str, Any]) -> bool:
        envelope_json = _to_json(payload)
        envelope_hash = hashlib.sha256(envelope_json.encode('utf-8')).hexdigest()
        now = _utcnow_iso()

        with self._lock:
            connection = self._require_connection()
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO kpi_domain_events (
                    external_tender_id,
                    event_type,
                    occurred_at,
                    actor_id,
                    source,
                    schema_version,
                    payload_json,
                    envelope_hash,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    external_tender_id,
                    payload['event_type'],
                    payload['occurred_at'],
                    payload.get('actor_id'),
                    payload['source'],
                    payload.get('schema_version', '1.0.0'),
                    envelope_json,
                    envelope_hash,
                    now,
                ),
            )
            connection.commit()
            return cursor.rowcount == 1

    def store_document_context(self, external_tender_id: str, payload: dict[str, Any]) -> None:
        with self._lock:
            connection = self._require_connection()
            connection.execute(
                """
                INSERT INTO kpi_document_contexts (
                    external_tender_id,
                    document_id,
                    document_type,
                    filename,
                    extracted_text_ref,
                    metadata_json,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    external_tender_id,
                    payload['document_id'],
                    payload['document_type'],
                    payload.get('filename'),
                    payload.get('extracted_text_ref'),
                    _to_json(payload.get('metadata', {})),
                    _utcnow_iso(),
                ),
            )
            connection.commit()

    def enqueue_analysis_job(self, external_tender_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        now = _utcnow_iso()
        with self._lock:
            connection = self._require_connection()
            cursor = connection.execute(
                """
                INSERT INTO kpi_analysis_jobs (
                    external_tender_id,
                    job_type,
                    requested_by,
                    priority,
                    reason,
                    metadata_json,
                    status,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    external_tender_id,
                    payload['job_type'],
                    payload.get('requested_by'),
                    payload.get('priority', 'normal'),
                    payload.get('reason'),
                    _to_json(payload.get('metadata', {})),
                    'queued',
                    now,
                    now,
                ),
            )
            connection.commit()
            job_id = int(cursor.lastrowid)
        record = self.get_analysis_job(job_id)
        if record is None:
            raise RuntimeError('Failed to persist analysis job.')
        return record

    def get_analysis_job(self, job_id: int) -> dict[str, Any] | None:
        with self._lock:
            connection = self._require_connection()
            row = connection.execute(
                """
                SELECT j.id, j.external_tender_id, j.job_type, j.requested_by, j.priority, j.reason,
                       j.metadata_json, j.status, j.created_at, j.started_at, j.completed_at,
                       j.updated_at, j.error_message, j.result_snapshot_id,
                       s.generated_at AS latest_snapshot_generated_at
                FROM kpi_analysis_jobs AS j
                LEFT JOIN kpi_snapshots AS s ON s.id = j.result_snapshot_id
                WHERE j.id = ?
                LIMIT 1
                """,
                (job_id,),
            ).fetchone()
        return self._deserialize_analysis_job(row)

    def get_latest_analysis_job(self, external_tender_id: str) -> dict[str, Any] | None:
        with self._lock:
            connection = self._require_connection()
            row = connection.execute(
                """
                SELECT j.id, j.external_tender_id, j.job_type, j.requested_by, j.priority, j.reason,
                       j.metadata_json, j.status, j.created_at, j.started_at, j.completed_at,
                       j.updated_at, j.error_message, j.result_snapshot_id,
                       s.generated_at AS latest_snapshot_generated_at
                FROM kpi_analysis_jobs AS j
                LEFT JOIN kpi_snapshots AS s ON s.id = j.result_snapshot_id
                WHERE j.external_tender_id = ?
                ORDER BY j.id DESC
                LIMIT 1
                """,
                (external_tender_id,),
            ).fetchone()
        return self._deserialize_analysis_job(row)

    def claim_next_analysis_job(self) -> dict[str, Any] | None:
        with self._lock:
            connection = self._require_connection()
            row = connection.execute(
                """
                SELECT id
                FROM kpi_analysis_jobs
                WHERE status = 'queued'
                ORDER BY
                    CASE priority
                        WHEN 'high' THEN 0
                        WHEN 'normal' THEN 1
                        ELSE 2
                    END,
                    created_at ASC,
                    id ASC
                LIMIT 1
                """
            ).fetchone()
            if row is None:
                return None

            now = _utcnow_iso()
            cursor = connection.execute(
                """
                UPDATE kpi_analysis_jobs
                SET status = 'running',
                    started_at = COALESCE(started_at, ?),
                    updated_at = ?,
                    error_message = NULL
                WHERE id = ? AND status = 'queued'
                """,
                (now, now, int(row['id'])),
            )
            connection.commit()
            if cursor.rowcount != 1:
                return None
        return self.get_analysis_job(int(row['id']))

    def mark_analysis_job_succeeded(self, job_id: int, *, snapshot_record: dict[str, Any]) -> None:
        now = _utcnow_iso()
        with self._lock:
            connection = self._require_connection()
            connection.execute(
                """
                UPDATE kpi_analysis_jobs
                SET status = 'succeeded',
                    completed_at = ?,
                    updated_at = ?,
                    error_message = NULL,
                    result_snapshot_id = ?
                WHERE id = ?
                """,
                (now, now, snapshot_record.get('id'), job_id),
            )
            connection.commit()

    def mark_analysis_job_failed(self, job_id: int, *, error_message: str) -> None:
        now = _utcnow_iso()
        with self._lock:
            connection = self._require_connection()
            connection.execute(
                """
                UPDATE kpi_analysis_jobs
                SET status = 'failed',
                    completed_at = ?,
                    updated_at = ?,
                    error_message = ?,
                    result_snapshot_id = NULL
                WHERE id = ?
                """,
                (now, now, error_message[:1000], job_id),
            )
            connection.commit()

    def record_analysis_snapshot(
        self,
        external_tender_id: str,
        *,
        analysis: AnalysisSnapshot,
        transition_snapshot: TransitionSnapshot,
        generated_at_override: str | None = None,
    ) -> dict[str, Any]:
        generated_at = generated_at_override or _utcnow_iso()
        with self._lock:
            connection = self._require_connection()
            analysis_metadata = dict(analysis.analysis_metadata or {})
            model_version_id = self._ensure_model_versions(connection, analysis_metadata)
            kpis_payload = [score.model_dump(mode='json') for score in analysis.kpis]
            notes_payload = list(analysis.notes)
            snapshot_payload = {
                'analytical_phase': analysis.analytical_phase,
                'health': analysis.health,
                'summary': analysis.summary,
                'kpis': kpis_payload,
                'notes': notes_payload,
                'analysis_metadata': analysis_metadata,
            }
            snapshot_hash = hashlib.sha256(_to_json(snapshot_payload).encode('utf-8')).hexdigest()
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO kpi_snapshots (
                    external_tender_id,
                    snapshot_hash,
                    analytical_phase,
                    health,
                    summary,
                    kpis_json,
                    notes_json,
                    analysis_metadata_json,
                    model_version_id,
                    generated_at,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    external_tender_id,
                    snapshot_hash,
                    analysis.analytical_phase,
                    analysis.health,
                    analysis.summary,
                    _to_json_list(kpis_payload),
                    _to_json_list(notes_payload),
                    _to_json(analysis_metadata),
                    model_version_id,
                    generated_at,
                    generated_at,
                ),
            )
            snapshot_row = connection.execute(
                """
                SELECT id
                FROM kpi_snapshots
                WHERE external_tender_id = ? AND snapshot_hash = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (external_tender_id, snapshot_hash),
            ).fetchone()
            if snapshot_row is None:
                raise RuntimeError('Failed to persist KPI snapshot.')
            snapshot_id = int(snapshot_row['id'])

            if cursor.rowcount == 1:
                self._insert_snapshot_findings(connection, snapshot_id, analysis, generated_at)

            self._insert_phase_transitions(
                connection,
                external_tender_id,
                snapshot_id,
                transition_snapshot,
                generated_at,
            )
            connection.commit()

        record = self.get_latest_snapshot_record(external_tender_id)
        if record is None:
            raise RuntimeError('Failed to load persisted KPI snapshot.')
        return record

    def get_tender(self, external_tender_id: str) -> dict[str, Any] | None:
        with self._lock:
            connection = self._require_connection()
            row = connection.execute(
                'SELECT * FROM kpi_tenders WHERE external_tender_id = ?',
                (external_tender_id,),
            ).fetchone()
        if row is None:
            return None

        return {
            'external_tender_id': row['external_tender_id'],
            'title': row['title'],
            'customer_name': row['customer_name'],
            'due_at': row['due_at'],
            'current_status': row['current_status'],
            'departments': json.loads(row['departments_json'] or '[]'),
            'requirement_contexts': json.loads(row['requirement_contexts_json'] or '[]'),
            'section_contexts': json.loads(row['section_contexts_json'] or '[]'),
            'metadata': json.loads(row['metadata_json'] or '{}'),
            'health': row['health'] or 'unknown',
            'analytical_phase': row['analytical_phase'],
            'last_synced_at': row['last_synced_at'],
        }

    def get_latest_snapshot_record(self, external_tender_id: str) -> dict[str, Any] | None:
        with self._lock:
            connection = self._require_connection()
            row = connection.execute(
                """
                SELECT s.id, s.generated_at, s.analytical_phase, s.health, s.summary, s.kpis_json, s.notes_json,
                       s.analysis_metadata_json,
                       mv.version_code AS model_version_code
                FROM kpi_snapshots AS s
                LEFT JOIN kpi_model_versions AS mv ON mv.id = s.model_version_id
                WHERE s.external_tender_id = ?
                ORDER BY s.id DESC
                LIMIT 1
                """,
                (external_tender_id,),
            ).fetchone()
            if row is None:
                return None
            findings = connection.execute(
                """
                SELECT content
                FROM kpi_findings
                WHERE snapshot_id = ?
                ORDER BY id ASC
                """,
                (row['id'],),
            ).fetchall()
        return {
            'id': int(row['id']),
            'generated_at': row['generated_at'],
            'analytical_phase': row['analytical_phase'],
            'health': row['health'],
            'summary': row['summary'],
            'kpis': json.loads(row['kpis_json'] or '[]'),
            'notes': json.loads(row['notes_json'] or '[]'),
            'analysis_metadata': json.loads(row['analysis_metadata_json'] or '{}'),
            'model_version_code': row['model_version_code'],
            'findings': [item['content'] for item in findings],
        }

    def list_domain_events(self, external_tender_id: str) -> list[dict[str, Any]]:
        with self._lock:
            connection = self._require_connection()
            rows = connection.execute(
                """
                SELECT event_type, occurred_at, actor_id, source, schema_version, payload_json
                FROM kpi_domain_events
                WHERE external_tender_id = ?
                ORDER BY occurred_at ASC, id ASC
                """,
                (external_tender_id,),
            ).fetchall()

        return [
            {
                'event_type': row['event_type'],
                'occurred_at': row['occurred_at'],
                'actor_id': row['actor_id'],
                'source': row['source'],
                'schema_version': row['schema_version'],
                'payload': json.loads(row['payload_json'] or '{}'),
            }
            for row in rows
        ]

    def list_phase_transitions(self, external_tender_id: str, limit: int = 12) -> list[dict[str, Any]]:
        with self._lock:
            connection = self._require_connection()
            rows = connection.execute(
                """
                SELECT from_state, to_state, occurred_at, cause, confidence, source_event_type, related_entity_id
                FROM kpi_phase_transitions
                WHERE external_tender_id = ?
                ORDER BY COALESCE(occurred_at, created_at) DESC, id DESC
                LIMIT ?
                """,
                (external_tender_id, limit),
            ).fetchall()
        return [
            {
                'from_state': row['from_state'],
                'to_state': row['to_state'],
                'occurred_at': row['occurred_at'],
                'cause': row['cause'],
                'confidence': row['confidence'],
                'source_event_type': row['source_event_type'],
                'source_type': 'inferred' if str(row['source_event_type'] or '').startswith('inferred_') else 'observed' if row['source_event_type'] else 'unknown',
                'related_entity_id': row['related_entity_id'],
            }
            for row in rows
        ]

    def list_snapshot_history(self, external_tender_id: str, limit: int = 12) -> list[dict[str, Any]]:
        with self._lock:
            connection = self._require_connection()
            rows = connection.execute(
                """
                SELECT id, generated_at, analytical_phase, health, summary, analysis_metadata_json
                FROM kpi_snapshots
                WHERE external_tender_id = ?
                ORDER BY generated_at DESC, id DESC
                LIMIT ?
                """,
                (external_tender_id, limit),
            ).fetchall()
        items: list[dict[str, Any]] = []
        for row in rows:
            metadata = json.loads(row['analysis_metadata_json'] or '{}')
            items.append(
                {
                    'snapshot_id': int(row['id']),
                    'generated_at': row['generated_at'],
                    'analytical_phase': row['analytical_phase'],
                    'health': row['health'] or 'unknown',
                    'summary': row['summary'],
                    'reconstructed': bool(metadata.get('reconstructed', False)),
                    'source_type': 'reconstructed' if bool(metadata.get('reconstructed', False)) else 'observed',
                    'replay_until': metadata.get('replay_until'),
                    'source_job_type': metadata.get('source_job_type'),
                    'replay_source_event_type': metadata.get('replay_source_event_type'),
                }
            )
        return items

    def list_markov_history_points(self) -> list[dict[str, Any]]:
        with self._lock:
            connection = self._require_connection()
            rows = connection.execute(
                """
                SELECT external_tender_id, id, generated_at, analytical_phase, analysis_metadata_json
                FROM kpi_snapshots
                WHERE analytical_phase IS NOT NULL
                ORDER BY external_tender_id ASC, generated_at ASC, id ASC
                """
            ).fetchall()
        items: list[dict[str, Any]] = []
        for row in rows:
            metadata = json.loads(row['analysis_metadata_json'] or '{}')
            source_type = 'reconstructed' if bool(metadata.get('reconstructed', False)) else 'observed'
            items.append(
                {
                    'external_tender_id': row['external_tender_id'],
                    'snapshot_id': int(row['id']),
                    'generated_at': row['generated_at'],
                    'analytical_phase': row['analytical_phase'],
                    'reconstructed': bool(metadata.get('reconstructed', False)),
                    'source_type': source_type,
                }
            )
        return items

    def update_tender_analysis(self, external_tender_id: str, *, health: str, analytical_phase: str | None) -> None:
        with self._lock:
            connection = self._require_connection()
            connection.execute(
                """
                UPDATE kpi_tenders
                SET health = ?, analytical_phase = ?, updated_at = ?
                WHERE external_tender_id = ?
                """,
                (health, analytical_phase, _utcnow_iso(), external_tender_id),
            )
            connection.commit()

    def count_domain_events(self, external_tender_id: str) -> int:
        with self._lock:
            connection = self._require_connection()
            row = connection.execute(
                'SELECT COUNT(*) AS count FROM kpi_domain_events WHERE external_tender_id = ?',
                (external_tender_id,),
            ).fetchone()
        return int(row['count'] or 0)

    def count_document_contexts(self, external_tender_id: str) -> int:
        with self._lock:
            connection = self._require_connection()
            row = connection.execute(
                'SELECT COUNT(*) AS count FROM kpi_document_contexts WHERE external_tender_id = ?',
                (external_tender_id,),
            ).fetchone()
        return int(row['count'] or 0)

    def count_analysis_jobs(self, external_tender_id: str) -> int:
        with self._lock:
            connection = self._require_connection()
            row = connection.execute(
                'SELECT COUNT(*) AS count FROM kpi_analysis_jobs WHERE external_tender_id = ?',
                (external_tender_id,),
            ).fetchone()
        return int(row['count'] or 0)

    def count_snapshots(self, external_tender_id: str) -> int:
        with self._lock:
            connection = self._require_connection()
            row = connection.execute(
                'SELECT COUNT(*) AS count FROM kpi_snapshots WHERE external_tender_id = ?',
                (external_tender_id,),
            ).fetchone()
        return int(row['count'] or 0)

    def count_findings(self, external_tender_id: str) -> int:
        with self._lock:
            connection = self._require_connection()
            row = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM kpi_findings AS f
                JOIN kpi_snapshots AS s ON s.id = f.snapshot_id
                WHERE s.external_tender_id = ?
                """,
                (external_tender_id,),
            ).fetchone()
        return int(row['count'] or 0)

    def count_phase_transitions(self, external_tender_id: str) -> int:
        with self._lock:
            connection = self._require_connection()
            row = connection.execute(
                'SELECT COUNT(*) AS count FROM kpi_phase_transitions WHERE external_tender_id = ?',
                (external_tender_id,),
            ).fetchone()
        return int(row['count'] or 0)

    def get_runtime_metrics(self) -> dict[str, Any]:
        with self._lock:
            connection = self._require_connection()
            tender_row = connection.execute('SELECT COUNT(*) AS count FROM kpi_tenders').fetchone()
            event_row = connection.execute('SELECT COUNT(*) AS count FROM kpi_domain_events').fetchone()
            document_row = connection.execute('SELECT COUNT(*) AS count FROM kpi_document_contexts').fetchone()
            snapshot_row = connection.execute('SELECT COUNT(*) AS count FROM kpi_snapshots').fetchone()
            finding_row = connection.execute('SELECT COUNT(*) AS count FROM kpi_findings').fetchone()
            transition_row = connection.execute('SELECT COUNT(*) AS count FROM kpi_phase_transitions').fetchone()
            status_rows = connection.execute(
                'SELECT status, COUNT(*) AS count FROM kpi_analysis_jobs GROUP BY status'
            ).fetchall()
            type_status_rows = connection.execute(
                'SELECT job_type, status, COUNT(*) AS count FROM kpi_analysis_jobs GROUP BY job_type, status ORDER BY job_type, status'
            ).fetchall()
            latest_job_row = connection.execute(
                'SELECT MAX(updated_at) AS latest_updated_at FROM kpi_analysis_jobs'
            ).fetchone()
            snapshot_rows = connection.execute(
                '''
                SELECT generated_at, analysis_metadata_json, kpis_json
                FROM kpi_snapshots
                ORDER BY generated_at DESC, id DESC
                '''
            ).fetchall()
            model_version_rows = connection.execute(
                '''
                SELECT version_type, version_code, descriptor_json, created_at
                FROM kpi_model_versions
                ORDER BY version_type ASC, created_at ASC, id ASC
                '''
            ).fetchall()
            schema_row = connection.execute('SELECT version_num FROM alembic_version LIMIT 1').fetchone()

        snapshot_output_schema_versions: dict[str, int] = defaultdict(int)
        contract_versions: dict[str, int] = defaultdict(int)
        semantic_bundle_versions: dict[str, int] = defaultdict(int)
        shadow_bundle_versions: dict[str, int] = defaultdict(int)
        source_job_types: dict[str, int] = defaultdict(int)
        semantic_fallback_total = 0
        semantic_official_total = 0
        shadow_mode_total = 0
        reconstructed_total = 0
        latest_snapshot_generated_at = snapshot_rows[0]['generated_at'] if snapshot_rows else None

        for row in snapshot_rows:
            metadata = json.loads(row['analysis_metadata_json'] or '{}')
            if metadata.get('reconstructed'):
                reconstructed_total += 1
            if metadata.get('shadow_mode_enabled'):
                shadow_mode_total += 1
            if metadata.get('semantic_official_enabled'):
                semantic_official_total += 1

            snapshot_output_schema_version = metadata.get('snapshot_output_schema_version')
            if snapshot_output_schema_version:
                snapshot_output_schema_versions[str(snapshot_output_schema_version)] += 1
            contract_version = metadata.get('contract_version')
            if contract_version:
                contract_versions[str(contract_version)] += 1
            semantic_bundle_version = metadata.get('semantic_bundle_version')
            if semantic_bundle_version:
                semantic_bundle_versions[str(semantic_bundle_version)] += 1
            shadow_bundle_version = metadata.get('shadow_bundle_version')
            if shadow_bundle_version:
                shadow_bundle_versions[str(shadow_bundle_version)] += 1
            source_job_type = metadata.get('source_job_type')
            if source_job_type:
                source_job_types[str(source_job_type)] += 1

            kpis = json.loads(row['kpis_json'] or '[]')
            if any(
                isinstance(score, dict)
                and isinstance(score.get('semantic'), dict)
                and score['semantic'].get('status') == 'fallback'
                for score in kpis
            ):
                semantic_fallback_total += 1

        model_versions: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in model_version_rows:
            model_versions[str(row['version_type'])].append(
                {
                    'version_code': row['version_code'],
                    'created_at': row['created_at'],
                    'descriptor': json.loads(row['descriptor_json'] or '{}'),
                }
            )

        return {
            'analysis_jobs': {
                'by_status': {row['status']: int(row['count'] or 0) for row in status_rows},
                'by_type_and_status': [
                    {
                        'job_type': row['job_type'],
                        'status': row['status'],
                        'count': int(row['count'] or 0),
                    }
                    for row in type_status_rows
                ],
                'latest_updated_at': None if latest_job_row is None else latest_job_row['latest_updated_at'],
            },
            'persistence': {
                'mirrored_tenders': int(tender_row['count'] or 0),
                'persisted_domain_events': int(event_row['count'] or 0),
                'persisted_document_contexts': int(document_row['count'] or 0),
                'persisted_snapshots': int(snapshot_row['count'] or 0),
                'persisted_findings': int(finding_row['count'] or 0),
                'persisted_phase_transitions': int(transition_row['count'] or 0),
            },
            'snapshots': {
                'persisted_total': int(snapshot_row['count'] or 0),
                'latest_generated_at': latest_snapshot_generated_at,
                'reconstructed_total': reconstructed_total,
                'shadow_mode_total': shadow_mode_total,
                'semantic_official_total': semantic_official_total,
                'semantic_fallback_total': semantic_fallback_total,
            },
            'version_governance': {
                'schema_version': None if schema_row is None else schema_row['version_num'],
                'snapshot_output_schema_versions': dict(sorted(snapshot_output_schema_versions.items())),
                'contract_versions': dict(sorted(contract_versions.items())),
                'semantic_bundle_versions': dict(sorted(semantic_bundle_versions.items())),
                'shadow_bundle_versions': dict(sorted(shadow_bundle_versions.items())),
                'source_job_types': dict(sorted(source_job_types.items())),
                'model_versions': dict(sorted(model_versions.items())),
            },
        }

    def get_schema_version(self) -> str | None:
        with self._lock:
            connection = self._require_connection()
            row = connection.execute('SELECT version_num FROM alembic_version LIMIT 1').fetchone()
        return None if row is None else row['version_num']

    def list_model_versions(self) -> list[dict[str, Any]]:
        with self._lock:
            connection = self._require_connection()
            rows = connection.execute(
                '''
                SELECT version_type, version_code, descriptor_json, created_at
                FROM kpi_model_versions
                ORDER BY version_type ASC, created_at ASC, id ASC
                '''
            ).fetchall()
        return [
            {
                'version_type': row['version_type'],
                'version_code': row['version_code'],
                'descriptor': json.loads(row['descriptor_json'] or '{}'),
                'created_at': row['created_at'],
            }
            for row in rows
        ]


    def _portfolio_phase_label(self, phase: str | None) -> str:
        labels = {
            'S0': 'Intake Opportunity',
            'S1': 'Go / No-Go',
            'S2': 'Bid Planning',
            'S3': 'Request Contributions',
            'S4': 'Coordination & Collection',
            'S5': 'Quality / Technical Review',
            'S6': 'Rework / Clarifications',
            'S7': 'Integrated Draft',
            'S8': 'Compliance Gate',
            'S9': 'Submission',
            'S10': 'Post-Submission Clarifications',
            'S11': 'Win',
            'S12': 'Loss',
            'S13': 'Excluded / Withdrawn / No-Bid',
            'analysis_pending': 'Analysis Pending',
        }
        return labels.get(phase or 'analysis_pending', phase or 'Analysis Pending')

    def _portfolio_bottleneck_fields(self, *, health: str, phase: str) -> dict[str, str]:
        normalized_phase = phase or 'analysis_pending'
        if health == 'unknown':
            return {
                'bottleneck_type': 'analysis_pending',
                'severity': 'unknown',
                'description': 'The tender has not produced a stable analytical mirror yet, so admin should resync or recompute before making decisions.',
            }
        if normalized_phase in {'S8', 'S10'}:
            return {
                'bottleneck_type': 'compliance_pressure',
                'severity': 'critical' if health == 'red' else 'high',
                'description': 'Compliance or clarification pressure is dominating the journey and can still reroute the tender away from a clean closure.',
            }
        if normalized_phase in {'S5', 'S6'}:
            return {
                'bottleneck_type': 'review_loop_pressure',
                'severity': 'high' if health == 'red' else 'medium',
                'description': 'The tender is circulating between review and rework, so admin should compress blockers before they become structural churn.',
            }
        if normalized_phase in {'S1', 'S2', 'S3'}:
            return {
                'bottleneck_type': 'orchestration_pressure',
                'severity': 'high' if health == 'red' else 'medium',
                'description': 'Early lifecycle orchestration is still unstable and requires explicit decisions, planning discipline and assignment closure.',
            }
        if normalized_phase == 'S13':
            return {
                'bottleneck_type': 'terminal_stop',
                'severity': 'critical',
                'description': 'The tender has already reached a stop state and should be classified clearly for retrospective learning and portfolio reporting.',
            }
        return {
            'bottleneck_type': 'analytical_risk',
            'severity': 'high' if health == 'red' else 'medium' if health == 'amber' else 'low',
            'description': 'The tender remains analytically fragile and should stay on the admin watchlist until the main drivers stabilize.',
        }

    def get_portfolio_overview(self) -> dict[str, Any]:
        with self._lock:
            connection = self._require_connection()
            total_row = connection.execute('SELECT COUNT(*) AS count FROM kpi_tenders').fetchone()
            health_rows = connection.execute(
                "SELECT COALESCE(health, 'unknown') AS health, COUNT(*) AS count FROM kpi_tenders GROUP BY COALESCE(health, 'unknown')"
            ).fetchall()
            phase_rows = connection.execute(
                "SELECT COALESCE(analytical_phase, 'analysis_pending') AS phase, COUNT(*) AS count FROM kpi_tenders GROUP BY COALESCE(analytical_phase, 'analysis_pending')"
            ).fetchall()
            critical_rows = connection.execute(
                """
                SELECT external_tender_id
                FROM kpi_tenders
                WHERE COALESCE(health, 'unknown') IN ('red', 'amber')
                ORDER BY
                    CASE COALESCE(health, 'unknown')
                        WHEN 'red' THEN 0
                        WHEN 'amber' THEN 1
                        ELSE 2
                    END,
                    updated_at DESC,
                    external_tender_id ASC
                LIMIT 8
                """
            ).fetchall()

        tenders_by_health = {row['health'] or 'unknown': int(row['count'] or 0) for row in health_rows}
        if not tenders_by_health:
            tenders_by_health = {'unknown': 0}

        analytical_phases = {row['phase'] or 'analysis_pending': int(row['count'] or 0) for row in phase_rows}

        if tenders_by_health.get('red'):
            portfolio_health = 'red'
        elif tenders_by_health.get('amber'):
            portfolio_health = 'amber'
        elif tenders_by_health.get('green'):
            portfolio_health = 'green'
        else:
            portfolio_health = 'unknown'

        return {
            'total_tenders': int(total_row['count'] or 0),
            'portfolio_health': portfolio_health,
            'tenders_by_health': tenders_by_health,
            'analytical_phases': analytical_phases,
            'critical_tenders': [str(row['external_tender_id']) for row in critical_rows],
        }

    def list_bottlenecks(self, limit: int = 10) -> list[dict[str, Any]]:
        with self._lock:
            connection = self._require_connection()
            rows = connection.execute(
                """
                SELECT external_tender_id, title, current_status, health, analytical_phase, updated_at
                FROM kpi_tenders
                ORDER BY
                    CASE COALESCE(health, 'unknown')
                        WHEN 'red' THEN 0
                        WHEN 'amber' THEN 1
                        WHEN 'green' THEN 2
                        ELSE 3
                    END,
                    updated_at DESC,
                    external_tender_id ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        items: list[dict[str, Any]] = []
        for row in rows:
            health = row['health'] or 'unknown'
            phase = row['analytical_phase'] or 'analysis_pending'
            bottleneck_fields = self._portfolio_bottleneck_fields(health=health, phase=phase)
            items.append(
                {
                    'external_tender_id': row['external_tender_id'],
                    'bottleneck_type': bottleneck_fields['bottleneck_type'],
                    'summary': f"{row['title']} is in {self._portfolio_phase_label(phase)} with {health} KPI health.",
                    'description': bottleneck_fields['description'],
                    'health': health,
                    'severity': bottleneck_fields['severity'],
                }
            )
        return items

    def get_portfolio_intelligence(self, limit: int = 5) -> dict[str, Any]:
        with self._lock:
            connection = self._require_connection()
            tender_rows = connection.execute(
                """
                SELECT external_tender_id, title, current_status, health, analytical_phase, updated_at
                FROM kpi_tenders
                ORDER BY updated_at DESC, external_tender_id ASC
                """
            ).fetchall()
            snapshot_rows = connection.execute(
                """
                SELECT s.external_tender_id, s.summary, s.kpis_json
                FROM kpi_snapshots AS s
                INNER JOIN (
                    SELECT external_tender_id, MAX(id) AS snapshot_id
                    FROM kpi_snapshots
                    GROUP BY external_tender_id
                ) AS latest
                    ON latest.external_tender_id = s.external_tender_id
                   AND latest.snapshot_id = s.id
                """
            ).fetchall()

        snapshot_map = {}
        for row in snapshot_rows:
            snapshot_map[str(row['external_tender_id'])] = {
                'summary': row['summary'],
                'kpis': json.loads(row['kpis_json'] or '[]'),
            }

        phase_counts = {}
        outcome_trends = {'S11': 0, 'S12': 0, 'S13': 0}
        watchlist = []
        risk_counts = {
            'A1': {'count': 0, 'severity': 'medium'},
            'A4': {'count': 0, 'severity': 'high'},
            'B1': {'count': 0, 'severity': 'high'},
            'B2': {'count': 0, 'severity': 'medium'},
            'B4': {'count': 0, 'severity': 'medium'},
        }
        risk_summaries = {
            'A1': 'Requirement coverage gaps are concentrating across the portfolio.',
            'A4': 'Compliance risk remains a dominant cross-tender blocker.',
            'B1': 'Deadline pressure is becoming a portfolio-level risk.',
            'B2': 'Responsiveness slippage is extending the operational corridor.',
            'B4': 'Contribution instability is generating repeated reopenings.',
        }

        for row in tender_rows:
            external_tender_id = str(row['external_tender_id'])
            phase = row['analytical_phase'] or 'analysis_pending'
            health = row['health'] or 'unknown'
            phase_counts[phase] = phase_counts.get(phase, 0) + 1
            if phase in outcome_trends:
                outcome_trends[phase] += 1

            snapshot = snapshot_map.get(external_tender_id, {})
            summary = snapshot.get('summary') or f"{row['title']} is currently mirrored in {self._portfolio_phase_label(phase)}."
            if health in {'red', 'amber'}:
                watchlist.append(
                    {
                        'external_tender_id': external_tender_id,
                        'title': row['title'],
                        'analytical_phase': phase,
                        'health': health,
                        'summary': summary,
                    }
                )

            for score in snapshot.get('kpis') or []:
                if not isinstance(score, dict):
                    continue
                code = str(score.get('kpi_code') or '')
                score_health = str(score.get('health') or 'unknown')
                if code not in risk_counts or score_health not in {'amber', 'red'}:
                    continue
                risk_counts[code]['count'] += 1
                if score_health == 'red' and risk_counts[code]['severity'] != 'critical':
                    risk_counts[code]['severity'] = 'critical' if code in {'A4', 'B1'} else 'high'

        phase_hotspots = [
            {
                'phase': phase,
                'count': count,
                'summary': f'{count} tenders are currently concentrated in {self._portfolio_phase_label(phase)}.',
            }
            for phase, count in sorted(phase_counts.items(), key=lambda item: (-item[1], item[0]))[:limit]
        ]
        risk_hotspots = [
            {
                'code': code,
                'count': spec['count'],
                'severity': spec['severity'],
                'summary': risk_summaries[code],
            }
            for code, spec in sorted(risk_counts.items(), key=lambda item: (-item[1]['count'], item[0]))
            if spec['count'] > 0
        ][:limit]
        watchlist.sort(key=lambda item: (0 if item['health'] == 'red' else 1, item['analytical_phase'] not in {'S8', 'S10', 'S13'}, item['external_tender_id']))
        watchlist = watchlist[:limit]

        notes = []
        if phase_hotspots:
            notes.append(phase_hotspots[0]['summary'])
        if risk_hotspots:
            notes.append(f"Primary hotspot is {risk_hotspots[0]['code']} with {risk_hotspots[0]['count']} mirrored tenders.")
        if watchlist:
            notes.append(f'{len(watchlist)} tenders currently require active admin intervention.')

        return {
            'phase_hotspots': phase_hotspots,
            'risk_hotspots': risk_hotspots,
            'outcome_trends': outcome_trends,
            'watchlist': watchlist,
            'notes': notes,
        }

    def _ensure_model_versions(self, connection: sqlite3.Connection, analysis_metadata: dict[str, Any]) -> int | None:
        version_specs = [
            ('formula_bundle', analysis_metadata.get('formula_bundle_version')),
            ('model_bundle', analysis_metadata.get('model_bundle_version')),
            ('prompt_bundle', analysis_metadata.get('prompt_bundle_version')),
        ]
        primary_version_id: int | None = None
        for version_type, version_code in version_specs:
            if not version_code:
                continue
            descriptor = {
                'bundle': version_code,
                'engine_kind': analysis_metadata.get('engine_kind'),
                'scored_kpis': analysis_metadata.get('scored_kpis', []),
            }
            connection.execute(
                """
                INSERT OR IGNORE INTO kpi_model_versions (
                    version_type,
                    version_code,
                    descriptor_json,
                    created_at
                ) VALUES (?, ?, ?, ?)
                """,
                (version_type, version_code, _to_json(descriptor), _utcnow_iso()),
            )
            row = connection.execute(
                """
                SELECT id FROM kpi_model_versions
                WHERE version_type = ? AND version_code = ?
                LIMIT 1
                """,
                (version_type, version_code),
            ).fetchone()
            if row is None:
                raise RuntimeError(f'Unable to resolve KPI model version for {version_type}.')
            if version_type == 'formula_bundle':
                primary_version_id = int(row['id'])
        return primary_version_id

    def _insert_snapshot_findings(
        self,
        connection: sqlite3.Connection,
        snapshot_id: int,
        analysis: AnalysisSnapshot,
        created_at: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO kpi_findings (snapshot_id, finding_kind, finding_key, content, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (snapshot_id, 'summary', 'summary', analysis.summary, created_at),
        )
        connection.execute(
            """
            INSERT INTO kpi_findings (snapshot_id, finding_kind, finding_key, content, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (snapshot_id, 'analysis_metadata', 'analysis_metadata', _to_json(analysis.analysis_metadata), created_at),
        )
        for note in analysis.notes:
            connection.execute(
                """
                INSERT INTO kpi_findings (snapshot_id, finding_kind, finding_key, content, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (snapshot_id, 'note', 'note', note, created_at),
            )
        for score in analysis.kpis:
            if score.value is not None:
                connection.execute(
                    """
                    INSERT INTO kpi_findings (snapshot_id, finding_kind, finding_key, content, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        snapshot_id,
                        'kpi_value',
                        score.kpi_code,
                        f"{score.kpi_code}: {score.value} ({score.health}) [{score.source_type or score.provenance}]",
                        created_at,
                    ),
                )
            if score.recommendation:
                connection.execute(
                    """
                    INSERT INTO kpi_findings (snapshot_id, finding_kind, finding_key, content, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (snapshot_id, 'kpi_recommendation', score.kpi_code, score.recommendation, created_at),
                )
            version_label = f"formula={score.formula_version}, model={score.model_version}, prompt={score.prompt_version}"
            connection.execute(
                """
                INSERT INTO kpi_findings (snapshot_id, finding_kind, finding_key, content, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (snapshot_id, 'kpi_version', score.kpi_code, version_label, created_at),
            )
            for criticality in score.criticalities:
                connection.execute(
                    """
                    INSERT INTO kpi_findings (snapshot_id, finding_kind, finding_key, content, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (snapshot_id, 'kpi_criticality', score.kpi_code, criticality, created_at),
                )
            for evidence in score.evidences or score.evidence:
                connection.execute(
                    """
                    INSERT INTO kpi_findings (snapshot_id, finding_kind, finding_key, content, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (snapshot_id, 'kpi_evidence', score.kpi_code, evidence, created_at),
                )
            if score.shadow and score.shadow.shadow_score is not None:
                shadow = score.shadow
                connection.execute(
                    """
                    INSERT INTO kpi_findings (snapshot_id, finding_kind, finding_key, content, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        snapshot_id,
                        'kpi_shadow_value',
                        score.kpi_code,
                        f"{score.kpi_code} shadow: {shadow.shadow_score} ({shadow.health}) delta={shadow.delta_vs_proxy} [{shadow.source_type}]",
                        created_at,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO kpi_findings (snapshot_id, finding_kind, finding_key, content, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        snapshot_id,
                        'kpi_shadow_version',
                        score.kpi_code,
                        f"formula={shadow.formula_version}, model={shadow.model_version}, prompt={shadow.prompt_version}",
                        created_at,
                    ),
                )
                for recommendation in shadow.recommendations:
                    connection.execute(
                        """
                        INSERT INTO kpi_findings (snapshot_id, finding_kind, finding_key, content, created_at)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (snapshot_id, 'kpi_shadow_recommendation', score.kpi_code, recommendation, created_at),
                    )
                for criticality in shadow.criticalities:
                    connection.execute(
                        """
                        INSERT INTO kpi_findings (snapshot_id, finding_kind, finding_key, content, created_at)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (snapshot_id, 'kpi_shadow_criticality', score.kpi_code, criticality, created_at),
                    )
                for evidence in shadow.evidences:
                    connection.execute(
                        """
                        INSERT INTO kpi_findings (snapshot_id, finding_kind, finding_key, content, created_at)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (snapshot_id, 'kpi_shadow_evidence', score.kpi_code, evidence, created_at),
                    )

    def _insert_phase_transitions(
        self,
        connection: sqlite3.Connection,
        external_tender_id: str,
        snapshot_id: int,
        transition_snapshot: TransitionSnapshot,
        created_at: str,
    ) -> None:
        for item in transition_snapshot.items:
            occurred_at = item.occurred_at.isoformat() if item.occurred_at else None
            fingerprint = {
                'from_state': item.from_state,
                'to_state': item.to_state,
                'occurred_at': occurred_at,
                'cause': item.cause,
                'confidence': item.confidence,
                'source_event_type': item.source_event_type,
                'related_entity_id': item.related_entity_id,
            }
            transition_hash = hashlib.sha256(_to_json(fingerprint).encode('utf-8')).hexdigest()
            connection.execute(
                """
                INSERT OR IGNORE INTO kpi_phase_transitions (
                    external_tender_id,
                    snapshot_id,
                    from_state,
                    to_state,
                    occurred_at,
                    cause,
                    confidence,
                    source_event_type,
                    related_entity_id,
                    transition_hash,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    external_tender_id,
                    snapshot_id,
                    item.from_state,
                    item.to_state,
                    occurred_at,
                    item.cause,
                    item.confidence,
                    item.source_event_type,
                    item.related_entity_id,
                    transition_hash,
                    created_at,
                ),
            )

    def _deserialize_analysis_job(self, row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        return {
            'job_id': int(row['id']),
            'external_tender_id': row['external_tender_id'],
            'job_type': row['job_type'],
            'job_status': row['status'],
            'requested_by': row['requested_by'],
            'priority': row['priority'],
            'reason': row['reason'],
            'metadata': json.loads(row['metadata_json'] or '{}'),
            'created_at': row['created_at'],
            'started_at': row['started_at'],
            'completed_at': row['completed_at'],
            'updated_at': row['updated_at'],
            'latest_snapshot_generated_at': row['latest_snapshot_generated_at'],
            'error_message': row['error_message'],
        }

    def _require_connection(self) -> sqlite3.Connection:
        if self._connection is None:
            raise RuntimeError('SQLite store is not open.')
        return self._connection

    def _validate_schema(self) -> None:
        connection = self._require_connection()
        rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        existing = {row['name'] for row in rows}
        missing = sorted(_REQUIRED_TABLES - existing)
        if missing:
            raise RuntimeError(f"Missing KPI persistence tables: {', '.join(missing)}")
