"""Unit tests for compliance observability helpers."""

import os
import unittest
from datetime import datetime, timezone

from test_module_loaders import load_models_test_module, load_service_test_module

_TEST_ENV = {
    "APP_SECRET_KEY": "alpha-key-123456789012345678901234567890",
    "ADMIN_PASSWORD": "test-admin-password-1234567890",
    "DATABASE_URL": "postgresql+asyncpg://tester:securepass@localhost:5432/tenderwriter",
    "NEO4J_PASSWORD": "test-neo4j-password-1234567890",
    "MINIO_SECRET_KEY": "test-minio-password-1234567890",
    "ONLYOFFICE_JWT_SECRET": "office-jwt-token-12345678901234567890",
}
for key, value in _TEST_ENV.items():
    os.environ.setdefault(key, value)

_MODELS_MODULE = load_models_test_module()
_COMPLIANCE_MODULE = load_service_test_module("app.services.compliance_observability")

ComplianceGateStatus = _MODELS_MODULE.ComplianceGateStatus
ComplianceStatus = _MODELS_MODULE.ComplianceStatus
ConsolidatedRequirement = _MODELS_MODULE.ConsolidatedRequirement
ProposalSection = _MODELS_MODULE.ProposalSection
SectionStatus = _MODELS_MODULE.SectionStatus
Tender = _MODELS_MODULE.Tender
TenderRequirement = _MODELS_MODULE.TenderRequirement

build_compliance_requirement_coverage = _COMPLIANCE_MODULE.build_compliance_requirement_coverage
determine_auto_gate_target_status = _COMPLIANCE_MODULE.determine_auto_gate_target_status
derive_requirement_compliance_status = _COMPLIANCE_MODULE.derive_requirement_compliance_status


class RequirementComplianceMappingTests(unittest.TestCase):
    def test_approved_section_maps_to_fully_addressed(self) -> None:
        status = derive_requirement_compliance_status(SectionStatus.APPROVED)
        self.assertEqual(status, ComplianceStatus.FULLY_ADDRESSED)

    def test_review_section_maps_to_partially_addressed(self) -> None:
        status = derive_requirement_compliance_status(SectionStatus.IN_REVIEW)
        self.assertEqual(status, ComplianceStatus.PARTIALLY_ADDRESSED)

    def test_todo_section_maps_to_not_addressed(self) -> None:
        status = derive_requirement_compliance_status(SectionStatus.TODO)
        self.assertEqual(status, ComplianceStatus.NOT_ADDRESSED)

    def test_coverage_falls_back_to_legacy_requirements_without_approved_consolidated_rows(
        self,
    ) -> None:
        tender = Tender(id=71, title="Legacy tender")
        tender.requirements = [
            TenderRequirement(
                id=501,
                tender_id=71,
                requirement_text="Provide signed annex A.",
                category="administrative",
                priority="high",
                compliance_status=ComplianceStatus.PARTIALLY_ADDRESSED,
            )
        ]
        tender.consolidated_requirements = [
            ConsolidatedRequirement(
                id=801,
                tender_id=71,
                canonical_text="Provide signed annex A.",
                normalized_text="provide signed annex a.",
                priority="high",
                source_count=1,
                consolidation_method="staging_v1",
                review_state="pending",
                graph_state="active",
            )
        ]

        coverage = build_compliance_requirement_coverage(tender)

        self.assertEqual(len(coverage), 1)
        self.assertEqual(coverage[0].id, 501)
        self.assertEqual(coverage[0].requirement_text, "Provide signed annex A.")
        self.assertEqual(coverage[0].coverage_source, "legacy")
        self.assertEqual(coverage[0].compliance_status, ComplianceStatus.PARTIALLY_ADDRESSED)

    def test_coverage_prefers_approved_consolidated_requirements_and_reuses_legacy_mapping(
        self,
    ) -> None:
        tender = Tender(id=72, title="Consolidated tender")
        mapped_section = ProposalSection(
            id=601, proposal_id=88, title="Compliance matrix", status=SectionStatus.APPROVED
        )
        legacy_requirement = TenderRequirement(
            id=502,
            tender_id=72,
            requirement_text="Submit insurance certificate.",
            category="risk",
            priority="medium",
            compliance_status=ComplianceStatus.FULLY_ADDRESSED,
            proposal_section_id=601,
        )
        legacy_requirement.proposal_section = mapped_section
        tender.requirements = [legacy_requirement]
        tender.consolidated_requirements = [
            ConsolidatedRequirement(
                id=802,
                tender_id=72,
                canonical_text="Submit cyber insurance certificate.",
                normalized_text="submit cyber insurance certificate.",
                category="risk",
                priority="high",
                source_count=1,
                consolidation_method="staging_v1",
                review_state="approved",
                graph_state="active",
                metadata_json={"sources": [{"legacy_requirement_id": 502}]},
            ),
            ConsolidatedRequirement(
                id=803,
                tender_id=72,
                canonical_text="Pending requirement not ready for coverage.",
                normalized_text="pending requirement not ready for coverage.",
                priority="high",
                source_count=1,
                consolidation_method="staging_v1",
                review_state="pending",
                graph_state="active",
            ),
        ]

        coverage = build_compliance_requirement_coverage(tender)

        self.assertEqual(len(coverage), 2)
        approved_coverage = next(item for item in coverage if item.id == 802)
        pending_coverage = next(item for item in coverage if item.id == 803)
        self.assertEqual(approved_coverage.requirement_text, "Submit cyber insurance certificate.")
        self.assertEqual(approved_coverage.priority, "high")
        self.assertEqual(approved_coverage.coverage_source, "consolidated_approved")
        self.assertEqual(approved_coverage.compliance_status, ComplianceStatus.FULLY_ADDRESSED)
        self.assertEqual(approved_coverage.proposal_section_id, 601)
        self.assertEqual(approved_coverage.proposal_section_title, "Compliance matrix")
        self.assertEqual(pending_coverage.coverage_source, "consolidated_review_pending")
        self.assertEqual(pending_coverage.compliance_status, ComplianceStatus.NOT_ADDRESSED)
        self.assertIsNone(pending_coverage.proposal_section_id)


class AutoComplianceGateDecisionTests(unittest.TestCase):
    def test_no_requirements_means_no_gate(self) -> None:
        gate_status = determine_auto_gate_target_status(
            requirements=[],
            sections=[],
            tender_due_at=None,
            now=datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc),
        )
        self.assertIsNone(gate_status)

    def test_in_review_with_unresolved_requirements_opens_gate(self) -> None:
        requirements = [
            TenderRequirement(
                requirement_text="Provide signed annex",
                compliance_status=ComplianceStatus.PARTIALLY_ADDRESSED,
            ),
            TenderRequirement(
                requirement_text="Provide insurance",
                compliance_status=ComplianceStatus.NOT_ADDRESSED,
            ),
        ]
        sections = [
            ProposalSection(
                id=11, proposal_id=7, title="Compliance", status=SectionStatus.IN_REVIEW
            ),
        ]

        gate_status = determine_auto_gate_target_status(
            requirements=requirements,
            sections=sections,
            tender_due_at=datetime(2026, 3, 20, 9, 0, tzinfo=timezone.utc),
            now=datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc),
        )

        self.assertEqual(gate_status, ComplianceGateStatus.OPEN)

    def test_in_progress_only_does_not_open_gate_when_sections_exist(self) -> None:
        requirements = [
            TenderRequirement(
                requirement_text="Provide signed annex",
                compliance_status=ComplianceStatus.PARTIALLY_ADDRESSED,
            ),
        ]
        sections = [
            ProposalSection(
                id=11, proposal_id=7, title="Compliance", status=SectionStatus.IN_PROGRESS
            ),
        ]

        gate_status = determine_auto_gate_target_status(
            requirements=requirements,
            sections=sections,
            tender_due_at=datetime(2026, 3, 20, 9, 0, tzinfo=timezone.utc),
            now=datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc),
        )

        self.assertIsNone(gate_status)

    def test_all_fully_addressed_passes_gate(self) -> None:
        requirements = [
            TenderRequirement(
                requirement_text="Provide signed annex",
                compliance_status=ComplianceStatus.FULLY_ADDRESSED,
            ),
            TenderRequirement(
                requirement_text="Provide insurance",
                compliance_status=ComplianceStatus.FULLY_ADDRESSED,
            ),
        ]
        sections = [
            ProposalSection(
                id=11, proposal_id=7, title="Compliance", status=SectionStatus.APPROVED
            ),
        ]

        gate_status = determine_auto_gate_target_status(
            requirements=requirements,
            sections=sections,
            tender_due_at=datetime(2026, 3, 20, 9, 0, tzinfo=timezone.utc),
            now=datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc),
        )

        self.assertEqual(gate_status, ComplianceGateStatus.PASSED)

    def test_overdue_unresolved_requirements_fail_gate(self) -> None:
        requirements = [
            TenderRequirement(
                requirement_text="Provide signed annex",
                compliance_status=ComplianceStatus.PARTIALLY_ADDRESSED,
            ),
        ]
        sections = [
            ProposalSection(
                id=11, proposal_id=7, title="Compliance", status=SectionStatus.APPROVED
            ),
        ]

        gate_status = determine_auto_gate_target_status(
            requirements=requirements,
            sections=sections,
            tender_due_at=datetime(2026, 3, 14, 9, 0, tzinfo=timezone.utc),
            now=datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc),
        )

        self.assertEqual(gate_status, ComplianceGateStatus.FAILED)


if __name__ == "__main__":
    unittest.main()
