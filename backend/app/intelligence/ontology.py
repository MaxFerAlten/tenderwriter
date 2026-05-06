"""Tender ontology tagging.

Keyword/rule based first-pass classification of requirements into a stable
procurement taxonomy. The service is deterministic and does not call any LLM:
it is safe to run in the ingestion pipeline. An LLM fallback may be added
later without changing the public interface.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from app.intelligence.schemas import (
    ONTOLOGY_VERSION,
    Criticality,
    EvaluationAxis,
    EvidenceType,
    OntologyDomain,
    OwnerRole,
    RequirementOntologyTag,
)


@dataclass(frozen=True)
class _DomainRule:
    domain: OntologyDomain
    subdomain: str
    keywords: tuple[str, ...]
    owner_role: OwnerRole = "unknown"
    evidence_type: EvidenceType = "documentary_proof"


# Italian-first rules — TenderWriter is primarily used on Italian public
# procurement documents. English synonyms are included where useful.
_RULES: tuple[_DomainRule, ...] = (
    _DomainRule(
        OntologyDomain.COMPLIANCE,
        "certificazioni",
        ("certificazion", "iso", "gdpr", "dpo", "soc 2", "nis2", "agid"),
        owner_role="legal",
        evidence_type="certification",
    ),
    _DomainRule(
        OntologyDomain.COMPLIANCE,
        "obblighi_normativi",
        ("normativ", "codice appalti", "d.lgs", "decreto", "legge"),
        owner_role="legal",
    ),
    _DomainRule(
        OntologyDomain.ECONOMICO_FINANZIARIO,
        "capacita_economica",
        (
            "fatturato",
            "bilancio",
            "capacità economica",
            "capacita economica",
            "garanzia",
            "cauzione",
            "polizza",
        ),
        owner_role="finance",
        evidence_type="financial_statement",
    ),
    _DomainRule(
        OntologyDomain.TECNICO,
        "sla_continuita",
        (
            "sla",
            "uptime",
            "tempi di intervento",
            "continuità operativa",
            "continuita operativa",
            "disaster recovery",
        ),
        owner_role="technical",
        evidence_type="technical_attachment",
    ),
    _DomainRule(
        OntologyDomain.TECNICO,
        "architettura",
        (
            "architettura",
            "stack",
            "componenti tecnici",
            "integrazione",
            "interoperabilità",
            "interoperabilita",
        ),
        owner_role="technical",
        evidence_type="technical_attachment",
    ),
    _DomainRule(
        OntologyDomain.DOCUMENTALE,
        "allegati_istanze",
        ("allegato", "istanza", "dichiarazione", "modulo", "form "),
        owner_role="bid_manager",
    ),
    _DomainRule(
        OntologyDomain.CONTRATTUALE,
        "clausole_penali",
        ("penale", "risoluzione contrattuale", "clausola", "risarcimento", "recesso"),
        owner_role="legal",
    ),
    _DomainRule(
        OntologyDomain.AMMINISTRATIVO,
        "rti_avvalimento",
        ("rti ", "raggruppamento temporaneo", "avvalimento", "subappalto", "consorzio"),
        owner_role="bid_manager",
    ),
    _DomainRule(
        OntologyDomain.SICUREZZA,
        "sicurezza_informazioni",
        ("sicurezza", "cybersecurity", "protezione dei dati", "riservatezza", "crittografia"),
        owner_role="security",
    ),
    _DomainRule(
        OntologyDomain.ORGANIZZATIVO,
        "organizzazione_team",
        ("gruppo di lavoro", "team", "organigramma", "ruoli", "personale", "cv", "curriculum"),
        owner_role="operations",
        evidence_type="organizational_plan",
    ),
    _DomainRule(
        OntologyDomain.PREMIALE,
        "criteri_premiali",
        ("premiale", "punteggio aggiuntivo", "criteri premiali", "miglioramento", "innovazion"),
        owner_role="bid_manager",
        evidence_type="narrative_claim",
    ),
)


_WHITESPACE_RE = re.compile(r"\s+")


def _normalize(text: str) -> str:
    collapsed = _WHITESPACE_RE.sub(" ", str(text or "")).strip().casefold()
    # Strip diacritics so "continuità" and "continuita" both match.
    stripped = "".join(
        ch for ch in unicodedata.normalize("NFKD", collapsed) if not unicodedata.combining(ch)
    )
    return stripped


_HIGH_PRIORITY = {"high", "critical", "mandatory", "must", "must-have", "required", "shall"}
_LOW_PRIORITY = {"low", "optional", "nice-to-have"}


def _map_priority_to_criticality(priority: str | None) -> Criticality:
    value = str(priority or "").strip().casefold()
    if value in _HIGH_PRIORITY:
        return "high"
    if value in _LOW_PRIORITY:
        return "low"
    return "medium"


def _infer_evaluation_axis(category: str | None, criticality: Criticality) -> EvaluationAxis:
    category_norm = _normalize(category or "")
    if "premial" in category_norm or "scored" in category_norm:
        return "scored"
    if criticality == "high":
        return "mandatory"
    if criticality == "low":
        return "supporting"
    return "mandatory"


def _keyword_matches(needle: str, text: str) -> bool:
    """Match ``needle`` against ``text`` respecting word boundaries.

    Uses a regex with ``\\b`` on each end so that short keywords like "iso" do
    not silently hit substrings of unrelated tokens (e.g. "provvisoria"). The
    needle is regex-escaped so dots and other punctuation are treated
    literally.
    """

    if not needle:
        return False
    pattern = r"(?<!\w)" + re.escape(needle) + r"(?!\w)"
    return re.search(pattern, text) is not None


def _match_domains(normalized_text: str) -> dict[_DomainRule, int]:
    scores: dict[_DomainRule, int] = {}
    for rule in _RULES:
        hits = 0
        for keyword in rule.keywords:
            needle = _normalize(keyword)
            if _keyword_matches(needle, normalized_text):
                hits += 1
        if hits:
            scores[rule] = hits
    return scores


class TenderOntologyService:
    """Deterministic ontology tagger for requirement candidates."""

    def __init__(self, rules: Iterable[_DomainRule] | None = None) -> None:
        self._rules = tuple(rules) if rules is not None else _RULES

    def tag_text(
        self,
        requirement_text: str,
        *,
        category: str | None = None,
        priority: str | None = None,
    ) -> RequirementOntologyTag:
        """Return an ontology tag for the given requirement text."""

        normalized = _normalize(requirement_text)
        criticality = _map_priority_to_criticality(priority)
        matches = _match_domains(normalized)

        if not matches:
            return RequirementOntologyTag(
                ontology_domain=OntologyDomain.ALTRO,
                ontology_subdomain="non_classificato",
                criticality=criticality,
                evidence_type="mixed",
                owner_role="unknown",
                evaluation_axis=_infer_evaluation_axis(category, criticality),
                ontology_version=ONTOLOGY_VERSION,
                mapping_confidence=0.1,
                matched_rules=[],
            )

        best_rule, best_hits = max(
            matches.items(),
            key=lambda item: (item[1], -self._rules.index(item[0])),
        )

        total_hits = sum(matches.values())
        # Confidence grows with the share of matches that fall into the
        # winning rule and with the absolute number of matches, capped at 0.95
        # so that the deterministic tagger never claims certainty.
        share = best_hits / total_hits if total_hits else 0.0
        confidence = min(0.95, 0.5 + 0.25 * share + 0.1 * min(best_hits, 3))

        matched_rule_ids = [f"{rule.domain.value}:{rule.subdomain}" for rule in matches]

        return RequirementOntologyTag(
            ontology_domain=best_rule.domain,
            ontology_subdomain=best_rule.subdomain,
            criticality=criticality,
            evidence_type=best_rule.evidence_type,
            owner_role=best_rule.owner_role,
            evaluation_axis=_infer_evaluation_axis(category, criticality),
            ontology_version=ONTOLOGY_VERSION,
            mapping_confidence=round(confidence, 3),
            matched_rules=matched_rule_ids,
        )

    def tag_candidate(self, candidate: Mapping[str, object]) -> RequirementOntologyTag:
        """Tag a parsed v2 candidate dict (as produced by requirement_extraction_v2)."""

        text = str(candidate.get("summary") or candidate.get("requirement_text") or "")
        return self.tag_text(
            text,
            category=str(candidate.get("category") or "") or None,
            priority=str(candidate.get("priority") or "") or None,
        )


_DEFAULT_SERVICE = TenderOntologyService()


def default_ontology_service() -> TenderOntologyService:
    """Return the process-wide default ontology service."""

    return _DEFAULT_SERVICE


def attach_ontology_to_candidates(
    candidates: Iterable[Mapping[str, object]],
    *,
    service: TenderOntologyService | None = None,
) -> list[dict[str, object]]:
    """Return a new list of candidate dicts with an ``ontology`` block added.

    The input is not mutated. Each candidate is shallow-copied and augmented
    with an ``ontology`` key holding the dict form of
    :class:`RequirementOntologyTag`. Candidates missing a requirement body are
    preserved untouched so that we never hide parsing errors.
    """

    tagger = service or _DEFAULT_SERVICE
    tagged: list[dict[str, object]] = []
    for candidate in candidates:
        enriched = dict(candidate)
        text = str(enriched.get("summary") or enriched.get("requirement_text") or "").strip()
        if text:
            tag = tagger.tag_candidate(enriched)
            enriched["ontology"] = tag.model_dump(mode="json")
        tagged.append(enriched)
    return tagged
