"""Unit tests for deterministic ingestion document quality helpers."""

from __future__ import annotations

import unittest

from app.ingestion.document_quality import extract_numeric_mentions, has_broken_numeric_fragment


class IngestionDocumentQualityTests(unittest.TestCase):
    def test_extract_numeric_mentions_finds_giorni_euro_percentuali_and_articles(self) -> None:
        mentions = extract_numeric_mentions(
            "entro 180 giorni, penale Euro 100/giorno, massimo 10%, art. 1456 c.c."
        )

        self.assertIn("180 giorni", mentions)
        self.assertIn("Euro 100", mentions)
        self.assertIn("10%", mentions)
        self.assertIn("art. 1456 c.c.", mentions)

    def test_detect_broken_numeric_fragment_flags_missing_number(self) -> None:
        self.assertTrue(has_broken_numeric_fragment("la fase deve concludersi entro giorni"))
        self.assertFalse(has_broken_numeric_fragment("la fase deve concludersi entro 180 giorni"))


if __name__ == "__main__":
    unittest.main()
