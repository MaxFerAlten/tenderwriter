"""Unit tests for deterministic RAG context hygiene helpers."""

from __future__ import annotations

import unittest

from app.rag.context_quality import compress_context_block, deduplicate_context_items


class RagContextQualityTests(unittest.TestCase):
    def test_deduplicate_context_blocks_keeps_best_source_score(self) -> None:
        items = [
            {"text": "La gara richiede qualificazione ACN entro 210 giorni.", "score": 0.2},
            {"text": "La gara richiede qualificazione ACN entro 210 giorni.", "score": 0.9},
        ]

        deduped, stats = deduplicate_context_items(items)

        self.assertEqual(len(deduped), 1)
        self.assertEqual(deduped[0]["score"], 0.9)
        self.assertEqual(stats["removed"], 1)

    def test_deduplicate_context_blocks_preserves_merged_provenance(self) -> None:
        items = [
            {
                "text": "La gara richiede qualificazione ACN entro 210 giorni.",
                "score": 0.9,
                "metadata": {"source": "dense", "document_id": 12},
                "retriever_sources": ["dense"],
                "source_scores": {"dense": 0.9},
            },
            {
                "text": "La gara richiede qualificazione ACN entro 210 giorni.",
                "score": 0.8,
                "metadata": {"source": "knowledge_graph", "requirement_id": 77},
                "retriever_sources": ["graph"],
                "source_scores": {"graph": 0.8},
            },
        ]

        deduped, stats = deduplicate_context_items(items)

        self.assertEqual(len(deduped), 1)
        self.assertEqual(stats["removed"], 1)
        self.assertEqual(deduped[0]["score"], 0.9)
        self.assertEqual(deduped[0]["metadata"].get("document_id"), 12)
        self.assertEqual(deduped[0]["metadata"].get("requirement_id"), 77)
        self.assertEqual(deduped[0].get("retriever_sources"), ["dense", "graph"])
        self.assertEqual(deduped[0].get("source_scores"), {"dense": 0.9, "graph": 0.8})

    def test_near_duplicate_context_blocks_are_removed(self) -> None:
        items = [
            {"text": "Il Fornitore deve completare la Fase 1 entro 180 giorni solari."},
            {
                "text": "Il fornitore deve completare la fase 1 entro 180 giorni "
                "solari continuativi."
            },
        ]

        deduped, stats = deduplicate_context_items(items, similarity_threshold=0.88)

        self.assertEqual(len(deduped), 1)
        self.assertEqual(stats["removed"], 1)

    def test_distinct_requirements_with_shared_boilerplate_are_not_deduplicated(self) -> None:
        items = [
            {
                "text": (
                    "Il Fornitore deve completare la Fase 1 entro 180 giorni solari "
                    "dalla data di avvio."
                )
            },
            {
                "text": (
                    "Il Fornitore deve garantire il servizio di assistenza entro 4 ore "
                    "lavorative dalla segnalazione."
                )
            },
        ]

        deduped, stats = deduplicate_context_items(items)

        self.assertEqual(len(deduped), 2)
        self.assertEqual(stats["removed"], 0)

    def test_appended_detail_near_duplicate_is_deduplicated_by_default(self) -> None:
        items = [
            {"text": "La gara richiede qualificazione ACN entro 210 giorni."},
            {
                "text": (
                    "La gara richiede la qualificazione ACN entro 210 giorni dalla stipula."
                )
            },
        ]

        deduped, stats = deduplicate_context_items(items)

        self.assertEqual(len(deduped), 1)
        self.assertEqual(stats["removed"], 1)

    def test_compress_context_preserves_numeric_and_query_sentences(self) -> None:
        text = (
            "La procedura contiene premesse generiche. "
            "Il Fornitore deve conseguire qualificazione ACN entro 210 giorni. "
            "Altra premessa generica ripetuta."
        )

        compressed = compress_context_block(
            text,
            query="Quale qualificazione ACN e richiesta?",
        )

        self.assertIn("qualificazione ACN entro 210 giorni", compressed)
        self.assertNotIn("premesse generiche", compressed)

    def test_compress_context_drops_unmatched_headings(self) -> None:
        text = (
            "Premessa amministrativa:\n"
            "La documentazione contiene testo introduttivo non pertinente.\n"
            "Il Fornitore deve conseguire qualificazione ACN entro 210 giorni.\n"
            "Note generiche:\n"
            "Altre informazioni di cornice."
        )

        compressed = compress_context_block(
            text,
            query="Quale qualificazione ACN e richiesta?",
        )

        self.assertIn("qualificazione ACN entro 210 giorni", compressed)
        self.assertNotIn("Premessa amministrativa", compressed)
        self.assertNotIn("Note generiche", compressed)

    def test_compress_generic_tender_overview_keeps_tender_relevant_sentences(self) -> None:
        text = (
            "Premessa generale senza dettagli operativi. "
            "Oggetto della gara e' la gestione del Sistema Cloud Toscana e dei servizi CCTT. "
            "Il codice CIG B123456789 identifica la procedura. "
            "La durata prevista e' di 48 mesi. "
            "Nota di stile non pertinente alla gara."
        )

        compressed = compress_context_block(text, query="descrivimi la gara")

        self.assertIn("Oggetto della gara", compressed)
        self.assertIn("CIG B123456789", compressed)
        self.assertIn("48 mesi", compressed)
        self.assertNotIn("Premessa generale", compressed)
        self.assertNotIn("Nota di stile", compressed)


if __name__ == "__main__":
    unittest.main()
