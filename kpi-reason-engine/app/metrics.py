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


def _label_value(value: object) -> str:
    return str(value).replace('\\', '\\\\').replace('"', '\\"').replace('\n', ' ')


class RuntimeMetrics:
    """In-memory runtime metrics exposed by the KPI service."""

    def __init__(self, *, service_name: str, service_version: str, release_channel: str | None = None) -> None:
        self.service_name = service_name
        self.service_version = service_version
        self.release_channel = release_channel
        self.started_at = datetime.now(timezone.utc)
        self._lock = threading.RLock()
        self._http_counts: dict[tuple[str, str, int], int] = defaultdict(int)
        self._latency_by_route: dict[tuple[str, str], _LatencyBucket] = defaultdict(_LatencyBucket)
        self._domain_events: dict[str, int] = defaultdict(int)
        self._job_requests: dict[str, int] = defaultdict(int)

    def _uptime_seconds(self) -> float:
        return round((datetime.now(timezone.utc) - self.started_at).total_seconds(), 3)

    def service_metadata(self) -> dict[str, Any]:
        return {
            'name': self.service_name,
            'version': self.service_version,
            'release_channel': self.release_channel,
            'started_at': self.started_at.isoformat(),
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'uptime_seconds': self._uptime_seconds(),
        }

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
                'service': self.service_metadata(),
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
                'snapshots': store_runtime.get('snapshots', {}),
                'version_governance': store_runtime.get('version_governance', {}),
            }

    def render_prometheus(self, *, store_runtime: dict[str, Any]) -> str:
        snapshot = self.snapshot(store_runtime=store_runtime)
        lines: list[str] = []

        def metric(name: str, value: float | int, labels: dict[str, object] | None = None) -> None:
            if labels:
                label_blob = ','.join(f'{key}="{_label_value(label)}"' for key, label in sorted(labels.items()))
                lines.append(f'{name}{{{label_blob}}} {value}')
            else:
                lines.append(f'{name} {value}')

        lines.extend([
            '# HELP tw_kpi_service_up KPI reason engine liveness flag.',
            '# TYPE tw_kpi_service_up gauge',
        ])
        metric(
            'tw_kpi_service_up',
            1,
            {
                'service': self.service_name,
                'version': self.service_version,
                'release_channel': self.release_channel or 'unknown',
            },
        )
        lines.extend([
            '# HELP tw_kpi_uptime_seconds KPI reason engine uptime in seconds.',
            '# TYPE tw_kpi_uptime_seconds gauge',
        ])
        metric('tw_kpi_uptime_seconds', snapshot['service'].get('uptime_seconds') or 0)
        lines.extend([
            '# HELP tw_kpi_http_requests_total HTTP requests handled by the service.',
            '# TYPE tw_kpi_http_requests_total counter',
        ])
        for item in snapshot['http'].get('breakdown', []):
            metric(
                'tw_kpi_http_requests_total',
                item.get('count', 0),
                {
                    'method': item.get('method', 'UNKNOWN'),
                    'path': item.get('path', '/unknown'),
                    'status_code': item.get('status_code', 0),
                },
            )
        lines.extend([
            '# HELP tw_kpi_http_latency_average_ms Average route latency in milliseconds.',
            '# TYPE tw_kpi_http_latency_average_ms gauge',
        ])
        for item in snapshot['http'].get('latency_ms', []):
            metric(
                'tw_kpi_http_latency_average_ms',
                item.get('average_ms', 0),
                {
                    'method': item.get('method', 'UNKNOWN'),
                    'path': item.get('path', '/unknown'),
                },
            )
        lines.extend([
            '# HELP tw_kpi_http_latency_max_ms Max route latency in milliseconds.',
            '# TYPE tw_kpi_http_latency_max_ms gauge',
        ])
        for item in snapshot['http'].get('latency_ms', []):
            metric(
                'tw_kpi_http_latency_max_ms',
                item.get('max_ms', 0),
                {
                    'method': item.get('method', 'UNKNOWN'),
                    'path': item.get('path', '/unknown'),
                },
            )
        lines.extend([
            '# HELP tw_kpi_domain_events_total Domain events ingested by type.',
            '# TYPE tw_kpi_domain_events_total counter',
        ])
        for event_type, count in sorted(snapshot['domain_events'].get('ingested_total', {}).items()):
            metric('tw_kpi_domain_events_total', count, {'event_type': event_type})
        lines.extend([
            '# HELP tw_kpi_analysis_job_requests_total Analysis job requests by type.',
            '# TYPE tw_kpi_analysis_job_requests_total counter',
        ])
        for job_type, count in sorted(snapshot['analysis_jobs'].get('requested_total', {}).items()):
            metric('tw_kpi_analysis_job_requests_total', count, {'job_type': job_type})
        lines.extend([
            '# HELP tw_kpi_analysis_jobs_total Persisted analysis jobs by status.',
            '# TYPE tw_kpi_analysis_jobs_total gauge',
        ])
        for job_status, count in sorted(snapshot['analysis_jobs'].get('runtime', {}).get('by_status', {}).items()):
            metric('tw_kpi_analysis_jobs_total', count, {'status': job_status})
        lines.extend([
            '# HELP tw_kpi_persistence_total Persisted KPI entities by category.',
            '# TYPE tw_kpi_persistence_total gauge',
        ])
        for entity, count in sorted(snapshot.get('persistence', {}).items()):
            metric('tw_kpi_persistence_total', count, {'entity': entity})
        lines.extend([
            '# HELP tw_kpi_snapshots_total Snapshot governance counters by kind.',
            '# TYPE tw_kpi_snapshots_total gauge',
        ])
        for kind in ('persisted_total', 'reconstructed_total', 'shadow_mode_total', 'semantic_official_total', 'semantic_fallback_total'):
            metric('tw_kpi_snapshots_total', snapshot.get('snapshots', {}).get(kind, 0), {'kind': kind})
        return '\n'.join(lines) + '\n'
