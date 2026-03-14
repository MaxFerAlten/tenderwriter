"""Unit tests for the Sprint 2 KPI reason engine backend integration."""

import json
import os
import unittest
from datetime import datetime, timezone

import httpx

_TEST_ENV = {
    "APP_SECRET_KEY": "alpha-key-123456789012345678901234567890",
    "ADMIN_PASSWORD": "test-admin-password-1234567890",
    "DATABASE_URL": "postgresql+asyncpg://tester:securepass@localhost:5432/tenderwriter",
    "NEO4J_PASSWORD": "test-neo4j-password-1234567890",
    "MINIO_SECRET_KEY": "test-minio-password-1234567890",
    "ONLYOFFICE_JWT_SECRET": "office-jwt-token-12345678901234567890",
    "KPI_REASON_ENGINE_BASE_URL": "http://kpi-service.test",
    "KPI_REASON_ENGINE_SERVICE_TOKEN": "service-token-123",
}
for key, value in _TEST_ENV.items():
    os.environ.setdefault(key, value)

from app.models import (
    KpiDomainEvent,
    KpiEventDeliveryStatus,
    Proposal,
    ProposalSection,
    ProposalStatus,
    SectionStatus,
    Tender,
    TenderRequirement,
    TenderStatus,
)
from app.services.kpi_reason_engine import (
    KpiClientResult,
    KpiReasonEngineClient,
    apply_delivery_result,
    build_domain_event_payload,
    build_proposal_section_updated_event_payload,
    build_tender_created_event_payload,
    build_tender_document_ingested_event_payload,
    build_tender_sync_payload,
    select_primary_proposal,
)


class TenderSyncPayloadTests(unittest.TestCase):
    def test_select_primary_proposal_prefers_latest_version(self) -> None:
        older = Proposal(id=10, tender_id=7, title="Old", version=1, status=ProposalStatus.DRAFT)
        newer = Proposal(id=11, tender_id=7, title="New", version=2, status=ProposalStatus.DRAFT)

        selected = select_primary_proposal([older, newer])

        self.assertIsNotNone(selected)
        self.assertEqual(selected.id, 11)

    def test_build_tender_sync_payload_uses_latest_proposal_sections(self) -> None:
        tender = Tender(
            id=7,
            title="Framework Tender",
            client="ACME",
            description="National procurement",
            deadline=datetime(2026, 4, 30, 9, 0, tzinfo=timezone.utc),
            status=TenderStatus.ACTIVE,
            category="ict",
            tags=["cloud", "security"],
            budget_estimate=125000.0,
            source_file_url="minio://tenders/source.pdf",
        )
        tender.requirements = [
            TenderRequirement(
                id=41,
                requirement_text="Must provide ISO 27001 evidence",
                category="1.2",
                priority="high",
            )
        ]

        older = Proposal(
            id=10,
            tender_id=7,
            title="Old Proposal",
            version=1,
            status=ProposalStatus.DRAFT,
            created_at=datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc),
        )
        older.sections = [
            ProposalSection(
                id=101,
                proposal_id=10,
                title="Old Section",
                status=SectionStatus.TODO,
                order=0,
            )
        ]

        newer = Proposal(
            id=11,
            tender_id=7,
            title="Current Proposal",
            version=2,
            status=ProposalStatus.IN_REVIEW,
            created_at=datetime(2026, 3, 2, 12, 0, tzinfo=timezone.utc),
        )
        newer.sections = [
            ProposalSection(
                id=202,
                proposal_id=11,
                title="Executive Summary",
                status=SectionStatus.IN_PROGRESS,
                order=0,
            )
        ]
        tender.proposals = [older, newer]

        payload = build_tender_sync_payload(tender)

        self.assertEqual(payload["external_tender_id"], "7")
        self.assertEqual(payload["current_status"], "active")
        self.assertEqual(payload["metadata"]["proposal_id"], 11)
        self.assertEqual(payload["requirement_contexts"][0]["external_requirement_id"], "41")
        self.assertEqual(payload["section_contexts"][0]["external_section_id"], "202")
        self.assertEqual(payload["section_contexts"][0]["status"], "in_progress")

    def test_build_domain_event_payload_serializes_actor_and_timestamp(self) -> None:
        payload = build_domain_event_payload(
            event_type="proposal_section_updated",
            occurred_at=datetime(2026, 3, 14, 12, 30, tzinfo=timezone.utc),
            actor_id=12,
            source="tw-backend",
            payload={"external_section_id": "22"},
        )

        self.assertEqual(payload["event_type"], "proposal_section_updated")
        self.assertEqual(payload["actor_id"], "12")
        self.assertEqual(payload["source"], "tw-backend")
        self.assertEqual(payload["occurred_at"], "2026-03-14T12:30:00+00:00")

    def test_build_event_payload_helpers_keep_expected_shape(self) -> None:
        tender = Tender(id=3, title="Tender", client="Client", status=TenderStatus.DRAFT)
        section = ProposalSection(
            id=90,
            proposal_id=5,
            title="Technical Approach",
            status=SectionStatus.IN_REVIEW,
            assigned_to=6,
        )

        created_payload = build_tender_created_event_payload(tender)
        document_payload = build_tender_document_ingested_event_payload(
            document_id="tenders/tender_3/source.pdf",
            filename="source.pdf",
            stats={"status": "completed", "chunks": 8, "entities": 0},
        )
        section_payload = build_proposal_section_updated_event_payload(
            section=section,
            change_type="section_content_saved",
            changed_fields=["content"],
            source="onlyoffice",
        )

        self.assertEqual(created_payload["status"], "draft")
        self.assertEqual(document_payload["document_id"], "tenders/tender_3/source.pdf")
        self.assertEqual(document_payload["chunks"], 8)
        self.assertEqual(section_payload["external_section_id"], "90")
        self.assertEqual(section_payload["source"], "onlyoffice")
        self.assertEqual(section_payload["changed_fields"], ["content"])


class KpiReasonEngineClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_sync_tender_posts_to_expected_endpoint_with_auth(self) -> None:
        observed: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            observed["path"] = request.url.path
            observed["auth"] = request.headers.get("Authorization")
            observed["service_token"] = request.headers.get("X-Service-Token")
            observed["payload"] = json.loads(request.content.decode("utf-8"))
            return httpx.Response(202, json={"status": "accepted"})

        client = KpiReasonEngineClient(
            base_url="http://kpi-service.test",
            service_token="service-token-123",
            transport=httpx.MockTransport(handler),
        )

        result = await client.sync_tender({"external_tender_id": "7", "title": "Framework Tender"})

        self.assertTrue(result.delivered)
        self.assertEqual(result.status_code, 202)
        self.assertEqual(observed["path"], "/v1/tenders")
        self.assertEqual(observed["auth"], "Bearer service-token-123")
        self.assertEqual(observed["service_token"], "service-token-123")
        self.assertEqual(observed["payload"], {"external_tender_id": "7", "title": "Framework Tender"})

    async def test_publish_event_posts_to_expected_tender_endpoint(self) -> None:
        observed: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            observed["path"] = request.url.path
            observed["payload"] = json.loads(request.content.decode("utf-8"))
            return httpx.Response(202, json={"status": "accepted", "event_type": "proposal_created"})

        client = KpiReasonEngineClient(
            base_url="http://kpi-service.test",
            transport=httpx.MockTransport(handler),
        )

        result = await client.publish_event("7", {"event_type": "proposal_created"})

        self.assertTrue(result.delivered)
        self.assertEqual(observed["path"], "/v1/tenders/7/events")
        self.assertEqual(observed["payload"], {"event_type": "proposal_created"})


class DeliveryStateTests(unittest.TestCase):
    def test_apply_delivery_result_marks_event_delivered(self) -> None:
        event = KpiDomainEvent(
            tender_id=7,
            event_type="tender_sync",
            source="tw-backend",
            external_tender_id="7",
            occurred_at=datetime(2026, 3, 14, 10, 0, tzinfo=timezone.utc),
            payload_json={"external_tender_id": "7"},
            delivery_status=KpiEventDeliveryStatus.PENDING,
            response_json={},
        )

        apply_delivery_result(
            event,
            KpiClientResult(
                delivered=True,
                status_code=202,
                response_json={"status": "accepted"},
            ),
        )

        self.assertEqual(event.delivery_status, KpiEventDeliveryStatus.DELIVERED)
        self.assertEqual(event.delivery_attempts, 1)
        self.assertEqual(event.response_status_code, 202)
        self.assertEqual(event.response_json, {"status": "accepted"})
        self.assertIsNotNone(event.published_at)
        self.assertIsNone(event.error_message)

    def test_apply_delivery_result_marks_event_failed(self) -> None:
        event = KpiDomainEvent(
            tender_id=7,
            event_type="proposal_created",
            source="tw-backend",
            external_tender_id="7",
            occurred_at=datetime(2026, 3, 14, 10, 0, tzinfo=timezone.utc),
            payload_json={"event_type": "proposal_created"},
            delivery_status=KpiEventDeliveryStatus.PENDING,
            response_json={},
        )

        apply_delivery_result(
            event,
            KpiClientResult(
                delivered=False,
                status_code=503,
                response_json={"detail": "temporarily unavailable"},
                error_message="KPI service returned HTTP 503",
            ),
        )

        self.assertEqual(event.delivery_status, KpiEventDeliveryStatus.FAILED)
        self.assertEqual(event.delivery_attempts, 1)
        self.assertEqual(event.response_status_code, 503)
        self.assertEqual(event.error_message, "KPI service returned HTTP 503")
        self.assertIsNone(event.published_at)


if __name__ == "__main__":
    unittest.main()

