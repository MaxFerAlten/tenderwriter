"""Unit tests for tender requirement response mapping."""

import os
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

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

from app.api.tenders import (
    TenderClarificationUpdate,
    _requirement_to_response,
    _tender_to_response,
    close_tender_clarification,
    draft_tender_clarification_response,
    submit_tender_clarification_response,
)
from app.models import ComplianceStatus, ProposalSection, SectionStatus, Tender, TenderRequirement, TenderStatus


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

    def test_tender_response_exposes_lifecycle_metadata(self) -> None:
        tender = Tender(
            id=13,
            title="Lifecycle tender",
            client="ACME",
            status=TenderStatus.ACTIVE,
        )
        tender.metadata_json = {
            "lifecycle": {
                "decision": {"decision": "go", "decided_at": "2026-03-20T08:00:00+00:00"},
                "submission_status": {"submission_status": "acknowledged"},
            }
        }

        response = _tender_to_response(tender)

        assert response.lifecycle_metadata is not None
        self.assertEqual(response.lifecycle_metadata["decision"]["decision"], "go")
        self.assertEqual(response.lifecycle_metadata["submission_status"]["submission_status"], "acknowledged")


class _FakeAsyncSession:
    def __init__(self) -> None:
        self.flush_called = False

    async def flush(self) -> None:
        self.flush_called = True


class TenderClarificationLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_clarification_update_routes_require_existing_record(self) -> None:
        current_user = type("User", (), {"id": 7, "role": "admin"})()
        data = TenderClarificationUpdate(response_summary="Response prepared")

        for route in (
            draft_tender_clarification_response,
            submit_tender_clarification_response,
            close_tender_clarification,
        ):
            tender = Tender(id=13, title="Lifecycle tender", client="ACME", status=TenderStatus.ACTIVE)
            tender.metadata_json = {"lifecycle": {}}
            db = _FakeAsyncSession()

            with self.subTest(route=route.__name__):
                with (
                    patch("app.api.tenders.check_tender_access", AsyncMock(return_value=tender)),
                    patch("app.api.tenders.sync_tender_and_publish_event", AsyncMock()) as sync_mock,
                ):
                    with self.assertRaises(HTTPException) as exc:
                        await route(
                            tender_id=13,
                            clarification_id="clar-missing",
                            data=data,
                            current_user=current_user,
                            db=db,
                        )

                    self.assertEqual(exc.exception.status_code, 404)
                    self.assertEqual(exc.exception.detail, "Clarification not found")
                    self.assertEqual(tender.metadata_json, {"lifecycle": {}})
                    self.assertFalse(db.flush_called)
                    sync_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
