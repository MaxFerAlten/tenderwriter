"""Versioned catalog of reviewer personas.

The catalog is deterministic and checked into the repo.  Rehearsal
runs snapshot the persona profile at request time, so bumping
``PERSONA_CATALOG_VERSION`` and the catalog below is sufficient to
roll forward without migrating previous runs.

Five initial personas cover the typical Italian public-procurement
commission:

- ``formalista_amministrativo`` — mandatory coverage + documentary proof
- ``valutatore_tecnico`` — solution strength + SLA + delivery
- ``compliance_officer`` — certifications + contradictions
- ``economico_finanziario`` — sustainability + claims
- ``rup_simulato`` — overall readiness + blocking risks
"""

from __future__ import annotations

from app.intelligence.personas import (
    PERSONA_CATALOG_VERSION,
    ReviewerPersona,
    _validate_persona,
)

DEFAULT_PERSONA_IDS: tuple[str, ...] = (
    "formalista_amministrativo",
    "valutatore_tecnico",
    "compliance_officer",
    "economico_finanziario",
    "rup_simulato",
)


_RAW_CATALOG: tuple[ReviewerPersona, ...] = (
    ReviewerPersona(
        persona_id="formalista_amministrativo",
        display_name="Formalista amministrativo",
        reviewer_type="formalista_amministrativo",
        focus_domains=("amministrativo", "documentale", "compliance"),
        strictness=5,
        risk_aversion=5,
        scoring_weights={
            "mandatory_coverage": 0.35,
            "evidence_depth": 0.30,
            "formal_consistency": 0.25,
            "innovation": 0.10,
        },
        mandatory_checks=(
            "signed_annexes",
            "required_certifications",
            "no_missing_documents",
        ),
        prompt_profile=(
            "Valuta come un commissario formalista. Penalizza severamente "
            "omissioni, allegati non firmati e coperture mandatory parziali. "
            "Pesi decisionali: mandatory_coverage, evidence_depth, formal_consistency."
        ),
    ),
    ReviewerPersona(
        persona_id="valutatore_tecnico",
        display_name="Valutatore tecnico",
        reviewer_type="valutatore_tecnico",
        focus_domains=("tecnico", "sicurezza", "organizzativo"),
        strictness=4,
        risk_aversion=3,
        scoring_weights={
            "technical_strength": 0.35,
            "service_levels": 0.25,
            "delivery_feasibility": 0.25,
            "evidence_depth": 0.15,
        },
        mandatory_checks=(
            "sla_coverage",
            "architecture_coherence",
        ),
        prompt_profile=(
            "Valuta come un reviewer tecnico senior. Cerca chiarezza "
            "architetturale, solidita SLA, continuita operativa e supporto "
            "probatorio tecnico. Penalizza claim non supportati."
        ),
    ),
    ReviewerPersona(
        persona_id="compliance_officer",
        display_name="Compliance officer",
        reviewer_type="compliance_officer",
        focus_domains=("compliance", "contrattuale", "amministrativo"),
        strictness=5,
        risk_aversion=5,
        scoring_weights={
            "regulatory_coverage": 0.40,
            "certifications_presence": 0.25,
            "contradiction_absence": 0.25,
            "evidence_depth": 0.10,
        },
        mandatory_checks=(
            "regulatory_alignment",
            "certifications_presence",
            "no_contradictions_with_gates",
        ),
        prompt_profile=(
            "Valuta come un compliance officer. Segnala certificazioni "
            "mancanti, obblighi normativi non coperti e contraddizioni tra "
            "requisiti e gate aperti."
        ),
    ),
    ReviewerPersona(
        persona_id="economico_finanziario",
        display_name="Economico-finanziario",
        reviewer_type="economico_finanziario",
        focus_domains=("economico_finanziario", "contrattuale"),
        strictness=4,
        risk_aversion=4,
        scoring_weights={
            "financial_sustainability": 0.40,
            "claim_credibility": 0.30,
            "guarantees_coverage": 0.20,
            "evidence_depth": 0.10,
        },
        mandatory_checks=(
            "financial_statements_presence",
            "guarantees_coverage",
        ),
        prompt_profile=(
            "Valuta come un reviewer economico-finanziario. Misura "
            "sostenibilita economica, credibilita dei claim, presenza di "
            "garanzie e rischio di claims non sostenibili."
        ),
    ),
    ReviewerPersona(
        persona_id="rup_simulato",
        display_name="RUP simulato",
        reviewer_type="rup_simulato",
        focus_domains=(
            "amministrativo",
            "tecnico",
            "compliance",
            "economico_finanziario",
        ),
        strictness=4,
        risk_aversion=4,
        scoring_weights={
            "overall_readiness": 0.40,
            "blocking_risk_absence": 0.30,
            "package_reliability": 0.20,
            "evidence_depth": 0.10,
        },
        mandatory_checks=(
            "no_blocking_gates_open",
            "overall_package_completeness",
        ),
        prompt_profile=(
            "Valuta come un RUP. Giudica readiness complessiva, punti di "
            "blocco e affidabilita generale del pacchetto di offerta. "
            "Adotta il punto di vista del responsabile del procedimento."
        ),
    ),
)


PERSONA_CATALOG: dict[str, ReviewerPersona] = {
    persona.persona_id: persona for persona in _RAW_CATALOG
}


for _persona in PERSONA_CATALOG.values():
    _validate_persona(_persona)


def get_persona(persona_id: str) -> ReviewerPersona:
    """Return the persona with ``persona_id`` or raise ``KeyError``."""

    try:
        return PERSONA_CATALOG[persona_id]
    except KeyError as exc:
        raise KeyError(
            f"unknown persona_id '{persona_id}'; available: {sorted(PERSONA_CATALOG)}"
        ) from exc


def resolve_personas(persona_ids: list[str] | None) -> list[ReviewerPersona]:
    """Resolve a list of persona ids to the catalog entries.

    Empty/missing input falls back to :data:`DEFAULT_PERSONA_IDS`.
    Unknown ids raise ``KeyError`` — callers are expected to validate
    request payloads before calling.
    """

    if not persona_ids:
        return [PERSONA_CATALOG[pid] for pid in DEFAULT_PERSONA_IDS]
    return [get_persona(pid) for pid in persona_ids]


__all__ = [
    "DEFAULT_PERSONA_IDS",
    "PERSONA_CATALOG",
    "PERSONA_CATALOG_VERSION",
    "get_persona",
    "resolve_personas",
]
