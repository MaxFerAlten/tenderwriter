"""Canonical KPI contract constants for the TenderWriter KPI reason engine."""

from __future__ import annotations

KPI_CONTRACT_VERSION = "kpi-contract-v1"
FORMULA_BUNDLE_VERSION = "kpi-contract-v1-formulas-v3"
MODEL_BUNDLE_VERSION = "deterministic-proxy-model-v3"
PROMPT_BUNDLE_VERSION = "deterministic-no-prompt-v1"
HEALTH_RULE_VERSION = "tender-health-v1"
READINESS_RULE_VERSION = "service-readiness-v1"
SNAPSHOT_OUTPUT_SCHEMA_VERSION = "snapshot-output-v1"
FORECAST_OUTPUT_SCHEMA_VERSION = "forecast-output-v1"
VERSION_MANIFEST_SCHEMA_VERSION = "version-manifest-v1"
METRICS_EXPORT_VERSION = "runtime-metrics-v1"

SCORE_SCALE_INTERNAL = "0-100"
SCORE_SCALE_EXTERNAL = "1-10"

QUALITY_WEIGHTS = {"A1": 0.30, "A2": 0.15, "A3": 0.30, "A4": 0.25}
OPERATIONAL_WEIGHTS = {"B1": 0.30, "B2": 0.30, "B3": 0.15, "B4": 0.25}

GREEN_Q_THRESHOLD = 75.0
GREEN_E_THRESHOLD = 70.0
GREEN_A4_THRESHOLD = 70.0
AMBER_Q_THRESHOLD = 60.0
AMBER_E_THRESHOLD = 50.0

MARKOV_PHASE_SCOPE = ["S0", "S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9", "S10", "S11", "S12", "S13"]
MARKOV_RELIABLE_PHASE_SCOPE = ["S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9", "S10", "S11", "S12", "S13"]
SEMANTIC_PRIORITY = ["A1", "A4", "A2", "A3"]

QUALITATIVE_ENGINE_PROXY = "deterministic_proxy"
QUALITATIVE_ENGINE_SHADOW = "semantic_shadow"
QUALITATIVE_ENGINE_SEMANTIC = "semantic_official"
QUALITATIVE_ENGINE_MODES = {"proxy_only", "shadow_control", "semantic_official"}

SEMANTIC_BUNDLE_VERSION = "semantic-official-v1"
SEMANTIC_ENGINE_KIND = "semantic_reasoning"
SEMANTIC_EXECUTION_MODE = "inline_analysis"
SEMANTIC_MODEL_VERSION = "semantic-rule-model-v2"
SEMANTIC_PROMPT_VERSION = "semantic-rubric-v2"
SEMANTIC_SUPPORTED_KPIS = ["A1", "A2", "A3", "A4"]
SEMANTIC_FORMULA_VERSIONS = {
    "A1": "semantic-requirement-coverage-v1",
    "A2": "semantic-editorial-quality-v1",
    "A3": "semantic-competitive-value-v1",
    "A4": "semantic-compliance-risk-v1",
    "Q": "qualitative-index-semantic-v1",
}
SEMANTIC_FALLBACK_POLICY_VERSION = "semantic-fallback-v1"

SHADOW_BUNDLE_VERSION = "semantic-shadow-v1"
SHADOW_ENGINE_KIND = "semantic_shadow"
SHADOW_EXECUTION_MODE = "inline_analysis"
SHADOW_MODEL_VERSION = "semantic-shadow-rule-model-v1"
SHADOW_PROMPT_VERSION = "semantic-shadow-rubric-v1"
SHADOW_SUPPORTED_KPIS = ["A1", "A4"]
SHADOW_FORMULA_VERSIONS = {
    "A1": "semantic-requirement-coverage-shadow-v1",
    "A4": "semantic-compliance-risk-shadow-v1",
}

FORECAST_HEURISTIC_ENGINE = "heuristic_rule_v1"
FORECAST_MARKOV_ENGINE = "markov_full_lifecycle_v1"
HEURISTIC_FORECAST_VERSION = "heuristic-rule-v1"
MARKOV_MODEL_VERSION = "markov-full-lifecycle-v1"
MARKOV_BUNDLE_KIND = "full_journey"
MARKOV_BACKTEST_VERSION = "markov-backtest-v1"
FORECAST_DECISION_BUNDLE_VERSION = "forecast-decision-support-v1"
MARKOV_STATE_SCOPE = MARKOV_PHASE_SCOPE
MARKOV_ABSORBING_STATES = ["S11", "S12", "S13"]
MARKOV_POSITIVE_STATES = ["S9", "S10", "S11", "S12"]
MARKOV_MIN_TOTAL_TRANSITIONS = 6
MARKOV_MIN_CURRENT_STATE_SUPPORT = 2

CANONICAL_SOURCE_TYPES = {"observed", "inferred", "reconstructed", "unknown"}


def normalize_source_type(value: str | None) -> str:
    normalized = str(value or "").strip().casefold()
    if normalized == "measured":
        return "observed"
    if normalized in CANONICAL_SOURCE_TYPES:
        return normalized
    return "unknown"
