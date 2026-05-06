"""Unit tests for answer-level RAG quality metrics."""

from __future__ import annotations

import unittest

from app.services import rag_answer_quality_evaluation as _service_module


class RagAnswerQualityEvaluationTests(unittest.TestCase):
    def test_duplicate_ratio_detects_repeated_paragraphs(self) -> None:
        text = (
            "A. La gara richiede ACN.\n\nA. La gara richiede ACN.\n\nB. Sono previsti 180 giorni."
        )

        metrics = _service_module.evaluate_answer_quality(
            answer=text,
            context="La gara richiede ACN. Sono previsti 180 giorni.",
            required_facts=("ACN", "180 giorni"),
        )

        self.assertEqual(metrics.duplicate_block_ratio, 0.3333)
        self.assertIn("duplicate_blocks", metrics.failures)

    def test_required_fact_coverage_reports_missing_facts(self) -> None:
        metrics = _service_module.evaluate_answer_quality(
            answer="La gara richiede qualificazione ACN.",
            context="La gara richiede ACN e usa START.",
            required_facts=("ACN", "START"),
        )

        self.assertEqual(metrics.required_fact_coverage, 0.5)
        self.assertIn("required_fact_coverage", metrics.failures)

    def test_numeric_coverage_requires_fact_in_answer_and_context(self) -> None:
        metrics = _service_module.evaluate_answer_quality(
            answer="La durata e di 48 mesi e la fase iniziale dura 180 giorni.",
            context="La durata e di 48 mesi. La fase iniziale dura 180 giorni. "
            "La proroga puo arrivare a 270 giorni.",
            required_facts=(),
            numeric_facts=("48 mesi", "180 giorni", "270 giorni"),
        )

        self.assertEqual(metrics.numeric_fact_coverage, 0.6667)
        self.assertIn("numeric_fact_coverage", metrics.failures)

    def test_unsupported_entity_detection_flags_entity_absent_from_context(self) -> None:
        metrics = _service_module.evaluate_answer_quality(
            answer="Il Consorzio Metis gestisce la gara.",
            context="Regione Toscana e ESTAR sono soggetti coinvolti.",
            required_facts=(),
        )

        self.assertIn("Consorzio Metis", metrics.unsupported_entities)
        self.assertIn("unsupported_entities", metrics.failures)

    def test_evaluate_answer_quality_cases_summarizes_fixture_list(self) -> None:
        report = _service_module.evaluate_answer_quality_cases(
            [
                {
                    "id": "overview-oscat",
                    "answer": "La gara richiede ACN.",
                    "context": "La gara richiede ACN.",
                    "required_facts": ["ACN"],
                    "numeric_facts": [],
                }
            ]
        )

        self.assertEqual(report.case_count, 1)
        self.assertEqual(report.average_required_fact_coverage, 1.0)
        self.assertEqual(report.unsupported_entity_count, 0)


if __name__ == "__main__":
    unittest.main()
