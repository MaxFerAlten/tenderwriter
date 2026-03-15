"""Runtime metrics tests for the KPI reason engine."""

import os
import shutil
import tempfile
import time
import unittest

from fastapi.testclient import TestClient

_TEST_DIR = tempfile.mkdtemp(prefix="kpi-reason-engine-metrics-")
os.environ.setdefault("KPI_REASON_ENGINE_SERVICE_TOKEN", "test-kpi-token")
os.environ.setdefault("KPI_REASON_ENGINE_DATABASE_PATH", os.path.join(_TEST_DIR, "kpi_reason_engine.db"))

from app.main import app


class RuntimeMetricsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._client_cm = TestClient(app)
        cls.client = cls._client_cm.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._client_cm.__exit__(None, None, None)
        shutil.rmtree(_TEST_DIR, ignore_errors=True)

    def setUp(self) -> None:
        self.client.app.state.store.clear_all()

    @staticmethod
    def _auth_headers() -> dict[str, str]:
        return {
            'Authorization': 'Bearer test-kpi-token',
            'X-Service-Token': 'test-kpi-token',
        }

    def test_metrics_endpoint_reports_runtime_counters_and_gauges(self) -> None:
        self.client.post(
            '/v1/tenders',
            headers=self._auth_headers(),
            json={
                'external_tender_id': 'TEN-METRICS',
                'title': 'Metrics Tender',
                'customer_name': 'Northwind',
                'due_at': '2030-04-30T10:00:00Z',
                'current_status': 'draft',
                'departments': ['sales'],
                'requirement_contexts': [],
                'section_contexts': [],
                'metadata': {},
            },
        )
        self.client.post(
            '/v1/tenders/TEN-METRICS/events',
            headers=self._auth_headers(),
            json={
                'event_type': 'tender_document_ingested',
                'occurred_at': '2026-03-15T08:00:00Z',
                'source': 'tw-backend',
                'payload': {'document_id': 'DOC-1'},
            },
        )
        self.client.post(
            '/v1/tenders/TEN-METRICS/analysis-jobs',
            headers=self._auth_headers(),
            json={
                'job_type': 'full_recompute',
                'requested_by': 'admin-1',
                'priority': 'high',
                'reason': 'Metrics refresh',
                'metadata': {'source': 'admin-ui'},
            },
        )

        for _ in range(20):
            latest_job = self.client.get(
                '/v1/tenders/TEN-METRICS/analysis-jobs/latest',
                headers=self._auth_headers(),
            ).json()
            if latest_job['job_status'] == 'succeeded':
                break
            time.sleep(0.05)

        response = self.client.get('/metrics')

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['service']['name'], 'tw-kpi-reason-engine')
        self.assertGreater(payload['http']['total_requests'], 0)
        self.assertEqual(payload['domain_events']['ingested_total']['tender_document_ingested'], 1)
        self.assertEqual(payload['analysis_jobs']['requested_total']['full_recompute'], 1)
        self.assertEqual(payload['persistence']['mirrored_tenders'], 1)
        self.assertGreaterEqual(payload['analysis_jobs']['runtime']['by_status'].get('succeeded', 0), 1)
        self.assertGreaterEqual(payload['persistence']['persisted_snapshots'], 1)
