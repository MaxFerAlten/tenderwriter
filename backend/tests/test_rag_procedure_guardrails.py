"""Tests for deterministic RAG procedure guardrails."""

# ruff: noqa: E402

from __future__ import annotations

import os
import re
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

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

from app.rag.engine import HybridRAGEngine, LLMRoute, QueryMode, RAGQuery
from app.rag.generator import GenerationResult
from app.rag.procedure_guardrails import (
    BLOCKED_OUTPUT_MESSAGE,
    FactSheet,
    FactStatus,
    build_fact_sheet,
    classify_chunk_procedure,
    fact_sheet_from_guarded_context,
    normalize_guardrail_config,
    repair_unsupported_protected_facts,
    source_procedure_labels_from_guarded_context,
    validate_guarded_answer,
)


class RagProcedureGuardrailsTests(unittest.TestCase):
    def test_classifies_oscat_and_sct_chunks_by_anchors(self) -> None:
        self.assertEqual(
            classify_chunk_procedure(
                "Servizi GitLab, Sonar, Nexus, Vulnerability Assessment, SME, MAM e STS."
            ),
            "OSCAT",
        )
        self.assertEqual(
            classify_chunk_procedure(
                "RTPC, CCTT, fase transitoria, qualificazione ACN e Via San Piero a Quaracchi."
            ),
            "SCT",
        )

    def test_build_fact_sheet_extracts_protected_fields_with_sources(self) -> None:
        items = [
            {
                "text": (
                    "Procedura OSCAT 012942/2025 per CI/CD. "
                    "CIG B123456789. Sono previsti 180 giorni e 48 mesi."
                ),
                "metadata": {"chunk_index": 7, "page_number": 3},
            }
        ]

        sheet = build_fact_sheet(items, query="descrivimi la gara OSCAT")

        self.assertEqual(sheet.procedure_label, "OSCAT")
        self.assertIn("012942/2025", sheet.procedure_ids)
        self.assertIn("B123456789", sheet.cigs)
        self.assertIn("180 giorni", sheet.critical_days)
        self.assertIn("48 mesi", sheet.durations)
        self.assertEqual(sheet.status, FactStatus.VERIFIED)
        self.assertIn("chunk:7", sheet.source_ids)

    def test_build_fact_sheet_extracts_neutral_admin_fields_for_procedure(self) -> None:
        items = [
            {
                "text": "Piattaforma OSCAT con GitLab, Sonar e Nexus. Procedura 012942/2025.",
                "metadata": {"chunk_index": 7, "document_id": 1, "tender_id": 10},
            },
            {
                "text": (
                    "DURATA La durata dell'accordo quadro e' di 36 mesi. "
                    "La durata prevista del procedimento e' pari a 9 mesi."
                ),
                "metadata": {"chunk_index": 8, "document_id": 1, "tender_id": 10},
            },
            {
                "text": (
                    "GARANZIA PROVVISORIA pari al 2% del valore complessivo "
                    "dell'appalto e precisamente di importo pari ad euro 223.451,66."
                ),
                "metadata": {"chunk_index": 9, "document_id": 1, "tender_id": 10},
            },
            {
                "text": (
                    "Il luogo di svolgimento del servizio e' la Regione Sardegna "
                    "(codice NUTS ITG2)."
                ),
                "metadata": {"chunk_index": 10, "document_id": 1, "tender_id": 10},
            },
        ]

        sheet = build_fact_sheet(items, query="descrivimi la gara OSCAT")

        self.assertEqual(sheet.procedure_label, "OSCAT")
        self.assertIn("012942/2025", sheet.procedure_ids)
        self.assertEqual(sheet.durations, ("36 mesi", "9 mesi"))
        self.assertIn("euro 223.451,66", sheet.amounts)
        self.assertIn("2%", sheet.percentages)
        self.assertIn("Regione Sardegna", sheet.locations)
        self.assertEqual(sheet.source_ids, ("chunk:7", "chunk:8", "chunk:9", "chunk:10"))

    def test_build_fact_sheet_rejects_unlinked_neutral_admin_fields(self) -> None:
        items = [
            {
                "text": "Piattaforma OSCAT con GitLab, Sonar e Nexus. Procedura 012942/2025.",
                "metadata": {"chunk_index": 7, "document_id": 1, "tender_id": 10},
            },
            {
                "text": (
                    "DURATA La durata dell'accordo quadro e' di 36 mesi. "
                    "GARANZIA PROVVISORIA pari al 2% e ad euro 223.451,66."
                ),
                "metadata": {"chunk_index": 8, "document_id": 2, "tender_id": 20},
            },
        ]

        sheet = build_fact_sheet(items, query="descrivimi la gara OSCAT")

        self.assertEqual(sheet.procedure_label, "OSCAT")
        self.assertEqual(sheet.procedure_ids, ("012942/2025",))
        self.assertEqual(sheet.durations, ())
        self.assertEqual(sheet.amounts, ())
        self.assertEqual(sheet.percentages, ())
        self.assertEqual(sheet.source_ids, ("chunk:7",))

    def test_conflicting_cigs_block_fact_sheet(self) -> None:
        sheet = build_fact_sheet(
            [
                {"text": "Gara OSCAT con CIG B123456789.", "metadata": {"chunk_index": 1}},
                {"text": "Gara OSCAT con CIG C987654321.", "metadata": {"chunk_index": 2}},
            ],
            query="descrivimi la gara OSCAT",
        )

        self.assertEqual(sheet.status, FactStatus.CONFLICT)
        self.assertIn("cig", sheet.conflicts)

    def test_fact_sheet_does_not_mix_protected_fields_from_other_procedures(self) -> None:
        sheet = build_fact_sheet(
            [
                {
                    "text": (
                        "Sistema Cloud Toscana SCT con RTPC, CCTT, qualificazione ACN. "
                        "CIG B33988ECF2. Fase transitoria di 270 giorni. "
                        "Sede in Via San Piero a Quaracchi 250."
                    ),
                    "metadata": {"chunk_index": 10},
                },
                {
                    "text": (
                        "OSCAT usa GitLab, Sonar e Nexus. Procedura 012942/2025. "
                        "CIG B123456789. Durata 48 mesi e verifica in 180 giorni."
                    ),
                    "metadata": {"chunk_index": 11},
                },
            ],
            query="descrivimi la gara SCT",
        )

        self.assertEqual(sheet.procedure_label, "SCT")
        self.assertEqual(sheet.cigs, ("B33988ECF2",))
        self.assertEqual(sheet.procedure_ids, ())
        self.assertEqual(sheet.critical_days, ("270 giorni",))
        self.assertEqual(sheet.durations, ())
        self.assertEqual(sheet.source_ids, ("chunk:10",))

    def test_fact_sheet_context_parser_preserves_decimal_amounts(self) -> None:
        sheet = fact_sheet_from_guarded_context(
            "FACT_SHEET_START\n"
            "procedura: OSCAT\n"
            "stato_verifica: verificato\n"
            "procedure_id: non_rilevato\n"
            "cig: non_rilevato\n"
            "giorni_critici: non_rilevato\n"
            "durata: non_rilevato\n"
            "importi: € 1.234,56\n"
            "sedi_luoghi: non_rilevato\n"
            "percentuali: non_rilevato\n"
            "fonti: chunk:1\n"
            "conflitti: nessuno\n"
            "FACT_SHEET_END"
        )

        self.assertIsNotNone(sheet)
        assert sheet is not None
        self.assertEqual(sheet.amounts, ("€ 1.234,56",))

    def test_fact_sheet_keeps_oscat_amounts_and_excludes_sct_millions(self) -> None:
        sheet = build_fact_sheet(
            [
                {
                    "text": (
                        "Sistema Cloud Toscana SCT con RTPC, CCTT e qualificazione ACN. "
                        "Valore stimato dell'appalto pari a 150 milioni di euro."
                    ),
                    "metadata": {"chunk_index": 10},
                },
                {
                    "text": (
                        "OSCAT usa GitLab, Sonar e Nexus. Procedura 012942/2025. "
                        "L'importo a base di gara e pari a 5.999.723,60 euro. "
                        "Il valore globale stimato comprensivo di opzioni e pari a "
                        "11.172.582,96 euro."
                    ),
                    "metadata": {"chunk_index": 11},
                },
            ],
            query="descrivimi la gara OSCAT",
        )

        self.assertEqual(sheet.procedure_label, "OSCAT")
        self.assertEqual(
            sheet.amounts,
            ("5.999.723,60 euro", "11.172.582,96 euro"),
        )
        self.assertNotIn("150 milioni di euro", sheet.amounts)

    def test_oscat_answer_with_sct_million_amount_is_blocked(self) -> None:
        sheet = build_fact_sheet(
            [
                {
                    "text": (
                        "OSCAT usa GitLab, Sonar e Nexus. Procedura 012942/2025. "
                        "Importo a base di gara pari a 5.999.723,60 euro. "
                        "Valore globale stimato pari a 11.172.582,96 euro."
                    ),
                    "metadata": {"chunk_index": 11},
                }
            ],
            query="descrivimi la gara OSCAT",
        )

        result = validate_guarded_answer(
            answer="La gara OSCAT ha un valore finale pari a 150 milioni di euro.",
            fact_sheet=sheet,
            guarded=True,
        )

        self.assertEqual(result.status, "BLOCK")
        self.assertIn("unverified_amount:150 milioni di euro", result.failures)

    def test_repair_replaces_unverified_amount_with_verified_oscat_amounts(self) -> None:
        sheet = build_fact_sheet(
            [
                {
                    "text": (
                        "OSCAT usa GitLab, Sonar e Nexus. Procedura 012942/2025. "
                        "Importo a base di gara pari a 5.999.723,60 euro. "
                        "Valore globale stimato pari a 11.172.582,96 euro."
                    ),
                    "metadata": {"chunk_index": 11},
                }
            ],
            query="descrivimi la gara OSCAT",
        )

        repaired = repair_unsupported_protected_facts(
            "Il valore della gara OSCAT e pari a 150.000.000,00 euro.",
            sheet,
        )

        self.assertNotIn("150.000.000,00", repaired)
        self.assertNotIn("importo non verificato0.00", repaired)
        # Single placeholder collapses to the closest verified amount, not the
        # full cluster.
        self.assertTrue(
            "5.999.723,60 euro" in repaired or "11.172.582,96 euro" in repaired,
            msg=f"expected at least one verified amount in {repaired!r}",
        )

    def test_false_missing_claim_for_verified_duration_and_amounts_is_blocked(self) -> None:
        sheet = build_fact_sheet(
            [
                {
                    "text": (
                        "OSCAT usa GitLab, Sonar e Nexus. Procedura 012942/2025. "
                        "Durata 48 mesi. Importo a base di gara pari a "
                        "5.999.723,60 euro e valore globale stimato pari a "
                        "11.172.582,96 euro."
                    ),
                    "metadata": {"chunk_index": 11},
                }
            ],
            query="descrivimi la gara OSCAT",
        )

        result = validate_guarded_answer(
            answer=(
                "Aspetti non coperti: non risultano disponibili durata "
                "e importi della procedura OSCAT."
            ),
            fact_sheet=sheet,
            guarded=True,
        )

        self.assertEqual(result.status, "BLOCK")
        self.assertIn("false_missing_duration", result.failures)
        self.assertIn("false_missing_amounts", result.failures)

    def test_repair_replaces_false_missing_claim_with_verified_facts(self) -> None:
        sheet = build_fact_sheet(
            [
                {
                    "text": (
                        "OSCAT usa GitLab, Sonar e Nexus. Procedura 012942/2025. "
                        "Durata 48 mesi. Importo a base di gara pari a "
                        "5.999.723,60 euro e valore globale stimato pari a "
                        "11.172.582,96 euro."
                    ),
                    "metadata": {"chunk_index": 11},
                }
            ],
            query="descrivimi la gara OSCAT",
        )

        repaired = repair_unsupported_protected_facts(
            "Aspetti non coperti: non risultano disponibili durata e importi.",
            sheet,
        )

        self.assertNotIn("non risultano disponibili durata e importi", repaired)
        self.assertIn("durata 48 mesi", repaired)
        self.assertIn("5.999.723,60 euro", repaired)
        self.assertIn("11.172.582,96 euro", repaired)

    def test_answer_with_unverified_number_is_blocked(self) -> None:
        sheet = build_fact_sheet(
            [{"text": "Gara OSCAT con CIG B123456789 e durata 48 mesi.", "metadata": {}}],
            query="descrivimi la gara OSCAT",
        )

        result = validate_guarded_answer(
            answer="La gara OSCAT dura 48 mesi e include una fase da 270 giorni.",
            fact_sheet=sheet,
            guarded=True,
        )

        self.assertEqual(result.status, "BLOCK")
        self.assertEqual(result.safe_answer, BLOCKED_OUTPUT_MESSAGE)
        self.assertIn("unverified_number:270", result.failures)

    def test_answer_with_unverified_singular_day_is_blocked(self) -> None:
        sheet = build_fact_sheet(
            [{"text": "Gara OSCAT con CIG B123456789 e durata 48 mesi.", "metadata": {}}],
            query="descrivimi la gara OSCAT",
        )

        result = validate_guarded_answer(
            answer="La gara OSCAT dura 48 mesi e include una fase da 270 giorno.",
            fact_sheet=sheet,
            guarded=True,
        )

        self.assertEqual(result.status, "BLOCK")
        self.assertIn("unverified_number:270", result.failures)

    def test_answer_mixing_oscat_and_sct_without_comparison_is_blocked(self) -> None:
        sheet = build_fact_sheet(
            [
                {
                    "text": "OSCAT usa GitLab, Sonar, Nexus e Vulnerability Assessment.",
                    "metadata": {},
                }
            ],
            query="descrivimi la gara OSCAT",
        )

        result = validate_guarded_answer(
            answer="OSCAT usa GitLab. SCT richiede RTPC e qualificazione ACN.",
            fact_sheet=sheet,
            guarded=True,
        )

        self.assertEqual(result.status, "BLOCK")
        self.assertIn("cross_procedure_mixing", result.failures)

    def test_answer_mixing_procedures_supported_by_sources_is_allowed(self) -> None:
        guarded_context = (
            "FACT_SHEET_START\n"
            "procedura: SCT\n"
            "stato_verifica: verificato\n"
            "procedure_id: non_rilevato\n"
            "cig: non_rilevato\n"
            "giorni_critici: 180 giorni, 270 giorni\n"
            "durata: non_rilevato\n"
            "importi: non_rilevato\n"
            "sedi_luoghi: non_rilevato\n"
            "percentuali: non_rilevato\n"
            "fonti: chunk:1200, chunk:943\n"
            "conflitti: nessuno\n"
            "FACT_SHEET_END\n"
            "SOURCE_START id=1200 page=1 procedure=SCT\n"
            "SCT prevede CCTT, RTPC, qualificazione ACN e fase transitoria.\n"
            "SOURCE_END\n"
            "SOURCE_START id=943 page=2 procedure=OSCAT\n"
            "OSCAT riguarda GitLab, Sonar, Nexus e Vulnerability Assessment.\n"
            "SOURCE_END"
        )
        sheet = fact_sheet_from_guarded_context(guarded_context)
        self.assertIsNotNone(sheet)
        assert sheet is not None

        result = validate_guarded_answer(
            answer=(
                "La gara SCT riguarda il Sistema Cloud Toscana, con criticita' su CCTT, "
                "RTPC, qualificazione ACN e tempi di 180 giorni e 270 giorni. Le fonti "
                "recuperate collegano anche OSCAT a GitLab, Sonar e Nexus."
            ),
            fact_sheet=sheet,
            guarded=True,
            allowed_procedure_labels=source_procedure_labels_from_guarded_context(guarded_context),
        )

        self.assertEqual(result.status, "PASS")

    def test_money_regex_does_not_extract_substring_from_long_amount(self) -> None:
        sheet = build_fact_sheet(
            [
                {
                    "text": (
                        "OSCAT usa GitLab. Procedura 012942/2025. "
                        "Valore globale stimato comprensivo di opzioni pari a "
                        "11.172.582,96 euro."
                    ),
                    "metadata": {"chunk_index": 7},
                }
            ],
            query="descrivimi la gara OSCAT",
        )

        self.assertEqual(sheet.amounts, ("11.172.582,96 euro",))
        self.assertNotIn("582,96 euro", sheet.amounts)

    def test_month_regex_ignores_digit_or_slash_prefixed_substrings(self) -> None:
        sheet = build_fact_sheet(
            [
                {
                    "text": (
                        "OSCAT usa GitLab. Procedura 012942/2025. "
                        "Durata 48 mesi prorogabile fino a 60 mesi. "
                        "Riferimento opzione 48/12 mesi."
                    ),
                    "metadata": {"chunk_index": 7},
                }
            ],
            query="descrivimi la gara OSCAT",
        )

        self.assertIn("48 mesi", sheet.durations)
        self.assertIn("60 mesi", sheet.durations)
        self.assertNotIn("12 mesi", sheet.durations)

    def test_classify_guardrail_failures_separates_critical_and_soft(self) -> None:
        from app.rag.procedure_guardrails import classify_guardrail_failures

        critical, soft = classify_guardrail_failures(
            (
                "unverified_amount:582,96 EUR",
                "fact_sheet_conflict",
                "false_missing_duration",
                "cross_procedure_mixing",
                "unverified_duration:12 mesi",
            )
        )

        self.assertIn("fact_sheet_conflict", critical)
        self.assertIn("cross_procedure_mixing", critical)
        self.assertIn("unverified_amount:582,96 EUR", soft)
        self.assertIn("false_missing_duration", soft)
        self.assertIn("unverified_duration:12 mesi", soft)

    def test_fact_sheet_missing_critical_slots_flags_incomplete_oscat(self) -> None:
        from app.rag.procedure_guardrails import fact_sheet_missing_critical_slots

        sheet = build_fact_sheet(
            [
                {
                    "text": (
                        "OSCAT usa GitLab. Procedura 012942/2025. "
                        "Spese accessorie 582,96 euro."
                    ),
                    "metadata": {"chunk_index": 7},
                }
            ],
            query="descrivimi la gara OSCAT",
        )

        missing = fact_sheet_missing_critical_slots(sheet)

        self.assertIn("duration", missing)
        self.assertIn("major_amount", missing)
        self.assertNotIn("procedure_id", missing)

    def test_money_replacement_dedups_canonical_duplicates(self) -> None:
        sheet = build_fact_sheet(
            [
                {
                    "text": (
                        "OSCAT usa GitLab. Procedura 012942/2025. "
                        "Valore globale 11.172.582,96 euro pari a "
                        "€ 11.172.582,96 totali."
                    ),
                    "metadata": {"chunk_index": 7},
                }
            ],
            query="descrivimi la gara OSCAT",
        )

        repaired = repair_unsupported_protected_facts(
            "Il valore della gara e di 999.999,99 euro.",
            sheet,
        )

        self.assertNotIn("999.999,99", repaired)
        self.assertEqual(repaired.count("11.172.582,96"), 1)

    def test_money_replacement_picks_closest_verified_amount(self) -> None:
        sheet = build_fact_sheet(
            [
                {
                    "text": (
                        "OSCAT usa GitLab. Procedura 012942/2025. "
                        "Importo a base di gara pari a 5.999.723,60 euro. "
                        "Valore globale stimato pari a 11.172.582,96 euro. "
                        "Proroga massima 1.573.025,20 euro."
                    ),
                    "metadata": {"chunk_index": 11},
                }
            ],
            query="descrivimi la gara OSCAT",
        )

        repaired = repair_unsupported_protected_facts(
            (
                "L'importo a base di gara e pari a 6.500.000,00 euro mentre "
                "il valore globale stimato raggiunge 11.500.000,00 euro."
            ),
            sheet,
        )

        # Each placeholder amount is replaced with the closest verified value,
        # not with a cluster of all amounts joined by " e ".
        self.assertIn("5.999.723,60", repaired)
        self.assertIn("11.172.582,96", repaired)
        self.assertNotIn("5.999.723,60 euro, 11.172.582,96 euro e 1.573.025,20", repaired)
        self.assertNotIn("6.500.000,00", repaired)
        self.assertNotIn("11.500.000,00", repaired)

    def test_repair_replaces_inline_unverified_procedure_id(self) -> None:
        sheet = build_fact_sheet(
            [
                {
                    "text": (
                        "OSCAT usa GitLab. Procedura 012942/2025. CIG B33988ECF0."
                    ),
                    "metadata": {"chunk_index": 11},
                }
            ],
            query="descrivimi la gara OSCAT",
        )

        repaired = repair_unsupported_protected_facts(
            (
                "La procedura identificata con il numero ID procedura non verificato "
                "denominata OSCAT prevede CI/CD."
            ),
            sheet,
        )

        self.assertNotIn("ID procedura non verificato", repaired)
        self.assertIn("ID procedura 012942/2025", repaired)

    def test_repair_inline_unverified_procedure_id_no_op_on_conflict(self) -> None:
        sheet = build_fact_sheet(
            [
                {
                    "text": "OSCAT usa GitLab. Procedura 012942/2025. CIG B11111111.",
                    "metadata": {"chunk_index": 11},
                },
                {
                    "text": "OSCAT usa GitLab. Procedura 999999/2024. CIG B22222222.",
                    "metadata": {"chunk_index": 12},
                },
            ],
            query="descrivimi la gara OSCAT",
        )

        repaired = repair_unsupported_protected_facts(
            "La procedura riporta ID procedura non verificato.",
            sheet,
        )

        # Two distinct procedure_ids: cannot safely pick one inline.
        self.assertIn("ID procedura non verificato", repaired)

    def test_filter_long_form_amounts_drops_sub_threshold_values(self) -> None:
        from app.rag.procedure_guardrails import filter_long_form_amounts

        sheet = build_fact_sheet(
            [
                {
                    "text": (
                        "OSCAT usa GitLab. Procedura 012942/2025. "
                        "Spese accessorie 582,96 euro e tariffa 1.000,00 euro. "
                        "Importo a base di gara 5.999.723,60 euro. "
                        "Valore globale stimato 11.172.582,96 euro."
                    ),
                    "metadata": {"chunk_index": 11},
                }
            ],
            query="descrivimi la gara OSCAT",
        )

        filtered = filter_long_form_amounts(sheet)

        joined = ", ".join(filtered.amounts)
        self.assertIn("5.999.723,60", joined)
        self.assertIn("11.172.582,96", joined)
        self.assertNotIn("582,96 euro", filtered.amounts)
        self.assertNotIn("1.000,00 euro", filtered.amounts)

    def test_filter_long_form_amounts_falls_back_when_all_below_threshold(self) -> None:
        from app.rag.procedure_guardrails import filter_long_form_amounts

        sheet = build_fact_sheet(
            [
                {
                    "text": (
                        "OSCAT usa GitLab. Procedura 012942/2025. "
                        "Tariffa amministrativa 100,00 euro e marca da bollo 16,00 euro."
                    ),
                    "metadata": {"chunk_index": 11},
                }
            ],
            query="descrivimi la gara OSCAT",
        )

        filtered = filter_long_form_amounts(sheet)

        # No amount clears the threshold: leave the original list intact so we
        # still surface what the corpus offers rather than wiping the field.
        self.assertEqual(filtered.amounts, sheet.amounts)

    def test_semantic_duplicate_garanzie_paragraphs_are_collapsed(self) -> None:
        from app.rag.procedure_guardrails import _drop_semantically_duplicate_paragraphs

        answer = (
            "**Garanzie e Svincoli** Il regime delle garanzie prevede che la "
            "garanzia definitiva sia svincolata solo al termine di ogni rapporto. "
            "Il garante puo essere liberato dal vincolo solo con consenso "
            "scritto. La stazione appaltante puo procedere all'escussione.\n\n"
            "**Garanzie e Responsabilita Contrattuali** La disciplina "
            "contrattuale prevede una garanzia definitiva che verra svincolata "
            "al termine di ogni rapporto. Il garante puo essere liberato solo "
            "tramite consenso espresso. L'escussione e prevista in caso di "
            "inadempimento e la cauzione resta vincolata fino allo svincolo "
            "completo della fideiussoria.\n\n"
            "**Sezione neutra** Questa sezione descrive aspetti tecnici "
            "neutri e non ha nulla a che vedere con le garanzie."
        )

        deduped = _drop_semantically_duplicate_paragraphs(answer)

        self.assertEqual(deduped.count("Garanzie"), 1)
        self.assertIn("Sezione neutra", deduped)
        self.assertIn("fideiussoria", deduped)

    def test_oscat_sct_contamination_regex_catches_extended_keywords(self) -> None:
        from app.rag.engine import OSCAT_SCT_CONTAMINATION_RE

        positives = [
            "Adeguamento data center TIX-SCT alla determina ACN n. 21",
            "Istituzione del CSIRT Regionale",
            "Settore Sanita Digitale e Innovazione",
            "PNRR Missione 1 Componente 1",
            "Coordinamento con ESTAR",
        ]
        for text in positives:
            self.assertIsNotNone(
                OSCAT_SCT_CONTAMINATION_RE.search(text),
                msg=f"contamination regex missed: {text!r}",
            )

        self.assertIsNone(
            OSCAT_SCT_CONTAMINATION_RE.search(
                "OSCAT usa GitLab, Sonar, Nexus per CI/CD."
            )
        )

    def test_longform_template_forbids_civil_code_article_hallucination(self) -> None:
        from app.rag.generator import PROMPT_TEMPLATES

        template = PROMPT_TEMPLATES["tender_longform_synthesis"]

        self.assertIn("articoli del codice civile", template)
        self.assertIn("citazione esatta non compare nelle fonti", template)

    def test_repair_strips_malformed_civil_code_article_references(self) -> None:
        sheet = build_fact_sheet(
            [
                {
                    "text": "OSCAT usa GitLab. Procedura 012942/2025.",
                    "metadata": {"chunk_index": 11},
                }
            ],
            query="descrivimi la gara OSCAT",
        )

        answer = (
            "Risoluzione espressa ai sensi dell'art. 14C56 del codice civile "
            "oppure secondo l'articolo 14456 c.c.; resta valido l'art. 1456 "
            "del codice civile come riferimento corretto."
        )
        repaired = repair_unsupported_protected_facts(answer, sheet)

        self.assertNotIn("14C56", repaired)
        self.assertNotIn("14456", repaired)
        self.assertIn("articolo non verificato", repaired)
        # Real civil code article numbers (≤4 digits, no embedded letters) are
        # preserved.
        self.assertIn("art. 1456", repaired)

    def test_repair_collapses_unverified_duration_range(self) -> None:
        sheet = build_fact_sheet(
            [
                {
                    "text": (
                        "OSCAT usa GitLab. Procedura 012942/2025. "
                        "Durata principale 48 mesi."
                    ),
                    "metadata": {"chunk_index": 11},
                }
            ],
            query="descrivimi la gara OSCAT",
        )

        repaired = repair_unsupported_protected_facts(
            "La durata complessiva del rapporto contrattuale puo variare tra i 12 e i 60 mesi.",
            sheet,
        )

        self.assertNotIn("tra i 12 e i 60 mesi", repaired)
        self.assertNotIn("tra 12 e 60 mesi", repaired)
        self.assertIn("durata non verificata", repaired)

    def test_repair_keeps_duration_range_when_both_endpoints_verified(self) -> None:
        sheet = build_fact_sheet(
            [
                {
                    "text": (
                        "OSCAT usa GitLab. Procedura 012942/2025. "
                        "Fase transitoria 12 mesi e opzioni 60 mesi."
                    ),
                    "metadata": {"chunk_index": 11},
                }
            ],
            query="descrivimi la gara OSCAT",
        )

        repaired = repair_unsupported_protected_facts(
            "La durata varia tra 12 e 60 mesi a seconda delle opzioni.",
            sheet,
        )

        self.assertIn("tra 12 e 60 mesi", repaired)

    def test_dedup_repeated_money_clusters(self) -> None:
        sheet = build_fact_sheet(
            [
                {
                    "text": (
                        "OSCAT usa GitLab. Procedura 012942/2025. "
                        "Importo a base di gara 5.999.723,60 euro. "
                        "Valore globale stimato 11.172.582,96 euro. "
                        "Proroga massima 1.573.025,20 euro."
                    ),
                    "metadata": {"chunk_index": 11},
                }
            ],
            query="descrivimi la gara OSCAT",
        )
        answer = (
            "La fact sheet riporta valori di € 5.999.723,60, € 1.573.025,20 e "
            "Euro 1.000,00 ricorrenti, € 5.999.723,60, € 1.573.025,20 e Euro "
            "1.000,00 di nuovo, mentre € 5.999.723,60, € 1.573.025,20 e Euro "
            "1.000,00 chiudono la sezione."
        )

        repaired = repair_unsupported_protected_facts(answer, sheet)

        self.assertLessEqual(repaired.count("5.999.723,60"), 2)

    def test_repair_strips_corrupt_money_artifacts(self) -> None:
        sheet = build_fact_sheet(
            [
                {
                    "text": (
                        "OSCAT usa GitLab. Procedura 012942/2025. "
                        "Importo a base di gara 5.999.723,60 euro. "
                        "Proroga massima 1.573.025,20 euro."
                    ),
                    "metadata": {"chunk_index": 11},
                }
            ],
            query="descrivimi la gara OSCAT",
        )
        answer = (
            "Quota indicata di € 1.573.025,20.0//25,20 oppure "
            "€ 1.573.025,20.0_25,20 nelle altre tabelle."
        )

        repaired = repair_unsupported_protected_facts(answer, sheet)

        self.assertNotIn("//", repaired)
        self.assertNotIn("_25,20", repaired)
        self.assertNotIn("1.573.025,20.0", repaired)

    def test_repair_normalizes_civil_article_thousand_separator(self) -> None:
        sheet = build_fact_sheet(
            [
                {
                    "text": "OSCAT usa GitLab. Procedura 012942/2025.",
                    "metadata": {"chunk_index": 11},
                }
            ],
            query="descrivimi la gara OSCAT",
        )

        repaired = repair_unsupported_protected_facts(
            "Risoluzione espressa ai sensi dell'art. 1.456 del codice civile.",
            sheet,
        )

        self.assertNotIn("art. 1.456", repaired)
        self.assertIn("art. 1456", repaired)

    def test_repair_money_range_narrative_when_distinct_amounts(self) -> None:
        sheet = build_fact_sheet(
            [
                {
                    "text": (
                        "OSCAT usa GitLab. Procedura 012942/2025. "
                        "Importo a base di gara 5.999.723,60 euro. "
                        "Proroga massima 1.573.025,20 euro."
                    ),
                    "metadata": {"chunk_index": 11},
                }
            ],
            query="descrivimi la gara OSCAT",
        )
        answer = (
            "L'importo complessivo associato alla procedura oscilla tra "
            "€ 1.573.025,20 e € 5.999.723,60 a seconda dell'opzione."
        )

        repaired = repair_unsupported_protected_facts(answer, sheet)

        self.assertNotIn("oscilla tra", repaired.lower())
        self.assertIn("valori distinti", repaired.lower())
        self.assertIn("1.573.025,20", repaired)
        self.assertIn("5.999.723,60", repaired)

    def test_false_missing_locations_is_detected(self) -> None:
        sheet = build_fact_sheet(
            [
                {
                    "text": (
                        "OSCAT usa GitLab. Procedura 012942/2025. "
                        "Il luogo di svolgimento del servizio e' la "
                        "Regione Toscana."
                    ),
                    "metadata": {"chunk_index": 11},
                }
            ],
            query="descrivimi la gara OSCAT",
        )

        result = validate_guarded_answer(
            answer=(
                "Aspetti non coperti: non sono disponibili dettagli sui luoghi "
                "di esecuzione del servizio."
            ),
            fact_sheet=sheet,
            guarded=True,
        )

        self.assertEqual(result.status, "BLOCK")
        self.assertIn("false_missing_locations", result.failures)

    def test_repair_replaces_inline_unverified_cig_with_single_verified(self) -> None:
        sheet = build_fact_sheet(
            [
                {
                    "text": (
                        "OSCAT usa GitLab, Sonar e Nexus per pipeline CI/CD. "
                        "Capitolato richiama gara collegata con CIG B33988ECF0. "
                        "Procedura 012942/2025."
                    ),
                    "metadata": {"chunk_index": 11},
                }
            ],
            query="descrivimi la gara OSCAT",
        )

        repaired = repair_unsupported_protected_facts(
            "La procedura collegata e identificata dal CIG non verificato.",
            sheet,
        )

        self.assertNotIn("CIG non verificato", repaired)
        self.assertIn("CIG B33988ECF0", repaired)

    def test_repair_inline_unverified_cig_no_op_on_conflict(self) -> None:
        sheet = build_fact_sheet(
            [
                {
                    "text": (
                        "OSCAT usa GitLab e Sonar. CIG B33988ECF0. Procedura 012942/2025."
                    ),
                    "metadata": {"chunk_index": 11},
                },
                {
                    "text": (
                        "OSCAT usa Nexus e DevSecOps. CIG B99999999. Procedura 012942/2025."
                    ),
                    "metadata": {"chunk_index": 12},
                },
            ],
            query="descrivimi la gara OSCAT",
        )

        repaired = repair_unsupported_protected_facts(
            "Il CIG non verificato della procedura collegata.",
            sheet,
        )

        self.assertIn("CIG non verificato", repaired)

    def test_repair_strips_contamination_sentences(self) -> None:
        sheet = build_fact_sheet(
            [
                {
                    "text": "OSCAT usa GitLab. Procedura 012942/2025.",
                    "metadata": {"chunk_index": 11},
                }
            ],
            query="descrivimi la gara OSCAT",
        )

        answer = (
            "OSCAT prevede pipeline CI/CD su GitLab e vulnerability assessment "
            "del codice sorgente. L'adeguamento del data center TIX-SCT alla "
            "determina ACN n. 21 nell'ambito del PNRR Missione 1 prevede "
            "istituzione del CSIRT Regionale ed ESTAR. La procedura 012942/2025 "
            "e gestita dal Soggetto Aggregatore."
        )

        repaired = repair_unsupported_protected_facts(answer, sheet)

        self.assertIn("GitLab", repaired)
        self.assertIn("Soggetto Aggregatore", repaired)
        self.assertNotIn("CSIRT Regionale", repaired)
        self.assertNotIn("PNRR Missione 1", repaired)
        self.assertNotIn("data center TIX-SCT", repaired)

    def test_oscat_contamination_dominance_filter_excludes_non_oscat_chunks(self) -> None:
        from app.rag.engine import HybridRAGEngine

        engine = HybridRAGEngine()
        rag_query = RAGQuery(
            text="descrivimi la gara OSCAT in 1500 parole",
            mode=QueryMode.QA,
        )
        contaminated_item = {
            "text": (
                "Adeguamento del data center TIX-SCT alla determina ACN n. 21 "
                "nell'ambito del PNRR Missione 1, con istituzione del CSIRT "
                "Regionale e coordinamento ESTAR per gli impianti industriali."
            ),
            "metadata": {"chunk_index": 17},
        }
        oscat_item = {
            "text": (
                "OSCAT usa GitLab, Sonar, Nexus per pipeline CI/CD e "
                "vulnerability assessment del codice sorgente."
            ),
            "metadata": {"chunk_index": 18},
        }

        self.assertTrue(
            engine._should_exclude_longform_context_item(contaminated_item, rag_query)
        )
        self.assertFalse(
            engine._should_exclude_longform_context_item(oscat_item, rag_query)
        )


class RagGuardrailConfigTests(unittest.TestCase):
    def test_default_config_blocks_only_tender_overviews(self) -> None:
        cfg = normalize_guardrail_config(None)

        self.assertTrue(cfg["enabled"])
        self.assertEqual(cfg["mode"], "block")
        self.assertTrue(cfg["onlyTenderOverview"])

    def test_invalid_mode_falls_back_to_block(self) -> None:
        cfg = normalize_guardrail_config({"mode": "loose"})

        self.assertEqual(cfg["mode"], "block")


class RagEngineGuardrailContextTests(unittest.IsolatedAsyncioTestCase):
    async def test_broad_tender_query_uses_guarded_tender_overview_template(self) -> None:
        engine = HybridRAGEngine()

        template_name, variables = engine._resolve_template(
            RAGQuery(
                text="descrivimi la gara OSCAT evidenzia punti critici",
                mode=QueryMode.QA,
            ),
            context="FACT_SHEET_START\nprocedura: OSCAT\nFACT_SHEET_END",
        )

        self.assertEqual(template_name, "tender_overview")
        self.assertIn("punti critici", variables["query"])

    async def test_longform_tender_query_uses_narrative_synthesis_template(self) -> None:
        engine = HybridRAGEngine()

        template_name, variables = engine._resolve_template(
            RAGQuery(
                text="descrivimi la gara OSCAT evidenzia punti critici in 1000 parole",
                mode=QueryMode.QA,
            ),
            context="FACT_SHEET_START\nprocedura: OSCAT\nFACT_SHEET_END",
        )

        self.assertEqual(template_name, "tender_longform_synthesis")
        self.assertIn("punti critici", variables["query"])

    async def test_retrieved_context_contains_fact_sheet_for_tender_overview(self) -> None:
        engine = HybridRAGEngine()
        engine.dense_retriever = SimpleNamespace(
            search=lambda **_kwargs: [
                SimpleNamespace(
                    text="OSCAT usa GitLab, Sonar, Nexus. CIG B123456789. Durata 48 mesi.",
                    score=0.91,
                    metadata={"chunk_index": 11, "page_number": 4},
                )
            ]
        )
        engine.sparse_retriever = None
        engine.graph_retriever = None
        engine.reranker = SimpleNamespace(rerank=lambda **kwargs: kwargs["results"])

        retrieved = await engine._retrieve_context_and_sources(
            RAGQuery(
                text="descrivimi la gara OSCAT evidenzia punti critici",
                mode=QueryMode.QA,
                retrievers={"dense": True, "sparse": False, "graph": False},
                planning_coverage_config={"enabled": False},
            )
        )

        self.assertIn("FACT_SHEET_START", retrieved.context)
        self.assertIn("procedura: OSCAT", retrieved.context)
        self.assertIn("CIG B123456789", retrieved.context)
        self.assertIn("48 mesi", retrieved.context)
        self.assertIn("SOURCE_START", retrieved.context)


class RagEngineFactSheetWiringTests(unittest.IsolatedAsyncioTestCase):
    """Regression coverage for the retrieval-to-context wiring contract:

    * structured tender-overview queries get a deterministic fact sheet
      and ``SOURCE_START`` envelopes with procedure metadata;
    * generic QA / SEARCH queries flow through the legacy ``<doc>`` path
      and contain no fact sheet;
    * the ``SOURCE_START`` envelope order matches the ``sources`` list
      so frontend pagination/citation indices stay aligned.
    """

    @staticmethod
    def _stub_engine(items):
        engine = HybridRAGEngine()
        engine.dense_retriever = SimpleNamespace(
            search=lambda **_kwargs: [
                SimpleNamespace(
                    text=item["text"],
                    score=item.get("score", 0.9),
                    metadata=item.get("metadata", {}),
                )
                for item in items
            ]
        )
        engine.sparse_retriever = None
        engine.graph_retriever = None
        engine.reranker = SimpleNamespace(rerank=lambda **kwargs: kwargs["results"])
        return engine

    async def test_generic_qa_does_not_inject_fact_sheet(self) -> None:
        engine = self._stub_engine(
            [
                {
                    "text": "OSCAT usa GitLab e Sonar. CIG B123456789. 48 mesi.",
                    "metadata": {"chunk_index": 4, "page_number": 2},
                }
            ]
        )
        retrieved = await engine._retrieve_context_and_sources(
            RAGQuery(
                text="qual è il CIG della gara",
                mode=QueryMode.QA,
                retrievers={"dense": True, "sparse": False, "graph": False},
                planning_coverage_config={"enabled": False},
            )
        )
        self.assertNotIn("FACT_SHEET_START", retrieved.context)
        self.assertNotIn("SOURCE_START", retrieved.context)
        # Standard QA path uses <doc> envelopes.
        self.assertIn("<doc", retrieved.context)
        self.assertEqual(len(retrieved.sources), 1)

    async def test_search_mode_does_not_inject_fact_sheet(self) -> None:
        engine = self._stub_engine(
            [
                {
                    "text": "OSCAT usa GitLab. CIG B123456789. 48 mesi.",
                    "metadata": {"chunk_index": 5, "page_number": 1},
                }
            ]
        )
        retrieved = await engine._retrieve_context_and_sources(
            RAGQuery(
                text="descrivimi la gara OSCAT evidenzia punti critici",
                mode=QueryMode.SEARCH,
                retrievers={"dense": True, "sparse": False, "graph": False},
                planning_coverage_config={"enabled": False},
            )
        )
        self.assertNotIn("FACT_SHEET_START", retrieved.context)
        self.assertNotIn("SOURCE_START", retrieved.context)

    async def test_disabled_guardrail_config_falls_back_to_legacy_envelopes(self) -> None:
        engine = self._stub_engine(
            [
                {
                    "text": "OSCAT usa GitLab. CIG B123456789. 48 mesi.",
                    "metadata": {"chunk_index": 6, "page_number": 1},
                }
            ]
        )
        retrieved = await engine._retrieve_context_and_sources(
            RAGQuery(
                text="descrivimi la gara OSCAT evidenzia punti critici",
                mode=QueryMode.QA,
                retrievers={"dense": True, "sparse": False, "graph": False},
                planning_coverage_config={"enabled": False},
                guardrail_config={"enabled": False},
            )
        )
        self.assertNotIn("FACT_SHEET_START", retrieved.context)

    async def test_guarded_sources_carry_procedure_metadata(self) -> None:
        engine = self._stub_engine(
            [
                {
                    "text": "OSCAT usa GitLab, Sonar, Nexus. CIG B123456789. 48 mesi.",
                    "metadata": {"chunk_index": 11, "page_number": 4},
                },
                {
                    "text": "Dettaglio aggiuntivo OSCAT con DevSecOps e DPA.",
                    "metadata": {"chunk_index": 12, "page_number": 5},
                },
            ]
        )
        retrieved = await engine._retrieve_context_and_sources(
            RAGQuery(
                text="descrivimi la gara OSCAT evidenzia punti critici",
                mode=QueryMode.QA,
                retrievers={"dense": True, "sparse": False, "graph": False},
                planning_coverage_config={"enabled": False},
            )
        )
        # Each source must surface the per-chunk procedure label and
        # the fact-sheet-level label/status so downstream observability
        # and the frontend can reason about provenance.
        for source in retrieved.sources:
            metadata = source["metadata"]
            self.assertEqual(metadata["procedure_label"], "OSCAT")
            self.assertEqual(metadata["fact_sheet_procedure_label"], "OSCAT")
            self.assertEqual(metadata["fact_sheet_status"], FactStatus.VERIFIED.value)

    async def test_source_envelope_order_matches_sources_list(self) -> None:
        engine = self._stub_engine(
            [
                {
                    "text": "OSCAT chunk uno con CIG B123456789.",
                    "metadata": {"chunk_index": 100, "page_number": 1},
                },
                {
                    "text": "OSCAT chunk due, GitLab Sonar, 48 mesi.",
                    "metadata": {"chunk_index": 200, "page_number": 2},
                },
                {
                    "text": "OSCAT chunk tre, Vulnerability Assessment SME MAM STS.",
                    "metadata": {"chunk_index": 300, "page_number": 3},
                },
            ]
        )
        retrieved = await engine._retrieve_context_and_sources(
            RAGQuery(
                text="descrivimi la gara OSCAT evidenzia punti critici",
                mode=QueryMode.QA,
                retrievers={"dense": True, "sparse": False, "graph": False},
                planning_coverage_config={"enabled": False},
            )
        )
        envelope_chunk_ids = [
            int(match) for match in re.findall(r"SOURCE_START id=(\d+)", retrieved.context)
        ]
        sources_chunk_ids = [source["metadata"]["chunk_index"] for source in retrieved.sources]
        self.assertEqual(envelope_chunk_ids, sources_chunk_ids)
        # Procedure tag in envelope must agree with the per-source metadata.
        envelope_procedures = re.findall(
            r"SOURCE_START id=\d+ page=\d+ procedure=(\S+)",
            retrieved.context,
        )
        self.assertEqual(
            envelope_procedures,
            [source["metadata"]["procedure_label"] for source in retrieved.sources],
        )

    async def test_fact_sheet_conflict_survives_context_deduplication(self) -> None:
        shared = (
            "OSCAT usa GitLab, Sonar, Nexus per servizi DevSecOps, DPA, GPA, "
            "GVA, SME, MAM e STS con perimetro tecnico identico. "
        )
        engine = self._stub_engine(
            [
                {
                    "text": f"{shared} CIG B123456789. Durata 48 mesi.",
                    "score": 0.9,
                    "metadata": {"chunk_index": 21, "page_number": 2},
                },
                {
                    "text": f"{shared} CIG C987654321. Durata 48 mesi.",
                    "score": 0.8,
                    "metadata": {"chunk_index": 22, "page_number": 3},
                },
            ]
        )

        retrieved = await engine._retrieve_context_and_sources(
            RAGQuery(
                text="descrivimi la gara OSCAT evidenzia punti critici",
                mode=QueryMode.QA,
                retrievers={"dense": True, "sparse": False, "graph": False},
                planning_coverage_config={"enabled": False},
            )
        )

        self.assertIn("stato_verifica: conflitto", retrieved.context)
        self.assertIn("conflitti: cig", retrieved.context)
        fact_sheet_body = re.search(
            r"FACT_SHEET_START\n(?P<body>.*?)\nFACT_SHEET_END",
            retrieved.context,
            re.DOTALL,
        )
        self.assertIsNotNone(fact_sheet_body)
        assert fact_sheet_body is not None
        self.assertIn("cig: conflitto_rilevato", fact_sheet_body.group("body"))
        self.assertNotIn("CIG B123456789", fact_sheet_body.group("body"))
        self.assertEqual(len(retrieved.sources), 1)


class RagEngineGuardrailValidationTests(unittest.IsolatedAsyncioTestCase):
    def test_blocked_fallback_masks_conflicted_protected_fields(self) -> None:
        engine = HybridRAGEngine()

        answer = engine._build_guardrail_blocked_answer(
            FactSheet(
                procedure_label="OSCAT",
                cigs=("B123456789", "C987654321"),
                conflicts=("cig",),
                status=FactStatus.CONFLICT,
            )
        )

        self.assertIn("CIG: conflitto rilevato", answer)
        self.assertNotIn("CIG B123456789", answer)
        self.assertNotIn("CIG C987654321", answer)

    def test_engine_allows_source_supported_oscat_sct_answer(self) -> None:
        engine = HybridRAGEngine()
        context = (
            "FACT_SHEET_START\n"
            "procedura: SCT\n"
            "stato_verifica: verificato\n"
            "procedure_id: non_rilevato\n"
            "cig: non_rilevato\n"
            "giorni_critici: 180 giorni, 270 giorni\n"
            "durata: non_rilevato\n"
            "importi: non_rilevato\n"
            "sedi_luoghi: non_rilevato\n"
            "percentuali: non_rilevato\n"
            "fonti: chunk:1200, chunk:943\n"
            "conflitti: nessuno\n"
            "FACT_SHEET_END\n"
            "SOURCE_START id=1200 page=1 procedure=SCT\n"
            "SCT prevede CCTT, RTPC, qualificazione ACN e fase transitoria.\n"
            "SOURCE_END\n"
            "SOURCE_START id=943 page=2 procedure=OSCAT\n"
            "OSCAT riguarda GitLab, Sonar, Nexus e Vulnerability Assessment.\n"
            "SOURCE_END"
        )
        answer = (
            "La gara SCT riguarda il Sistema Cloud Toscana, CCTT, RTPC e "
            "qualificazione ACN. Le fonti recuperate collegano anche OSCAT a "
            "GitLab, Sonar e Nexus."
        )

        guarded = engine._apply_generation_guardrails(
            RAGQuery(
                text="descrivimi la gara della regione toscana evidenzia i punti critici",
                mode=QueryMode.QA,
            ),
            context=context,
            answer=answer,
        )

        self.assertEqual(guarded, answer)

    def test_procedure_id_conflict_does_not_block_technical_overview_without_ids(self) -> None:
        engine = HybridRAGEngine()
        context = (
            "FACT_SHEET_START\n"
            "procedura: OSCAT\n"
            "stato_verifica: conflitto\n"
            "procedure_id: 012942/2025, 099999/2025\n"
            "cig: CIG B33988ECF0\n"
            "giorni_critici: 30 giorni\n"
            "durata: 9 mesi, 6 anni, 2 mesi\n"
            "importi: non_rilevato\n"
            "sedi_luoghi: non_rilevato\n"
            "percentuali: non_rilevato\n"
            "fonti: chunk:223, chunk:248\n"
            "conflitti: procedure_id\n"
            "FACT_SHEET_END\n"
            "SOURCE_START id=223 page=1 procedure=OSCAT\n"
            "OSCAT riguarda GitLab, Sonar, Nexus e Vulnerability Assessment.\n"
            "SOURCE_END\n"
            "SOURCE_START id=248 page=2 procedure=OSCAT\n"
            "Sono richiesti coordinamento gestionale, governance e presidio operativo.\n"
            "SOURCE_END"
        )
        answer = (
            "Gli aspetti tecnici piu difficili riguardano GitLab, Sonar, Nexus e "
            "Vulnerability Assessment. Gli aspetti gestionali richiedono governance, "
            "coordinamento operativo e presidio continuativo."
        )

        guarded = engine._apply_generation_guardrails(
            RAGQuery(
                text=(
                    "analizza la gara della regione toscana descrivi tutti gli aspetti "
                    "tecnici e gestionali in ordine di difficolta in 1000 parole"
                ),
                mode=QueryMode.QA,
            ),
            context=context,
            answer=answer,
        )

        self.assertEqual(guarded, answer)

    def test_guardrail_repairs_conflicted_ids_and_unverified_days_instead_of_blocking(
        self,
    ) -> None:
        engine = HybridRAGEngine()
        context = (
            "FACT_SHEET_START\n"
            "procedura: OSCAT\n"
            "stato_verifica: conflitto\n"
            "procedure_id: 012942/2025, 099999/2025\n"
            "cig: CIG B33988ECF0\n"
            "giorni_critici: 30 giorni\n"
            "durata: 9 mesi, 6 anni, 2 mesi\n"
            "importi: non_rilevato\n"
            "sedi_luoghi: non_rilevato\n"
            "percentuali: non_rilevato\n"
            "fonti: chunk:223, chunk:248\n"
            "conflitti: procedure_id\n"
            "FACT_SHEET_END\n"
            "SOURCE_START id=223 page=1 procedure=OSCAT\n"
            "OSCAT riguarda GitLab, Sonar, Nexus e Vulnerability Assessment.\n"
            "SOURCE_END"
        )
        answer = (
            "La procedura 012942/2025 richiede GitLab, Sonar, Nexus e "
            "Vulnerability Assessment. La fase di migrazione dura 270 giorni."
        )

        guarded = engine._apply_generation_guardrails(
            RAGQuery(
                text=(
                    "analizza la gara della regione toscana descrivi tutti gli aspetti "
                    "tecnici e gestionali in ordine di difficolta in 1000 parole"
                ),
                mode=QueryMode.QA,
            ),
            context=context,
            answer=answer,
        )

        self.assertNotIn(BLOCKED_OUTPUT_MESSAGE, guarded)
        self.assertNotIn("012942/2025", guarded)
        self.assertNotIn("270 giorni", guarded)
        self.assertIn("non verificato", guarded)
        self.assertIn("GitLab", guarded)

    def test_guardrail_repairs_numeric_placeholder_instead_of_blocking(self) -> None:
        engine = HybridRAGEngine()
        context = (
            "FACT_SHEET_START\n"
            "procedura: OSCAT\n"
            "stato_verifica: verificato\n"
            "procedure_id: 012942/2025\n"
            "cig: CIG B33988ECF0\n"
            "giorni_critici: non_rilevato\n"
            "durata: 6 anni\n"
            "importi: non_rilevato\n"
            "sedi_luoghi: non_rilevato\n"
            "percentuali: non_rilevato\n"
            "fonti: chunk:223, chunk:248\n"
            "conflitti: nessuno\n"
            "FACT_SHEET_END\n"
            "SOURCE_START id=223 page=1 procedure=OSCAT\n"
            "OSCAT riguarda GitLab, Sonar, Nexus e Vulnerability Assessment.\n"
            "SOURCE_END"
        )
        answer = (
            "La gara OSCAT ha durata di 6 anni. Gli aspetti tecnici richiedono "
            "interventi entro giorni, CIG: e presidio GitLab, Sonar e Nexus."
        )

        guarded = engine._apply_generation_guardrails(
            RAGQuery(
                text=(
                    "analizza la gara della regione toscana descrivi tutti gli aspetti "
                    "tecnici e gestionali in ordine di difficolta in 1000 parole"
                ),
                mode=QueryMode.QA,
            ),
            context=context,
            answer=answer,
        )

        self.assertNotIn(BLOCKED_OUTPUT_MESSAGE, guarded)
        self.assertNotIn("entro giorni", guarded)
        self.assertNotIn("CIG:", guarded)
        self.assertIn("termine non verificato", guarded)
        # The CIG placeholder is hydrated from the single verified CIG in the
        # fact sheet, not left as "non verificato".
        self.assertIn("CIG B33988ECF0", guarded)
        self.assertIn("GitLab", guarded)

    def test_guardrail_regression_oscat_polluted_fact_sheet_preserves_narrative(self) -> None:
        engine = HybridRAGEngine()
        context = (
            "FACT_SHEET_START\n"
            "procedura: OSCAT\n"
            "stato_verifica: verificato\n"
            "procedure_id: 012942/2025\n"
            "cig: CIG B33988ECF0\n"
            "giorni_critici: non_rilevato\n"
            "durata: 12 mesi, 60 mesi\n"
            "importi: 582,96 EUR, € 5.999.723,60, € 1.573.025,20, Euro 1.000,00\n"
            "sedi_luoghi: non_rilevato\n"
            "percentuali: non_rilevato\n"
            "fonti: chunk:1, chunk:2\n"
            "conflitti: nessuno\n"
            "FACT_SHEET_END\n"
            "SOURCE_START id=1 page=1 procedure=OSCAT\n"
            "OSCAT riguarda GitLab, Sonar, Nexus e Vulnerability Assessment.\n"
            "SOURCE_END"
        )
        answer = (
            "La gara OSCAT 012942/2025 ha durata pari a 48 mesi e un valore "
            "globale stimato di 11.172.582,96 EUR. Il perimetro tecnico "
            "comprende GitLab, Sonar, Nexus e attivita di Vulnerability "
            "Assessment per il presidio DevSecOps."
        )

        guarded = engine._apply_generation_guardrails(
            RAGQuery(
                text="descrivimi la gara OSCAT in 1500 parole",
                mode=QueryMode.QA,
            ),
            context=context,
            answer=answer,
        )

        self.assertNotIn(BLOCKED_OUTPUT_MESSAGE, guarded)
        self.assertNotIn("Risposta generata scartata", guarded)
        self.assertIn("GitLab", guarded)
        self.assertIn("Vulnerability Assessment", guarded)
        self.assertIn("OSCAT 012942/2025", guarded)
        self.assertNotIn("11.172.582,96", guarded)
        self.assertNotIn("48 mesi", guarded)

    def test_guardrail_soft_warning_footer_appended_when_only_soft_failures(self) -> None:
        engine = HybridRAGEngine()
        warning_marker = "Nota:"

        cleaned = engine._append_guardrail_soft_warning("La gara OSCAT include GitLab.")
        self.assertIn(warning_marker, cleaned)
        self.assertIn("GitLab", cleaned)

        repeated = engine._append_guardrail_soft_warning(cleaned)
        self.assertEqual(repeated.count(warning_marker), 1)

        empty = engine._append_guardrail_soft_warning("")
        self.assertIn(warning_marker, empty)

    async def test_query_repairs_answer_with_unverified_number_after_generation(self) -> None:
        engine = HybridRAGEngine()
        engine.ensure_initialized = AsyncMock()
        engine._retrieve_context_and_sources = AsyncMock(
            return_value=SimpleNamespace(
                context=(
                    "FACT_SHEET_START\n"
                    "procedura: OSCAT\n"
                    "stato_verifica: verificato\n"
                    "procedure_id: non_rilevato\n"
                    "cig: CIG B123456789\n"
                    "giorni_critici: non_rilevato\n"
                    "durata: 48 mesi\n"
                    "importi: non_rilevato\n"
                    "sedi_luoghi: non_rilevato\n"
                    "percentuali: non_rilevato\n"
                    "fonti: chunk:1\n"
                    "conflitti: nessuno\n"
                    "FACT_SHEET_END\n"
                    "SOURCE_START id=1 page=1 procedure=OSCAT\n"
                    "OSCAT usa GitLab. CIG B123456789. Durata 48 mesi.\n"
                    "SOURCE_END"
                ),
                sources=[],
            )
        )
        engine._prepare_generation_route = AsyncMock(
            return_value=(
                SimpleNamespace(provider="llama"),
                {"context": "", "query": "descrivimi la gara OSCAT"},
                LLMRoute.INTERNAL,
                False,
                None,
                False,
            )
        )
        engine._extend_answer_if_needed = AsyncMock(
            side_effect=lambda _rag_query, **kwargs: kwargs["generation_result"]
        )
        engine._complete_trailing_sentence_if_needed = AsyncMock(return_value=None)
        engine._generate = AsyncMock(
            return_value=GenerationResult(
                text="La gara OSCAT dura 48 mesi e include una fase da 270 giorni.",
                model="test",
                completion_tokens=20,
                template_used="tender_overview",
            )
        )

        response = await engine.query(
            RAGQuery(
                text="descrivimi la gara OSCAT evidenzia punti critici",
                mode=QueryMode.QA,
            )
        )

        self.assertNotIn(BLOCKED_OUTPUT_MESSAGE, response.answer)
        self.assertIn("48 mesi", response.answer)
        self.assertNotIn("270 giorni", response.answer)
        self.assertIn("giorni non verificati", response.answer)
        self.assertIn("48 mesi", response.answer)
        self.assertNotIn("270 giorni", response.answer)


class RagEngineLiveValidationTests(unittest.IsolatedAsyncioTestCase):
    """Pipeline-level coverage of the post-generation guardrail.

    The deterministic validator is exercised directly elsewhere; these
    tests prove that ``engine.query`` actually wires it after generation
    for the four failure modes that must produce the canonical blocked
    fallback: factsheet conflict, cross-procedure mixing, severe
    duplicate paragraphs, and the procedure_id conflict variant of the
    fallback masking guarantee.
    """

    @staticmethod
    def _stub_pipeline(*, context: str, generated: str) -> HybridRAGEngine:
        engine = HybridRAGEngine()
        engine.ensure_initialized = AsyncMock()
        engine._retrieve_context_and_sources = AsyncMock(
            return_value=SimpleNamespace(context=context, sources=[])
        )
        engine._prepare_generation_route = AsyncMock(
            return_value=(
                SimpleNamespace(provider="llama"),
                {"context": "", "query": "x"},
                LLMRoute.INTERNAL,
                False,
                None,
                False,
            )
        )
        engine._extend_answer_if_needed = AsyncMock(
            side_effect=lambda _rag_query, **kwargs: kwargs["generation_result"]
        )
        engine._complete_trailing_sentence_if_needed = AsyncMock(return_value=None)
        engine._generate = AsyncMock(
            return_value=GenerationResult(
                text=generated,
                model="test",
                completion_tokens=20,
                template_used="tender_overview",
            )
        )
        return engine

    async def test_factsheet_conflict_repairs_answer_and_masks_protected_values(self) -> None:
        context = (
            "FACT_SHEET_START\n"
            "procedura: OSCAT\n"
            "stato_verifica: conflitto\n"
            "procedure_id: non_rilevato\n"
            "cig: CIG B123456789, CIG C987654321\n"
            "giorni_critici: non_rilevato\n"
            "durata: non_rilevato\n"
            "importi: non_rilevato\n"
            "sedi_luoghi: non_rilevato\n"
            "percentuali: non_rilevato\n"
            "fonti: chunk:1, chunk:2\n"
            "conflitti: cig\n"
            "FACT_SHEET_END\n"
            "SOURCE_START id=1 page=1 procedure=OSCAT\n"
            "OSCAT con CIG B123456789.\nSOURCE_END\n"
            "SOURCE_START id=2 page=2 procedure=OSCAT\n"
            "OSCAT con CIG C987654321.\nSOURCE_END"
        )
        engine = self._stub_pipeline(
            context=context,
            generated="La gara OSCAT ha CIG B123456789.",
        )
        response = await engine.query(
            RAGQuery(
                text="descrivimi la gara OSCAT evidenzia i punti critici",
                mode=QueryMode.QA,
            )
        )
        self.assertNotIn(BLOCKED_OUTPUT_MESSAGE, response.answer)
        self.assertIn("CIG non verificato", response.answer)
        # Conflicting raw values must NEVER reach the user surface.
        self.assertNotIn("CIG B123456789", response.answer)
        self.assertNotIn("CIG C987654321", response.answer)

    async def test_cross_procedure_mixing_without_user_request_is_blocked(self) -> None:
        context = (
            "FACT_SHEET_START\n"
            "procedura: OSCAT\n"
            "stato_verifica: verificato\n"
            "procedure_id: non_rilevato\n"
            "cig: CIG B123456789\n"
            "giorni_critici: non_rilevato\n"
            "durata: 48 mesi\n"
            "importi: non_rilevato\n"
            "sedi_luoghi: non_rilevato\n"
            "percentuali: non_rilevato\n"
            "fonti: chunk:1\n"
            "conflitti: nessuno\n"
            "FACT_SHEET_END\n"
            "SOURCE_START id=1 page=1 procedure=OSCAT\n"
            "OSCAT usa GitLab, Sonar, Nexus, Vulnerability Assessment.\n"
            "SOURCE_END"
        )
        engine = self._stub_pipeline(
            context=context,
            generated=(
                "OSCAT usa GitLab e Sonar. SCT richiede RTPC, qualificazione "
                "ACN e fase transitoria."
            ),
        )
        response = await engine.query(
            RAGQuery(
                text="descrivimi la gara OSCAT evidenzia punti critici",
                mode=QueryMode.QA,
            )
        )
        self.assertIn(BLOCKED_OUTPUT_MESSAGE, response.answer)
        # Verified-facts fallback summary stays grounded in OSCAT only.
        self.assertIn("Procedura: OSCAT", response.answer)
        self.assertIn("CIG B123456789", response.answer)
        # Cross-procedure tokens that triggered the block must not leak
        # back through the fallback.
        self.assertNotIn("RTPC", response.answer)
        self.assertNotIn("qualificazione ACN", response.answer)

    async def test_severe_duplicate_paragraph_is_collapsed_by_repair(self) -> None:
        context = (
            "FACT_SHEET_START\n"
            "procedura: OSCAT\n"
            "stato_verifica: verificato\n"
            "procedure_id: non_rilevato\n"
            "cig: CIG B123456789\n"
            "giorni_critici: non_rilevato\n"
            "durata: 48 mesi\n"
            "importi: non_rilevato\n"
            "sedi_luoghi: non_rilevato\n"
            "percentuali: non_rilevato\n"
            "fonti: chunk:1\n"
            "conflitti: nessuno\n"
            "FACT_SHEET_END\n"
            "SOURCE_START id=1 page=1 procedure=OSCAT\n"
            "OSCAT usa GitLab. CIG B123456789. Durata 48 mesi.\n"
            "SOURCE_END"
        )
        # ≥80 chars per block, two identical blocks. The semantic dedup repair
        # collapses them rather than blocking the entire answer.
        repeated_block = (
            "La gara OSCAT è strutturata su servizi DevSecOps con CIG "
            "B123456789 e durata complessiva di 48 mesi."
        )
        engine = self._stub_pipeline(
            context=context,
            generated=f"{repeated_block}\n\n{repeated_block}",
        )
        response = await engine.query(
            RAGQuery(
                text="descrivimi la gara OSCAT evidenzia punti critici",
                mode=QueryMode.QA,
            )
        )
        self.assertNotIn(BLOCKED_OUTPUT_MESSAGE, response.answer)
        self.assertEqual(response.answer.count("DevSecOps"), 1)
        self.assertIn("CIG B123456789", response.answer)

    async def test_blocked_fallback_masks_procedure_id_conflict(self) -> None:
        engine = HybridRAGEngine()
        answer = engine._build_guardrail_blocked_answer(
            FactSheet(
                procedure_label="OSCAT",
                procedure_ids=("012942/2025", "099999/2025"),
                conflicts=("procedure_id",),
                status=FactStatus.CONFLICT,
            )
        )
        self.assertIn("ID procedura: conflitto rilevato", answer)
        self.assertNotIn("012942/2025", answer)
        self.assertNotIn("099999/2025", answer)

    async def test_pass_through_keeps_clean_answer_intact(self) -> None:
        # Negative regression: a clean answer that satisfies every
        # deterministic check must reach the caller unchanged.
        context = (
            "FACT_SHEET_START\n"
            "procedura: OSCAT\n"
            "stato_verifica: verificato\n"
            "procedure_id: non_rilevato\n"
            "cig: CIG B123456789\n"
            "giorni_critici: non_rilevato\n"
            "durata: 48 mesi\n"
            "importi: non_rilevato\n"
            "sedi_luoghi: non_rilevato\n"
            "percentuali: non_rilevato\n"
            "fonti: chunk:1\n"
            "conflitti: nessuno\n"
            "FACT_SHEET_END\n"
            "SOURCE_START id=1 page=1 procedure=OSCAT\n"
            "OSCAT usa GitLab. CIG B123456789. Durata 48 mesi.\n"
            "SOURCE_END"
        )
        clean_answer = (
            "La gara OSCAT prevede CIG B123456789 e durata 48 mesi sui "
            "servizi DevSecOps GitLab Sonar Nexus."
        )
        engine = self._stub_pipeline(context=context, generated=clean_answer)
        response = await engine.query(
            RAGQuery(
                text="descrivimi la gara OSCAT evidenzia punti critici",
                mode=QueryMode.QA,
            )
        )
        self.assertNotIn(BLOCKED_OUTPUT_MESSAGE, response.answer)
        self.assertIn("CIG B123456789", response.answer)
        self.assertIn("48 mesi", response.answer)

    async def test_false_missing_final_note_is_repaired_with_verified_values(self) -> None:
        context = (
            "FACT_SHEET_START\n"
            "procedura: OSCAT\n"
            "stato_verifica: verificato\n"
            "procedure_id: 012942/2025\n"
            "cig: CIG B123456789\n"
            "giorni_critici: non_rilevato\n"
            "durata: 48 mesi\n"
            "importi: 5.999.723,60 euro, 11.172.582,96 euro\n"
            "sedi_luoghi: non_rilevato\n"
            "percentuali: non_rilevato\n"
            "fonti: chunk:1\n"
            "conflitti: nessuno\n"
            "FACT_SHEET_END\n"
            "SOURCE_START id=1 page=1 procedure=OSCAT\n"
            "OSCAT usa GitLab. Procedura 012942/2025. CIG B123456789. "
            "Durata 48 mesi. Importo a base di gara pari a 5.999.723,60 euro. "
            "Valore globale stimato pari a 11.172.582,96 euro.\n"
            "SOURCE_END"
        )
        engine = self._stub_pipeline(
            context=context,
            generated=(
                "La gara OSCAT riguarda servizi DevSecOps. Aspetti non coperti: "
                "non risultano disponibili durata e importi."
            ),
        )

        response = await engine.query(
            RAGQuery(
                text="descrivimi dettagliatamente ogni aspetto della gara OSCAT in 1500 parole",
                mode=QueryMode.QA,
            )
        )

        self.assertNotIn(BLOCKED_OUTPUT_MESSAGE, response.answer)
        self.assertNotIn("non risultano disponibili durata e importi", response.answer)
        self.assertIn("durata 48 mesi", response.answer)
        self.assertIn("5.999.723,60 euro", response.answer)
        self.assertIn("11.172.582,96 euro", response.answer)


class RagGuardrailObservabilityTests(unittest.TestCase):
    def test_validation_result_exposes_failure_codes_for_logging(self) -> None:
        sheet = build_fact_sheet(
            [{"text": "OSCAT con CIG B123456789.", "metadata": {}}],
            query="OSCAT",
        )

        result = validate_guarded_answer(
            answer="OSCAT con CIG B123456789 e fase da 270 giorni.",
            fact_sheet=sheet,
            guarded=True,
        )

        self.assertEqual(result.status, "BLOCK")
        self.assertIn("unverified_number:270", result.failures)


class RagGuardrailBranchCoverageTests(unittest.TestCase):
    """Regression coverage for branches that other tests do not exercise.

    These guard the deterministic guardrail layer against silent
    regressions when the runtime config is permissive (``guarded=False``
    or ``enabled=False``), when the conflict detector hits a procedure
    id rather than a CIG, when the operator opts into ``audit`` mode and
    expects the answer to flow through unmodified, and when an answer
    contains a numeric placeholder.
    """

    _FACT_SHEET = FactSheet(procedure_label="OSCAT")

    def test_guarded_false_short_circuits_to_pass(self) -> None:
        result = validate_guarded_answer(
            answer="qualunque cosa: 270 giorni, CIG INVENTATO.",
            fact_sheet=self._FACT_SHEET,
            guarded=False,
        )
        self.assertEqual(result.status, "PASS")
        self.assertEqual(result.failures, ())

    def test_disabled_config_short_circuits_to_pass_even_when_guarded(self) -> None:
        result = validate_guarded_answer(
            answer="OSCAT con CIG INVENTATO e 270 giorni inventati.",
            fact_sheet=self._FACT_SHEET,
            guarded=True,
            config={"enabled": False},
        )
        self.assertEqual(result.status, "PASS")
        self.assertEqual(result.failures, ())

    def test_default_guardrail_config_blocks_when_no_config_passed(self) -> None:
        sheet = build_fact_sheet(
            [{"text": "Gara OSCAT con CIG B123456789.", "metadata": {}}],
            query="OSCAT",
        )
        result = validate_guarded_answer(
            answer="OSCAT con CIG INVENTATO e 270 giorni.",
            fact_sheet=sheet,
            guarded=True,
        )
        self.assertEqual(result.status, "BLOCK")

    def test_conflicting_procedure_ids_are_flagged_at_fact_sheet_level(self) -> None:
        sheet = build_fact_sheet(
            [
                {"text": "OSCAT procedura 012942/2025.", "metadata": {"chunk_index": 1}},
                {"text": "OSCAT procedura 099999/2025.", "metadata": {"chunk_index": 2}},
            ],
            query="OSCAT",
        )
        self.assertEqual(sheet.status, FactStatus.CONFLICT)
        self.assertIn("procedure_id", sheet.conflicts)
        result = validate_guarded_answer(
            answer="La procedura OSCAT è 012942/2025.",
            fact_sheet=sheet,
            guarded=True,
        )
        self.assertEqual(result.status, "BLOCK")
        self.assertIn("fact_sheet_conflict", result.failures)

    def test_audit_mode_keeps_answer_but_still_reports_failures(self) -> None:
        sheet = build_fact_sheet(
            [{"text": "Gara OSCAT con CIG B123456789.", "metadata": {}}],
            query="OSCAT",
        )
        answer = "OSCAT dura 270 giorni inventati."
        result = validate_guarded_answer(
            answer=answer,
            fact_sheet=sheet,
            guarded=True,
            config={"mode": "audit"},
        )
        self.assertEqual(result.status, "AUDIT")
        self.assertEqual(result.safe_answer, answer)
        self.assertIn("unverified_number:270", result.failures)

    def test_numeric_placeholder_pattern_is_blocked(self) -> None:
        sheet = build_fact_sheet(
            [{"text": "Gara OSCAT con CIG B123456789.", "metadata": {}}],
            query="OSCAT",
        )
        result = validate_guarded_answer(
            answer="La consegna avviene entro giorni dall'ordine.",
            fact_sheet=sheet,
            guarded=True,
        )
        self.assertEqual(result.status, "BLOCK")
        self.assertIn("numeric_placeholder", result.failures)

    def test_masked_cig_with_raw_value_is_blocked_and_repaired(self) -> None:
        sheet = build_fact_sheet(
            [{"text": "Gara OSCAT con CIG B33988ECF0.", "metadata": {}}],
            query="OSCAT",
        )
        answer = "Fatti verificati: CIG non verificato B33988ECF2."

        result = validate_guarded_answer(answer=answer, fact_sheet=sheet, guarded=True)
        repaired = repair_unsupported_protected_facts(answer, sheet)
        repaired_result = validate_guarded_answer(
            answer=repaired,
            fact_sheet=sheet,
            guarded=True,
        )

        self.assertEqual(result.status, "BLOCK")
        self.assertIn("masked_cig_value", result.failures)
        # Repair strips the wrong raw CIG and restores the single verified CIG
        # from the fact sheet via the inline-CIG rewriter.
        self.assertEqual(repaired, "Fatti verificati: CIG B33988ECF0.")
        self.assertEqual(repaired_result.status, "PASS")

    def test_short_procedure_id_year_is_blocked_and_repaired(self) -> None:
        sheet = build_fact_sheet(
            [{"text": "Gara OSCAT procedura 012942/2025.", "metadata": {}}],
            query="OSCAT",
        )
        answer = "Fatti verificati: ID procedura 012942/25."

        result = validate_guarded_answer(answer=answer, fact_sheet=sheet, guarded=True)
        repaired = repair_unsupported_protected_facts(answer, sheet)
        repaired_result = validate_guarded_answer(
            answer=repaired,
            fact_sheet=sheet,
            guarded=True,
        )

        self.assertEqual(result.status, "BLOCK")
        self.assertIn("unverified_procedure_id:012942/25", result.failures)
        self.assertNotIn("012942/25", repaired)
        self.assertEqual(repaired_result.status, "PASS")

    def test_broken_procedure_id_field_is_normalized_to_verified_value(self) -> None:
        sheet = build_fact_sheet(
            [{"text": "Gara OSCAT procedura 012942/2025.", "metadata": {}}],
            query="OSCAT",
        )
        answer = "Fatti verificati\n- ID procedura: 012942/2\n\n5/2025\n- CIG non rilevato"

        result = validate_guarded_answer(answer=answer, fact_sheet=sheet, guarded=True)
        repaired = repair_unsupported_protected_facts(answer, sheet)
        repaired_result = validate_guarded_answer(
            answer=repaired,
            fact_sheet=sheet,
            guarded=True,
        )

        self.assertEqual(result.status, "BLOCK")
        self.assertIn("malformed_procedure_id:012942/25/2025", result.failures)
        self.assertIn("ID procedura: 012942/2025", repaired)
        self.assertNotIn("5/2025", repaired)
        self.assertEqual(repaired_result.status, "PASS")

    def test_incomplete_procedure_id_fragment_is_normalized_to_verified_value(self) -> None:
        sheet = build_fact_sheet(
            [{"text": "Gara OSCAT procedura 012942/2025.", "metadata": {}}],
            query="OSCAT",
        )
        answer = "La Regione Toscana identifica la procedura OSCAT con ID 012942/2."

        result = validate_guarded_answer(answer=answer, fact_sheet=sheet, guarded=True)
        repaired = repair_unsupported_protected_facts(answer, sheet)
        repaired_result = validate_guarded_answer(
            answer=repaired,
            fact_sheet=sheet,
            guarded=True,
        )

        self.assertEqual(result.status, "BLOCK")
        self.assertIn("incomplete_procedure_id:012942/2", result.failures)
        self.assertIn("ID 012942/2025", repaired)
        self.assertEqual(repaired_result.status, "PASS")

    def test_wrapped_procedure_id_fragment_is_normalized_to_verified_value(self) -> None:
        sheet = build_fact_sheet(
            [{"text": "Gara OSCAT procedura 012942/2025.", "metadata": {}}],
            query="OSCAT",
        )
        answer = "La gara riguarda la procedura 012942/2\n\n025 per OSCAT."

        result = validate_guarded_answer(answer=answer, fact_sheet=sheet, guarded=True)
        repaired = repair_unsupported_protected_facts(answer, sheet)
        repaired_result = validate_guarded_answer(
            answer=repaired,
            fact_sheet=sheet,
            guarded=True,
        )

        self.assertEqual(result.status, "BLOCK")
        self.assertIn("incomplete_procedure_id:012942/2025", result.failures)
        self.assertIn("procedura 012942/2025", repaired)
        self.assertNotIn("012942/2\n\n025", repaired)
        self.assertEqual(repaired_result.status, "PASS")

    def test_block_on_unverified_numbers_disabled_lets_unverified_numbers_pass(self) -> None:
        sheet = build_fact_sheet(
            [{"text": "Gara OSCAT con CIG B123456789.", "metadata": {}}],
            query="OSCAT",
        )
        result = validate_guarded_answer(
            answer="La gara OSCAT prevede 270 giorni.",
            fact_sheet=sheet,
            guarded=True,
            config={"blockOnUnverifiedNumbers": False},
        )
        # Other deterministic checks still apply — only the unverified
        # numeric scrubber is silenced.
        self.assertEqual(result.status, "PASS")
        self.assertEqual(result.failures, ())


if __name__ == "__main__":
    unittest.main()
