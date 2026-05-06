"""Pydantic contracts for the :class:`ProposalWriterAgent`.

The agent is a controlled, tool-driven, rehearsal-aware writer for
``ProposalSection`` content. It must never mutate the database unless
called with ``apply=True``; even then mutation is restricted to the
single section identified by the request.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ProposalWriterMode = Literal[
    "draft",
    "rewrite",
    "improve",
    "address_rehearsal_findings",
]


class ProposalWriterRequest(BaseModel):
    """Input contract for the proposal writer agent.

    ``apply`` defaults to ``False``: callers must opt in to DB mutation
    explicitly. The ``use_*`` flags decide which read-only intelligence
    tools are folded into the generation context.
    """

    model_config = ConfigDict(extra="forbid")

    tender_id: int = Field(gt=0)
    proposal_id: int = Field(gt=0)
    section_id: int = Field(gt=0)
    instruction: str | None = Field(default=None, max_length=4000)
    mode: ProposalWriterMode = "draft"
    apply: bool = False
    use_rehearsal_summary: bool = True
    use_contradiction_check: bool = True
    use_evidence_audit: bool = True
    use_coverage_analyzer: bool = True


class ProposalWriterResult(BaseModel):
    """Output contract returned to API callers.

    Always includes the generated ``draft_text``; ``applied`` is ``True``
    only when ``apply=True`` succeeded against the canonical section row.
    """

    model_config = ConfigDict(extra="forbid")

    tender_id: int
    proposal_id: int
    section_id: int
    mode: ProposalWriterMode
    draft_text: str
    coverage_summary: dict[str, Any] = Field(default_factory=dict)
    evidence_summary: dict[str, Any] = Field(default_factory=dict)
    contradictions: list[dict[str, Any]] = Field(default_factory=list)
    rehearsal_context: dict[str, Any] | None = None
    warnings: list[str] = Field(default_factory=list)
    applied: bool = False
    agent_version: str = "tw-proposal-writer-v1"


__all__ = [
    "ProposalWriterMode",
    "ProposalWriterRequest",
    "ProposalWriterResult",
]
