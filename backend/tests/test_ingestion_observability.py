"""Unit tests for structured ingestion observability helpers."""

from __future__ import annotations

import os
import unittest

_TEST_ENV = {
    "APP_SECRET_KEY": "alpha-key-123456789012345678901234567890",
    "ADMIN_PASSWORD": "test-admin-password-1234567890",
    "DATABASE_URL": "postgresql+asyncpg://tester:securepass@localhost:5432/tenderwriter",
    "NEO4J_PASSWORD": "test-neo4j-password-1234567890",
    "MINIO_SECRET_KEY": "test-minio-password-1234567890",
    "ONLYOFFICE_JWT_SECRET": "office-jwt-token-12345678901234567890",
}
for key, value in _TEST_ENV.items():
    os.environ.setdefault(key, value)

from app.ingestion.observability import (
    extract_ingestion_observability,
    update_ingestion_observability,
)


class IngestionObservabilityTests(unittest.TestCase):
    def test_update_tracks_stage_progress_and_preserves_existing_metadata(self) -> None:
        metadata = {"original_filename": "tender.pdf"}

        metadata = update_ingestion_observability(
            metadata,
            stage="parse",
            status="started",
            detail="Parsing started.",
        )
        metadata = update_ingestion_observability(
            metadata,
            stage="parse",
            status="completed",
            stats={"elements_detected": 12},
        )

        observability = extract_ingestion_observability(metadata)

        self.assertEqual(metadata["original_filename"], "tender.pdf")
        self.assertEqual(observability["current_stage"], "parse")
        self.assertEqual(observability["current_stage_status"], "completed")
        self.assertEqual(observability["progress"], 30.0)
        self.assertEqual(observability["stages"]["parse"]["stats"]["elements_detected"], 12)
        self.assertEqual(observability["completed_stages"], ["parse"])

    def test_update_marks_failure_on_current_stage(self) -> None:
        metadata = update_ingestion_observability(
            {},
            stage="chunking",
            status="started",
            detail="Chunking started.",
        )
        metadata = update_ingestion_observability(
            metadata,
            stage="chunking",
            status="failed",
            detail="Failure while chunking.",
            error_message="worker timeout",
        )

        observability = extract_ingestion_observability(metadata)

        self.assertEqual(observability["current_stage"], "chunking")
        self.assertEqual(observability["current_stage_status"], "failed")
        self.assertEqual(observability["failed_stage"], "chunking")
        self.assertEqual(observability["failure"]["message"], "worker timeout")
        self.assertEqual(observability["stages"]["chunking"]["error_message"], "worker timeout")
        self.assertEqual(observability["progress"], 50.0)


if __name__ == "__main__":
    unittest.main()
