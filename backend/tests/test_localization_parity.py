# ruff: noqa: E402
"""R9 — comprehensive parity coverage for the externalized localization layer.

These tests guard against regressions when keyword groups in the Markdown
assets drift from the behavior the engine relied on prior to extraction. They
exercise:

* asset coverage — every MD asset loads cleanly for IT and EN;
* regex semantic parity — canonical IT inputs still match each compiled
  intent regex and prompt-leakage regex;
* per-request locale override — a request-scoped ``language`` field flips the
  guardrail emission to English without touching ``settings.default_locale``.
"""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

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

from app.rag.internal_prompting import (
    INTERNAL_PROMPTING_ROOT,
    load_keyword_group,
    load_localized_messages,
    load_prompt_template,
)
from app.rag.localization import (
    get_guardrail_messages,
    get_intent_regexes,
    get_prompt_leakage_regexes,
    get_prompt_template_text,
)


class AssetCoverageSmokeTests(unittest.TestCase):
    """Every shipped asset must load for both supported languages."""

    PROMPT_ASSETS = ("qa-continuation", "qa-sentence-closure")
    MESSAGE_ASSETS = ("guardrail-messages", "guardrail-repair-messages")
    KEYWORD_ASSETS = (
        ("query-intent", "Tender Documents"),
        ("query-intent", "Summary Intent Markers"),
        ("query-intent", "Integrity Pact Context"),
        ("query-intent", "Continuation Headings"),
        ("query-intent", "Sentence End Tokens"),
        ("query-intent", "Prompt Garbage Tokens"),
        ("prompt-leakage", "Plain Labels"),
        ("prompt-leakage", "User Query Verbs"),
        ("prompt-leakage", "Instruction Lines"),
        ("retrieval-critical-coverage", "Query Variants"),
        ("guardrail-lexicon", "Procedure Anchors OSCAT"),
        ("guardrail-lexicon", "Procedure Anchors SCT"),
        ("guardrail-lexicon", "Semantic Theme garanzie"),
        ("guardrail-lexicon", "Comparison Markers"),
        ("guardrail-patterns", "Day Word"),
        ("guardrail-patterns", "Money Currency Words"),
        ("guardrail-patterns", "Contamination Markers"),
        ("guardrail-patterns", "False Missing Markers"),
        ("context-quality", "Broad Query Verbs"),
        ("context-quality", "Tender Overview Terms"),
        ("context-quality", "Query Stopwords"),
    )

    def test_internal_prompting_root_resolves(self) -> None:
        self.assertTrue(
            INTERNAL_PROMPTING_ROOT.exists(),
            msg=f"internal_prompting root not found at {INTERNAL_PROMPTING_ROOT}",
        )
        for language in ("it", "en"):
            self.assertTrue(
                (INTERNAL_PROMPTING_ROOT / language).exists(),
                msg=f"missing language directory: {language}",
            )

    def test_prompt_assets_load_for_both_languages(self) -> None:
        for asset in self.PROMPT_ASSETS:
            for language in ("it", "en"):
                body = load_prompt_template(asset, language=language)
                self.assertTrue(
                    body.strip(),
                    msg=f"empty prompt body: {asset} ({language})",
                )

    def test_message_assets_load_for_both_languages(self) -> None:
        for asset in self.MESSAGE_ASSETS:
            for language in ("it", "en"):
                messages = load_localized_messages(asset, language=language)
                self.assertGreater(len(messages), 0)

    def test_keyword_groups_load_for_both_languages(self) -> None:
        for asset, group in self.KEYWORD_ASSETS:
            for language in ("it", "en"):
                items = load_keyword_group(asset, group, language=language)
                self.assertGreater(
                    len(items),
                    0,
                    msg=f"empty group: {asset}/{group} ({language})",
                )


class IntentRegexSemanticParityTests(unittest.TestCase):
    """Canonical IT inputs must match the externalized intent regexes."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.intent = get_intent_regexes("it")

    def test_word_count_request_matches_italian_phrasing(self) -> None:
        match = self.intent.word_count_request.search("scrivi 1500 parole sulla gara")
        self.assertIsNotNone(match)
        assert match is not None
        self.assertEqual(match.group(1), "1500")

    def test_line_count_request_matches_italian_phrasing(self) -> None:
        match = self.intent.line_count_request.search("scrivi 200 righe finali")
        self.assertIsNotNone(match)
        assert match is not None
        self.assertEqual(match.group(1), "200")

    def test_summary_intent_matches_italian_summary_verbs(self) -> None:
        for sample in (
            "riassumi la procedura",
            "spiega gli obblighi",
            "panoramica esaustiva",
            "fornisci un overview",
            "approfondisci gli aspetti",
        ):
            self.assertIsNotNone(
                self.intent.summary_intent.search(sample),
                msg=f"summary_intent missed: {sample!r}",
            )

    def test_tender_document_matches_italian_terms(self) -> None:
        for sample in (
            "descrivi la gara",
            "il bando della procedura",
            "leggi il capitolato",
            "vedi il disciplinare",
            "il lotto principale",
            "tender notice",
        ):
            self.assertIsNotNone(
                self.intent.tender_document.search(sample),
                msg=f"tender_document missed: {sample!r}",
            )

    def test_generic_tender_indefinite_requires_article_plus_noun(self) -> None:
        self.assertIsNotNone(
            self.intent.generic_tender_indefinite.search("cos'e una gara")
        )
        self.assertIsNotNone(
            self.intent.generic_tender_indefinite.search("definisci un appalto")
        )
        self.assertIsNone(
            self.intent.generic_tender_indefinite.search("la gara OSCAT 012942/2025")
        )

    def test_integrity_pact_context_and_query_match_canonical_terms(self) -> None:
        self.assertIsNotNone(
            self.intent.integrity_pact_context.search(
                "il patto di integrita prevede soglie economiche"
            )
        )
        self.assertIsNotNone(
            self.intent.integrity_pact_query.search("anticorruzione e soglie")
        )

    def test_plural_day_only_matches_italian_singular_form(self) -> None:
        self.assertIsNotNone(self.intent.plural_day.search("scadenza tra 30 giorno"))
        self.assertIsNone(self.intent.plural_day.search("entro 30 giorni"))

    def test_math_rendering_request_matches_italian_and_english_terms(self) -> None:
        for sample in ("usa LaTeX", "scrivi una formula", "math notation"):
            self.assertIsNotNone(
                self.intent.math_rendering_request.search(sample),
                msg=f"math marker missed: {sample!r}",
            )

    def test_length_meta_paragraph_matches_compound_pattern(self) -> None:
        self.assertIsNotNone(
            self.intent.length_meta_paragraph.search(
                "le parole in totale risultano sufficienti"
            )
        )
        self.assertIsNotNone(
            self.intent.length_meta_paragraph.search("words count is enough")
        )

    def test_continuation_heading_strips_markdown_prefix(self) -> None:
        self.assertIsNotNone(
            self.intent.continuation_heading.match("## Continuazione capitolo 2")
        )
        self.assertIsNotNone(
            self.intent.continuation_heading.match("Proseguimento note")
        )

    def test_token_sets_contain_known_italian_and_mixed_entries(self) -> None:
        self.assertIn("di", self.intent.incomplete_sentence_end_tokens)
        self.assertIn("the", self.intent.incomplete_sentence_end_tokens)
        self.assertIn("answer", self.intent.prompt_garbage_prefix_tokens)
        self.assertIn("retrieved", self.intent.prompt_garbage_prefix_tokens)


class PromptLeakageRegexParityTests(unittest.TestCase):
    """Canonical leakage samples must still trigger the externalized regexes."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.leak = get_prompt_leakage_regexes("it")

    def test_heading_matches_known_label_lines(self) -> None:
        for sample in (
            "## Domanda Utente: testo",
            "## Contesto Recuperato: testo",
            "Own Answer: testo",
            "Your Answer: testo",
            "## Answer (final): testo",
        ):
            self.assertIsNotNone(
                self.leak.heading.match(sample),
                msg=f"leakage heading missed: {sample!r}",
            )

    def test_loop_matches_repeated_label_runs(self) -> None:
        self.assertIsNotNone(
            self.leak.loop.match("own answer your answer answer ")
        )

    def test_own_token_loop_and_prefix(self) -> None:
        self.assertIsNotNone(self.leak.own_token_loop.match("own own own"))
        self.assertIsNotNone(
            self.leak.own_token_prefix.match("own own own actual content")
        )

    def test_likely_user_query_start_matches_italian_imperatives(self) -> None:
        for sample in (
            "fai una sintesi",
            "spiega il bando",
            "descrivi il capitolato",
            "elenca le penali",
        ):
            self.assertIsNotNone(
                self.leak.likely_user_query_start.match(sample),
                msg=f"likely_user_query_start missed: {sample!r}",
            )
        self.assertIsNone(
            self.leak.likely_user_query_start.match("la procedura prevede")
        )

    def test_instruction_lines_cover_known_italian_and_english_directives(self) -> None:
        samples = (
            "scrivi solo il seguito naturale della risposta, "
            "iniziando direttamente dal contenuto mancante.",
            "use only the retrieved context.",
            "respond in the same language as the user's question.",
            "- non commentare il numero di parole.",
            "- chiudi con una frase completa e coerente.",
        )
        hits = sum(
            1
            for sample in samples
            for pattern in self.leak.instruction_lines
            if pattern.match(sample)
        )
        self.assertEqual(hits, len(samples))


class GuardrailMessagesParityTests(unittest.TestCase):
    """The dataclass projection of guardrail-messages must round-trip values."""

    def test_italian_messages_roundtrip(self) -> None:
        raw = load_localized_messages("guardrail-messages", language="it")
        messages = get_guardrail_messages("it")

        self.assertEqual(messages.soft_warning, raw["soft_warning"])
        self.assertEqual(messages.blocked_intro, raw["blocked_intro"])
        self.assertEqual(messages.fact_sheet_heading, raw["fact_sheet_heading"])
        self.assertEqual(messages.procedure_label, raw["procedure_label"])
        self.assertEqual(messages.not_detected, raw["not_detected"])

    def test_english_messages_roundtrip(self) -> None:
        raw = load_localized_messages("guardrail-messages", language="en")
        messages = get_guardrail_messages("en")

        self.assertEqual(messages.soft_warning, raw["soft_warning"])
        self.assertEqual(messages.blocked_intro, raw["blocked_intro"])
        self.assertEqual(messages.fact_sheet_heading, raw["fact_sheet_heading"])
        self.assertEqual(messages.procedure_label, raw["procedure_label"])
        self.assertEqual(messages.not_detected, raw["not_detected"])


class PromptTemplateParityTests(unittest.TestCase):
    """Cached template wrapper must match the low-level loader output."""

    def test_qa_templates_load_for_both_languages(self) -> None:
        for asset in ("qa-continuation", "qa-sentence-closure"):
            for language in ("it", "en"):
                wrapped = get_prompt_template_text(asset, language)
                direct = load_prompt_template(asset, language=language)
                self.assertEqual(wrapped, direct)
                self.assertIn("{query}", wrapped)
                self.assertIn("{context}", wrapped)
                self.assertIn("{current_answer_tail}", wrapped)


class EndToEndLocaleSwitchTests(unittest.TestCase):
    """Per-request override must flip both messages and prompt templates."""

    def test_request_language_en_emits_english_blocked_answer(self) -> None:
        from app.rag.engine import HybridRAGEngine
        from app.rag.procedure_guardrails import FactSheet

        engine = HybridRAGEngine()
        sheet = FactSheet(procedure_label="OSCAT", procedure_ids=("012942/2025",))

        rendered_en = engine._build_guardrail_blocked_answer(sheet, language="en")
        rendered_it = engine._build_guardrail_blocked_answer(sheet, language="it")

        self.assertNotEqual(rendered_en, rendered_it)
        self.assertIn("Verified facts available:", rendered_en)
        self.assertIn("Fatti verificati disponibili:", rendered_it)
        self.assertIn("- Procedure: OSCAT", rendered_en)
        self.assertIn("- Procedura: OSCAT", rendered_it)

    def test_request_language_en_uses_english_prompt_template(self) -> None:
        en_template = get_prompt_template_text("qa-continuation", "en")
        it_template = get_prompt_template_text("qa-continuation", "it")

        self.assertIn("IMPORTANT INSTRUCTIONS", en_template)
        self.assertIn("ISTRUZIONI IMPORTANTI", it_template)
        self.assertNotEqual(en_template, it_template)

    def test_default_language_falls_back_to_settings(self) -> None:
        from app.rag.internal_prompting import default_language

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TENDERWRITER_LOCALE", None)
            self.assertEqual(default_language(), "it")

    def test_env_var_promotes_default_language_to_english(self) -> None:
        from app.rag.internal_prompting import default_language

        with patch.dict(os.environ, {"TENDERWRITER_LOCALE": "en"}, clear=False):
            self.assertEqual(default_language(), "en")


class GuardrailRepairMessagesParityTests(unittest.TestCase):
    """R11 — externalized procedure_guardrails repair strings."""

    def test_italian_repair_messages_load_with_required_keys(self) -> None:
        from app.rag.localization import (
            GuardrailRepairMessages,
            get_guardrail_repair_messages,
        )

        messages = get_guardrail_repair_messages("it")

        self.assertIsInstance(messages, GuardrailRepairMessages)
        self.assertEqual(messages.unverified_procedure_id, "ID procedura non verificato")
        self.assertEqual(messages.unverified_cig, "CIG non verificato")
        self.assertEqual(messages.unverified_amount, "importo non verificato")
        self.assertEqual(messages.unverified_duration, "durata non verificata")
        self.assertEqual(messages.unverified_article, "articolo non verificato")
        self.assertEqual(messages.fragment_procedure_id_label, "ID procedura")
        self.assertEqual(messages.verified_data_intro, "Dati verificati")
        self.assertIn("{low}", messages.distinct_amounts_template)
        self.assertIn("{high}", messages.distinct_amounts_template)

    def test_english_repair_messages_load_with_required_keys(self) -> None:
        from app.rag.localization import get_guardrail_repair_messages

        messages = get_guardrail_repair_messages("en")

        self.assertEqual(messages.unverified_procedure_id, "unverified procedure ID")
        self.assertEqual(messages.unverified_cig, "unverified CIG")
        self.assertEqual(messages.unverified_amount, "unverified amount")
        self.assertEqual(messages.unverified_article, "unverified article")
        self.assertEqual(messages.fragment_procedure_id_label, "Procedure ID")
        self.assertEqual(messages.verified_data_intro, "Verified data")
        self.assertIn("{low}", messages.distinct_amounts_template)

    def test_repair_uses_localized_unverified_amount_for_corrupt_artifact(self) -> None:
        from app.rag.procedure_guardrails import (
            _strip_corrupt_money_artifacts,
        )

        repaired = _strip_corrupt_money_artifacts("Quota di € 1.573.025,20.0//25,20")

        self.assertIn("importo non verificato", repaired)
        self.assertNotIn("//", repaired)

    def test_repair_uses_localized_unverified_article(self) -> None:
        from app.rag.procedure_guardrails import _strip_malformed_article_references

        repaired = _strip_malformed_article_references(
            "ai sensi dell'art. 14C56 del codice civile"
        )

        self.assertIn("articolo non verificato", repaired)
        self.assertNotIn("14C56", repaired)


class EngineMessagesAssetsTests(unittest.TestCase):
    """Engine-messages assets load with required keys for IT and EN."""

    def test_italian_engine_messages_load(self) -> None:
        from app.rag.localization import get_engine_messages

        messages = get_engine_messages("it")

        self.assertEqual(messages.fact_sheet_heading_text, "Fatti verificati")
        self.assertEqual(messages.length_unit_lines, "righe")
        self.assertEqual(messages.length_unit_words, "parole")
        self.assertIn("non disponibile", messages.model_unavailable_fallback)
        self.assertEqual(messages.fact_sheet_label_procedure, "procedura")
        self.assertEqual(messages.fact_sheet_label_status, "stato_verifica")
        self.assertEqual(messages.fact_sheet_label_critical_days, "giorni_critici")
        self.assertEqual(messages.fact_sheet_label_locations, "sedi_luoghi")
        self.assertEqual(messages.fact_sheet_value_not_detected, "non_rilevato")
        self.assertEqual(messages.fact_sheet_value_no_conflicts, "nessuno")
        self.assertEqual(messages.fact_sheet_value_conflict_detected, "conflitto_rilevato")
        self.assertEqual(messages.procedure_label_unattributed, "non_attribuibile")

    def test_english_engine_messages_load(self) -> None:
        from app.rag.localization import get_engine_messages

        messages = get_engine_messages("en")

        self.assertEqual(messages.fact_sheet_heading_text, "Verified facts")
        self.assertEqual(messages.length_unit_lines, "lines")
        self.assertEqual(messages.length_unit_words, "words")
        self.assertIn("temporarily unavailable", messages.model_unavailable_fallback)
        self.assertEqual(messages.fact_sheet_label_procedure, "procedure")
        self.assertEqual(messages.fact_sheet_label_status, "verification_status")
        self.assertEqual(messages.fact_sheet_label_critical_days, "critical_days")
        self.assertEqual(messages.fact_sheet_value_not_detected, "not_detected")
        self.assertEqual(messages.fact_sheet_value_no_conflicts, "none")
        self.assertEqual(messages.procedure_label_unattributed, "unattributed")

    def test_serialize_then_parse_fact_sheet_roundtrips_with_localized_keys(self) -> None:
        from app.rag.engine import HybridRAGEngine
        from app.rag.procedure_guardrails import (
            FactSheet,
            FactStatus,
            fact_sheet_from_guarded_context,
        )

        engine = HybridRAGEngine()
        original = FactSheet(
            procedure_label="OSCAT",
            procedure_ids=("012942/2025",),
            cigs=("B33988ECF0",),
            critical_days=("15 giorni",),
            durations=("48 mesi",),
            amounts=("5.999.723,60 euro",),
            locations=("Regione Toscana",),
            percentages=("2%",),
            source_ids=("chunk:1",),
            conflicts=(),
            status=FactStatus.VERIFIED,
        )
        serialized = engine._format_fact_sheet(original)
        wrapped = f"FACT_SHEET_START\n{serialized.split('FACT_SHEET_START', 1)[1]}"
        parsed = fact_sheet_from_guarded_context(wrapped)

        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.procedure_label, "OSCAT")
        self.assertEqual(parsed.procedure_ids, ("012942/2025",))
        self.assertEqual(parsed.cigs, ("B33988ECF0",))
        self.assertEqual(parsed.critical_days, ("15 giorni",))
        self.assertEqual(parsed.durations, ("48 mesi",))
        self.assertEqual(parsed.amounts, ("5.999.723,60 euro",))
        self.assertEqual(parsed.locations, ("Regione Toscana",))
        self.assertEqual(parsed.percentages, ("2%",))
        self.assertEqual(parsed.status, FactStatus.VERIFIED)


class EngineResponseConstraintsAssetsTests(unittest.TestCase):
    """Engine response-constraint groups load and provide expected templates."""

    def test_italian_constraints_groups_present(self) -> None:
        from app.rag.localization import get_engine_response_constraints

        constraints = get_engine_response_constraints("it")

        self.assertGreater(len(constraints.general), 0)
        self.assertEqual(len(constraints.length_target_templates), 4)
        self.assertEqual(len(constraints.lines_mode), 1)
        self.assertEqual(len(constraints.no_length_target), 1)
        self.assertEqual(len(constraints.expanded_explanation), 1)
        self.assertEqual(len(constraints.broad_summary), 1)
        self.assertEqual(len(constraints.structured_overview_sections), 5)
        self.assertEqual(len(constraints.structured_overview_heading), 1)
        self.assertGreater(len(constraints.structured_overview), 0)
        self.assertEqual(len(constraints.math_rendering), 3)

        # Length-target templates expose Python placeholders for runtime
        # interpolation.
        joined = "\n".join(constraints.length_target_templates)
        self.assertIn("{requested_label}", joined)
        self.assertIn("{min_words}", joined)
        self.assertIn("{max_words}", joined)
        self.assertIn("{target_words}", joined)

    def test_english_constraints_groups_present(self) -> None:
        from app.rag.localization import get_engine_response_constraints

        constraints = get_engine_response_constraints("en")

        self.assertEqual(len(constraints.length_target_templates), 4)
        self.assertEqual(len(constraints.structured_overview_sections), 5)
        joined_sections = "\n".join(constraints.structured_overview_sections)
        self.assertIn("Object and scope", joined_sections)


class EngineCleanupPatternsAssetsTests(unittest.TestCase):
    """OCR replacements + numeric/skip pattern bundles load and compile."""

    def test_italian_cleanup_patterns_compile(self) -> None:
        from app.rag.localization import get_engine_cleanup_patterns

        cleanup = get_engine_cleanup_patterns("it")

        self.assertGreater(len(cleanup.ocr_replacements), 0)
        first_pattern, first_replacement = cleanup.ocr_replacements[0]
        self.assertEqual(first_replacement, "ulteriore")
        self.assertEqual(first_pattern.flags & 2, 2)  # re.IGNORECASE bit
        self.assertIn("ecco la continuazione", cleanup.continuation_skip_prefixes)
        self.assertGreaterEqual(len(cleanup.broken_numeric_patterns), 3)
        self.assertGreaterEqual(len(cleanup.critical_numeric_patterns), 6)

    def test_ocr_replacements_apply_to_known_corrupted_text(self) -> None:
        from app.rag.localization import get_engine_cleanup_patterns

        cleanup = get_engine_cleanup_patterns("it")
        text = "ulter ulteriore Migliore (MAM) Infrastruttura Digitali"
        for pattern, replacement in cleanup.ocr_replacements:
            text = pattern.sub(replacement, text)

        self.assertIn("ulteriore", text)
        self.assertIn("Migliorativa (MAM)", text)
        self.assertIn("Infrastrutture Digitali", text)


class EngineLanguageMarkersAssetsTests(unittest.TestCase):
    """Language detection markers load and contain canonical entries."""

    def test_italian_language_markers_load(self) -> None:
        from app.rag.localization import get_engine_language_markers

        markers = get_engine_language_markers("it")

        self.assertIn("gara", markers.italian_markers)
        self.assertIn("punti chiave", markers.italian_markers)
        self.assertIn("tender", markers.english_markers)
        self.assertIn("rfp", markers.english_markers)

    def test_english_language_markers_match_italian_set(self) -> None:
        from app.rag.localization import get_engine_language_markers

        it_markers = get_engine_language_markers("it")
        en_markers = get_engine_language_markers("en")

        # Cross-lingual lookup tables: both locales ship the same content.
        self.assertEqual(it_markers.italian_markers, en_markers.italian_markers)
        self.assertEqual(it_markers.english_markers, en_markers.english_markers)


class EngineConsumesExternalizedAssetsTests(unittest.TestCase):
    """Engine module-level wiring binds to the new localization assets."""

    def test_engine_module_uses_localized_engine_messages(self) -> None:
        from app.rag import engine
        from app.rag.localization import get_engine_messages

        messages = get_engine_messages("it")

        self.assertEqual(
            engine._ENGINE_MESSAGES.length_unit_lines, messages.length_unit_lines
        )
        self.assertEqual(
            engine._ENGINE_MESSAGES.model_unavailable_fallback,
            messages.model_unavailable_fallback,
        )

    def test_engine_uses_cleanup_patterns_from_asset(self) -> None:
        from app.rag import engine
        from app.rag.localization import get_engine_cleanup_patterns

        cleanup = get_engine_cleanup_patterns("it")
        self.assertEqual(
            engine._ENGINE_CLEANUP.continuation_skip_prefixes,
            cleanup.continuation_skip_prefixes,
        )
        self.assertEqual(
            len(engine.HybridRAGEngine.BROKEN_NUMERIC_PATTERNS),
            len(cleanup.broken_numeric_patterns),
        )

    def test_engine_uses_language_markers_from_asset(self) -> None:
        from app.rag import engine
        from app.rag.localization import get_engine_language_markers

        markers = get_engine_language_markers("it")
        self.assertEqual(
            engine._ENGINE_LANG_MARKERS.italian_markers, markers.italian_markers
        )
        self.assertEqual(
            engine._ENGINE_LANG_MARKERS.english_markers, markers.english_markers
        )


class GeneratorTemplateAssetsTests(unittest.TestCase):
    """All generator templates load for IT and EN with required placeholders."""

    REQUIRED_PLACEHOLDERS = {
        "proposal_section": ("{context}", "{section_title}", "{instructions}", "{requirements}"),
        "executive_summary": ("{sections}", "{context}", "{requirements}"),
        "requirement_analyzer": ("{document_text}",),
        "requirement_extractor_v2": (
            "{schema_version}",
            "{source_document_ref}",
            "{section_path}",
            "{document_text}",
        ),
        "participation_requirement_extractor_v1": (
            "{schema_version}",
            "{source_document_ref}",
            "{section_path}",
            "{document_text}",
        ),
        "compliance_checker": ("{requirement}", "{section_content}", "{context}"),
        "general_qa": ("{context}", "{query}", "{response_constraints}"),
        "tender_overview": ("{context}", "{query}", "{response_constraints}"),
        "tender_longform_synthesis": ("{context}", "{query}", "{response_constraints}"),
    }

    def test_all_templates_load_for_both_languages(self) -> None:
        from app.rag.localization import GENERATOR_TEMPLATE_ASSETS

        for name, asset in GENERATOR_TEMPLATE_ASSETS.items():
            for language in ("it", "en"):
                body = get_prompt_template_text(asset, language=language)
                self.assertTrue(
                    body.strip(),
                    msg=f"empty generator template body: {name} ({language})",
                )

    def test_required_placeholders_present_in_both_languages(self) -> None:
        from app.rag.localization import GENERATOR_TEMPLATE_ASSETS

        for name, asset in GENERATOR_TEMPLATE_ASSETS.items():
            placeholders = self.REQUIRED_PLACEHOLDERS[name]
            for language in ("it", "en"):
                body = get_prompt_template_text(asset, language=language)
                for placeholder in placeholders:
                    self.assertIn(
                        placeholder,
                        body,
                        msg=f"{name} ({language}) missing placeholder {placeholder}",
                    )

    def test_prompt_templates_module_dict_built_from_assets(self) -> None:
        from app.rag.generator import PROMPT_TEMPLATES
        from app.rag.localization import GENERATOR_TEMPLATE_ASSETS

        self.assertEqual(set(PROMPT_TEMPLATES.keys()), set(GENERATOR_TEMPLATE_ASSETS.keys()))


class GeneratorMessagesAssetsTests(unittest.TestCase):
    """Generator system messages and detection keywords externalized correctly."""

    def test_italian_generator_messages_load(self) -> None:
        from app.rag.localization import get_generator_messages

        msgs = get_generator_messages("it")
        self.assertIn("ITALIANO", msgs.system_message_general_qa)
        self.assertIn("chi", msgs.question_detection_keywords)
        self.assertIn("cosa", msgs.question_detection_keywords)
        self.assertIn("perché", msgs.question_detection_keywords)

    def test_english_generator_messages_load(self) -> None:
        from app.rag.localization import get_generator_messages

        msgs = get_generator_messages("en")
        self.assertIn("AI assistant", msgs.system_message_general_qa)
        self.assertIn("what", msgs.question_detection_keywords)
        self.assertIn("how", msgs.question_detection_keywords)

    def test_generator_resolves_template_text_for_known_name(self) -> None:
        from app.rag.generator import _resolve_template_text

        body, name = _resolve_template_text("tender_overview", "it")
        self.assertEqual(name, "tender_overview")
        self.assertIn("{context}", body)
        self.assertIn("Fatti verificati", body)

    def test_generator_treats_unknown_name_as_raw_template(self) -> None:
        from app.rag.generator import _resolve_template_text

        raw = "raw prompt with {var}"
        body, name = _resolve_template_text(raw, "it")
        self.assertEqual(name, "custom")
        self.assertEqual(body, raw)

    def test_general_qa_system_message_uses_it_when_query_has_it_keyword(self) -> None:
        from app.rag.generator import _resolve_general_qa_system_message

        msg = _resolve_general_qa_system_message(
            "general_qa", {"query": "Cosa fare?"}, "en"
        )
        self.assertIsNotNone(msg)
        assert msg is not None
        self.assertIn("ITALIANO", msg)

    def test_general_qa_system_message_uses_resolved_language_otherwise(self) -> None:
        from app.rag.generator import _resolve_general_qa_system_message

        msg = _resolve_general_qa_system_message(
            "general_qa", {"query": "summarize the procurement"}, "en"
        )
        self.assertIsNotNone(msg)
        assert msg is not None
        self.assertIn("AI assistant", msg)

    def test_general_qa_system_message_none_for_other_templates(self) -> None:
        from app.rag.generator import _resolve_general_qa_system_message

        self.assertIsNone(
            _resolve_general_qa_system_message("tender_overview", {"query": "x"}, "it")
        )


class GuardrailLexiconAssetsTests(unittest.TestCase):
    """R12 — externalized guardrail anchor/keyword lexicon."""

    def test_lexicon_loads_for_both_languages_with_canonical_members(self) -> None:
        from app.rag.localization import GuardrailLexicon, get_guardrail_lexicon

        for language in ("it", "en"):
            lex = get_guardrail_lexicon(language)
            self.assertIsInstance(lex, GuardrailLexicon)
            self.assertEqual(set(lex.procedure_anchors), {"OSCAT", "SCT"})
            self.assertIn("oscat", lex.procedure_anchors["OSCAT"])
            self.assertIn("sct", lex.procedure_anchors["SCT"])
            self.assertEqual(
                set(lex.semantic_theme_keywords),
                {"garanzie", "manleva", "integrita"},
            )
            self.assertIn("cauzione", lex.semantic_theme_keywords["garanzie"])
            self.assertIn("confront", lex.comparison_markers)

    def test_lexicon_bodies_identical_between_it_and_en(self) -> None:
        from app.rag.localization import get_guardrail_lexicon

        it_lex = get_guardrail_lexicon("it")
        en_lex = get_guardrail_lexicon("en")
        self.assertEqual(it_lex.procedure_anchors, en_lex.procedure_anchors)
        self.assertEqual(
            it_lex.semantic_theme_keywords, en_lex.semantic_theme_keywords
        )
        self.assertEqual(it_lex.comparison_markers, en_lex.comparison_markers)

    def test_module_binds_lexicon_into_public_anchors(self) -> None:
        from app.rag import procedure_guardrails as pg
        from app.rag.localization import get_guardrail_lexicon

        self.assertEqual(
            pg.PROCEDURE_ANCHORS, get_guardrail_lexicon("it").procedure_anchors
        )

    def test_classify_chunk_procedure_still_resolves_anchors(self) -> None:
        from app.rag.procedure_guardrails import classify_chunk_procedure

        self.assertEqual(
            classify_chunk_procedure("Servizi GitLab, Sonar, Nexus, DevSecOps."),
            "OSCAT",
        )
        self.assertEqual(
            classify_chunk_procedure(
                "RTPC, CCTT, fase transitoria, Via San Piero a Quaracchi."
            ),
            "SCT",
        )


class GuardrailPatternsAssetsTests(unittest.TestCase):
    """R13 — externalized guardrail regex bundle preserves behavior."""

    @classmethod
    def setUpClass(cls) -> None:
        from app.rag.localization import get_guardrail_patterns

        cls.pat = get_guardrail_patterns("it")

    def test_bundle_compiles_for_both_languages(self) -> None:
        from app.rag.localization import GuardrailPatterns, get_guardrail_patterns

        for language in ("it", "en"):
            bundle = get_guardrail_patterns(language)
            self.assertIsInstance(bundle, GuardrailPatterns)
            self.assertEqual(len(bundle.false_missing_field_res), 5)

    def test_numeric_unit_patterns_match_italian_phrasing(self) -> None:
        self.assertIsNotNone(self.pat.day.search("scadenza 180 giorni"))
        self.assertIsNotNone(self.pat.month.search("durata 48 mesi"))
        self.assertIsNotNone(self.pat.year.search("validità 2 anni"))
        # date-like tokens must not be misread as durations
        self.assertIsNone(self.pat.day.search("012942/2025 giorni"))

    def test_money_pattern_matches_currency_and_million_forms(self) -> None:
        for sample in (
            "€ 5.999.723,60",
            "euro 1.200.000,00",
            "1.500.000 euro",
            "2 milioni di euro",
        ):
            self.assertIsNotNone(
                self.pat.money.search(sample), msg=f"money missed: {sample!r}"
            )

    def test_location_and_address_patterns(self) -> None:
        self.assertIsNotNone(
            self.pat.address.search("sede in Via San Piero a Quaracchi 13")
        )
        match = self.pat.service_location.search(
            "il luogo di svolgimento del servizio è la Regione Toscana."
        )
        self.assertIsNotNone(match)
        assert match is not None
        self.assertEqual(match.group(1), "Regione Toscana")

    def test_duration_range_and_inline_unverified_patterns(self) -> None:
        m = self.pat.duration_range.search("tra i 12 e i 48 mesi")
        self.assertIsNotNone(m)
        assert m is not None
        self.assertEqual((m.group(1), m.group(2)), ("12", "48"))
        self.assertIsNotNone(
            self.pat.inline_unverified_procedure_id.search(
                "ID procedura non verificata"
            )
        )
        self.assertIsNotNone(
            self.pat.inline_unverified_cig.search("CIG non verificato")
        )

    def test_contamination_identity_article_and_false_missing(self) -> None:
        self.assertIsNotNone(self.pat.oscat_sct_contamination.search("PNRR missione 1"))
        self.assertIsNotNone(self.pat.oscat_identity_keyword.search("pipeline CI/CD"))
        self.assertIsNotNone(
            self.pat.malformed_article.search("ai sensi dell'art. 14C56 c.c.")
        )
        self.assertIsNotNone(
            self.pat.false_missing_marker.search("il dato non è disponibile")
        )
        self.assertIsNotNone(
            self.pat.procedure_id_false_missing.search(
                "ID procedura: non verificato"
            )
        )

    def test_module_aliases_bind_to_bundle(self) -> None:
        from app.rag import procedure_guardrails as pg
        from app.rag.localization import get_guardrail_patterns

        bundle = get_guardrail_patterns("it")
        self.assertIs(pg._DAY_RE, bundle.day)
        self.assertIs(pg._MONEY_RE, bundle.money)
        self.assertIs(pg.OSCAT_SCT_CONTAMINATION_RE, bundle.oscat_sct_contamination)


class GuardrailExtendedRepairAndLocaleSwitchTests(unittest.TestCase):
    """R14 — extended repair keys + blocked-output localization."""

    def test_extended_repair_keys_load_for_both_languages(self) -> None:
        from app.rag.localization import get_guardrail_repair_messages

        it_msgs = get_guardrail_repair_messages("it")
        en_msgs = get_guardrail_repair_messages("en")

        self.assertEqual(
            it_msgs.blocked_output,
            "output bloccato: conflitto o dato non verificato",
        )
        self.assertEqual(
            en_msgs.blocked_output, "output blocked: conflict or unverified data"
        )
        self.assertEqual(
            (it_msgs.unit_days, it_msgs.unit_months, it_msgs.unit_years),
            ("giorni", "mesi", "anni"),
        )
        self.assertEqual(
            (en_msgs.unit_days, en_msgs.unit_months, en_msgs.unit_years),
            ("days", "months", "years"),
        )
        self.assertEqual(it_msgs.conjunction_and, "e")
        self.assertEqual(en_msgs.conjunction_and, "and")

    def test_module_blocked_output_constant_bound_from_asset(self) -> None:
        from app.rag.procedure_guardrails import BLOCKED_OUTPUT_MESSAGE

        self.assertEqual(
            BLOCKED_OUTPUT_MESSAGE,
            "output bloccato: conflitto o dato non verificato",
        )

    def test_extract_day_values_uses_localized_unit_at_default_locale(self) -> None:
        from app.rag.procedure_guardrails import _extract_day_values

        self.assertEqual(
            _extract_day_values("sono previsti 180 giorni"), ("180 giorni",)
        )


class ContextQualityAssetsTests(unittest.TestCase):
    """R15 — externalized context_quality regex/lexicon bundle."""

    @classmethod
    def setUpClass(cls) -> None:
        from app.rag.localization import get_context_quality

        cls.cq = get_context_quality("it")

    def test_bundle_loads_for_both_languages_with_canonical_members(self) -> None:
        from app.rag.localization import ContextQuality, get_context_quality

        for language in ("it", "en"):
            bundle = get_context_quality(language)
            self.assertIsInstance(bundle, ContextQuality)
            self.assertIn("capitolato", bundle.tender_overview_terms)
            self.assertIn("quali", bundle.query_stopwords)

    def test_bodies_identical_between_it_and_en(self) -> None:
        from app.rag.localization import get_context_quality

        it_cq = get_context_quality("it")
        en_cq = get_context_quality("en")
        self.assertEqual(
            it_cq.tender_overview_terms, en_cq.tender_overview_terms
        )
        self.assertEqual(it_cq.query_stopwords, en_cq.query_stopwords)
        self.assertEqual(
            it_cq.numeric_or_legal.pattern, en_cq.numeric_or_legal.pattern
        )

    def test_numeric_or_legal_matches_canonical_facts(self) -> None:
        for sample in (
            "180 giorni",
            "48 mesi",
            "5 years",
            "euro 1.200.000",
            "12 %",
            "CIG B33988ECF0",
            "012942/2025",
            "art. 113 c.c.",
        ):
            self.assertIsNotNone(
                self.cq.numeric_or_legal.search(sample),
                msg=f"numeric_or_legal missed: {sample!r}",
            )

    def test_broad_tender_query_matches_both_orderings(self) -> None:
        self.assertIsNotNone(
            self.cq.broad_tender_query.search("riassumi la gara OSCAT")
        )
        self.assertIsNotNone(
            self.cq.broad_tender_query.search("la procedura, fammi una panoramica")
        )
        self.assertIsNone(
            self.cq.broad_tender_query.search("qual è il CIG della fornitura")
        )

    def test_module_aliases_bind_to_bundle(self) -> None:
        from app.rag import context_quality as cq
        from app.rag.localization import get_context_quality

        bundle = get_context_quality("it")
        self.assertIs(cq._NUMERIC_OR_LEGAL_RE, bundle.numeric_or_legal)
        self.assertIs(cq._QUERY_STOPWORDS, bundle.query_stopwords)

    def test_compress_context_block_preserves_numeric_sentence(self) -> None:
        from app.rag.context_quality import compress_context_block

        text = (
            "Premessa generica non pertinente. "
            "La durata del contratto è di 48 mesi."
        )
        out = compress_context_block(text, query="durata della gara")
        self.assertIn("48 mesi", out)


if __name__ == "__main__":
    unittest.main()
