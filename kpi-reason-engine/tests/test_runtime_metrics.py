"""Runtime metrics tests for the KPI reason engine."""

import os
import shutil
import tempfile
import time
import unittest
from unittest.mock import patch

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

    def _seed_runtime_data(self) -> None:
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

    def test_metrics_endpoint_reports_runtime_counters_and_governance(self) -> None:
        self._seed_runtime_data()

        response = self.client.get('/metrics')

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['service']['name'], 'tw-kpi-reason-engine')
        self.assertEqual(payload['service']['release_channel'], 'production')
        self.assertGreater(payload['service']['uptime_seconds'], 0)
        self.assertGreater(payload['http']['total_requests'], 0)
        self.assertEqual(payload['domain_events']['ingested_total']['tender_document_ingested'], 1)
        self.assertEqual(payload['analysis_jobs']['requested_total']['full_recompute'], 1)
        self.assertEqual(payload['persistence']['mirrored_tenders'], 1)
        self.assertGreaterEqual(payload['analysis_jobs']['runtime']['by_status'].get('succeeded', 0), 1)
        self.assertGreaterEqual(payload['persistence']['persisted_snapshots'], 1)
        self.assertGreaterEqual(payload['snapshots']['semantic_official_total'], 1)
        self.assertEqual(payload['version_governance']['schema_version'], '20260315_0003')
        self.assertIn('snapshot-output-v1', payload['version_governance']['snapshot_output_schema_versions'])

    def test_readiness_endpoint_reports_ready_runtime_state(self) -> None:
        self._seed_runtime_data()

        response = self.client.get('/ready')

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'ready')
        self.assertTrue(payload['ready'])
        self.assertTrue(payload['worker_running'])
        self.assertEqual(payload['service'], 'tw-kpi-reason-engine')
        self.assertEqual(payload['readiness_rule_version'], 'service-readiness-v1')

    def test_readiness_endpoint_degrades_when_failed_jobs_exceed_threshold(self) -> None:
        runtime_payload = {
            'analysis_jobs': {'by_status': {'failed': 2, 'queued': 0}, 'by_type_and_status': [], 'latest_updated_at': None},
            'persistence': {'mirrored_tenders': 0, 'persisted_domain_events': 0, 'persisted_document_contexts': 0, 'persisted_snapshots': 0, 'persisted_findings': 0, 'persisted_phase_transitions': 0},
            'snapshots': {'persisted_total': 0, 'latest_generated_at': None, 'reconstructed_total': 0, 'shadow_mode_total': 0, 'semantic_official_total': 0, 'semantic_fallback_total': 0},
            'version_governance': {'schema_version': '20260315_0003', 'snapshot_output_schema_versions': {}, 'contract_versions': {}, 'semantic_bundle_versions': {}, 'shadow_bundle_versions': {}, 'source_job_types': {}, 'model_versions': {}},
        }
        with patch.object(self.client.app.state.store, 'get_runtime_metrics', return_value=runtime_payload):
            response = self.client.get('/ready')

        self.assertEqual(response.status_code, 503)
        payload = response.json()
        self.assertEqual(payload['status'], 'degraded')
        self.assertFalse(payload['ready'])
        self.assertIn('Failed analysis jobs (2) exceed threshold 0.', payload['warnings'])

    def test_version_manifest_endpoint_reports_output_and_model_versions(self) -> None:
        self._seed_runtime_data()

        response = self.client.get('/version-manifest')

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'available')
        self.assertEqual(payload['snapshot_output_schema_version'], 'snapshot-output-v1')
        self.assertEqual(payload['forecast_output_schema_version'], 'forecast-output-v1')
        self.assertEqual(payload['version_manifest_schema_version'], 'version-manifest-v1')
        components = {item['component'] for item in payload['entries']}
        self.assertIn('contract', components)
        self.assertIn('snapshot_output', components)
        self.assertIn('forecast_output', components)
        self.assertIn('formula_bundle', components)

    def test_prometheus_metrics_export_exposes_core_series(self) -> None:
        self._seed_runtime_data()

        response = self.client.get('/metrics/prometheus')

        self.assertEqual(response.status_code, 200)
        body = response.text
        self.assertIn('tw_kpi_service_up', body)
        self.assertIn('tw_kpi_uptime_seconds', body)
        self.assertIn('tw_kpi_http_requests_total', body)
        self.assertIn('tw_kpi_analysis_jobs_total', body)
        self.assertIn('tw_kpi_snapshots_total', body)


if __name__ == '__main__':
    unittest.main()

