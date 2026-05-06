"""Wave-1 TenderWriter intelligence tools.

This package collects the three read-only tools transplanted from MiroFish's
ReportAgent pattern and specialised for procurement:

- :class:`CoverageAnalyzer` — requirement → section mapping and gap audit;
- :class:`EvidenceAuditor` — evidence-depth classification per requirement;
- :class:`CompliancePanorama` — adapter over the KPI reason engine.

All tools are read-only. They must never mutate workflow, review, rework or
compliance gate state — the KPI engine and the existing observability
services remain the single source of truth.
"""

from __future__ import annotations

from app.intelligence.tool_registry import TenderToolRegistry
from app.intelligence.tools.compliance_panorama import CompliancePanorama
from app.intelligence.tools.contradiction_finder import ContradictionFinder
from app.intelligence.tools.coverage_analyzer import CoverageAnalyzer
from app.intelligence.tools.evidence_auditor import EvidenceAuditor
from app.intelligence.tools.graph_path_explainer import GraphPathExplainer


def build_default_tool_registry(
    *,
    compliance_panorama: CompliancePanorama | None = None,
    contradiction_finder: ContradictionFinder | None = None,
    coverage_analyzer: CoverageAnalyzer | None = None,
    evidence_auditor: EvidenceAuditor | None = None,
    graph_path_explainer: GraphPathExplainer | None = None,
) -> TenderToolRegistry:
    """Return a registry pre-populated with the Wave-1 + Wave-2 tools."""

    registry = TenderToolRegistry()
    registry.register(coverage_analyzer or CoverageAnalyzer())
    registry.register(evidence_auditor or EvidenceAuditor())
    registry.register(compliance_panorama or CompliancePanorama())
    registry.register(graph_path_explainer or GraphPathExplainer())
    registry.register(contradiction_finder or ContradictionFinder())
    return registry


__all__ = [
    "CompliancePanorama",
    "ContradictionFinder",
    "CoverageAnalyzer",
    "EvidenceAuditor",
    "GraphPathExplainer",
    "build_default_tool_registry",
]
