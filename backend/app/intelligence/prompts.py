"""Deterministic intent rules and answer templates for the intelligence agent.

The TenderIntelligenceAgent does **not** call an LLM. MiroFish's ReportAgent
is LLM-driven, but in the procurement domain we need predictable, auditable
behaviour, and the Wave-1 toolset is small enough that keyword-matching
plus structured synthesis suffices. When/if an LLM front-end is added, it
should sit *above* this deterministic core, not replace it.

All keywords are lower-cased and matched against the lower-cased question.
Italian and English variants are supported because TenderWriter is used in
mixed-language settings.
"""

from __future__ import annotations

from collections.abc import Mapping

from app.intelligence.result_models import AgentIntent

INTENT_KEYWORDS: Mapping[AgentIntent, tuple[str, ...]] = {
    "coverage": (
        "coverage",
        "covered",
        "uncovered",
        "copertura",
        "scoperto",
        "scoperti",
        "non coperto",
        "non coperti",
        "gap",
        "mapping",
        "mappato",
        "mappatura",
        "missing requirement",
        "requisiti mancanti",
        "requisiti scoperti",
    ),
    "evidence": (
        "evidence",
        "evidenza",
        "evidenze",
        "prova",
        "prove",
        "approved",
        "approvata",
        "approvate",
        "weak",
        "missing evidence",
        "lacuna probatoria",
        "lacune probatorie",
        "documentazione",
        "citazione",
        "citazioni",
    ),
    "panorama": (
        "amber",
        "red",
        "green",
        "stato",
        "salute",
        "health",
        "phase",
        "fase",
        "panorama",
        "snapshot",
        "blocking",
        "bottleneck",
        "rischio",
        "risk",
        "gate",
        "rework",
        "stuck",
        "bloccato",
        "perché",
        "perche",
        "why",
    ),
    "diagnostic": (
        "diagnos",
        "explain why",
        "spiega perché",
        "deep dive",
        "approfond",
    ),
    "contradiction": (
        "contradict",
        "contradd",
        "contraddizion",
        "conflict",
        "conflitt",
        "incoeren",
        "inconsist",
        "discrepanc",
        "discordan",
    ),
}


# Order matters: when multiple intents match, we use this priority for the
# *primary* intent label. Tool selection still considers all matched intents
# (capped at MAX_TOOLS_PER_QUERY).
INTENT_PRIORITY: tuple[AgentIntent, ...] = (
    "diagnostic",
    "contradiction",
    "panorama",
    "coverage",
    "evidence",
    "unknown",
)


# Primary tool for each intent. Diagnostic is special: it triggers all
# three Wave-1 tools to build a wide-angle answer.
PRIMARY_TOOL_BY_INTENT: Mapping[AgentIntent, str] = {
    "coverage": "coverage_analyzer",
    "evidence": "evidence_auditor",
    "panorama": "compliance_panorama",
    "diagnostic": "compliance_panorama",
    "contradiction": "contradiction_finder",
    "unknown": "compliance_panorama",
}


# Secondary tools added when extra capacity allows it. Order matters because
# `select_tools` walks them in sequence until the cap is reached.
SECONDARY_TOOLS_BY_INTENT: Mapping[AgentIntent, tuple[str, ...]] = {
    "coverage": ("evidence_auditor", "compliance_panorama"),
    "evidence": ("coverage_analyzer", "compliance_panorama"),
    "panorama": ("coverage_analyzer", "evidence_auditor"),
    "diagnostic": ("coverage_analyzer", "evidence_auditor"),
    "contradiction": ("compliance_panorama", "coverage_analyzer"),
    "unknown": ("coverage_analyzer", "evidence_auditor"),
}


MAX_TOOLS_PER_QUERY = 3


# Headline templates for the synthesised answer. Each template gets a
# context dict and is rendered with .format(**context).
ANSWER_TEMPLATES: Mapping[AgentIntent, str] = {
    "coverage": (
        "Su {total} requisiti, {fully_covered} sono coperti, "
        "{partially_covered} parzialmente e {uncovered} scoperti "
        "({high_priority_uncovered} ad alta priorità)."
    ),
    "evidence": (
        "Verificate {requirements_checked} requirement: {strong_evidence} con evidenza "
        "forte, {weak_evidence} debole, {missing_evidence} senza evidenza."
    ),
    "panorama": (
        "Stato complessivo {health}. Fase analitica: {analytical_phase}. "
        "Gate aperti: {open_gates}, gate falliti: {failed_gates}, "
        "rework bloccanti: {blocking_reworks}."
    ),
    "diagnostic": (
        "Diagnosi tender {tender_id}: stato {health}, {high_priority_uncovered} "
        "requisiti high-priority scoperti, {missing_evidence} senza evidenza, "
        "{blocking_reworks} rework bloccanti."
    ),
    "contradiction": (
        "Trovate {contradiction_total} contraddizioni candidate: "
        "{contradiction_req_vs_proposal} requisito↔proposta, "
        "{contradiction_proposal_vs_evidence} proposta↔evidenza, "
        "{contradiction_req_vs_req} requisito↔requisito."
    ),
    "unknown": (
        "Domanda non riconosciuta. Restituito panorama generico: stato {health}, "
        "fase {analytical_phase}."
    ),
}


__all__ = [
    "ANSWER_TEMPLATES",
    "INTENT_KEYWORDS",
    "INTENT_PRIORITY",
    "MAX_TOOLS_PER_QUERY",
    "PRIMARY_TOOL_BY_INTENT",
    "SECONDARY_TOOLS_BY_INTENT",
]
