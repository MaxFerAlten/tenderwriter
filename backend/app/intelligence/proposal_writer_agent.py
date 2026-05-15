"""Controlled, tool-driven proposal section writer (Wave-4 finalization).

The :class:`ProposalWriterAgent` is the writing counterpart to the
read-only :class:`TenderIntelligenceAgent`: it wraps the existing
``HybridRAGEngine`` ``WRITE_SECTION`` mode with the Wave-1/2/3 tool
context (coverage gaps, evidence audit, contradictions, rehearsal
recommendations) so that drafts and improvements are *grounded* in the
same evidence the rehearsal personas consume.

Mutation contract
-----------------
* ``apply=False`` (default): preview only. No DB writes. Tool calls are
  read-only by construction.
* ``apply=True``: update *only* the targeted ``ProposalSection`` row.
  The agent rewrites ``content`` (TipTap JSON) and ``status``; an audit
  marker is embedded in ``content.attrs._proposal_writer_audit`` so the
  origin of the text is recoverable without a schema migration.

The agent never mutates ``contribution_units``, ``review_cycles``,
``rework_actions`` or ``compliance_gates`` — those remain owned by
``operational_workflow`` and the manual recommendation → rework path.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.intelligence.proposal_writer_models import (
    ProposalWriterMode,
    ProposalWriterRequest,
    ProposalWriterResult,
)
from app.intelligence.rehearsal_summary import build_rehearsal_summary
from app.intelligence.tool_registry import TenderToolRegistry
from app.models import (
    Proposal,
    ProposalSection,
    RehearsalRecommendation,
    RehearsalRecommendationStatus,
    SectionStatus,
    Tender,
)

logger = logging.getLogger(__name__)


_AGENT_VERSION = "tw-proposal-writer-v1"


class ProposalWriterError(ValueError):
    """Raised for caller-facing validation failures (bad ids, ownership mismatch)."""


class ProposalWriterAgent:
    """Tool-driven, rehearsal-aware writing agent.

    The agent does not own the RAG engine — it accepts the engine via
    constructor injection so tests can substitute a stub and so the
    process-wide ``HybridRAGEngine`` (registered on ``app.state``) is
    reused without re-initialisation.
    """

    def __init__(
        self,
        registry: TenderToolRegistry,
        *,
        rag_engine: Any | None = None,
    ) -> None:
        self._registry = registry
        self._rag_engine = rag_engine

    async def execute(
        self,
        db: AsyncSession,
        request: ProposalWriterRequest,
    ) -> ProposalWriterResult:
        section, proposal, tender = await self._load_chain(
            db,
            tender_id=request.tender_id,
            proposal_id=request.proposal_id,
            section_id=request.section_id,
        )

        warnings: list[str] = []

        coverage_summary = await self._maybe_run_tool(
            "coverage_analyzer",
            request.use_coverage_analyzer,
            db,
            tender.id,
            warnings,
        )
        evidence_summary = await self._maybe_run_tool(
            "evidence_auditor",
            request.use_evidence_audit,
            db,
            tender.id,
            warnings,
        )
        contradiction_output = await self._maybe_run_tool(
            "contradiction_finder",
            request.use_contradiction_check,
            db,
            tender.id,
            warnings,
        )
        contradictions = list((contradiction_output or {}).get("findings") or [])

        rehearsal_context = await self._maybe_load_rehearsal_context(
            db=db,
            tender_id=tender.id,
            proposal_id=proposal.id,
            mode=request.mode,
            enabled=request.use_rehearsal_summary,
            warnings=warnings,
        )

        prompt = self._build_prompt(
            section=section,
            request=request,
            coverage=coverage_summary,
            evidence=evidence_summary,
            contradictions=contradictions,
            rehearsal_context=rehearsal_context,
        )

        draft_text = await self._generate_draft(
            section=section,
            tender_id=tender.id,
            prompt=prompt,
            request=request,
            warnings=warnings,
        )

        applied = False
        if request.apply:
            applied = await self._apply_to_section(
                db,
                section=section,
                draft_text=draft_text,
                request=request,
            )

        return ProposalWriterResult(
            tender_id=tender.id,
            proposal_id=proposal.id,
            section_id=section.id,
            mode=request.mode,
            draft_text=draft_text,
            coverage_summary=self._summary_or_empty(coverage_summary),
            evidence_summary=self._summary_or_empty(evidence_summary),
            contradictions=contradictions,
            rehearsal_context=rehearsal_context,
            warnings=warnings,
            applied=applied,
            agent_version=_AGENT_VERSION,
        )

    async def _load_chain(
        self,
        db: AsyncSession,
        *,
        tender_id: int,
        proposal_id: int,
        section_id: int,
    ) -> tuple[ProposalSection, Proposal, Tender]:
        section = (
            await db.execute(
                select(ProposalSection)
                .where(ProposalSection.id == section_id)
                .options(selectinload(ProposalSection.proposal))
            )
        ).scalar_one_or_none()
        if section is None:
            raise ProposalWriterError(f"section {section_id} not found")
        if section.proposal_id != proposal_id:
            raise ProposalWriterError(
                f"section {section_id} does not belong to proposal {proposal_id}"
            )

        proposal = section.proposal
        if proposal is None:
            proposal = await db.get(Proposal, proposal_id)
        if proposal is None:
            raise ProposalWriterError(f"proposal {proposal_id} not found")
        if proposal.tender_id != tender_id:
            raise ProposalWriterError(
                f"proposal {proposal_id} does not belong to tender {tender_id}"
            )

        tender = await db.get(Tender, tender_id)
        if tender is None:
            raise ProposalWriterError(f"tender {tender_id} not found")

        return section, proposal, tender

    async def _maybe_run_tool(
        self,
        name: str,
        enabled: bool,
        db: AsyncSession,
        tender_id: int,
        warnings: list[str],
    ) -> dict[str, Any]:
        if not enabled:
            return {}
        if not self._registry.contains(name):
            warnings.append(f"tool {name!r} unavailable in registry")
            return {}
        try:
            return (await self._registry.run(name, db=db, inputs={"tender_id": tender_id})) or {}
        except Exception as exc:
            warnings.append(f"tool {name!r} failed: {exc}")
            logger.exception(
                "proposal_writer.tool_failed",
                extra={"tool": name, "tender_id": tender_id},
            )
            return {}

    async def _maybe_load_rehearsal_context(
        self,
        *,
        db: AsyncSession,
        tender_id: int,
        proposal_id: int,
        mode: ProposalWriterMode,
        enabled: bool,
        warnings: list[str],
    ) -> dict[str, Any] | None:
        if not enabled and mode != "address_rehearsal_findings":
            return None
        try:
            summary = await build_rehearsal_summary(
                db, tender_id=tender_id, proposal_id=proposal_id
            )
        except Exception as exc:
            warnings.append(f"rehearsal_summary lookup failed: {exc}")
            logger.exception(
                "proposal_writer.rehearsal_summary_failed",
                extra={"tender_id": tender_id, "proposal_id": proposal_id},
            )
            return None

        if summary is None:
            if mode == "address_rehearsal_findings":
                warnings.append(
                    "address_rehearsal_findings requested but no completed rehearsal exists"
                )
            return None

        run_id = summary.get("run_id")
        recommendations: list[dict[str, Any]] = []
        if run_id is not None:
            try:
                rows = (
                    (
                        await db.execute(
                            select(RehearsalRecommendation)
                            .where(RehearsalRecommendation.rehearsal_run_id == run_id)
                            .where(
                                RehearsalRecommendation.status
                                == RehearsalRecommendationStatus.PROPOSED
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
            except Exception as exc:
                warnings.append(f"rehearsal recommendations lookup failed: {exc}")
                rows = []
            for row in rows:
                recommendations.append(
                    {
                        "scope_type": row.scope_type,
                        "scope_id": row.scope_id,
                        "severity": row.severity,
                        "is_blocking": bool(row.is_blocking),
                        "rationale": row.rationale,
                        "suggested_owner_role": row.suggested_owner_role,
                    }
                )

        return {"summary": summary, "recommendations": recommendations}

    def _build_prompt(
        self,
        *,
        section: ProposalSection,
        request: ProposalWriterRequest,
        coverage: dict[str, Any],
        evidence: dict[str, Any],
        contradictions: list[dict[str, Any]],
        rehearsal_context: dict[str, Any] | None,
    ) -> str:
        parts: list[str] = []
        title = section.title or f"Sezione {section.id}"
        parts.append(f"Titolo sezione: {title}")
        parts.append(f"Modalità: {request.mode}")

        if request.instruction:
            parts.append(f"Istruzioni operative: {request.instruction.strip()}")

        if request.mode in {"rewrite", "improve", "address_rehearsal_findings"}:
            existing = _extract_section_text(section.content)
            if existing:
                parts.append("Testo attuale della sezione:")
                parts.append(existing)
            else:
                parts.append("Testo attuale della sezione: (vuoto)")

        coverage_gaps = (coverage or {}).get("gaps") or []
        if coverage_gaps:
            top = coverage_gaps[:5]
            parts.append("Gap di copertura ad alta priorità:")
            for gap in top:
                summary = gap.get("summary") or gap.get("requirement_id") or "(n.d.)"
                priority = gap.get("priority") or "n/a"
                parts.append(f"- [{priority}] {summary}")

        evidence_findings = (evidence or {}).get("findings") or []
        if evidence_findings:
            parts.append("Carenze di evidenza segnalate:")
            for finding in evidence_findings[:5]:
                summary = finding.get("summary") or finding.get("requirement_id") or "(n.d.)"
                parts.append(f"- {summary}")

        if contradictions:
            parts.append("Contraddizioni rilevate (da risolvere o evitare):")
            for finding in contradictions[:5]:
                summary = finding.get("summary") or finding.get("description") or "(n.d.)"
                parts.append(f"- {summary}")

        if rehearsal_context:
            summary = rehearsal_context.get("summary") or {}
            score = summary.get("overall_score")
            health = summary.get("health_projection")
            if score is not None or health is not None:
                parts.append(f"Stato rehearsal: punteggio={score}, salute={health}")
            recs = rehearsal_context.get("recommendations") or []
            if recs and request.mode == "address_rehearsal_findings":
                parts.append("Raccomandazioni rehearsal da indirizzare nel testo:")
                for rec in recs[:6]:
                    rationale = rec.get("rationale") or "(senza dettaglio)"
                    severity = rec.get("severity") or "?"
                    blocking = " [BLOCCANTE]" if rec.get("is_blocking") else ""
                    parts.append(f"- [{severity}{blocking}] {rationale}")

        if request.mode == "draft":
            parts.append(
                "Genera una bozza professionale, in italiano, completa e fondata sulle evidenze."
            )
        elif request.mode == "rewrite":
            parts.append(
                "Riscrivi il testo mantenendo intento ed evidenze, migliorando chiarezza e tono formale."
            )
        elif request.mode == "improve":
            parts.append(
                "Migliora il testo affrontando i gap di copertura e le carenze di evidenza elencate."
            )
        elif request.mode == "address_rehearsal_findings":
            parts.append(
                "Riscrivi il testo affrontando esplicitamente le raccomandazioni rehearsal sopra."
            )

        return "\n\n".join(parts)

    async def _generate_draft(
        self,
        *,
        section: ProposalSection,
        tender_id: int,
        prompt: str,
        request: ProposalWriterRequest,
        warnings: list[str],
    ) -> str:
        engine = self._rag_engine
        if engine is None:
            warnings.append("rag_engine unavailable; returning prompt skeleton")
            return prompt

        from app.rag.engine import QueryMode, RAGQuery  # local import to avoid cycles

        rag_query = RAGQuery(
            text=prompt,
            mode=QueryMode.WRITE_SECTION,
            section_title=section.title or "",
            instructions=request.instruction or "",
            section_content=_extract_section_text(section.content),
            tender_id=tender_id,
            filters={
                "tender_id": tender_id,
                "proposal_id": request.proposal_id,
                "section_id": request.section_id,
            },
        )
        try:
            await engine.ensure_initialized()
            response = await engine.query(rag_query)
        except Exception as exc:
            warnings.append(f"rag_engine generation failed: {exc}")
            logger.exception(
                "proposal_writer.generation_failed",
                extra={"tender_id": tender_id, "section_id": section.id},
            )
            return prompt

        return getattr(response, "answer", "") or ""

    async def _apply_to_section(
        self,
        db: AsyncSession,
        *,
        section: ProposalSection,
        draft_text: str,
        request: ProposalWriterRequest,
    ) -> bool:
        if not draft_text.strip():
            return False
        audit = {
            "agent": _AGENT_VERSION,
            "mode": request.mode,
            "applied_at": datetime.now(timezone.utc).isoformat(),
            "instruction": (request.instruction or "")[:1000],
        }
        section.content = _text_to_tiptap_doc(draft_text, audit=audit)
        if section.status in (None, SectionStatus.TODO):
            section.status = SectionStatus.IN_PROGRESS
        await db.flush()
        return True

    @staticmethod
    def _summary_or_empty(payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return {}
        summary = payload.get("summary")
        if isinstance(summary, dict):
            return summary
        return {}


def _extract_section_text(content: Any) -> str:
    """Flatten a TipTap JSON document into plain text for prompt context."""
    if isinstance(content, str):
        return content
    if not isinstance(content, dict):
        return ""

    text_chunks: list[str] = []

    def _walk(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") == "text" and isinstance(node.get("text"), str):
                text_chunks.append(node["text"])
            children = node.get("content")
            if isinstance(children, list):
                for child in children:
                    _walk(child)
                if node.get("type") in {"paragraph", "heading", "listItem"}:
                    text_chunks.append("\n")
        elif isinstance(node, list):
            for child in node:
                _walk(child)

    _walk(content)
    flat = "".join(text_chunks).strip()
    return flat


def _text_to_tiptap_doc(text: str, *, audit: dict[str, Any] | None = None) -> dict[str, Any]:
    """Wrap plain text in a minimal TipTap doc, optionally tagging audit metadata."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    content: list[dict[str, Any]] = [
        {
            "type": "paragraph",
            "content": [{"type": "text", "text": p}],
        }
        for p in paragraphs
    ] or [{"type": "paragraph"}]
    doc: dict[str, Any] = {"type": "doc", "content": content}
    if audit:
        doc["attrs"] = {"_proposal_writer_audit": audit}
    return doc


__all__ = [
    "ProposalWriterAgent",
    "ProposalWriterError",
]
