"""Offline evaluation helpers for the requirement intelligence pipeline."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
from typing import Any


_TOKEN_RE = re.compile(r"[a-z0-9]+")
_WHITESPACE_RE = re.compile(r"\s+")
_REQUIREMENT_TEXT_KEYS = ("text", "requirement_text", "canonical_text", "summary", "summary_text")
_RELATION_SOURCE_KEYS = ("source_text", "source_requirement_text", "source")
_RELATION_TARGET_KEYS = ("target_text", "target_requirement_text", "target")
_SYMMETRIC_RELATION_TYPES = {"conflicts_with"}
GOLD_SET_SCHEMA_VERSION = "requirement_evaluation.gold.v1"


@dataclass(frozen=True)
class RequirementEvaluationThresholds:
    min_requirement_recall: float = 0.8
    min_requirement_precision: float = 0.75
    min_citation_coverage: float = 0.8
    min_conflict_detection_recall: float = 0.7


@dataclass(frozen=True)
class RequirementEvaluationReport:
    case_count: int
    expected_requirements: int
    predicted_requirements: int
    matched_requirements: int
    requirement_precision: float
    requirement_recall: float
    requirement_f1: float
    citation_coverage: float
    expected_relations: int
    predicted_relations: int
    matched_relations: int
    relation_precision: float
    relation_recall: float
    conflict_detection_recall: float
    review_rate: float
    passed: bool
    failures: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _read_mapping_text(payload: Mapping[str, Any], keys: Sequence[str]) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, Mapping):
            nested_text = _read_mapping_text(value, _REQUIREMENT_TEXT_KEYS)
            if nested_text:
                return nested_text
            continue
        text = " ".join(str(item) for item in value) if isinstance(value, list) else str(value or "")
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            return text
    return ""


def _requirement_text(payload: Mapping[str, Any]) -> str:
    return _read_mapping_text(payload, _REQUIREMENT_TEXT_KEYS)


def _relation_endpoint_text(payload: Mapping[str, Any], keys: Sequence[str]) -> str:
    return _read_mapping_text(payload, keys)


def _tokens(value: str) -> set[str]:
    normalized = _WHITESPACE_RE.sub(" ", str(value or "").strip().casefold())
    return {token for token in _TOKEN_RE.findall(normalized) if len(token) > 1}


def _text_overlap(left: str, right: str) -> float:
    left_tokens = _tokens(left)
    right_tokens = _tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / min(len(left_tokens), len(right_tokens))


def _safe_ratio(numerator: int, denominator: int, *, empty_value: float = 1.0) -> float:
    if denominator == 0:
        return empty_value
    return round(numerator / denominator, 4)


def _f1(precision: float, recall: float) -> float:
    if precision + recall == 0:
        return 0.0
    return round(2 * precision * recall / (precision + recall), 4)


def _match_requirements(
    expected: Sequence[Mapping[str, Any]],
    predicted: Sequence[Mapping[str, Any]],
    *,
    match_threshold: float,
) -> list[tuple[int, int]]:
    matches: list[tuple[int, int]] = []
    used_predictions: set[int] = set()
    for expected_index, expected_item in enumerate(expected):
        expected_text = _requirement_text(expected_item)
        best_index = None
        best_score = 0.0
        for predicted_index, predicted_item in enumerate(predicted):
            if predicted_index in used_predictions:
                continue
            score = _text_overlap(expected_text, _requirement_text(predicted_item))
            if score > best_score:
                best_score = score
                best_index = predicted_index
        if best_index is not None and best_score >= match_threshold:
            used_predictions.add(best_index)
            matches.append((expected_index, best_index))
    return matches


def _has_citation(payload: Mapping[str, Any]) -> bool:
    for key in ("citations", "source_citations", "evidence", "source_evidence"):
        citations = payload.get(key)
        if isinstance(citations, list) and any(item for item in citations):
            return True
    metadata_json = payload.get("metadata_json")
    if isinstance(metadata_json, Mapping):
        raw_candidate = metadata_json.get("raw_candidate")
        if isinstance(raw_candidate, Mapping):
            return _has_citation(raw_candidate)
    return False


def _requires_review(payload: Mapping[str, Any]) -> bool:
    if bool(payload.get("review_required")):
        return True
    review_state = str(payload.get("review_state") or "").strip().casefold()
    if not review_state:
        return False
    return review_state not in {"approved", "accepted", "verified"}


def _relation_type(payload: Mapping[str, Any]) -> str:
    return str(payload.get("relation_type") or "").strip().casefold()


def _relation_matches(
    expected: Mapping[str, Any],
    predicted: Mapping[str, Any],
    *,
    match_threshold: float,
) -> bool:
    relation_type = _relation_type(expected)
    if relation_type != _relation_type(predicted):
        return False

    expected_source = _relation_endpoint_text(expected, _RELATION_SOURCE_KEYS)
    expected_target = _relation_endpoint_text(expected, _RELATION_TARGET_KEYS)
    predicted_source = _relation_endpoint_text(predicted, _RELATION_SOURCE_KEYS)
    predicted_target = _relation_endpoint_text(predicted, _RELATION_TARGET_KEYS)
    forward = (
        _text_overlap(expected_source, predicted_source) >= match_threshold
        and _text_overlap(expected_target, predicted_target) >= match_threshold
    )
    if forward:
        return True
    if relation_type not in _SYMMETRIC_RELATION_TYPES:
        return False
    return (
        _text_overlap(expected_source, predicted_target) >= match_threshold
        and _text_overlap(expected_target, predicted_source) >= match_threshold
    )


def _match_relations(
    expected: Sequence[Mapping[str, Any]],
    predicted: Sequence[Mapping[str, Any]],
    *,
    match_threshold: float,
) -> list[tuple[int, int]]:
    matches: list[tuple[int, int]] = []
    used_predictions: set[int] = set()
    for expected_index, expected_item in enumerate(expected):
        for predicted_index, predicted_item in enumerate(predicted):
            if predicted_index in used_predictions:
                continue
            if not _relation_matches(expected_item, predicted_item, match_threshold=match_threshold):
                continue
            used_predictions.add(predicted_index)
            matches.append((expected_index, predicted_index))
            break
    return matches


def _case_items(case: Mapping[str, Any], *keys: str) -> list[Mapping[str, Any]]:
    for key in keys:
        value = case.get(key)
        if value is not None:
            return [item for item in _as_list(value) if isinstance(item, Mapping)]
    return []


def load_requirement_evaluation_payload(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("Requirement evaluation payload must be a JSON object.")
    validate_requirement_evaluation_payload(payload)
    return payload


def validate_requirement_evaluation_payload(payload: Mapping[str, Any]) -> None:
    """Validate the offline gold-set envelope before computing metrics."""

    schema_version = payload.get("schema_version", GOLD_SET_SCHEMA_VERSION)
    if schema_version != GOLD_SET_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported requirement evaluation schema_version: {schema_version!r}"
        )

    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("Requirement evaluation payload must contain a non-empty cases array.")

    for index, case in enumerate(cases):
        if not isinstance(case, Mapping):
            raise ValueError(f"Requirement evaluation case #{index + 1} must be an object.")
        case_id = str(case.get("id") or "").strip()
        if not case_id:
            raise ValueError(f"Requirement evaluation case #{index + 1} must define an id.")
        expected_requirements = _case_items(
            case,
            "expected_requirements",
            "gold_requirements",
            "requirements_expected",
        )
        expected_relations = _case_items(case, "expected_relations", "gold_relations")
        negative_case = bool(case.get("negative_case") or case.get("expected_no_requirements"))
        if not negative_case and not expected_requirements and not expected_relations:
            raise ValueError(
                f"Requirement evaluation case {case_id!r} must define expected requirements or relations."
            )


def evaluate_requirement_pipeline_payload(
    payload: Mapping[str, Any],
    *,
    thresholds: RequirementEvaluationThresholds | None = None,
    match_threshold: float = 0.72,
) -> RequirementEvaluationReport:
    validate_requirement_evaluation_payload(payload)
    cases = payload.get("cases")
    return evaluate_requirement_pipeline_cases(
        [case for case in cases if isinstance(case, Mapping)],
        thresholds=thresholds,
        match_threshold=match_threshold,
    )


def evaluate_requirement_pipeline_cases(
    cases: Sequence[Mapping[str, Any]],
    *,
    thresholds: RequirementEvaluationThresholds | None = None,
    match_threshold: float = 0.72,
) -> RequirementEvaluationReport:
    thresholds = thresholds or RequirementEvaluationThresholds()
    expected_requirements: list[Mapping[str, Any]] = []
    predicted_requirements: list[Mapping[str, Any]] = []
    expected_relations: list[Mapping[str, Any]] = []
    predicted_relations: list[Mapping[str, Any]] = []

    for case in cases:
        expected_requirements.extend(
            _case_items(case, "expected_requirements", "gold_requirements", "requirements_expected")
        )
        predicted_requirements.extend(
            _case_items(case, "predicted_requirements", "actual_requirements", "requirements_predicted")
        )
        expected_relations.extend(_case_items(case, "expected_relations", "gold_relations"))
        predicted_relations.extend(_case_items(case, "predicted_relations", "actual_relations"))

    requirement_matches = _match_requirements(
        expected_requirements,
        predicted_requirements,
        match_threshold=match_threshold,
    )
    relation_matches = _match_relations(
        expected_relations,
        predicted_relations,
        match_threshold=match_threshold,
    )
    matched_prediction_indexes = {predicted_index for _, predicted_index in requirement_matches}
    matched_relation_expected_indexes = {expected_index for expected_index, _ in relation_matches}
    expected_conflict_indexes = {
        index for index, item in enumerate(expected_relations) if _relation_type(item) == "conflicts_with"
    }
    matched_conflict_count = len(expected_conflict_indexes & matched_relation_expected_indexes)

    requirement_precision = _safe_ratio(
        len(requirement_matches),
        len(predicted_requirements),
        empty_value=1.0 if not expected_requirements else 0.0,
    )
    requirement_recall = _safe_ratio(
        len(requirement_matches),
        len(expected_requirements),
        empty_value=1.0,
    )
    citation_coverage = _safe_ratio(
        sum(1 for index in matched_prediction_indexes if _has_citation(predicted_requirements[index])),
        len(matched_prediction_indexes),
        empty_value=1.0,
    )
    relation_precision = _safe_ratio(
        len(relation_matches),
        len(predicted_relations),
        empty_value=1.0 if not expected_relations else 0.0,
    )
    relation_recall = _safe_ratio(
        len(relation_matches),
        len(expected_relations),
        empty_value=1.0,
    )
    conflict_detection_recall = _safe_ratio(
        matched_conflict_count,
        len(expected_conflict_indexes),
        empty_value=1.0,
    )
    review_rate = _safe_ratio(
        sum(1 for item in predicted_requirements if _requires_review(item)),
        len(predicted_requirements),
        empty_value=0.0,
    )

    failures: list[str] = []
    if requirement_recall < thresholds.min_requirement_recall:
        failures.append("requirement_recall")
    if requirement_precision < thresholds.min_requirement_precision:
        failures.append("requirement_precision")
    if citation_coverage < thresholds.min_citation_coverage:
        failures.append("citation_coverage")
    if conflict_detection_recall < thresholds.min_conflict_detection_recall:
        failures.append("conflict_detection_recall")

    return RequirementEvaluationReport(
        case_count=len(cases),
        expected_requirements=len(expected_requirements),
        predicted_requirements=len(predicted_requirements),
        matched_requirements=len(requirement_matches),
        requirement_precision=requirement_precision,
        requirement_recall=requirement_recall,
        requirement_f1=_f1(requirement_precision, requirement_recall),
        citation_coverage=citation_coverage,
        expected_relations=len(expected_relations),
        predicted_relations=len(predicted_relations),
        matched_relations=len(relation_matches),
        relation_precision=relation_precision,
        relation_recall=relation_recall,
        conflict_detection_recall=conflict_detection_recall,
        review_rate=review_rate,
        passed=not failures,
        failures=tuple(failures),
    )
