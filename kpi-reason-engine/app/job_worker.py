"""Background worker for KPI analysis jobs."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

import structlog

from app.store import SqliteStore

logger = structlog.get_logger(__name__)


class AnalysisJobWorker:
    """Minimal polling worker that processes queued analysis jobs."""

    def __init__(
        self,
        store: SqliteStore,
        *,
        run_analysis: Callable[[str], tuple[dict[str, Any] | None, Any, Any, dict[str, Any] | None]],
        poll_interval_seconds: float = 0.25,
    ) -> None:
        self.store = store
        self.run_analysis = run_analysis
        self.poll_interval_seconds = poll_interval_seconds
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._wake_event.set()
        self._thread = threading.Thread(target=self._run, name="kpi-analysis-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._wake_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=max(1.0, self.poll_interval_seconds * 4))
        self._thread = None

    def notify(self) -> None:
        self._wake_event.set()

    def _run(self) -> None:
        while not self._stop_event.is_set():
            job = self.store.claim_next_analysis_job()
            if job is None:
                self._wake_event.wait(self.poll_interval_seconds)
                self._wake_event.clear()
                continue

            job_id = int(job["job_id"])
            external_tender_id = str(job["external_tender_id"])
            try:
                _, _, _, snapshot_record = self.run_analysis(external_tender_id)
                if snapshot_record is None:
                    raise RuntimeError("Tender snapshot could not be recomputed.")
                self.store.mark_analysis_job_succeeded(job_id, snapshot_record=snapshot_record)
                logger.info(
                    "analysis_job.succeeded",
                    job_id=job_id,
                    external_tender_id=external_tender_id,
                    generated_at=snapshot_record.get("generated_at"),
                )
            except Exception as exc:  # pragma: no cover - defensive path
                self.store.mark_analysis_job_failed(job_id, error_message=str(exc))
                logger.exception(
                    "analysis_job.failed",
                    job_id=job_id,
                    external_tender_id=external_tender_id,
                    error_message=str(exc),
                )
