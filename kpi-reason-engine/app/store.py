"""SQLite-backed persistence for tw-kpi-reason-engine."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_json(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, sort_keys=True)


class SqliteStore:
    """Minimal persistent store for the KPI service bootstrap and ingestion phases."""

    def __init__(self, database_path: str) -> None:
        self.database_path = Path(database_path)
        self._lock = threading.RLock()
        self._connection: sqlite3.Connection | None = None

    def open(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.database_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        with self._lock:
            self._connection.execute("PRAGMA journal_mode=WAL;")
            self._connection.execute("PRAGMA foreign_keys=ON;")
            self._connection.execute("PRAGMA synchronous=NORMAL;")
            self._init_schema()

    def close(self) -> None:
        if self._connection is None:
            return
        with self._lock:
            self._connection.close()
            self._connection = None

    def clear_all(self) -> None:
        with self._lock:
            connection = self._require_connection()
            connection.execute("DELETE FROM kpi_analysis_jobs")
            connection.execute("DELETE FROM kpi_document_contexts")
            connection.execute("DELETE FROM kpi_domain_events")
            connection.execute("DELETE FROM kpi_tenders")
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
                    payload["external_tender_id"],
                    payload["title"],
                    payload.get("customer_name"),
                    payload.get("due_at"),
                    payload.get("current_status"),
                    _to_json(payload.get("departments", [])),
                    _to_json(payload.get("requirement_contexts", [])),
                    _to_json(payload.get("section_contexts", [])),
                    _to_json(payload.get("metadata", {})),
                    "unknown",
                    None,
                    now,
                    now,
                    now,
                ),
            )
            connection.commit()

    def insert_domain_event(self, external_tender_id: str, payload: dict[str, Any]) -> bool:
        envelope_json = _to_json(payload)
        envelope_hash = hashlib.sha256(envelope_json.encode("utf-8")).hexdigest()
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
                    payload["event_type"],
                    payload["occurred_at"],
                    payload.get("actor_id"),
                    payload["source"],
                    payload.get("schema_version", "1.0.0"),
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
                    payload["document_id"],
                    payload["document_type"],
                    payload.get("filename"),
                    payload.get("extracted_text_ref"),
                    _to_json(payload.get("metadata", {})),
                    _utcnow_iso(),
                ),
            )
            connection.commit()

    def enqueue_analysis_job(self, external_tender_id: str, payload: dict[str, Any]) -> None:
        with self._lock:
            connection = self._require_connection()
            connection.execute(
                """
                INSERT INTO kpi_analysis_jobs (
                    external_tender_id,
                    job_type,
                    requested_by,
                    priority,
                    reason,
                    metadata_json,
                    status,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    external_tender_id,
                    payload["job_type"],
                    payload.get("requested_by"),
                    payload.get("priority", "normal"),
                    payload.get("reason"),
                    _to_json(payload.get("metadata", {})),
                    "queued",
                    _utcnow_iso(),
                ),
            )
            connection.commit()

    def get_tender(self, external_tender_id: str) -> dict[str, Any] | None:
        with self._lock:
            connection = self._require_connection()
            row = connection.execute(
                "SELECT * FROM kpi_tenders WHERE external_tender_id = ?",
                (external_tender_id,),
            ).fetchone()
        if row is None:
            return None

        return {
            "external_tender_id": row["external_tender_id"],
            "title": row["title"],
            "customer_name": row["customer_name"],
            "due_at": row["due_at"],
            "current_status": row["current_status"],
            "departments": json.loads(row["departments_json"] or "[]"),
            "requirement_contexts": json.loads(row["requirement_contexts_json"] or "[]"),
            "section_contexts": json.loads(row["section_contexts_json"] or "[]"),
            "metadata": json.loads(row["metadata_json"] or "{}"),
            "health": row["health"] or "unknown",
            "analytical_phase": row["analytical_phase"],
            "last_synced_at": row["last_synced_at"],
        }

    def count_domain_events(self, external_tender_id: str) -> int:
        with self._lock:
            connection = self._require_connection()
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM kpi_domain_events WHERE external_tender_id = ?",
                (external_tender_id,),
            ).fetchone()
        return int(row["count"] or 0)

    def count_document_contexts(self, external_tender_id: str) -> int:
        with self._lock:
            connection = self._require_connection()
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM kpi_document_contexts WHERE external_tender_id = ?",
                (external_tender_id,),
            ).fetchone()
        return int(row["count"] or 0)

    def count_analysis_jobs(self, external_tender_id: str) -> int:
        with self._lock:
            connection = self._require_connection()
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM kpi_analysis_jobs WHERE external_tender_id = ?",
                (external_tender_id,),
            ).fetchone()
        return int(row["count"] or 0)

    def get_portfolio_overview(self) -> dict[str, Any]:
        with self._lock:
            connection = self._require_connection()
            total_row = connection.execute("SELECT COUNT(*) AS count FROM kpi_tenders").fetchone()
            health_rows = connection.execute(
                "SELECT health, COUNT(*) AS count FROM kpi_tenders GROUP BY health"
            ).fetchall()

        tenders_by_health = {
            row["health"] or "unknown": int(row["count"] or 0)
            for row in health_rows
        }
        if not tenders_by_health:
            tenders_by_health = {"unknown": 0}

        return {
            "total_tenders": int(total_row["count"] or 0),
            "portfolio_health": "unknown",
            "tenders_by_health": tenders_by_health,
        }

    def list_bottlenecks(self, limit: int = 10) -> list[dict[str, Any]]:
        with self._lock:
            connection = self._require_connection()
            rows = connection.execute(
                """
                SELECT external_tender_id, title, current_status, health
                FROM kpi_tenders
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [
            {
                "external_tender_id": row["external_tender_id"],
                "bottleneck_type": "analysis_pending",
                "summary": f"{row['title']} is synchronized but analytical scoring is not ready yet.",
                "health": row["health"] or "unknown",
            }
            for row in rows
        ]

    def _require_connection(self) -> sqlite3.Connection:
        if self._connection is None:
            raise RuntimeError("SQLite store is not open.")
        return self._connection

    def _init_schema(self) -> None:
        connection = self._require_connection()
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS kpi_tenders (
                external_tender_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                customer_name TEXT,
                due_at TEXT,
                current_status TEXT,
                departments_json TEXT NOT NULL DEFAULT '[]',
                requirement_contexts_json TEXT NOT NULL DEFAULT '[]',
                section_contexts_json TEXT NOT NULL DEFAULT '[]',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                health TEXT NOT NULL DEFAULT 'unknown',
                analytical_phase TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_synced_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS kpi_domain_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                external_tender_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                actor_id TEXT,
                source TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                envelope_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE (external_tender_id, event_type, occurred_at, source, envelope_hash)
            );

            CREATE TABLE IF NOT EXISTS kpi_document_contexts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                external_tender_id TEXT NOT NULL,
                document_id TEXT NOT NULL,
                document_type TEXT NOT NULL,
                filename TEXT,
                extracted_text_ref TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS kpi_analysis_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                external_tender_id TEXT NOT NULL,
                job_type TEXT NOT NULL,
                requested_by TEXT,
                priority TEXT NOT NULL,
                reason TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        connection.commit()
