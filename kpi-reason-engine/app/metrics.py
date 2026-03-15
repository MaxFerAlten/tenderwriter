from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
import threading
from typing import Any


@dataclass(slots=True)
class _LatencyBucket:
    count: int = 0
    total_ms: float = 0.0
    max_ms: float = 0.0

    def record(self, duration_ms: float) -> None:
        self.count += 1
        self.total_ms += duration_ms
        self.max_ms = max(self.max_ms, duration_ms)

    def as_dict(self) -> dict[str, float]:
        average_ms = 0.0 if self.count == 0 else round(self.total_ms / self.count, 2)
        return {
            'count': self.count,
            'average_ms': average_ms,
            'max_ms': round(self.max_ms, 2),
            'total_ms': round(self.total_ms, 2),
        }


class RuntimeMetrics:
    """In-memory runtime metrics exposed by the KPI service."""

    def __init__(self, *, service_name: str, service_version: str) -> None:
        self.service_name = service_name
        self.service_version = service_version
        self._lock = threading.RLock()
        self._http_counts: dict[tuple[str, str, int], int] = defaultdict(int)
        self._latency_by_route: dict[tuple[str, str], _LatencyBucket] = defaultdict(_LatencyBucket)
        self._domain_events: dict[str, int] = defaultdict(int)
        self._job_requests: dict[str, int] = defaultdict(int)

    def record_request(self, *, method: str, path: str, status_code: int, duration_ms: float) -> None:
        with self._lock:
            self._http_counts[(method.upper(), path, int(status_code))] += 1
            self._latency_by_route[(method.upper(), path)].record(duration_ms)

    def record_domain_event(self, event_type: str) -> None:
        with self._lock:
            self._domain_events[str(event_type)] += 1

    def record_analysis_job_request(self, job_type: str) -> None:
        with self._lock:
            self._job_requests[str(job_type)] += 1

    def snapshot(self, *, store_runtime: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            http_breakdown = [
                {
                    'method': method,
                    'path': path,
                    'status_code': status_code,
                    'count': count,
                }
                for (method, path, status_code), count in sorted(self._http_counts.items())
            ]
            latency_breakdown = [
                {
                    'method': method,
                    'path': path,
                    **bucket.as_dict(),
                }
                for (method, path), bucket in sorted(self._latency_by_route.items())
            ]
            total_requests = sum(item['count'] for item in http_breakdown)
            return {
                'service': {
                    'name': self.service_name,
                    'version': self.service_version,
                    'generated_at': datetime.now(timezone.utc).isoformat(),
                },
                'http': {
                    'total_requests': total_requests,
                    'breakdown': http_breakdown,
                    'latency_ms': latency_breakdown,
                },
                'domain_events': {
                    'ingested_total': dict(sorted(self._domain_events.items())),
                },
                'analysis_jobs': {
                    'requested_total': dict(sorted(self._job_requests.items())),
                    'runtime': store_runtime.get('analysis_jobs', {}),
                },
                'persistence': store_runtime.get('persistence', {}),
            }
