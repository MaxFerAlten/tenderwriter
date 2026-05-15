# ruff: noqa: E402
"""Tests for the extended internal_prompting loaders (R1)."""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
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

from app.rag import internal_prompting
from app.rag.internal_prompting import (
    default_language,
    load_keyword_group,
    load_localized_messages,
    load_prompt_template,
    load_retrieval_query_variants,
)


def _write_asset(root: Path, language: str, name: str, body: str) -> Path:
    target_dir = root / language
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"{name}.md"
    path.write_text(body, encoding="utf-8")
    return path


class LoadPromptTemplateTests(unittest.TestCase):
    def test_extracts_prompt_body_between_markers(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_asset(
                root,
                "it",
                "qa-continuation",
                "# Title\n\n"
                "<!-- prompt:start -->\n"
                "ISTRUZIONI:\n- Riga uno\n- Riga due {placeholder}\n"
                "<!-- prompt:end -->\n"
                "Trailing notes ignored.\n",
            )

            body = load_prompt_template(
                "qa-continuation", language="it", root=root
            )

        self.assertIn("ISTRUZIONI:", body)
        self.assertIn("{placeholder}", body)
        self.assertNotIn("Trailing notes", body)
        self.assertFalse(body.startswith("\n"))
        self.assertFalse(body.endswith("\n"))

    def test_missing_markers_raise_value_error(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_asset(root, "it", "broken", "no markers here")

            with self.assertRaises(ValueError):
                load_prompt_template("broken", language="it", root=root)

    def test_unsupported_language_raises(self) -> None:
        with self.assertRaises(ValueError):
            load_prompt_template("qa-continuation", language="fr")


class LoadLocalizedMessagesTests(unittest.TestCase):
    def test_parses_messages_section_into_mapping(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_asset(
                root,
                "it",
                "guardrail-messages",
                "# Title\n\n"
                "## Messages\n"
                "soft_warning: Nota: alcuni dati mascherati.\n"
                "blocked_intro: Risposta scartata.\n"
                "fact_sheet_heading: Fatti verificati disponibili:\n"
                "\n"
                "## Other\n"
                "ignored_key: ignored_value\n",
            )

            messages = load_localized_messages(
                "guardrail-messages", language="it", root=root
            )

        self.assertEqual(messages["soft_warning"], "Nota: alcuni dati mascherati.")
        self.assertEqual(messages["blocked_intro"], "Risposta scartata.")
        self.assertEqual(
            messages["fact_sheet_heading"], "Fatti verificati disponibili:"
        )
        self.assertNotIn("ignored_key", messages)

    def test_missing_messages_section_raises(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_asset(root, "it", "no-messages", "# Title\n\n## Other\n- foo\n")

            with self.assertRaises(ValueError):
                load_localized_messages("no-messages", language="it", root=root)


class LoadKeywordGroupTests(unittest.TestCase):
    def test_returns_bullet_items_for_named_group(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_asset(
                root,
                "it",
                "query-intent",
                "# Title\n\n"
                "## Tender Documents\n"
                "- gara\n"
                "- bando\n"
                "- capitolato\n\n"
                "## Summary Verbs\n"
                "- riassumi\n"
                "- spiega\n",
            )

            documents = load_keyword_group(
                "query-intent",
                "Tender Documents",
                language="it",
                root=root,
            )
            verbs = load_keyword_group(
                "query-intent",
                "Summary Verbs",
                language="it",
                root=root,
            )

        self.assertEqual(documents, ("gara", "bando", "capitolato"))
        self.assertEqual(verbs, ("riassumi", "spiega"))

    def test_unknown_group_raises(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_asset(
                root,
                "it",
                "query-intent",
                "## Tender Documents\n- gara\n",
            )

            with self.assertRaises(ValueError):
                load_keyword_group(
                    "query-intent",
                    "Missing Group",
                    language="it",
                    root=root,
                )


class LoadRetrievalQueryVariantsBackcompatTests(unittest.TestCase):
    def test_existing_asset_still_loads_via_query_variants_helper(self) -> None:
        italian_variants = load_retrieval_query_variants(
            "retrieval-critical-coverage", language="it"
        )
        english_variants = load_retrieval_query_variants(
            "retrieval-critical-coverage", language="en"
        )

        self.assertGreaterEqual(len(italian_variants), 1)
        self.assertGreaterEqual(len(english_variants), 1)


class DefaultLanguageTests(unittest.TestCase):
    def test_defaults_to_italian_when_no_override(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TENDERWRITER_LOCALE", None)
            with patch.object(
                internal_prompting,
                "settings" if hasattr(internal_prompting, "settings") else "_unused",
                None,
                create=True,
            ):
                self.assertEqual(default_language(), "it")

    def test_env_var_override(self) -> None:
        with patch.dict(os.environ, {"TENDERWRITER_LOCALE": "en"}, clear=False):
            self.assertEqual(default_language(), "en")

    def test_unknown_locale_falls_back_to_italian(self) -> None:
        with patch.dict(os.environ, {"TENDERWRITER_LOCALE": "fr"}, clear=False):
            self.assertEqual(default_language(), "it")


class SettingsDefaultLocaleTests(unittest.TestCase):
    def test_settings_field_defaults_to_italian(self) -> None:
        from app.config import Settings

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TENDERWRITER_LOCALE", None)
            instance = Settings()

        self.assertEqual(instance.default_locale, "it")

    def test_settings_field_reads_tenderwriter_locale_env_var(self) -> None:
        from app.config import Settings

        with patch.dict(os.environ, {"TENDERWRITER_LOCALE": "en"}, clear=False):
            instance = Settings()

        self.assertEqual(instance.default_locale, "en")

    def test_default_language_falls_back_to_settings_when_env_unset(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TENDERWRITER_LOCALE", None)
            with patch.object(
                internal_prompting,
                "_test_settings_proxy",
                type("S", (), {"default_locale": "en"})(),
                create=True,
            ):
                # Replace the runtime ``settings`` import target via sys.modules
                import sys

                fake_module = type(sys)("app.config_test_proxy")
                fake_module.settings = internal_prompting._test_settings_proxy
                with patch.dict(
                    sys.modules,
                    {"app.config": fake_module},
                ):
                    self.assertEqual(default_language(), "en")


class GuardrailMessagesAssetsTests(unittest.TestCase):
    """Verify guardrail-messages MD assets load correctly for IT and EN."""

    def test_italian_messages_contain_required_keys(self) -> None:
        messages = load_localized_messages("guardrail-messages", language="it")

        for key in (
            "soft_warning",
            "blocked_intro",
            "fact_sheet_heading",
            "procedure_label",
            "procedure_id_label",
            "cig_label",
            "critical_days_label",
            "duration_label",
            "amounts_label",
            "locations_label",
            "percentages_label",
            "sources_label",
            "not_detected",
            "conflict_detected",
        ):
            self.assertIn(key, messages, msg=f"missing key: {key}")
        self.assertIn("Nota:", messages["soft_warning"])
        self.assertIn("Risposta generata scartata", messages["blocked_intro"])
        self.assertEqual(messages["procedure_label"], "Procedura")
        self.assertEqual(messages["not_detected"], "non rilevato")

    def test_english_messages_contain_required_keys(self) -> None:
        messages = load_localized_messages("guardrail-messages", language="en")

        for key in (
            "soft_warning",
            "blocked_intro",
            "procedure_label",
            "not_detected",
            "conflict_detected",
        ):
            self.assertIn(key, messages, msg=f"missing key: {key}")
        self.assertIn("Note:", messages["soft_warning"])
        self.assertIn("Generated answer discarded", messages["blocked_intro"])
        self.assertEqual(messages["procedure_label"], "Procedure")
        self.assertEqual(messages["not_detected"], "not detected")

    def test_engine_blocked_answer_uses_italian_messages_by_default(self) -> None:
        from app.rag.engine import HybridRAGEngine
        from app.rag.procedure_guardrails import FactSheet, FactStatus

        engine = HybridRAGEngine()
        sheet = FactSheet(
            procedure_label="OSCAT",
            procedure_ids=("012942/2025",),
            cigs=("B33988ECF0",),
            durations=("48 mesi",),
            amounts=("5.999.723,60 euro",),
            source_ids=("chunk:1",),
            status=FactStatus.VERIFIED,
        )

        rendered = engine._build_guardrail_blocked_answer(sheet)

        self.assertIn("Risposta generata scartata", rendered)
        self.assertIn("Fatti verificati disponibili:", rendered)
        self.assertIn("- Procedura: OSCAT", rendered)
        self.assertIn("- ID procedura: 012942/2025", rendered)
        self.assertIn("- CIG: CIG B33988ECF0", rendered)

    def test_engine_soft_warning_uses_italian_message_by_default(self) -> None:
        from app.rag.engine import HybridRAGEngine

        engine = HybridRAGEngine()
        rendered = engine._append_guardrail_soft_warning("Risposta narrativa.")

        self.assertIn("Nota:", rendered)
        self.assertIn("non verificabili dalle fonti recuperate", rendered)
        self.assertTrue(rendered.startswith("Risposta narrativa."))


class QAEngineAssetsTests(unittest.TestCase):
    """Verify that QA prompt templates are sourced from MD assets."""

    def test_qa_continuation_template_loaded_from_italian_asset(self) -> None:
        from app.rag.localization import get_prompt_template_text

        wrapped = get_prompt_template_text("qa-continuation", "it")
        direct = load_prompt_template("qa-continuation", language="it")

        self.assertEqual(wrapped, direct)
        self.assertIn("ISTRUZIONI IMPORTANTI", wrapped)
        self.assertIn("{query}", wrapped)
        self.assertIn("{context}", wrapped)
        self.assertIn("{current_answer_tail}", wrapped)

    def test_qa_sentence_closure_template_loaded_from_italian_asset(self) -> None:
        from app.rag.localization import get_prompt_template_text

        wrapped = get_prompt_template_text("qa-sentence-closure", "it")
        direct = load_prompt_template("qa-sentence-closure", language="it")

        self.assertEqual(wrapped, direct)
        self.assertIn("ISTRUZIONI IMPORTANTI", wrapped)
        self.assertIn("60 parole", wrapped)

    def test_english_qa_assets_load_with_placeholders(self) -> None:
        en_continuation = load_prompt_template("qa-continuation", language="en")
        en_closure = load_prompt_template("qa-sentence-closure", language="en")

        self.assertIn("IMPORTANT INSTRUCTIONS", en_continuation)
        self.assertIn("{query}", en_continuation)
        self.assertIn("{context}", en_continuation)
        self.assertIn("{current_answer_tail}", en_continuation)

        self.assertIn("IMPORTANT INSTRUCTIONS", en_closure)
        self.assertIn("60 words", en_closure)


class IntentRegexesAssetsTests(unittest.TestCase):
    """Verify that intent regexes are built from query-intent.md assets."""

    def test_italian_intent_regexes_match_known_inputs(self) -> None:
        from app.rag.localization import get_intent_regexes

        intent = get_intent_regexes("it")

        self.assertIsNotNone(intent.tender_document.search("descrivi la gara OSCAT"))
        self.assertIsNotNone(intent.tender_document.search("bando di gara"))
        self.assertIsNotNone(intent.summary_intent.search("riassumi i punti"))
        self.assertIsNotNone(intent.expanded_explanation.search("spiega il capitolato"))
        self.assertIsNotNone(intent.structured_overview.search("elenco dettagliato"))
        self.assertIsNotNone(intent.integrity_pact_query.search("patto di integrita"))
        self.assertIsNotNone(intent.plural_day.search("scadenza tra 30 giorno"))
        self.assertIsNotNone(intent.math_rendering_request.search("usa LaTeX"))
        self.assertIsNotNone(intent.continuation_heading.match("## Continuazione capitolo 1"))
        self.assertIsNotNone(
            intent.length_meta_paragraph.search("le parole sono troppo poche")
        )
        self.assertIsNotNone(intent.word_count_request.search("scrivi 1500 parole"))
        self.assertIsNotNone(intent.line_count_request.search("scrivi 200 righe"))
        self.assertIsNotNone(
            intent.generic_tender_indefinite.search("cos'e una gara")
        )
        self.assertIsNotNone(
            intent.generic_tender_concept.search("la procedura aperta")
        )
        self.assertIsNotNone(
            intent.generic_tender_definition.search("cos'e un appalto")
        )
        self.assertIn("di", intent.incomplete_sentence_end_tokens)
        self.assertIn("answer", intent.prompt_garbage_prefix_tokens)

    def test_english_intent_regexes_match_known_inputs(self) -> None:
        from app.rag.localization import get_intent_regexes

        intent = get_intent_regexes("en")

        self.assertIsNotNone(intent.tender_document.search("describe the tender"))
        self.assertIsNotNone(intent.summary_intent.search("summarize the bid"))
        self.assertIsNotNone(intent.word_count_request.search("write 1500 words"))
        self.assertIsNotNone(intent.continuation_heading.match("## Continuation"))
        self.assertIsNotNone(intent.integrity_pact_query.search("integrity pact"))
        self.assertIn("of", intent.incomplete_sentence_end_tokens)
        self.assertIn("answer", intent.prompt_garbage_prefix_tokens)

    def test_engine_module_constants_match_italian_intent_regexes(self) -> None:
        from app.rag import engine
        from app.rag.localization import get_intent_regexes

        intent = get_intent_regexes("it")

        self.assertIs(engine.WORD_COUNT_REQUEST_RE, intent.word_count_request)
        self.assertIs(engine.LINE_COUNT_REQUEST_RE, intent.line_count_request)
        self.assertIs(engine.SUMMARY_INTENT_QUERY_RE, intent.summary_intent)
        self.assertIs(engine.TENDER_DOCUMENT_QUERY_RE, intent.tender_document)
        self.assertIs(engine.STRUCTURED_OVERVIEW_QUERY_RE, intent.structured_overview)
        self.assertIs(engine.INTEGRITY_PACT_CONTEXT_RE, intent.integrity_pact_context)
        self.assertIs(engine.PLURAL_DAY_RE, intent.plural_day)
        self.assertIs(engine.MATH_RENDERING_REQUEST_RE, intent.math_rendering_request)
        self.assertEqual(
            engine.PROMPT_GARBAGE_PREFIX_TOKENS, intent.prompt_garbage_prefix_tokens
        )

    def test_get_intent_regexes_rejects_unsupported_language(self) -> None:
        from app.rag.localization import get_intent_regexes

        with self.assertRaises(ValueError):
            get_intent_regexes("fr")


class PromptLeakageRegexesAssetsTests(unittest.TestCase):
    """Verify prompt-leakage regexes are built from prompt-leakage.md."""

    def test_italian_leakage_regexes_match_known_inputs(self) -> None:
        from app.rag.localization import get_prompt_leakage_regexes

        leak = get_prompt_leakage_regexes("it")

        self.assertIsNotNone(leak.heading.match("## Domanda Utente: testo"))
        self.assertIsNotNone(leak.heading.match("Own Answer: testo"))
        self.assertIsNotNone(
            leak.loop.match("own answer your answer answer ")
        )
        self.assertIsNotNone(leak.own_token_loop.match("own own own"))
        self.assertIsNotNone(leak.own_token_prefix.match("own own own resto"))
        self.assertIsNotNone(
            leak.likely_user_query_start.match("descrivi la procedura")
        )
        self.assertIsNotNone(
            leak.likely_user_query_start.match("riassumi questo")
        )
        self.assertIsNone(leak.likely_user_query_start.match("la procedura e"))

        instruction_hits = sum(
            1
            for line in (
                "scrivi solo il seguito naturale della risposta, "
                "iniziando direttamente dal contenuto mancante.",
                "respond in the same language as the user's question.",
                "use only the retrieved context.",
                "- non commentare il numero di parole.",
                "- chiudi con una frase completa e coerente.",
            )
            for pattern in leak.instruction_lines
            if pattern.match(line)
        )
        self.assertGreaterEqual(instruction_hits, 5)

    def test_english_leakage_regexes_match_known_inputs(self) -> None:
        from app.rag.localization import get_prompt_leakage_regexes

        leak = get_prompt_leakage_regexes("en")

        self.assertIsNotNone(leak.heading.match("## User Question: text"))
        self.assertIsNotNone(leak.heading.match("Own Answer: text"))
        self.assertIsNotNone(
            leak.likely_user_query_start.match("describe the procedure")
        )

    def test_engine_module_uses_localized_leakage_regexes(self) -> None:
        from app.rag import engine
        from app.rag.localization import get_prompt_leakage_regexes

        leak = get_prompt_leakage_regexes("it")

        self.assertIs(engine.PROMPT_LEAKAGE_HEADING_RE, leak.heading)
        self.assertIs(engine.PROMPT_LEAKAGE_INLINE_RE, leak.inline)
        self.assertIs(engine.PROMPT_LEAKAGE_LOOP_RE, leak.loop)
        self.assertIs(engine.PROMPT_OWN_TOKEN_LOOP_RE, leak.own_token_loop)
        self.assertIs(engine.PROMPT_LEAKAGE_SUFFIX_RE, leak.suffix)
        self.assertIs(engine.LIKELY_USER_QUERY_START_RE, leak.likely_user_query_start)
        self.assertEqual(
            engine.PROMPT_LEAKAGE_INSTRUCTION_RES,
            leak.instruction_lines,
        )


class ConsolidatedLocalizationApiTests(unittest.TestCase):
    """R7 — consolidated localization API surface (dataclass + cached getters)."""

    def test_get_guardrail_messages_returns_dataclass_for_italian(self) -> None:
        from app.rag.localization import GuardrailMessages, get_guardrail_messages

        messages = get_guardrail_messages("it")

        self.assertIsInstance(messages, GuardrailMessages)
        self.assertEqual(messages.procedure_label, "Procedura")
        self.assertEqual(messages.not_detected, "non rilevato")
        self.assertIn("Nota:", messages.soft_warning)

    def test_get_guardrail_messages_returns_dataclass_for_english(self) -> None:
        from app.rag.localization import get_guardrail_messages

        messages = get_guardrail_messages("en")

        self.assertEqual(messages.procedure_label, "Procedure")
        self.assertEqual(messages.not_detected, "not detected")
        self.assertIn("Note:", messages.soft_warning)

    def test_get_guardrail_messages_caches_per_language(self) -> None:
        from app.rag.localization import get_guardrail_messages

        first = get_guardrail_messages("it")
        second = get_guardrail_messages("it")

        self.assertIs(first, second)

    def test_get_prompt_template_text_matches_low_level_loader(self) -> None:
        from app.rag.localization import get_prompt_template_text

        wrapped = get_prompt_template_text("qa-continuation", "it")
        direct = load_prompt_template("qa-continuation", language="it")

        self.assertEqual(wrapped, direct)

    def test_engine_constants_use_consolidated_api(self) -> None:
        from app.rag import engine
        from app.rag.localization import (
            get_guardrail_messages,
            get_prompt_template_text,
        )
        from app.rag.procedure_guardrails import FactSheet

        # QA prompt templates are now resolved per-request via
        # ``get_prompt_template_text`` rather than via module-level constants.
        self.assertTrue(get_prompt_template_text("qa-continuation", "it").strip())

        instance = engine.HybridRAGEngine()
        rendered = instance._build_guardrail_blocked_answer(
            FactSheet(procedure_label="OSCAT")
        )
        messages = get_guardrail_messages("it")

        self.assertIn(messages.fact_sheet_heading, rendered)
        self.assertIn(messages.procedure_label, rendered)


class PerRequestLanguageOverrideTests(unittest.TestCase):
    """R8 — RAGQuery.language enables per-request locale override."""

    def test_resolve_query_language_uses_rag_query_override(self) -> None:
        from app.rag.engine import QueryMode, RAGQuery, _resolve_query_language

        query = RAGQuery(text="describe", mode=QueryMode.QA, language="en")

        self.assertEqual(_resolve_query_language(query), "en")

    def test_resolve_query_language_falls_back_to_default_when_unset(self) -> None:
        from app.rag.engine import QueryMode, RAGQuery, _resolve_query_language

        query = RAGQuery(text="descrivi", mode=QueryMode.QA)

        self.assertEqual(_resolve_query_language(query), "it")

    def test_resolve_query_language_ignores_unsupported_value(self) -> None:
        from app.rag.engine import QueryMode, RAGQuery, _resolve_query_language

        query = RAGQuery(text="describe", mode=QueryMode.QA, language="fr")

        self.assertEqual(_resolve_query_language(query), "it")

    def test_blocked_answer_localizes_to_english_when_query_language_is_en(self) -> None:
        from app.rag.engine import HybridRAGEngine
        from app.rag.procedure_guardrails import FactSheet

        engine = HybridRAGEngine()
        sheet = FactSheet(procedure_label="OSCAT", procedure_ids=("012942/2025",))

        rendered = engine._build_guardrail_blocked_answer(sheet, language="en")

        self.assertIn("Generated answer discarded", rendered)
        self.assertIn("Verified facts available:", rendered)
        self.assertIn("- Procedure: OSCAT", rendered)

    def test_soft_warning_localizes_to_english_when_language_override(self) -> None:
        from app.rag.engine import HybridRAGEngine

        rendered = HybridRAGEngine._append_guardrail_soft_warning(
            "Narrative answer.", language="en"
        )

        self.assertIn("Note:", rendered)
        self.assertNotIn("Nota:", rendered)


if __name__ == "__main__":
    unittest.main()
