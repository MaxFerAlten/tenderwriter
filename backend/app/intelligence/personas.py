"""Reviewer persona schema for the TenderWriter intelligence layer.

The rehearsal layer (Wave 3) simulates a heterogeneous procurement
commission via a fixed set of reviewer personas.  A persona is not a
"social" profile: it is a deterministic, decision-shaped bundle of
focus domains, strictness, risk aversion and scoring weights that
drives which Wave-1/Wave-2 tools are invoked and how their outputs are
scored.

Personas live as versioned code — they are not persisted in SQL — so
that upgrading the catalog is a code/migration-less operation and
reproducibility of historical rehearsal runs is guaranteed via the
``version`` field snapshotted on the run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

PERSONA_CATALOG_VERSION = "tw-reviewer-v1"


ReviewerType = Literal[
    "formalista_amministrativo",
    "valutatore_tecnico",
    "compliance_officer",
    "economico_finanziario",
    "rup_simulato",
    "delivery_manager_critico",
]


@dataclass(frozen=True, slots=True)
class ReviewerPersona:
    """Deterministic reviewer profile used by the rehearsal service.

    ``focus_domains`` must draw from
    :class:`app.intelligence.schemas.OntologyDomain` values (plus the
    free-form ``"organizzativo"`` / ``"documentale"`` terms already in
    that enum) so the persona can filter ontology-tagged requirements
    via ``requirement.ontology_domain``.

    ``scoring_weights`` must sum to ~1.0.  Values are normalised at
    load time via :func:`_validate_persona` — an out-of-tolerance sum
    is a programming error and will raise at import.
    """

    persona_id: str
    display_name: str
    reviewer_type: ReviewerType
    focus_domains: tuple[str, ...]
    strictness: int
    risk_aversion: int
    scoring_weights: dict[str, float]
    mandatory_checks: tuple[str, ...] = field(default_factory=tuple)
    prompt_profile: str = ""
    version: str = PERSONA_CATALOG_VERSION


_WEIGHT_SUM_TOLERANCE = 0.01


def _validate_persona(persona: ReviewerPersona) -> None:
    if not 1 <= persona.strictness <= 5:
        raise ValueError(
            f"persona {persona.persona_id}: strictness must be in [1, 5], got {persona.strictness}"
        )
    if not 1 <= persona.risk_aversion <= 5:
        raise ValueError(
            f"persona {persona.persona_id}: risk_aversion must be in [1, 5], "
            f"got {persona.risk_aversion}"
        )
    if not persona.scoring_weights:
        raise ValueError(f"persona {persona.persona_id}: scoring_weights cannot be empty")
    total = sum(persona.scoring_weights.values())
    if abs(total - 1.0) > _WEIGHT_SUM_TOLERANCE:
        raise ValueError(
            f"persona {persona.persona_id}: scoring_weights must sum to ~1.0, got {total:.4f}"
        )


def persona_as_dict(persona: ReviewerPersona) -> dict[str, object]:
    """Serialise a persona to a JSON-compatible dict for snapshotting.

    Used by :mod:`app.intelligence.rehearsal` to embed the exact
    persona profile inside the run's ``context_snapshot_json`` so that
    historical runs remain interpretable even if the catalog is later
    bumped.
    """

    return {
        "persona_id": persona.persona_id,
        "display_name": persona.display_name,
        "reviewer_type": persona.reviewer_type,
        "focus_domains": list(persona.focus_domains),
        "strictness": persona.strictness,
        "risk_aversion": persona.risk_aversion,
        "scoring_weights": dict(persona.scoring_weights),
        "mandatory_checks": list(persona.mandatory_checks),
        "prompt_profile": persona.prompt_profile,
        "version": persona.version,
    }
