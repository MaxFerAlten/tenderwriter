from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

ProfileKind = Literal["base", "sector", "tender_instance"]


@dataclass(frozen=True)
class ProcedureProfile:
    """Activatable procedure profile (base / sector / tender instance).

    Instances with a non-empty ``procedure_anchors`` dict are intentionally
    UNHASHABLE (dataclass is frozen but holds a dict). Do NOT wrap any
    function that takes ``ProcedureProfile`` / a profile tuple in
    ``functools.lru_cache``. The decontamination design caches localized
    bundles on ``language`` only and applies the active-profile overlay
    OUTSIDE the cached layer (see procedure_profiles overlay helpers and the
    guardrail-patterns overlay). Keep that split.
    """

    profile_id: str
    kind: ProfileKind
    enabled_by_default: bool = False
    # Anchor sets keyed by canonical procedure label (e.g. "OSCAT", "SCT").
    procedure_anchors: dict[str, tuple[str, ...]] = field(default_factory=dict)
    contamination_markers: tuple[str, ...] = ()
    identity_markers: tuple[str, ...] = ()
    address_patterns: tuple[str, ...] = ()
    critical_coverage_queries_it: tuple[str, ...] = ()
    critical_coverage_queries_en: tuple[str, ...] = ()
    graph_query_terms: tuple[str, ...] = ()
    # Lower-cased tokens that, if seen in the query text or a retrieved chunk,
    # auto-activate this profile when no explicit profile_id is set.
    activation_anchors: tuple[str, ...] = ()

    @property
    def main_label(self) -> str:
        # First declared label is the "main" procedure; "" if none.
        return next(iter(self.procedure_anchors), "")

    @property
    def referenced_label(self) -> str:
        labels = list(self.procedure_anchors)
        return labels[1] if len(labels) > 1 else ""

    def critical_coverage_queries(self, language: str) -> tuple[str, ...]:
        return (
            self.critical_coverage_queries_en
            if language == "en"
            else self.critical_coverage_queries_it
        )


BASE_PROCUREMENT_PROFILE = ProcedureProfile(
    profile_id="base_procurement_it",
    kind="base",
    enabled_by_default=True,
)

_OSCAT_ANCHORS: tuple[str, ...] = (
    "gitlab",
    "sonar",
    "nexus",
    "vulnerability assessment",
    "dpa",
    "gpa",
    "gva",
    "sme",
    "mam",
    "sts",
    "devsecops",
    "oscat",
)
_SCT_ANCHORS: tuple[str, ...] = (
    "cctt",
    "rtpc",
    "presa in carico",
    "fase transitoria",
    "qualificazione acn",
    "tix",
    "via san piero a quaracchi",
    "sistema cloud toscana",
    "sistema cloud toscano",
    "sct",
)

OSCAT_SCT_TOSCANA_PROFILE = ProcedureProfile(
    profile_id="oscat_sct_toscana",
    kind="tender_instance",
    enabled_by_default=False,
    procedure_anchors={"OSCAT": _OSCAT_ANCHORS, "SCT": _SCT_ANCHORS},
    contamination_markers=(
        r"sct[-\s]*tix",
        r"tix[-\s]*sct",
        r"cctt",
        r"estar",
        r"impianti\s+industriali",
        r"sistema\s+cloud\s+toscana",
        r"determin[ae]\s+acn",
        r"acn\s+n\.?\s*\d+",
        r"csirt\s+regional[ei]?",
        r"sanit[aà]\s+digitale",
        r"missione\s+1",
        r"pnrr",
    ),
    identity_markers=(
        r"gitlab",
        r"sonar",
        r"nexus",
        r"devsecops",
        r"continuous\s+integration",
        r"continuous\s+delivery",
        r"continuous\s+deployment",
        r"ci\s*/\s*cd",
        r"vulnerability\s+assessment",
        r"analisi\s+(?:statica\s+|del\s+)?(?:codice\s+sorgente|codice)",
        r"pipeline\s+(?:ci|cd|di\s+rilascio)",
    ),
    address_patterns=(r"via\s+san\s+piero\s+a\s+quaracchi\s+\d+",),
    critical_coverage_queries_it=(
        "OSCAT CIG identificativo procedura",
        "OSCAT durata accordo quadro fase transitoria regime",
        "OSCAT importo base gara valore stimato opzioni",
        "OSCAT luogo sede svolgimento servizio",
        "OSCAT integrazione SCT CCTT RTPC CMDBuild",
        "OSCAT GitLab Sonar Nexus Vulnerability Assessment",
        "qualificazione ACN CCTT RTPC fase transitoria gara",
        "CCTT monitoraggio governance servizi cloud Toscana",
        "CO-LO-KW colocation energia impianti industriali SLA",
    ),
    critical_coverage_queries_en=(
        "OSCAT CIG procedure identifier",
        "OSCAT duration framework agreement transition phase",
        "OSCAT amount tender base estimated value options",
        "OSCAT location place of service",
        "OSCAT integration SCT CCTT RTPC CMDBuild",
        "OSCAT GitLab Sonar Nexus Vulnerability Assessment",
        "ACN qualification CCTT RTPC transition phase tender",
        "CCTT monitoring governance cloud services",
        "CO-LO-KW colocation energy industrial plants SLA",
    ),
    graph_query_terms=("acn", "oscat", "sct"),
    activation_anchors=(
        "oscat",
        "sct",
        "cctt",
        "rtpc",
        "sistema cloud toscana",
        "sistema cloud toscano",
    ),
)

_REGISTRY: dict[str, ProcedureProfile] = {
    BASE_PROCUREMENT_PROFILE.profile_id: BASE_PROCUREMENT_PROFILE,
    OSCAT_SCT_TOSCANA_PROFILE.profile_id: OSCAT_SCT_TOSCANA_PROFILE,
}


def get_profile(profile_id: str) -> ProcedureProfile | None:
    return _REGISTRY.get(profile_id)


def resolve_active_profiles(
    query_text: str,
    *,
    chunk_texts: tuple[str, ...] = (),
    explicit_profile_ids: tuple[str, ...] = (),
) -> tuple[ProcedureProfile, ...]:
    """Return active profiles. BASE is always included. Non-default profiles
    activate when their id is explicitly requested OR an activation anchor is
    seen in the query text or any retrieved chunk."""
    active: list[ProcedureProfile] = [
        p for p in _REGISTRY.values() if p.enabled_by_default
    ]
    haystack = " ".join((query_text or "", *chunk_texts)).casefold()
    for profile in _REGISTRY.values():
        if profile.enabled_by_default:
            continue
        if profile.profile_id in explicit_profile_ids:
            active.append(profile)
            continue
        if any(anchor in haystack for anchor in profile.activation_anchors):
            active.append(profile)
    # De-dup, preserve order.
    seen: set[str] = set()
    return tuple(p for p in active if not (p.profile_id in seen or seen.add(p.profile_id)))


def active_procedure_anchors(
    profiles: tuple[ProcedureProfile, ...],
) -> dict[str, tuple[str, ...]]:
    merged: dict[str, tuple[str, ...]] = {}
    for profile in profiles:
        for label, anchors in profile.procedure_anchors.items():
            merged[label] = (*merged.get(label, ()), *anchors)
    return merged


def active_contamination_markers(profiles: tuple[ProcedureProfile, ...]) -> tuple[str, ...]:
    out: tuple[str, ...] = ()
    for profile in profiles:
        out = (*out, *profile.contamination_markers)
    return out


def active_identity_markers(profiles: tuple[ProcedureProfile, ...]) -> tuple[str, ...]:
    out: tuple[str, ...] = ()
    for profile in profiles:
        out = (*out, *profile.identity_markers)
    return out


def active_address_patterns(profiles: tuple[ProcedureProfile, ...]) -> tuple[str, ...]:
    out: tuple[str, ...] = ()
    for profile in profiles:
        out = (*out, *profile.address_patterns)
    return out


def active_critical_coverage_queries(
    profiles: tuple[ProcedureProfile, ...], *, language: str
) -> tuple[str, ...]:
    out: tuple[str, ...] = ()
    for profile in profiles:
        out = (*out, *profile.critical_coverage_queries(language))
    return out


def active_graph_query_terms(profiles: tuple[ProcedureProfile, ...]) -> tuple[str, ...]:
    out: tuple[str, ...] = ()
    for profile in profiles:
        out = (*out, *profile.graph_query_terms)
    return out
