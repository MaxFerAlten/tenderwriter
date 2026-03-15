"""Unit tests for tender requirement response mapping."""

import os
import unittest

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

from app.api.tenders import _requirement_to_response
from app.models import ComplianceStatus, ProposalSection, SectionStatus, TenderRequirement


class TenderRequirementResponseTests(unittest.TestCase):
    def test_requirement_response_includes_mapping_metadata(self) -> None:
        section = ProposalSection(
            id=42,
            proposal_id=7,
            title="Compliance matrix",
            status=SectionStatus.IN_REVIEW,
        )
        requirement = TenderRequirement(
            id=5,
            requirement_text="Provide signed annex",
            category="legal",
            priority="high",
            compliance_status=ComplianceStatus.PARTIALLY_ADDRESSED,
            proposal_section_id=42,
        )
        requirement.proposal_section = section

        response = _requirement_to_response(requirement)

        self.assertEqual(response.mapped_section_id, 42)
        self.assertEqual(response.mapped_section_title, "Compliance matrix")
        self.assertEqual(response.compliance_status, "partially_addressed")

    def test_requirement_response_handles_unmapped_requirement(self) -> None:
        requirement = TenderRequirement(
            id=8,
            requirement_text="Provide insurance",
            category="risk",
            priority="medium",
            compliance_status=ComplianceStatus.NOT_ADDRESSED,
            proposal_section_id=None,
        )

        response = _requirement_to_response(requirement)

        self.assertIsNone(response.mapped_section_id)
        self.assertIsNone(response.mapped_section_title)
        self.assertEqual(response.compliance_status, "not_addressed")


if __name__ == "__main__":
    unittest.main()

