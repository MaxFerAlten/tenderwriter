"""ContradictionFinder — Wave-2 deterministic conflict scanner.

Three categories of contradictions are surfaced:

1. ``requirement_vs_proposal``
   Requirement is high-priority and the mapped proposal section / contribution
   unit is in a state that contradicts the claim (REJECTED section, BLOCKED
   contribution, FAILED gate, OPEN blocking rework).

2. ``proposal_vs_evidence``
   Section is APPROVED but the consolidated requirement has no citation
   metadata at all — the proposal claims something with no documentary
   anchor. Risk of contestation.

3. ``requirement_vs_requirement``
   Two consolidated requirements on the same tender carry contradictory
   modal/quantitative wording (``deve`` vs ``non deve``, ``obbligatorio`` vs
   ``opzionale``, ``massimo X giorni`` vs ``minimo Y giorni`` for the same
   normalized topic).

The scanner is intentionally a *pre-filter*: it raises *candidate* findings
that a human reviewer can confirm or dismiss. We deliberately accept some
false positives over silently dropping real conflicts. The acceptance bar
for adding a new heuristic is "would a reviewer actually want to see this?"
— if the rule produces noise, it gets removed in a follow-up.

Read-only and LLM-free. No mutation of compliance or workflow state.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    ComplianceGate,
    ComplianceGateStatus,
    ConsolidatedRequirement,
    ContributionUnit,
    ContributionUnitStatus,
    Proposal,
    ProposalSection,
    ReworkAction,
    ReworkStatus,
    SectionStatus,
    Tender,
    TenderRequirement,
)

_CONTRADICTION_KIND = (
    "requirement_vs_proposal",
    "proposal_vs_evidence",
    "requirement_vs_requirement",
)

_NEGATIVE_MARKERS = (
    "non deve",
    "non può",
    "non puo",
    "non è ammesso",
    "non e ammesso",
    "non ammesso",
    "non consentito",
    "vietato",
    "escluso",
    "facoltativo",
    "opzionale",
)

_POSITIVE_MARKERS = (
    "deve",
    "obbligatorio",
    "obbligatoria",
    "richiesto",
    "necessario",
    "tassativo",
    "vincolante",
    "indispensabile",
)

_MIN_MAX_PATTERN = re.compile(
    r"(massimo|minimo|almeno|al massimo|al minimo|non superiore|non inferiore)\s+(\d+)\s*([a-zA-ZàèìòùÀÈÌÒÙ]+)",
    re.IGNORECASE,
)

_TOPIC_STOPWORDS = {
    "il",
    "la",
    "lo",
    "i",
    "le",
    "gli",
    "un",
    "una",
    "uno",
    "del",
    "della",
    "dello",
    "dei",
    "delle",
    "degli",
    "al",
    "alla",
    "allo",
    "ai",
    "alle",
    "agli",
    "in",
    "su",
    "per",
    "con",
    "tra",
    "fra",
    "da",
    "che",
    "ed",
    "et",
    "ma",
    "o",
    "e",
    "è",
    "non",
    "deve",
    "puo",
    "può",
    "sono",
    "essere",
    "avere",
    "ha",
    "fa",
    "do",
    "si",
    "ne",
    "ci",
    "vi",
}


def _normalize(text: str) -> str:
    return " ".join((text or "").casefold().split())


def _topic_signature(text: str) -> str:
    """Pick a coarse topic signature: 3 most informative non-stopword tokens."""

    tokens = re.findall(r"[a-zA-ZàèìòùÀÈÌÒÙ0-9]+", (text or "").casefold())
    informative = [tok for tok in tokens if tok not in _TOPIC_STOPWORDS and len(tok) > 3]
    informative.sort()
    return " ".join(informative[:3])


def _has_marker(text: str, markers: Iterable[str]) -> bool:
    haystack = " " + _normalize(text) + " "
    return any(f" {marker} " in haystack for marker in markers)


def _has_citation_metadata(consolidated: ConsolidatedRequirement) -> bool:
    metadata = consolidated.metadata_json or {}
    if not isinstance(metadata, Mapping):
        return False
    sources = metadata.get("sources") or []
    if not isinstance(sources, list):
        return False
    for source in sources:
        if not isinstance(source, Mapping):
            continue
        raw_candidate = source.get("raw_candidate")
        if isinstance(raw_candidate, Mapping) and raw_candidate.get("citations"):
            return True
        if source.get("citations"):
            return True
    return False


class ContradictionFinder:
    """Wave-2 contradiction scanner. Deterministic pre-filter, no LLM."""

    name = "contradiction_finder"
    description = (
        "Surfaces candidate contradictions: requirement vs proposal state, "
        "proposal claims without evidence, and requirements with conflicting "
        "modal wording. Deterministic, read-only, false positives expected."
    )
    input_keys = ("tender_id",)

    async def run(
        self,
        db: AsyncSession,
        inputs: Mapping[str, Any],
    ) -> dict[str, Any]:
        tender_id = inputs.get("tender_id")
        if tender_id is None:
            raise ValueError("contradiction_finder requires 'tender_id'")
        tender_id_int = int(tender_id)
        tender = await self._load_tender(db, tender_id_int)
        if tender is None:
            return self._empty_result(tender_id_int)

        contributions = await self._load_contributions(db, tender_id_int)
        reworks = await self._load_open_blocking_reworks(db, tender_id_int)
        gates = await self._load_failed_gates(db, tender_id_int)

        findings: list[dict[str, Any]] = []
        findings.extend(self._scan_requirement_vs_proposal(tender, contributions, reworks, gates))
        findings.extend(self._scan_proposal_vs_evidence(tender))
        findings.extend(self._scan_requirement_vs_requirement(tender))

        summary = {kind: 0 for kind in _CONTRADICTION_KIND}
        for finding in findings:
            kind = finding["kind"]
            if kind in summary:
                summary[kind] += 1

        return {
            "tender_id": tender_id_int,
            "summary": {
                "total": len(findings),
                **summary,
            },
            "findings": findings,
        }

    async def _load_tender(self, db: AsyncSession, tender_id: int) -> Tender | None:
        result = await db.execute(
            select(Tender)
            .where(Tender.id == tender_id)
            .options(
                selectinload(Tender.requirements).selectinload(TenderRequirement.proposal_section),
                selectinload(Tender.consolidated_requirements),
                selectinload(Tender.proposals).selectinload(Proposal.sections),
            )
        )
        return result.scalar_one_or_none()

    async def _load_contributions(
        self,
        db: AsyncSession,
        tender_id: int,
    ) -> dict[int, ContributionUnit]:
        result = await db.execute(
            select(ContributionUnit).where(ContributionUnit.tender_id == tender_id)
        )
        contributions = list(result.scalars())
        by_section: dict[int, ContributionUnit] = {}
        for contribution in contributions:
            section_id = contribution.proposal_section_id
            if section_id is None:
                continue
            existing = by_section.get(int(section_id))
            if existing is None or self._severity_score(contribution.status) > self._severity_score(
                existing.status
            ):
                by_section[int(section_id)] = contribution
        return by_section

    async def _load_open_blocking_reworks(
        self,
        db: AsyncSession,
        tender_id: int,
    ) -> dict[int, ReworkAction]:
        result = await db.execute(
            select(ReworkAction)
            .join(ContributionUnit, ContributionUnit.id == ReworkAction.contribution_unit_id)
            .where(
                ContributionUnit.tender_id == tender_id,
                ReworkAction.status == ReworkStatus.OPEN,
                ReworkAction.is_blocking.is_(True),
            )
        )
        out: dict[int, ReworkAction] = {}
        for rework in result.scalars():
            out[int(rework.contribution_unit_id)] = rework
        return out

    async def _load_failed_gates(
        self,
        db: AsyncSession,
        tender_id: int,
    ) -> dict[int, ComplianceGate]:
        result = await db.execute(
            select(ComplianceGate).where(
                ComplianceGate.tender_id == tender_id,
                ComplianceGate.status == ComplianceGateStatus.FAILED,
            )
        )
        out: dict[int, ComplianceGate] = {}
        for gate in result.scalars():
            if gate.contribution_unit_id is not None:
                out[int(gate.contribution_unit_id)] = gate
        return out

    @staticmethod
    def _severity_score(status: ContributionUnitStatus | None) -> int:
        if status is None:
            return 0
        order = {
            ContributionUnitStatus.BLOCKED: 5,
            ContributionUnitStatus.REWORK: 4,
            ContributionUnitStatus.IN_REVIEW: 3,
            ContributionUnitStatus.RECEIVED: 2,
            ContributionUnitStatus.REQUESTED: 1,
            ContributionUnitStatus.OPEN: 0,
            ContributionUnitStatus.COMPLETED: -1,
        }
        return order.get(status, 0)

    def _scan_requirement_vs_proposal(
        self,
        tender: Tender,
        contributions_by_section: dict[int, ContributionUnit],
        reworks_by_contribution: dict[int, ReworkAction],
        gates_by_contribution: dict[int, ComplianceGate],
    ) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        for requirement in list(tender.requirements or []):
            section_id = requirement.proposal_section_id
            if section_id is None:
                continue
            section = self._find_section(tender, int(section_id))
            if section is None:
                continue
            priority = (requirement.priority or "medium").casefold()
            evidence: list[str] = []
            contribution = contributions_by_section.get(int(section_id))
            if contribution is not None:
                if contribution.status == ContributionUnitStatus.BLOCKED:
                    evidence.append(f"contribution #{contribution.id} status=blocked")
                if int(contribution.id) in reworks_by_contribution:
                    rework = reworks_by_contribution[int(contribution.id)]
                    evidence.append(f"open blocking rework #{rework.id} severity={rework.severity}")
                if int(contribution.id) in gates_by_contribution:
                    gate = gates_by_contribution[int(contribution.id)]
                    evidence.append(f'failed compliance gate #{gate.id} "{gate.gate_name}"')
            if not evidence:
                continue
            severity = "critical" if priority == "high" else "high"
            findings.append(
                {
                    "kind": "requirement_vs_proposal",
                    "severity": severity,
                    "requirement_id": int(requirement.id),
                    "summary": (
                        f"Requirement #{requirement.id} ({priority}) is mapped to "
                        f"section #{section.id} but the chain is in a contradicting "
                        f"state: {', '.join(evidence)}"
                    )[:560],
                    "evidence": evidence,
                    "section_id": int(section.id),
                }
            )
        return findings

    def _scan_proposal_vs_evidence(self, tender: Tender) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        section_status_by_id: dict[int, SectionStatus] = {}
        for proposal in list(tender.proposals or []):
            for section in list(proposal.sections or []):
                if section.id is None:
                    continue
                section_status_by_id[int(section.id)] = section.status

        consolidated_by_section: dict[int, list[ConsolidatedRequirement]] = defaultdict(list)
        for consolidated in list(tender.consolidated_requirements or []):
            metadata = consolidated.metadata_json or {}
            if not isinstance(metadata, Mapping):
                continue
            section_id = metadata.get("proposal_section_id")
            try:
                section_id_int = int(section_id) if section_id is not None else None
            except (TypeError, ValueError):
                section_id_int = None
            if section_id_int is None:
                continue
            consolidated_by_section[section_id_int].append(consolidated)

        for section_id, consolidated_list in consolidated_by_section.items():
            if section_status_by_id.get(section_id) != SectionStatus.APPROVED:
                continue
            for consolidated in consolidated_list:
                if _has_citation_metadata(consolidated):
                    continue
                findings.append(
                    {
                        "kind": "proposal_vs_evidence",
                        "severity": "high",
                        "requirement_id": int(consolidated.id),
                        "summary": (
                            f"Consolidated requirement #{consolidated.id} mapped to "
                            f"approved section #{section_id} but has no citation "
                            f"metadata."
                        )[:560],
                        "evidence": [
                            f"section #{section_id} status=approved",
                            "no citations in consolidated.metadata_json.sources",
                        ],
                        "section_id": section_id,
                    }
                )
        return findings

    def _scan_requirement_vs_requirement(self, tender: Tender) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        by_topic: dict[str, list[ConsolidatedRequirement]] = defaultdict(list)
        for consolidated in list(tender.consolidated_requirements or []):
            text = consolidated.canonical_text or consolidated.normalized_text or ""
            topic = _topic_signature(text)
            if not topic:
                continue
            by_topic[topic].append(consolidated)

        for topic, group in by_topic.items():
            if len(group) < 2:
                continue
            positives = [r for r in group if _has_marker(r.canonical_text or "", _POSITIVE_MARKERS)]
            negatives = [r for r in group if _has_marker(r.canonical_text or "", _NEGATIVE_MARKERS)]
            if positives and negatives:
                pos = positives[0]
                neg = negatives[0]
                if pos.id == neg.id:
                    continue
                findings.append(
                    {
                        "kind": "requirement_vs_requirement",
                        "severity": "high",
                        "requirement_id": int(pos.id),
                        "summary": (
                            f'Modal contradiction on topic "{topic}": '
                            f"requirement #{pos.id} (positive) vs requirement "
                            f"#{neg.id} (negative)."
                        )[:560],
                        "evidence": [
                            f"#{pos.id}: {(pos.canonical_text or '')[:160]}",
                            f"#{neg.id}: {(neg.canonical_text or '')[:160]}",
                        ],
                        "related_requirement_id": int(neg.id),
                        "topic": topic,
                    }
                )
                continue

            numeric = [
                (r, match)
                for r in group
                for match in [_MIN_MAX_PATTERN.search(r.canonical_text or "")]
                if match
            ]
            if len(numeric) >= 2:
                first, first_match = numeric[0]
                second, second_match = numeric[1]
                if first.id == second.id:
                    continue
                first_keyword = first_match.group(1).casefold()
                second_keyword = second_match.group(1).casefold()
                first_value = int(first_match.group(2))
                second_value = int(second_match.group(2))
                if (
                    first_keyword.startswith(("massimo", "al massimo", "non superiore"))
                    and second_keyword.startswith(
                        ("minimo", "almeno", "al minimo", "non inferiore")
                    )
                    and first_value < second_value
                ):
                    findings.append(
                        {
                            "kind": "requirement_vs_requirement",
                            "severity": "medium",
                            "requirement_id": int(first.id),
                            "summary": (
                                f'Numerical contradiction on topic "{topic}": '
                                f"requirement #{first.id} requires "
                                f"{first_keyword} {first_value} while requirement "
                                f"#{second.id} requires {second_keyword} {second_value}."
                            )[:560],
                            "evidence": [
                                f"#{first.id}: {first_match.group(0)}",
                                f"#{second.id}: {second_match.group(0)}",
                            ],
                            "related_requirement_id": int(second.id),
                            "topic": topic,
                        }
                    )
        return findings

    @staticmethod
    def _find_section(tender: Tender, section_id: int) -> ProposalSection | None:
        for proposal in list(tender.proposals or []):
            for section in list(proposal.sections or []):
                if section.id is not None and int(section.id) == section_id:
                    return section
        return None

    @staticmethod
    def _empty_result(tender_id: int) -> dict[str, Any]:
        return {
            "tender_id": tender_id,
            "summary": {"total": 0, **{kind: 0 for kind in _CONTRADICTION_KIND}},
            "findings": [],
        }


__all__ = ["ContradictionFinder"]
