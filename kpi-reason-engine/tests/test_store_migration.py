"""Legacy SQLite to primary store migration tests."""

import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from app.migrations import run_migrations
from app.store import SqliteStore, _from_json_value, _to_iso_value
from app.store_migration import migrate_legacy_sqlite_to_store, validate_legacy_sqlite_counts


class StoreMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = Path(tempfile.mkdtemp(prefix='kpi-store-migration-'))
        self.source_path = self._temp_dir / 'source.db'
        self.target_path = self._temp_dir / 'target.db'

        run_migrations(database_path=str(self.source_path))
        run_migrations(database_url=f"sqlite:///{self.target_path.as_posix()}")

        self.source_store = SqliteStore(str(self.source_path))
        self.target_store = SqliteStore(
            str(self.target_path),
            database_url=f"sqlite:///{self.target_path.as_posix()}",
        )
        self.source_store.open()
        self.target_store.open()

    def tearDown(self) -> None:
        self.source_store.close()
        self.target_store.close()
        shutil.rmtree(self._temp_dir, ignore_errors=True)

    def test_migrates_legacy_sqlite_into_empty_primary_store(self) -> None:
        self.source_store.upsert_tender(
            {
                'external_tender_id': 'TEN-MIGRATE',
                'title': 'Migrated Tender',
                'customer_name': 'Northwind',
                'due_at': '2030-04-30T10:00:00Z',
                'current_status': 'draft',
                'departments': ['sales'],
                'requirement_contexts': [],
                'section_contexts': [],
                'metadata': {'priority': 'high'},
            }
        )
        inserted = self.source_store.insert_domain_event(
            'TEN-MIGRATE',
            {
                'event_type': 'tender_document_ingested',
                'occurred_at': '2026-03-20T09:00:00Z',
                'source': 'tw-backend',
                'schema_version': '1.0.0',
                'payload': {'document_id': 'DOC-1'},
            },
        )

        self.assertTrue(inserted)

        report = migrate_legacy_sqlite_to_store(str(self.source_path), self.target_store)
        validation = validate_legacy_sqlite_counts(str(self.source_path), self.target_store)

        self.assertEqual(report['status'], 'completed')
        self.assertEqual(report['migrated_tables']['kpi_tenders'], 1)
        self.assertEqual(report['migrated_tables']['kpi_domain_events'], 1)
        self.assertEqual(validation['status'], 'completed')
        self.assertEqual(
            self.target_store.get_tender('TEN-MIGRATE')['title'],
            'Migrated Tender',
        )
        self.assertEqual(self.target_store.count_domain_events('TEN-MIGRATE'), 1)

    def test_skips_migration_when_target_already_contains_data(self) -> None:
        self.target_store.upsert_tender(
            {
                'external_tender_id': 'TEN-TARGET',
                'title': 'Existing Primary Tender',
                'customer_name': 'Northwind',
                'due_at': '2030-04-30T10:00:00Z',
                'current_status': 'draft',
                'departments': [],
                'requirement_contexts': [],
                'section_contexts': [],
                'metadata': {},
            }
        )

        report = migrate_legacy_sqlite_to_store(str(self.source_path), self.target_store)

        self.assertEqual(report['status'], 'skipped')
        self.assertEqual(report['reason'], 'target_store_not_empty')


class StoreNativeTypeCompatibilityTests(unittest.TestCase):
    def test_from_json_value_accepts_already_deserialized_json(self) -> None:
        payload = {'engine': 'postgres', 'enabled': True}

        self.assertIs(_from_json_value(payload, default={}), payload)

    def test_to_iso_value_normalizes_datetime_to_utc_isoformat(self) -> None:
        timestamp = datetime(2030, 4, 30, 12, 0, tzinfo=timezone.utc)

        self.assertEqual(_to_iso_value(timestamp), '2030-04-30T12:00:00+00:00')


if __name__ == '__main__':
    unittest.main()
