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
ProposalSection = _MODELS_MODULE.ProposalSection
SectionStatus = _MODELS_MODULE.SectionStatus
TenderRequirement = _MODELS_MODULE.TenderRequirement

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
            TenderRequirement(requirement_text="Provide signed annex", compliance_status=ComplianceStatus.PARTIALLY_ADDRESSED),
            TenderRequirement(requirement_text="Provide insurance", compliance_status=ComplianceStatus.NOT_ADDRESSED),
        ]
        sections = [
            ProposalSection(id=11, proposal_id=7, title="Compliance", status=SectionStatus.IN_REVIEW),
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
            TenderRequirement(requirement_text="Provide signed annex", compliance_status=ComplianceStatus.PARTIALLY_ADDRESSED),
        ]
        sections = [
            ProposalSection(id=11, proposal_id=7, title="Compliance", status=SectionStatus.IN_PROGRESS),
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
            TenderRequirement(requirement_text="Provide signed annex", compliance_status=ComplianceStatus.FULLY_ADDRESSED),
            TenderRequirement(requirement_text="Provide insurance", compliance_status=ComplianceStatus.FULLY_ADDRESSED),
        ]
        sections = [
            ProposalSection(id=11, proposal_id=7, title="Compliance", status=SectionStatus.APPROVED),
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
            TenderRequirement(requirement_text="Provide signed annex", compliance_status=ComplianceStatus.PARTIALLY_ADDRESSED),
        ]
        sections = [
            ProposalSection(id=11, proposal_id=7, title="Compliance", status=SectionStatus.APPROVED),
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

