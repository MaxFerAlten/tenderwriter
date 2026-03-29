"""Golden dataset regression tests for the KPI reason engine."""

import importlib
import os
import shutil
import sys
import tempfile
import unittest

from fastapi.testclient import TestClient

from golden_dataset import GOLDEN_DATASET_CASES

_TEST_DIR = tempfile.mkdtemp(prefix="kpi-reason-engine-golden-")
os.environ["KPI_REASON_ENGINE_SERVICE_TOKEN"] = "test-kpi-token"
os.environ["KPI_REASON_ENGINE_DATABASE_URL"] = ""
os.environ["KPI_REASON_ENGINE_DATABASE_PATH"] = os.path.join(_TEST_DIR, "kpi_reason_engine.db")
os.environ["KPI_REASON_ENGINE_AUTO_MIGRATE_LEGACY_ON_STARTUP"] = "false"
os.environ["KPI_REASON_ENGINE_VALIDATE_LEGACY_MIGRATION"] = "false"


def _load_app():
    os.environ["KPI_REASON_ENGINE_SERVICE_TOKEN"] = "test-kpi-token"
    os.environ["KPI_REASON_ENGINE_DATABASE_URL"] = ""
    os.environ["KPI_REASON_ENGINE_DATABASE_PATH"] = os.path.join(_TEST_DIR, "kpi_reason_engine.db")
    os.environ["KPI_REASON_ENGINE_AUTO_MIGRATE_LEGACY_ON_STARTUP"] = "false"
    os.environ["KPI_REASON_ENGINE_VALIDATE_LEGACY_MIGRATION"] = "false"

    for module_name in list(sys.modules):
        if module_name == "app" or module_name.startswith("app."):
            sys.modules.pop(module_name, None)

    import app.config as app_config
    import app.main as app_main

    app_config = importlib.reload(app_config)
    app_main = importlib.reload(app_main)
    return app_main.app


class GoldenDatasetRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        app = _load_app()
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

    def test_golden_dataset_regression_cases(self) -> None:
        for case in GOLDEN_DATASET_CASES:
            with self.subTest(case_id=case['case_id']):
                self.client.app.state.store.clear_all()
                sync_response = self.client.post(
                    '/v1/tenders',
                    headers=self._auth_headers(),
                    json=case['tender'],
                )
                self.assertEqual(sync_response.status_code, 202)

                external_tender_id = case['tender']['external_tender_id']
                for event in case['events']:
                    response = self.client.post(
                        f'/v1/tenders/{external_tender_id}/events',
                        headers=self._auth_headers(),
                        json=event,
                    )
                    self.assertEqual(response.status_code, 202)

                snapshot = self.client.get(
                    f'/v1/tenders/{external_tender_id}/snapshot',
                    headers=self._auth_headers(),
                ).json()
                forecast = self.client.get(
                    f'/v1/tenders/{external_tender_id}/forecast',
                    headers=self._auth_headers(),
                ).json()
                transitions = self.client.get(
                    f'/v1/tenders/{external_tender_id}/transitions',
                    headers=self._auth_headers(),
                ).json()

                expected = case['expected']
                self.assertEqual(snapshot['analytical_phase'], expected['analytical_phase'])
                if 'health' in expected:
                    self.assertEqual(snapshot['health'], expected['health'])
                self.assertGreaterEqual(len(transitions['history_items']), 1)
                top_forecast = max(
                    forecast['scenarios'],
                    key=lambda item: -1.0 if item['probability'] is None else item['probability'],
                )
                self.assertEqual(top_forecast['name'], expected['top_forecast'])
                self.assertTrue(forecast['summary'])
                self.assertIsNotNone(forecast['overall_confidence'])
