"""Compiled localization assets for the RAG engine.

This module owns the lazy-cached construction of regex patterns and token
lists from the Markdown assets under ``app/rag/internalprompting/{lang}/``.
The engine consumes the resulting ``IntentRegexes`` dataclass instead of
hard-coding Italian-only patterns.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING

from app.rag.internal_prompting import (
    default_language,
    load_keyword_group,
    load_localized_messages,
    load_prompt_template,
)

if TYPE_CHECKING:
    from app.rag.procedure_profiles import ProcedureProfile

_INTENT_ASSET = "query-intent"
_PROMPT_LEAKAGE_ASSET = "prompt-leakage"
_GUARDRAIL_MESSAGES_ASSET = "guardrail-messages"
_GUARDRAIL_REPAIR_MESSAGES_ASSET = "guardrail-repair-messages"
_GUARDRAIL_LEXICON_ASSET = "guardrail-lexicon"
_GUARDRAIL_PATTERNS_ASSET = "guardrail-patterns"
_CONTEXT_QUALITY_ASSET = "context-quality"

# Numeric money skeleton — locale-invariant, owned here so the money regexes
# can be rebuilt entirely from this module while currency/million words come
# from the asset.
_GUARDRAIL_MONEY_NUMBER = r"(?:\d{1,3}(?:\.\d{3})+|\d+)(?:[,.]\d{2})?"
_GUARDRAIL_MONEY_GUARDED = rf"(?<![\d.,])\b{_GUARDRAIL_MONEY_NUMBER}"
_ENGINE_MESSAGES_ASSET = "engine-messages"
_ENGINE_CONSTRAINTS_ASSET = "engine-constraints"
_ENGINE_CLEANUP_ASSET = "engine-cleanup-patterns"
_ENGINE_LANGUAGE_MARKERS_ASSET = "engine-language-markers"
_GENERATOR_MESSAGES_ASSET = "generator-messages"
_GRAPH_RETRIEVER_MESSAGES_ASSET = "graph-retriever-messages"
_PLANNING_COVERAGE_MESSAGES_ASSET = "planning-coverage"

GENERATOR_TEMPLATE_ASSETS: dict[str, str] = {
    "proposal_section": "proposal-section",
    "executive_summary": "executive-summary",
    "requirement_analyzer": "requirement-analyzer",
    "requirement_extractor_v2": "requirement-extractor-v2",
    "participation_requirement_extractor_v1": "participation-requirement-extractor-v1",
    "compliance_checker": "compliance-checker",
    "general_qa": "general-qa",
    "tender_overview": "tender-overview",
    "tender_longform_synthesis": "tender-longform-synthesis",
}


def _alt(fragments: tuple[str, ...]) -> str:
    if not fragments:
        raise ValueError("alternation requires at least one fragment")
    return "|".join(fragments)


@dataclass(frozen=True)
class EngineMessages:
    """Localized labels and short messages used by the engine module.

    Both the engine serializer and the procedure_guardrails parser bind to
    the same bundle resolved via :func:`default_language` so the wire
    protocol stays consistent within the process. The FACT_SHEET start/end
    markers stay locale-invariant by design (same value in both files).
    """

    fact_sheet_heading_text: str
    fact_sheet_start_marker: str
    fact_sheet_end_marker: str
    fact_sheet_label_procedure: str
    fact_sheet_label_status: str
    fact_sheet_label_procedure_id: str
    fact_sheet_label_cig: str
    fact_sheet_label_critical_days: str
    fact_sheet_label_duration: str
    fact_sheet_label_amounts: str
    fact_sheet_label_locations: str
    fact_sheet_label_percentages: str
    fact_sheet_label_sources: str
    fact_sheet_label_conflicts: str
    fact_sheet_value_not_detected: str
    fact_sheet_value_no_conflicts: str
    fact_sheet_value_conflict_detected: str
    procedure_label_unattributed: str
    model_unavailable_fallback: str
    length_unit_lines: str
    length_unit_words: str


@dataclass(frozen=True)
class EngineResponseConstraints:
    """Constraint sentence templates emitted by ``_build_response_constraints``."""

    general: tuple[str, ...]
    length_target_templates: tuple[str, ...]
    lines_mode: tuple[str, ...]
    no_length_target: tuple[str, ...]
    expanded_explanation: tuple[str, ...]
    broad_summary: tuple[str, ...]
    structured_overview_sections: tuple[str, ...]
    structured_overview_heading: tuple[str, ...]
    structured_overview: tuple[str, ...]
    math_rendering: tuple[str, ...]


@dataclass(frozen=True)
class EngineCleanupPatterns:
    """Compiled cleanup patterns for ``_clean_generation_artifacts``."""

    ocr_replacements: tuple[tuple[re.Pattern[str], str], ...]
    continuation_skip_prefixes: tuple[str, ...]
    broken_numeric_patterns: tuple[re.Pattern[str], ...]
    critical_numeric_patterns: tuple[re.Pattern[str], ...]


@dataclass(frozen=True)
class EngineLanguageMarkers:
    """Cross-lingual marker tuples for retrieval-language detection."""

    italian_markers: tuple[str, ...]
    english_markers: tuple[str, ...]


@dataclass(frozen=True)
class GeneratorMessages:
    """Localized strings used by ``Generator`` for the ``general_qa`` template."""

    system_message_general_qa: str
    question_detection_keywords: tuple[str, ...]


@dataclass(frozen=True)
class GraphRetrieverMessages:
    """Localized strings used by ``GraphRetriever`` for result text and logs."""

    graph_connected: str
    graph_schema_ensured: str
    tender_upserted: str
    project_added: str
    graph_search_complete: str
    label_requirement: str
    label_category: str
    label_priority: str
    label_ontology: str
    label_tender: str
    label_page: str
    label_client: str
    label_status: str
    label_deadline: str
    label_known_requirements: str
    label_description: str
    label_year: str
    label_team: str
    label_certifications: str
    label_team_member: str
    label_title: str
    label_experience: str
    label_projects: str
    default_role_team_member: str
    na: str
    unknown: str
    gold_domain_mapping: dict[str, set[str]]
    ontology_domain_mapping: dict[str, set[str]]
    query_stopwords: set[str]
    query_terms: dict[str, tuple[str, ...]]
    allowed_ontology_domains: frozenset[str]


@dataclass(frozen=True)
class PlanningCoverageMessages:
    """Localized labels, notes, and slot definitions for planning coverage."""

    slot_labels: dict[str, str]
    tender_query_terms: tuple[str, ...]
    note_disabled: str
    note_not_tender: str
    note_activated_tender: str
    note_activated_always: str
    note_no_slot_activated: str
    error_sparse_retrieval: str
    error_dense_retrieval: str
    error_graph_retrieval: str
    slot_triggers: dict[str, tuple[str, ...]]
    slot_queries: dict[str, tuple[str, ...]]
    slot_evidence: dict[str, tuple[str, ...]]


@dataclass(frozen=True)
class GuardrailRepairMessages:
    """Replacement strings emitted by the procedure_guardrails repair layer."""

    unverified_procedure_id: str
    unverified_cig: str
    unverified_amount: str
    unverified_term: str
    unverified_days: str
    unverified_duration: str
    unverified_percentage: str
    unverified_location: str
    unverified_article: str
    fragment_procedure_id_label: str
    fragment_cig_label: str
    fragment_duration_label: str
    fragment_amounts_label: str
    fragment_locations_label: str
    verified_data_intro: str
    distinct_amounts_template: str
    blocked_output: str
    unit_days: str
    unit_months: str
    unit_years: str
    conjunction_and: str


# Base RAG knows no tender-specific procedure labels. Labels are supplied by
# the active profile layer (app.rag.procedure_profiles).
_GUARDRAIL_PROCEDURE_LABELS: tuple[str, ...] = ()
_GUARDRAIL_SEMANTIC_THEMES: tuple[str, ...] = ("garanzie", "manleva", "integrita")


@dataclass(frozen=True)
class GuardrailLexicon:
    """Anchor/keyword lists used by the deterministic guardrail classifier.

    ``procedure_anchors`` maps the canonical procedure label to its anchor
    tuple; ``semantic_theme_keywords`` maps the canonical theme key to its
    keyword set; ``comparison_markers`` lists stems that signal an explicit
    comparison request. Labels and theme keys stay canonical in code — only
    the members are externalized to the Markdown asset.
    """

    procedure_anchors: dict[str, tuple[str, ...]]
    semantic_theme_keywords: dict[str, frozenset[str]]
    comparison_markers: tuple[str, ...]


@dataclass(frozen=True)
class GuardrailPatterns:
    """Compiled regex bundle for the deterministic guardrail layer.

    Each field mirrors a module-level pattern that previously lived in
    ``procedure_guardrails``. The structural skeleton stays here; only the
    Italian token alternations come from the ``guardrail-patterns`` asset.
    Pattern-string equivalence with the pre-extraction literals is asserted
    by the parity suite, so behavior is preserved.
    """

    procedure_id_field: re.Pattern[str]
    incomplete_procedure_id: re.Pattern[str]
    day: re.Pattern[str]
    month: re.Pattern[str]
    year: re.Pattern[str]
    money: re.Pattern[str]
    money_million: re.Pattern[str]
    address: re.Pattern[str]
    service_location: re.Pattern[str]
    placeholder: re.Pattern[str]
    day_placeholder: re.Pattern[str]
    incomplete_cig: re.Pattern[str]
    masked_cig_with_value: re.Pattern[str]
    inline_unverified_procedure_id: re.Pattern[str]
    inline_unverified_cig: re.Pattern[str]
    oscat_sct_contamination: re.Pattern[str]
    oscat_identity_keyword: re.Pattern[str]
    malformed_article: re.Pattern[str]
    duration_range: re.Pattern[str]
    civil_article_thousand_sep: re.Pattern[str]
    money_range_narrative: re.Pattern[str]
    false_missing_marker: re.Pattern[str]
    procedure_id_false_missing: re.Pattern[str]
    false_missing_field_res: tuple[tuple[str, re.Pattern[str]], ...]


@dataclass(frozen=True)
class ContextQuality:
    """Compiled regex/lexicon bundle for ``context_quality`` hygiene helpers.

    Structural skeletons (numeric, lookaround) stay in the builder; only the
    Italian/English token alternations come from the ``context-quality``
    asset. Section bodies are identical across ``it``/``en``.
    """

    numeric_or_legal: re.Pattern[str]
    broad_tender_query: re.Pattern[str]
    tender_overview_terms: frozenset[str]
    query_stopwords: frozenset[str]


@dataclass(frozen=True)
class GuardrailMessages:
    """User-facing strings emitted by the engine guardrail layer."""

    soft_warning: str
    blocked_intro: str
    fact_sheet_heading: str
    procedure_label: str
    procedure_id_label: str
    cig_label: str
    critical_days_label: str
    duration_label: str
    amounts_label: str
    locations_label: str
    percentages_label: str
    sources_label: str
    not_detected: str
    conflict_detected: str


@dataclass(frozen=True)
class PromptLeakageRegexes:
    """Compiled regex bundle for prompt-leakage detection in LLM output."""

    plain_label_pattern: str
    plain_answer_label_pattern: str
    heading_only_label_pattern: str
    loop: re.Pattern[str]
    own_token_loop: re.Pattern[str]
    own_token_prefix: re.Pattern[str]
    suffix: re.Pattern[str]
    likely_user_query_start: re.Pattern[str]
    heading: re.Pattern[str]
    inline: re.Pattern[str]
    instruction_lines: tuple[re.Pattern[str], ...]


@dataclass(frozen=True)
class IntentRegexes:
    """Bundle of compiled regex patterns and token sets for a single language."""

    word_count_request: re.Pattern[str]
    line_count_request: re.Pattern[str]
    expanded_explanation: re.Pattern[str]
    summary_intent: re.Pattern[str]
    structured_overview: re.Pattern[str]
    tender_document: re.Pattern[str]
    generic_tender_definition: re.Pattern[str]
    generic_tender_indefinite: re.Pattern[str]
    generic_tender_concept: re.Pattern[str]
    retrieval_intent_strip: re.Pattern[str]
    retrieval_stopword_strip: re.Pattern[str]
    math_rendering_request: re.Pattern[str]
    length_meta_paragraph: re.Pattern[str]
    integrity_pact_context: re.Pattern[str]
    integrity_pact_query: re.Pattern[str]
    continuation_heading: re.Pattern[str]
    plural_day: re.Pattern[str]
    incomplete_sentence_end_tokens: frozenset[str]
    prompt_garbage_prefix_tokens: frozenset[str]


def _resolve_language(language: str | None) -> str:
    if language is None:
        return default_language()
    if language not in {"it", "en"}:
        raise ValueError("language must be 'it' or 'en'")
    return language


def _group(language: str, group_name: str) -> tuple[str, ...]:
    return load_keyword_group(_INTENT_ASSET, group_name, language=language)


def _leak_group(language: str, group_name: str) -> tuple[str, ...]:
    return load_keyword_group(_PROMPT_LEAKAGE_ASSET, group_name, language=language)


@lru_cache(maxsize=4)
def get_engine_messages(language: str | None = None) -> EngineMessages:
    """Return cached engine UI labels and short messages for ``language``."""

    lang = _resolve_language(language)
    raw = load_localized_messages(_ENGINE_MESSAGES_ASSET, language=lang)

    def required(key: str) -> str:
        if key not in raw:
            raise KeyError(
                f"Missing required engine message key '{key}' for language '{lang}'"
            )
        return raw[key]

    return EngineMessages(
        fact_sheet_heading_text=required("fact_sheet_heading_text"),
        fact_sheet_start_marker=required("fact_sheet_start_marker"),
        fact_sheet_end_marker=required("fact_sheet_end_marker"),
        fact_sheet_label_procedure=required("fact_sheet_label_procedure"),
        fact_sheet_label_status=required("fact_sheet_label_status"),
        fact_sheet_label_procedure_id=required("fact_sheet_label_procedure_id"),
        fact_sheet_label_cig=required("fact_sheet_label_cig"),
        fact_sheet_label_critical_days=required("fact_sheet_label_critical_days"),
        fact_sheet_label_duration=required("fact_sheet_label_duration"),
        fact_sheet_label_amounts=required("fact_sheet_label_amounts"),
        fact_sheet_label_locations=required("fact_sheet_label_locations"),
        fact_sheet_label_percentages=required("fact_sheet_label_percentages"),
        fact_sheet_label_sources=required("fact_sheet_label_sources"),
        fact_sheet_label_conflicts=required("fact_sheet_label_conflicts"),
        fact_sheet_value_not_detected=required("fact_sheet_value_not_detected"),
        fact_sheet_value_no_conflicts=required("fact_sheet_value_no_conflicts"),
        fact_sheet_value_conflict_detected=required("fact_sheet_value_conflict_detected"),
        procedure_label_unattributed=required("procedure_label_unattributed"),
        model_unavailable_fallback=required("model_unavailable_fallback"),
        length_unit_lines=required("length_unit_lines"),
        length_unit_words=required("length_unit_words"),
    )


@lru_cache(maxsize=4)
def get_engine_response_constraints(
    language: str | None = None,
) -> EngineResponseConstraints:
    """Return cached response-constraint sentence groups for ``language``."""

    lang = _resolve_language(language)

    def group(name: str) -> tuple[str, ...]:
        return load_keyword_group(_ENGINE_CONSTRAINTS_ASSET, name, language=lang)

    return EngineResponseConstraints(
        general=group("General Constraints"),
        length_target_templates=group("Length Target Constraints"),
        lines_mode=group("Lines Mode Constraint"),
        no_length_target=group("No Length Target Constraint"),
        expanded_explanation=group("Expanded Explanation Constraint"),
        broad_summary=group("Broad Summary Constraint"),
        structured_overview_sections=group("Structured Overview Sections"),
        structured_overview_heading=group("Structured Overview Heading"),
        structured_overview=group("Structured Overview Constraints"),
        math_rendering=group("Math Rendering Constraints"),
    )


def _parse_ocr_replacement_line(raw_line: str) -> tuple[re.Pattern[str], str]:
    if "||" not in raw_line:
        raise ValueError(
            f"Invalid OCR replacement line (missing '||' separator): {raw_line!r}"
        )
    pattern_text, replacement = raw_line.split("||", 1)
    return (
        re.compile(pattern_text.strip(), re.IGNORECASE),
        replacement.strip(),
    )


@lru_cache(maxsize=4)
def get_engine_cleanup_patterns(
    language: str | None = None,
) -> EngineCleanupPatterns:
    """Return cached engine cleanup pattern bundle for ``language``."""

    lang = _resolve_language(language)

    def group(name: str) -> tuple[str, ...]:
        return load_keyword_group(_ENGINE_CLEANUP_ASSET, name, language=lang)

    ocr_pairs = tuple(
        _parse_ocr_replacement_line(line) for line in group("OCR Replacements")
    )
    skip_prefixes = tuple(item.casefold() for item in group("Continuation Skip Prefixes"))
    broken = tuple(re.compile(item, re.IGNORECASE) for item in group("Broken Numeric Patterns"))
    critical = tuple(re.compile(item, re.IGNORECASE) for item in group("Critical Numeric Patterns"))

    return EngineCleanupPatterns(
        ocr_replacements=ocr_pairs,
        continuation_skip_prefixes=skip_prefixes,
        broken_numeric_patterns=broken,
        critical_numeric_patterns=critical,
    )


@lru_cache(maxsize=4)
def get_engine_language_markers(
    language: str | None = None,
) -> EngineLanguageMarkers:
    """Return cached cross-lingual retrieval-detection marker tuples."""

    lang = _resolve_language(language)
    italian = load_keyword_group(
        _ENGINE_LANGUAGE_MARKERS_ASSET, "Italian Markers", language=lang
    )
    english = load_keyword_group(
        _ENGINE_LANGUAGE_MARKERS_ASSET, "English Markers", language=lang
    )
    return EngineLanguageMarkers(
        italian_markers=italian,
        english_markers=english,
    )


@lru_cache(maxsize=4)
def get_guardrail_repair_messages(
    language: str | None = None,
) -> GuardrailRepairMessages:
    """Return cached repair-layer replacement strings for ``language``."""

    lang = _resolve_language(language)
    raw = load_localized_messages(_GUARDRAIL_REPAIR_MESSAGES_ASSET, language=lang)

    def required(key: str) -> str:
        if key not in raw:
            raise KeyError(
                f"Missing required guardrail repair message key '{key}' for "
                f"language '{lang}'"
            )
        return raw[key]

    return GuardrailRepairMessages(
        unverified_procedure_id=required("unverified_procedure_id"),
        unverified_cig=required("unverified_cig"),
        unverified_amount=required("unverified_amount"),
        unverified_term=required("unverified_term"),
        unverified_days=required("unverified_days"),
        unverified_duration=required("unverified_duration"),
        unverified_percentage=required("unverified_percentage"),
        unverified_location=required("unverified_location"),
        unverified_article=required("unverified_article"),
        fragment_procedure_id_label=required("fragment_procedure_id_label"),
        fragment_cig_label=required("fragment_cig_label"),
        fragment_duration_label=required("fragment_duration_label"),
        fragment_amounts_label=required("fragment_amounts_label"),
        fragment_locations_label=required("fragment_locations_label"),
        verified_data_intro=required("verified_data_intro"),
        distinct_amounts_template=required("distinct_amounts_template"),
        blocked_output=required("blocked_output"),
        unit_days=required("unit_days"),
        unit_months=required("unit_months"),
        unit_years=required("unit_years"),
        conjunction_and=required("conjunction_and"),
    )


@lru_cache(maxsize=4)
def get_guardrail_lexicon(language: str | None = None) -> GuardrailLexicon:
    """Return cached guardrail anchor/keyword lexicon for ``language``."""

    lang = _resolve_language(language)

    procedure_anchors = {
        label: load_keyword_group(
            _GUARDRAIL_LEXICON_ASSET,
            f"Procedure Anchors {label}",
            language=lang,
        )
        for label in _GUARDRAIL_PROCEDURE_LABELS
    }
    semantic_theme_keywords = {
        theme: frozenset(
            load_keyword_group(
                _GUARDRAIL_LEXICON_ASSET,
                f"Semantic Theme {theme}",
                language=lang,
            )
        )
        for theme in _GUARDRAIL_SEMANTIC_THEMES
    }
    comparison_markers = load_keyword_group(
        _GUARDRAIL_LEXICON_ASSET,
        "Comparison Markers",
        language=lang,
    )

    return GuardrailLexicon(
        procedure_anchors=procedure_anchors,
        semantic_theme_keywords=semantic_theme_keywords,
        comparison_markers=comparison_markers,
    )


def procedure_anchors_for_profiles(
    profiles: tuple[ProcedureProfile, ...],
    *,
    language: str | None = None,
) -> dict[str, tuple[str, ...]]:
    """Base anchors (currently empty) merged with the active profiles' anchors."""
    from app.rag.procedure_profiles import active_procedure_anchors

    base = dict(get_guardrail_lexicon(_resolve_language(language)).procedure_anchors)
    for label, anchors in active_procedure_anchors(profiles).items():
        base[label] = (*base.get(label, ()), *anchors)
    return base


@lru_cache(maxsize=4)
def _get_guardrail_patterns_base(language: str | None = None) -> GuardrailPatterns:
    """Return cached compiled guardrail regex bundle for ``language``.

    Structural skeletons live here verbatim; only the Italian token
    alternations are sourced from the ``guardrail-patterns`` asset so the
    rebuilt pattern strings stay equivalent to the pre-extraction literals.

    This is the profile-agnostic cached base. ``ProcedureProfile`` instances
    are unhashable, so the active-profile overlay is applied OUTSIDE this
    cached layer by the public ``get_guardrail_patterns`` wrapper.
    """

    lang = _resolve_language(language)

    def grp(name: str) -> str:
        return _alt(
            load_keyword_group(_GUARDRAIL_PATTERNS_ASSET, name, language=lang)
        )

    flags = re.IGNORECASE
    g = _GUARDRAIL_MONEY_GUARDED

    field_label = grp("Procedure Id Field Label")
    prefix_alt = grp("Procedure Id Prefix Alternatives")
    day = grp("Day Word")
    day_plural = grp("Day Plural Word")
    month = grp("Month Word")
    year = grp("Year Word")
    neg = grp("Negation Word")
    status = grp("Unverified Status Words")
    adj = grp("Unverified Adjective")
    syn = grp("Procedure Id Synonyms")
    currency = grp("Money Currency Words")
    million = grp("Money Million Words")
    of = grp("Money Of Connector")
    address = grp("Address Pattern")
    loc_lead = grp("Service Location Lead")
    copula = grp("Copula Forms")
    loc_article = grp("Service Location Article")
    region = grp("Region Word")
    day_leads = grp("Placeholder Day Leads")
    art_words = grp("Article Words")
    art_compact = grp("Article Word Compact")
    civil = grp("Civil Code Phrase")
    range_lead = grp("Duration Range Lead")
    range_arts = grp("Duration Range Articles")
    range_conns = grp("Duration Range Connectors")
    money_verbs = grp("Money Range Verbs")
    money_conns = grp("Money Range Connectors")
    contamination = grp("Contamination Markers")
    identity = grp("Identity Markers")
    false_missing = grp("False Missing Markers")
    field_duration = grp("Field Duration Words")
    field_amount = grp("Field Amount Words")
    field_location = grp("Field Location Words")

    money_expr = (
        rf"(?:€\s*{g}|"
        rf"(?:{currency})\s+{g}|"
        rf"{g}\s*(?:€|{currency}))"
    )

    return GuardrailPatterns(
        procedure_id_field=re.compile(
            rf"(?P<prefix>\b{field_label}\s*:\s*)"
            r"(?P<value>[0-9/\s]{3,30}?)(?=(?:\n\s*[-*])|$|[.;,])",
            flags,
        ),
        incomplete_procedure_id=re.compile(
            rf"\b(?P<prefix>(?:{prefix_alt})\s+)"
            r"(?P<value>[0-9]{5,6}/(?:[0-9](?:\s+[0-9]{1,3})+|[0-9]{1,3}(?![0-9])))\b",
            flags,
        ),
        day=re.compile(rf"(?<![\d/-])\b([1-9][0-9]{{0,3}})\s+(?:{day})\b", flags),
        month=re.compile(rf"(?<![\d/-])\b([1-9][0-9]{{0,2}})\s+(?:{month})\b", flags),
        year=re.compile(rf"(?<![\d/-])\b([1-9][0-9]{{0,2}})\s+(?:{year})\b", flags),
        money=re.compile(
            rf"(?:{g}\s+(?:{million})\s+(?:(?:{of})\s+)?(?:{currency})\b|"
            rf"€\s*{g}\b|"
            rf"\b(?:{currency})\s+{g}\b|"
            rf"{g}\s*(?:€|(?:{currency})\b))",
            flags,
        ),
        money_million=re.compile(rf"\b(?:{million})\b", flags),
        address=re.compile(rf"\b(?:{address})\b", flags),
        service_location=re.compile(
            rf"\b{loc_lead}\s+(?:{copula})\s+{loc_article}\s+"
            rf"({region}\s+[A-Za-zÀ-ÿ' -]+?)(?=\s*(?:\(|[.;,\n]|$))",
            flags,
        ),
        placeholder=re.compile(
            rf"\b(?:{day_leads})\s+(?:{day_plural})\b|"
            rf"\bCIG\s*[:\-]?\s*(?!(?:{neg}\s+(?:{status}))\b)"
            r"(?:[A-Z0-9]{1,7}\b|(?=$|[,.;:)\]\n]))",
            flags,
        ),
        day_placeholder=re.compile(
            rf"\b(?P<prefix>{day_leads})\s+(?:{day_plural})\b",
            flags,
        ),
        incomplete_cig=re.compile(
            rf"\bCIG\s*[:\-]?\s*(?!(?:{neg}\s+(?:{status}))\b)"
            r"(?:[A-Z0-9]{1,7}\b|(?=$|[,.;:)\]\n]))",
            flags,
        ),
        masked_cig_with_value=re.compile(
            rf"\bCIG\s+{neg}\s+(?:{status})\s*[:\-]?\s+[A-Z0-9]{{8,12}}\b",
            flags,
        ),
        inline_unverified_procedure_id=re.compile(
            rf"\b{field_label}\s+{neg}\s+(?:{adj})\b",
            flags,
        ),
        inline_unverified_cig=re.compile(
            rf"\bCIG\s+{neg}\s+(?:{adj})\b",
            flags,
        ),
        oscat_sct_contamination=re.compile(rf"\b(?:{contamination})\b", flags),
        oscat_identity_keyword=re.compile(rf"\b(?:{identity})\b", flags),
        malformed_article=re.compile(
            rf"\b(?:{art_words})\s+(?:\d{{1,4}}[A-Za-z]+\d*|\d{{5,}})"
            rf"(?:\s+(?:{civil}))?",
            flags,
        ),
        duration_range=re.compile(
            rf"\b{range_lead}\s+(?:(?:{range_arts})\s+)?(\d{{1,3}})\s+"
            rf"(?:{range_conns})\s+(?:(?:{range_arts})\s+)?(\d{{1,3}})\s+"
            rf"(?:{month})\b",
            flags,
        ),
        civil_article_thousand_sep=re.compile(
            rf"\b({art_compact})\s+(\d)\.(\d{{3}})\b",
            flags,
        ),
        money_range_narrative=re.compile(
            rf"\b(?:{money_verbs})\s+{range_lead}\s+"
            rf"({money_expr})\s+(?:{money_conns})\s+({money_expr})",
            flags,
        ),
        false_missing_marker=re.compile(rf"\b(?:{false_missing})\b", flags),
        procedure_id_false_missing=re.compile(
            rf"\b(?:{syn})\s*[:\-]?\s*{neg}\s+(?:{status})\b",
            flags,
        ),
        false_missing_field_res=(
            ("procedure_id", re.compile(rf"\b(?:{syn})\b", flags)),
            ("cig", re.compile(r"\bCIG\b", flags)),
            ("duration", re.compile(rf"\b(?:{field_duration})\b", flags)),
            ("amounts", re.compile(rf"\b(?:{field_amount})\b", flags)),
            ("locations", re.compile(rf"\b(?:{field_location})\b", flags)),
        ),
    )


def get_guardrail_patterns(
    language: str | None = None,
    *,
    profiles: tuple[ProcedureProfile, ...] = (),
) -> GuardrailPatterns:
    """Return the compiled guardrail regex bundle for ``language``.

    With no active profiles this returns the cached, profile-agnostic base
    bundle (byte-behavior-equivalent to the pre-decontamination function).
    When profiles are active their contamination/identity/address regex
    fragments are overlaid on top of the generic base markers. Profiles are
    unhashable, so the overlay is computed here, OUTSIDE the cached base.
    """

    base = _get_guardrail_patterns_base(language)
    if not profiles:
        return base

    from dataclasses import replace

    from app.rag.procedure_profiles import (
        active_address_patterns,
        active_contamination_markers,
        active_identity_markers,
    )

    lang = _resolve_language(language)
    flags = re.IGNORECASE  # same flags _get_guardrail_patterns_base compiles these 3 with

    contam = list(
        load_keyword_group(_GUARDRAIL_PATTERNS_ASSET, "Contamination Markers", language=lang)
    )
    contam += list(active_contamination_markers(profiles))
    ident = list(
        load_keyword_group(_GUARDRAIL_PATTERNS_ASSET, "Identity Markers", language=lang)
    )
    ident += list(active_identity_markers(profiles))
    addr = list(
        load_keyword_group(_GUARDRAIL_PATTERNS_ASSET, "Address Pattern", language=lang)
    )
    addr += list(active_address_patterns(profiles))

    return replace(
        base,
        oscat_sct_contamination=re.compile(rf"\b(?:{_alt(tuple(contam))})\b", flags),
        oscat_identity_keyword=re.compile(rf"\b(?:{_alt(tuple(ident))})\b", flags),
        address=re.compile(rf"\b(?:{_alt(tuple(addr))})\b", flags),
    )


@lru_cache(maxsize=4)
def get_context_quality(language: str | None = None) -> ContextQuality:
    """Return cached context-quality regex/lexicon bundle for ``language``.

    Numeric/lookaround skeletons stay here verbatim; only the token
    alternations are sourced from the ``context-quality`` asset so the
    rebuilt pattern strings stay equivalent to the pre-extraction literals.
    """

    lang = _resolve_language(language)

    def keywords(name: str) -> tuple[str, ...]:
        return load_keyword_group(_CONTEXT_QUALITY_ASSET, name, language=lang)

    units = _alt(keywords("Duration Unit Words"))
    currency = _alt(keywords("Money Currency Words"))
    verbs = _alt(keywords("Broad Query Verbs"))
    nouns = _alt(keywords("Tender Noun Markers"))

    return ContextQuality(
        numeric_or_legal=re.compile(
            rf"\b\d{{1,4}}\s+(?:{units})\b"
            rf"|\b(?:{currency})\s*[\d.,]+"
            r"|\b\d{1,3}\s*%"
            r"|\bCIG\s*[:\-]?\s*[A-Z0-9]{8,12}\b"
            r"|\b[0-9]{5,6}/20[0-9]{2}\b"
            r"|\bart\.?\s*\d+[^\s,.;)]*(?:\s*c\.c\.)?",
            re.IGNORECASE,
        ),
        broad_tender_query=re.compile(
            rf"\b(?:{verbs})\b.*\b(?:{nouns})\b"
            rf"|\b(?:{nouns})\b.*\b(?:{verbs})\b",
            re.IGNORECASE,
        ),
        tender_overview_terms=frozenset(keywords("Tender Overview Terms")),
        query_stopwords=frozenset(keywords("Query Stopwords")),
    )


@lru_cache(maxsize=4)
def get_guardrail_messages(language: str | None = None) -> GuardrailMessages:
    """Return cached guardrail user-facing messages for ``language``."""

    lang = _resolve_language(language)
    raw = load_localized_messages(_GUARDRAIL_MESSAGES_ASSET, language=lang)

    def required(key: str) -> str:
        if key not in raw:
            raise KeyError(
                f"Missing required guardrail message key '{key}' for language '{lang}'"
            )
        return raw[key]

    return GuardrailMessages(
        soft_warning=required("soft_warning"),
        blocked_intro=required("blocked_intro"),
        fact_sheet_heading=required("fact_sheet_heading"),
        procedure_label=required("procedure_label"),
        procedure_id_label=required("procedure_id_label"),
        cig_label=required("cig_label"),
        critical_days_label=required("critical_days_label"),
        duration_label=required("duration_label"),
        amounts_label=required("amounts_label"),
        locations_label=required("locations_label"),
        percentages_label=required("percentages_label"),
        sources_label=required("sources_label"),
        not_detected=required("not_detected"),
        conflict_detected=required("conflict_detected"),
    )


@lru_cache(maxsize=4)
def get_generator_messages(language: str | None = None) -> GeneratorMessages:
    """Return cached generator-layer messages and detection keywords."""

    lang = _resolve_language(language)
    raw = load_localized_messages(_GENERATOR_MESSAGES_ASSET, language=lang)

    def required(key: str) -> str:
        if key not in raw:
            raise KeyError(
                f"Missing required generator message key '{key}' for language '{lang}'"
            )
        return raw[key]

    keywords = load_keyword_group(
        _GENERATOR_MESSAGES_ASSET,
        "Question Detection Keywords",
        language=lang,
    )

    return GeneratorMessages(
        system_message_general_qa=required("system_message_general_qa"),
        question_detection_keywords=keywords,
    )


def _load_gold_domain_mapping(language: str) -> dict[str, set[str]]:
    raw = load_localized_messages(_GRAPH_RETRIEVER_MESSAGES_ASSET, language=language)
    gold_prefix = "gold_"
    mapping: dict[str, set[str]] = {}
    for key, value in raw.items():
        if not key.startswith(gold_prefix):
            continue
        parts = value.split("|")
        gold_code = parts[0].strip()
        domains = {d.strip() for d in parts[1:]}
        mapping[gold_code] = domains
    return mapping


def _load_ontology_domain_mapping(language: str) -> dict[str, set[str]]:
    raw = load_localized_messages(_GRAPH_RETRIEVER_MESSAGES_ASSET, language=language)
    return {
        "amministrativo": {
            raw["query_term_administrative"],
            raw["query_term_platform"],
            raw["query_term_subcontracting"],
            raw["query_term_rti"],
            raw["query_term_consortium"],
        },
        "compliance": {
            raw["query_term_certification"],
            raw["query_term_certifications"],
            raw["query_term_iso"],
            raw["query_term_gdpr"],
            raw["query_term_audit"],
        },
        "contrattuale": {
            raw["query_term_penalties"],
            raw["query_term_penalty"],
            raw["query_term_rescission"],
            raw["query_term_withdrawal"],
            raw["query_term_damages"],
            raw["query_term_guarantees"],
        },
        "economico_finanziario": {
            raw["query_term_revenue"],
            raw["query_term_deposit"],
            raw["query_term_insurance"],
            raw["query_term_consideration"],
        },
        "organizzativo": {
            raw["query_term_personnel"],
            raw["query_term_resources"],
            raw["query_term_team"],
            raw["query_term_profiles"],
            raw["query_term_manager"],
        },
        "tecnico": {
            raw["query_term_acn"],
            raw["query_term_oscat"],
            raw["query_term_sct"],
            raw["query_term_sla"],
            raw["query_term_integration"],
            raw["query_term_infrastructure"],
            raw["query_term_services"],
        },
    }


def _load_query_stopwords(language: str) -> set[str]:
    raw = load_localized_messages(_GRAPH_RETRIEVER_MESSAGES_ASSET, language=language)
    return {
        raw["stopword_which"],
        raw["stopword_which_singular"],
        raw["stopword_what"],
        raw["stopword_how"],
        raw["stopword_are"],
        raw["stopword_must"],
        raw["stopword_must_plural"],
        raw["stopword_supplier"],
        raw["stopword_supply"],
        raw["stopword_tender"],
        raw["stopword_contract"],
        raw["stopword_during"],
        raw["stopword_within"],
        raw["stopword_how_much"],
        raw["stopword_times"],
        raw["stopword_requests"],
        raw["stopword_request"],
        raw["stopword_mandatory_plural"],
        raw["stopword_mandatory"],
        raw["stopword_expected"],
        raw["stopword_expected_fem"],
        raw["stopword_agreement"],
        raw["stopword_framework"],
    }


def _load_query_terms(language: str) -> dict[str, tuple[str, ...]]:
    raw = load_localized_messages(_GRAPH_RETRIEVER_MESSAGES_ASSET, language=language)
    return {
        "amministrativo": (
            raw["query_term_administrative"],
            raw["query_term_platform"],
            raw["query_term_subcontracting"],
            raw["query_term_rti"],
            raw["query_term_consortium"],
        ),
        "compliance": (
            raw["query_term_certification"],
            raw["query_term_certifications"],
            raw["query_term_iso"],
            raw["query_term_gdpr"],
            raw["query_term_audit"],
        ),
        "contrattuale": (
            raw["query_term_penalties"],
            raw["query_term_penalty"],
            raw["query_term_rescission"],
            raw["query_term_withdrawal"],
            raw["query_term_damages"],
            raw["query_term_guarantees"],
        ),
        "economico_finanziario": (
            raw["query_term_revenue"],
            raw["query_term_deposit"],
            raw["query_term_insurance"],
            raw["query_term_consideration"],
        ),
        "organizzativo": (
            raw["query_term_personnel"],
            raw["query_term_resources"],
            raw["query_term_team"],
            raw["query_term_profiles"],
            raw["query_term_manager"],
        ),
        "tecnico": (
            raw["query_term_acn"],
            raw["query_term_oscat"],
            raw["query_term_sct"],
            raw["query_term_sla"],
            raw["query_term_integration"],
            raw["query_term_infrastructure"],
            raw["query_term_services"],
        ),
    }


def _load_allowed_ontology_domains(language: str) -> frozenset[str]:
    raw = load_localized_messages(_GRAPH_RETRIEVER_MESSAGES_ASSET, language=language)
    return frozenset({
        raw["allowed_administrative"],
        raw["allowed_economic_financial"],
        raw["allowed_technical"],
        raw["allowed_bonus"],
        raw["allowed_compliance"],
        raw["allowed_contractual"],
        raw["allowed_safety"],
        raw["allowed_organizational"],
        raw["allowed_documentary"],
        raw["allowed_other"],
    })


@lru_cache(maxsize=4)
def get_graph_retriever_messages(language: str | None = None) -> GraphRetrieverMessages:
    """Return cached graph retriever messages for ``language``."""

    lang = _resolve_language(language)
    raw = load_localized_messages(_GRAPH_RETRIEVER_MESSAGES_ASSET, language=lang)

    def required(key: str) -> str:
        if key not in raw:
            raise KeyError(
                f"Missing required graph retriever message key '{key}' for language '{lang}'"
            )
        return raw[key]

    return GraphRetrieverMessages(
        graph_connected=required("graph_connected"),
        graph_schema_ensured=required("graph_schema_ensured"),
        tender_upserted=required("tender_upserted"),
        project_added=required("project_added"),
        graph_search_complete=required("graph_search_complete"),
        label_requirement=required("label_requirement"),
        label_category=required("label_category"),
        label_priority=required("label_priority"),
        label_ontology=required("label_ontology"),
        label_tender=required("label_tender"),
        label_page=required("label_page"),
        label_client=required("label_client"),
        label_status=required("label_status"),
        label_deadline=required("label_deadline"),
        label_known_requirements=required("label_known_requirements"),
        label_description=required("label_description"),
        label_year=required("label_year"),
        label_team=required("label_team"),
        label_certifications=required("label_certifications"),
        label_team_member=required("label_team_member"),
        label_title=required("label_title"),
        label_experience=required("label_experience"),
        label_projects=required("label_projects"),
        default_role_team_member=required("default_role_team_member"),
        na=required("na"),
        unknown=required("unknown"),
        gold_domain_mapping=_load_gold_domain_mapping(lang),
        ontology_domain_mapping=_load_ontology_domain_mapping(lang),
        query_stopwords=_load_query_stopwords(lang),
        query_terms=_load_query_terms(lang),
        allowed_ontology_domains=_load_allowed_ontology_domains(lang),
    )


_SLOT_KEYS = (
    "identification",
    "cig_lots",
    "amounts",
    "duration",
    "deadlines",
    "platform",
    "scoring",
    "certifications",
    "sla_penalties",
    "documents",
)


def _parse_pipe_tuple(raw: str) -> tuple[str, ...]:
    return tuple(p.strip() for p in raw.split("|") if p.strip())


def _load_slot_labels(raw: dict[str, str]) -> dict[str, str]:
    labels: dict[str, str] = {}
    for key in _SLOT_KEYS:
        labels[key] = raw[f"slot_label_{key}"]
    return labels


def _load_slot_triggers(raw: dict[str, str]) -> dict[str, tuple[str, ...]]:
    result: dict[str, tuple[str, ...]] = {}
    for key in _SLOT_KEYS:
        result[key] = _parse_pipe_tuple(raw[f"slot_{key}_trigger"])
    return result


def _load_slot_queries(raw: dict[str, str]) -> dict[str, tuple[str, ...]]:
    result: dict[str, tuple[str, ...]] = {}
    for key in _SLOT_KEYS:
        result[key] = _parse_pipe_tuple(raw[f"slot_{key}_queries"])
    return result


def _load_slot_evidence(raw: dict[str, str]) -> dict[str, tuple[str, ...]]:
    result: dict[str, tuple[str, ...]] = {}
    for key in _SLOT_KEYS:
        result[key] = _parse_pipe_tuple(raw[f"slot_{key}_evidence"])
    return result


@lru_cache(maxsize=4)
def get_planning_coverage_messages(
    language: str | None = None,
) -> PlanningCoverageMessages:
    """Return cached planning coverage labels, notes, and slot definitions."""

    lang = _resolve_language(language)
    raw = load_localized_messages(_PLANNING_COVERAGE_MESSAGES_ASSET, language=lang)

    def required(key: str) -> str:
        if key not in raw:
            raise KeyError(
                f"Missing required planning coverage key '{key}' for language '{lang}'"
            )
        return raw[key]

    return PlanningCoverageMessages(
        slot_labels=_load_slot_labels(raw),
        tender_query_terms=_parse_pipe_tuple(required("tender_query_terms")),
        note_disabled=required("note_disabled"),
        note_not_tender=required("note_not_tender"),
        note_activated_tender=required("note_activated_tender"),
        note_activated_always=required("note_activated_always"),
        note_no_slot_activated=required("note_no_slot_activated"),
        error_sparse_retrieval=required("error_sparse_retrieval"),
        error_dense_retrieval=required("error_dense_retrieval"),
        error_graph_retrieval=required("error_graph_retrieval"),
        slot_triggers=_load_slot_triggers(raw),
        slot_queries=_load_slot_queries(raw),
        slot_evidence=_load_slot_evidence(raw),
    )


@lru_cache(maxsize=8)
def get_prompt_template_text(
    asset_name: str,
    language: str | None = None,
) -> str:
    """Return cached prompt template body for ``asset_name`` and ``language``."""

    lang = _resolve_language(language)
    return load_prompt_template(asset_name, language=lang)


@lru_cache(maxsize=4)
def get_prompt_leakage_regexes(language: str | None = None) -> PromptLeakageRegexes:
    """Return cached prompt-leakage regex bundle for ``language``."""

    lang = _resolve_language(language)

    plain_labels = _alt(_leak_group(lang, "Plain Labels"))
    plain_answer_labels = _alt(_leak_group(lang, "Plain Answer Labels"))
    heading_only_labels = _alt(_leak_group(lang, "Heading Only Answer Labels"))
    loop_labels = _alt(_leak_group(lang, "Loop Labels"))
    inline_trigger_labels = _alt(_leak_group(lang, "Inline Trigger Labels"))
    user_query_verbs = _alt(
        tuple(f"{verb}\\b" for verb in _leak_group(lang, "User Query Verbs"))
    )
    instruction_fragments = _leak_group(lang, "Instruction Lines")

    plain_label_pattern = f"(?:{plain_labels})"
    plain_answer_label_pattern = f"(?:{plain_answer_labels})"
    heading_only_label_pattern = f"(?:{heading_only_labels})"

    return PromptLeakageRegexes(
        plain_label_pattern=plain_label_pattern,
        plain_answer_label_pattern=plain_answer_label_pattern,
        heading_only_label_pattern=heading_only_label_pattern,
        loop=re.compile(
            rf"^\s*(?:(?:[A-Za-z]\s+)?(?:{loop_labels})\s*){{3,}}\s*$",
            re.IGNORECASE,
        ),
        own_token_loop=re.compile(
            r"^\s*(?:s\s+)?(?:own\s*){3,}\s*$",
            re.IGNORECASE,
        ),
        own_token_prefix=re.compile(
            r"^\s*(?:s\s+)?(?:own\s*){3,}",
            re.IGNORECASE,
        ),
        suffix=re.compile(
            rf"\s+(?:(?:[A-Za-z]{{1,3}}\s+)?(?:{loop_labels})\s*){{3,}}$",
            re.IGNORECASE,
        ),
        likely_user_query_start=re.compile(
            rf"^(?:{user_query_verbs})",
            re.IGNORECASE,
        ),
        heading=re.compile(
            rf"^\s*(?:(?:#{{1,6}}\s*)(?:{plain_label_pattern}|{heading_only_label_pattern})(?:\s|:|$)|"
            rf"(?:{plain_label_pattern}|{plain_answer_label_pattern})(?:\s|:|$)).*$",
            re.IGNORECASE,
        ),
        inline=re.compile(
            rf"\s+(?:#{{1,6}}\s*(?:{plain_label_pattern}|own answer|your answer|"
            rf"(?<!own )(?<!your )answer(?:\s*\([^)]*\))?)(?:\s|:|$)|"
            rf"(?:{inline_trigger_labels})\s*:).*$",
            re.IGNORECASE,
        ),
        instruction_lines=tuple(
            re.compile(rf"^{fragment}$", re.IGNORECASE)
            for fragment in instruction_fragments
        ),
    )


@lru_cache(maxsize=4)
def get_intent_regexes(language: str | None = None) -> IntentRegexes:
    """Return cached compiled regexes and token sets for ``language``.

    Defaults to :func:`default_language` when ``language`` is ``None``. Unknown
    languages raise ``ValueError``.
    """

    lang = _resolve_language(language)

    word_units = _alt(_group(lang, "Word Count Units"))
    line_units = _alt(_group(lang, "Line Count Units"))
    expanded = _alt(_group(lang, "Expanded Explanation Verbs"))
    summary = _alt(_group(lang, "Summary Intent Markers"))
    structured = _alt(_group(lang, "Structured Overview Markers"))
    tender_documents = _alt(_group(lang, "Tender Documents"))
    tender_definitions = _alt(_group(lang, "Tender Definition Phrases"))
    tender_articles = _alt(_group(lang, "Tender Indefinite Articles"))
    tender_indefinite_nouns = _alt(_group(lang, "Tender Indefinite Nouns"))
    tender_concepts = _alt(_group(lang, "Tender Concept Phrases"))
    retrieval_intent = _alt(_group(lang, "Retrieval Intent Verbs"))
    retrieval_stopwords = _alt(_group(lang, "Retrieval Stopwords"))
    math_markers = _alt(_group(lang, "Math Markers"))
    length_units = _alt(_group(lang, "Length Meta Units"))
    length_adjectives = _alt(_group(lang, "Length Meta Adjectives"))
    integrity_context = _alt(_group(lang, "Integrity Pact Context"))
    integrity_query = _alt(_group(lang, "Integrity Pact Query"))
    continuation = _alt(_group(lang, "Continuation Headings"))
    singular_day = _alt(_group(lang, "Singular Day Word"))
    sentence_end_tokens = _group(lang, "Sentence End Tokens")
    prompt_garbage_tokens = _group(lang, "Prompt Garbage Tokens")

    return IntentRegexes(
        word_count_request=re.compile(
            rf"\b(\d{{2,5}})\s+(?:{word_units})\b",
            re.IGNORECASE,
        ),
        line_count_request=re.compile(
            rf"\b(\d{{2,5}})\s+(?:{line_units})\b",
            re.IGNORECASE,
        ),
        expanded_explanation=re.compile(
            rf"\b(?:{expanded})\b",
            re.IGNORECASE,
        ),
        summary_intent=re.compile(
            rf"\b(?:{summary})\b",
            re.IGNORECASE,
        ),
        structured_overview=re.compile(
            rf"\b(?:{structured})\b",
            re.IGNORECASE,
        ),
        tender_document=re.compile(
            rf"\b(?:{tender_documents})\b",
            re.IGNORECASE,
        ),
        generic_tender_definition=re.compile(
            rf"\b(?:{tender_definitions})\b",
            re.IGNORECASE,
        ),
        generic_tender_indefinite=re.compile(
            rf"\b(?:{tender_articles})\s+(?:{tender_indefinite_nouns})\b",
            re.IGNORECASE,
        ),
        generic_tender_concept=re.compile(
            rf"\b(?:{tender_concepts})\b",
            re.IGNORECASE,
        ),
        retrieval_intent_strip=re.compile(
            rf"\b(?:{retrieval_intent})\b",
            re.IGNORECASE,
        ),
        retrieval_stopword_strip=re.compile(
            rf"\b(?:{retrieval_stopwords})\b",
            re.IGNORECASE,
        ),
        math_rendering_request=re.compile(
            rf"\b(?:{math_markers})\b",
            re.IGNORECASE,
        ),
        length_meta_paragraph=re.compile(
            rf"\b(?:{length_units})\b.*\b(?:{length_adjectives})\b",
            re.IGNORECASE,
        ),
        integrity_pact_context=re.compile(
            rf"\b(?:{integrity_context})\b",
            re.IGNORECASE,
        ),
        integrity_pact_query=re.compile(
            rf"\b(?:{integrity_query})\b",
            re.IGNORECASE,
        ),
        continuation_heading=re.compile(
            rf"^\s*(?:#{{1,6}}\s*)?(?:{continuation})\b.*$",
            re.IGNORECASE,
        ),
        plural_day=re.compile(
            rf"\b([2-9][0-9]*)\s+(?:{singular_day})\b",
            re.IGNORECASE,
        ),
        incomplete_sentence_end_tokens=frozenset(sentence_end_tokens),
        prompt_garbage_prefix_tokens=frozenset(prompt_garbage_tokens),
    )
