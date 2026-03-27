"""Unit tests for the KPI reason engine backend integration and payload helpers."""

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
    AttendanceRecord,
    AttendanceStatus,
    CallSession,
    ComplianceGate,
    ComplianceGateStatus,
    ComplianceStatus,
    ContributionRequest,
    ContributionRequestStatus,
    ContributionUnit,
    ContributionUnitStatus,
    KpiDomainEvent,
    KpiEventDeliveryStatus,
    Proposal,
    ProposalSection,
    ProposalStatus,
    ReviewCycle,
    ReviewCycleStatus,
    ReworkAction,
    ReworkStatus,
    SectionStatus,
    Tender,
    TenderRequirement,
    TenderStatus,
)
from app.services.kpi_reason_engine import (
    build_bid_plan_event_payload,
    build_bid_team_assigned_event_payload,
    build_clarification_event_payload,
    build_compliance_gate_rework_requested_event_payload,
    build_contribution_assignment_confirmed_event_payload,
    build_coordination_risk_raised_event_payload,
    build_draft_integrated_ready_event_payload,
    build_rework_reescalated_to_coordination_event_payload,
    build_submission_status_event_payload,
    build_tender_decision_event_payload,
    build_terminal_lifecycle_event_payload,
    build_tender_stopped_at_gate_event_payload,
    KpiClientResult,
    KpiReasonEngineClient,
    apply_delivery_result,
    build_call_attendance_recorded_event_payload,
    build_call_scheduled_event_payload,
    build_compliance_gate_decision_event_payload,
    build_compliance_gate_opened_event_payload,
    build_contribution_due_date_set_event_payload,
    build_contribution_received_event_payload,
    build_contribution_request_created_event_payload,
    build_contribution_review_completed_event_payload,
    build_domain_event_payload,
    build_proposal_section_updated_event_payload,
    build_requirements_extracted_event_payload,
    build_review_cycle_started_event_payload,
    build_rework_requested_event_payload,
    build_rework_resolved_event_payload,
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
                compliance_status=ComplianceStatus.NOT_ADDRESSED,
                proposal_section_id=202,
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
        self.assertEqual(payload["requirement_contexts"][0]["priority"], "high")
        self.assertEqual(payload["requirement_contexts"][0]["compliance_status"], "not_addressed")
        self.assertEqual(payload["requirement_contexts"][0]["mapped_section_id"], "202")
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
        requirement_payload = build_requirements_extracted_event_payload(
            document_id="tenders/tender_3/source.pdf",
            filename="source.pdf",
            extracted_candidates=[
                {"summary": "Must provide ISO 27001 evidence", "reference": "1.2", "priority": "high"},
                {"summary": "Include continuity plan", "reference": "1.3", "priority": "medium"},
            ],
            created_requirements=[
                TenderRequirement(
                    id=44,
                    requirement_text="Must provide ISO 27001 evidence",
                    category="1.2",
                    priority="high",
                )
            ],
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
        self.assertEqual(requirement_payload["requirement_count"], 2)
        self.assertEqual(requirement_payload["new_requirement_count"], 1)
        self.assertEqual(requirement_payload["created_requirement_ids"], ["44"])
        self.assertEqual(requirement_payload["priority_breakdown"], {"high": 1, "medium": 1})
        self.assertEqual(section_payload["external_section_id"], "90")
        self.assertEqual(section_payload["source"], "onlyoffice")
        self.assertEqual(section_payload["changed_fields"], ["content"])


class KpiReasonEngineClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_sync_tender_posts_to_expected_endpoint_with_auth(self) -> None:
        observed: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            observed["method"] = request.method
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
        self.assertEqual(observed["method"], "POST")
        self.assertEqual(observed["path"], "/v1/tenders")
        self.assertEqual(observed["auth"], "Bearer service-token-123")
        self.assertEqual(observed["service_token"], "service-token-123")
        self.assertEqual(observed["payload"], {"external_tender_id": "7", "title": "Framework Tender"})

    async def test_publish_event_posts_to_expected_tender_endpoint(self) -> None:
        observed: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            observed["method"] = request.method
            observed["path"] = request.url.path
            observed["payload"] = json.loads(request.content.decode("utf-8"))
            return httpx.Response(202, json={"status": "accepted", "event_type": "proposal_created"})

        client = KpiReasonEngineClient(
            base_url="http://kpi-service.test",
            transport=httpx.MockTransport(handler),
        )

        result = await client.publish_event("7", {"event_type": "proposal_created"})

        self.assertTrue(result.delivered)
        self.assertEqual(observed["method"], "POST")
        self.assertEqual(observed["path"], "/v1/tenders/7/events")
        self.assertEqual(observed["payload"], {"event_type": "proposal_created"})

    async def test_service_runtime_endpoints_query_expected_paths(self) -> None:
        observed_paths: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            observed_paths.append(request.url.path)
            return httpx.Response(200, json={"status": "ok"})

        client = KpiReasonEngineClient(
            base_url="http://kpi-service.test",
            transport=httpx.MockTransport(handler),
        )

        health_result = await client.get_service_health()
        readiness_result = await client.get_service_readiness()
        manifest_result = await client.get_version_manifest()

        self.assertTrue(health_result.delivered)
        self.assertTrue(readiness_result.delivered)
        self.assertTrue(manifest_result.delivered)
        self.assertEqual(observed_paths, ["/health", "/ready", "/version-manifest"])

    async def test_get_tender_snapshot_queries_expected_endpoint(self) -> None:
        observed: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            observed["method"] = request.method
            observed["path"] = request.url.path
            observed["auth"] = request.headers.get("Authorization")
            return httpx.Response(200, json={"external_tender_id": "7", "status": "not_ready"})

        client = KpiReasonEngineClient(
            base_url="http://kpi-service.test",
            service_token="service-token-123",
            transport=httpx.MockTransport(handler),
        )

        result = await client.get_tender_snapshot("7")

        self.assertTrue(result.delivered)
        self.assertEqual(observed["method"], "GET")
        self.assertEqual(observed["path"], "/v1/tenders/7/snapshot")
        self.assertEqual(observed["auth"], "Bearer service-token-123")
        self.assertEqual(result.response_json["external_tender_id"], "7")

    async def test_get_portfolio_overview_queries_expected_endpoint(self) -> None:
        observed: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            observed["method"] = request.method
            observed["path"] = request.url.path
            return httpx.Response(200, json={"total_tenders": 2, "status": "not_ready"})

        client = KpiReasonEngineClient(
            base_url="http://kpi-service.test",
            transport=httpx.MockTransport(handler),
        )

        result = await client.get_portfolio_overview()

        self.assertTrue(result.delivered)
        self.assertEqual(observed["method"], "GET")
        self.assertEqual(observed["path"], "/v1/admin/portfolio/overview")
        self.assertEqual(result.response_json["total_tenders"], 2)

    async def test_get_tender_transitions_queries_expected_endpoint(self) -> None:
        observed: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            observed["method"] = request.method
            observed["path"] = request.url.path
            return httpx.Response(200, json={"external_tender_id": "7", "items": [], "requirement_items": []})

        client = KpiReasonEngineClient(
            base_url="http://kpi-service.test",
            transport=httpx.MockTransport(handler),
        )

        result = await client.get_tender_transitions("7")

        self.assertTrue(result.delivered)
        self.assertEqual(observed["method"], "GET")
        self.assertEqual(observed["path"], "/v1/tenders/7/transitions")
        self.assertEqual(result.response_json["external_tender_id"], "7")

    async def test_request_analysis_job_posts_to_expected_endpoint(self) -> None:
        observed: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            observed["method"] = request.method
            observed["path"] = request.url.path
            observed["payload"] = json.loads(request.content.decode("utf-8"))
            return httpx.Response(202, json={"external_tender_id": "7", "job_id": 99, "job_status": "queued"})

        client = KpiReasonEngineClient(
            base_url="http://kpi-service.test",
            transport=httpx.MockTransport(handler),
        )

        result = await client.request_analysis_job("7", {"job_type": "full_recompute"})

        self.assertTrue(result.delivered)
        self.assertEqual(observed["method"], "POST")
        self.assertEqual(observed["path"], "/v1/tenders/7/analysis-jobs")
        self.assertEqual(observed["payload"], {"job_type": "full_recompute"})
        self.assertEqual(result.response_json["job_id"], 99)

    async def test_get_latest_analysis_job_queries_expected_endpoint(self) -> None:
        observed: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            observed["method"] = request.method
            observed["path"] = request.url.path
            return httpx.Response(200, json={"external_tender_id": "7", "job_status": "running"})

        client = KpiReasonEngineClient(
            base_url="http://kpi-service.test",
            transport=httpx.MockTransport(handler),
        )

        result = await client.get_latest_analysis_job("7")

        self.assertTrue(result.delivered)
        self.assertEqual(observed["method"], "GET")
        self.assertEqual(observed["path"], "/v1/tenders/7/analysis-jobs/latest")
        self.assertEqual(result.response_json["job_status"], "running")


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


class OperationalPayloadBuilderTests(unittest.TestCase):
    def test_contribution_operational_payloads_keep_expected_shape(self) -> None:
        contribution = ContributionUnit(
            id=201,
            tender_id=7,
            proposal_section_id=90,
            owner_user_id=14,
            department_name="legal",
            title="Collect compliance annex",
            due_at=datetime(2026, 3, 18, 9, 0, tzinfo=timezone.utc),
            status=ContributionUnitStatus.REQUESTED,
        )
        request_row = ContributionRequest(
            id=301,
            contribution_unit_id=201,
            requested_to_user_id=18,
            requested_to_label="Legal team",
            request_channel="chat",
            requested_at=datetime(2026, 3, 15, 9, 0, tzinfo=timezone.utc),
            due_at=datetime(2026, 3, 17, 9, 0, tzinfo=timezone.utc),
            sla_target_hours=8,
            sla_max_hours=24,
            response_received_at=datetime(2026, 3, 15, 15, 0, tzinfo=timezone.utc),
            response_summary="Draft annex delivered",
            status=ContributionRequestStatus.RECEIVED,
        )
        review = ReviewCycle(
            id=401,
            contribution_unit_id=201,
            reviewer_id=21,
            stage_name="quality_review",
            started_at=datetime(2026, 3, 15, 16, 0, tzinfo=timezone.utc),
            completed_at=datetime(2026, 3, 16, 10, 0, tzinfo=timezone.utc),
            outcome="approved",
            notes="Looks good",
            status=ReviewCycleStatus.COMPLETED,
        )
        rework = ReworkAction(
            id=501,
            contribution_unit_id=201,
            review_cycle_id=401,
            assigned_to_user_id=18,
            severity="high",
            is_blocking=True,
            reason="Missing signature",
            requested_at=datetime(2026, 3, 15, 17, 0, tzinfo=timezone.utc),
            resolved_at=datetime(2026, 3, 15, 20, 0, tzinfo=timezone.utc),
            resolution_notes="Signed version uploaded",
            status=ReworkStatus.RESOLVED,
        )
        gate = ComplianceGate(
            id=601,
            tender_id=7,
            contribution_unit_id=201,
            owner_user_id=21,
            gate_name="Compliance approval",
            due_at=datetime(2026, 3, 18, 12, 0, tzinfo=timezone.utc),
            evaluated_at=datetime(2026, 3, 18, 11, 0, tzinfo=timezone.utc),
            decision_notes="Approved",
            status=ComplianceGateStatus.PASSED,
        )
        call = CallSession(
            id=701,
            tender_id=7,
            title="Bid coordination",
            scheduled_at=datetime(2026, 3, 16, 9, 0, tzinfo=timezone.utc),
        )
        attendance = AttendanceRecord(
            id=801,
            call_session_id=701,
            user_id=18,
            attendee_label="Legal team",
            attendance_status=AttendanceStatus.ATTENDED,
            recorded_at=datetime(2026, 3, 16, 9, 5, tzinfo=timezone.utc),
            notes="Joined on time",
        )

        request_payload = build_contribution_request_created_event_payload(request=request_row, contribution=contribution)
        due_payload = build_contribution_due_date_set_event_payload(request=request_row, contribution=contribution)
        received_payload = build_contribution_received_event_payload(request=request_row, contribution=contribution)
        review_started_payload = build_review_cycle_started_event_payload(review=review, contribution=contribution)
        review_completed_payload = build_contribution_review_completed_event_payload(review=review, contribution=contribution)
        rework_requested_payload = build_rework_requested_event_payload(rework=rework, contribution=contribution)
        rework_resolved_payload = build_rework_resolved_event_payload(rework=rework, contribution=contribution)
        gate_opened_payload = build_compliance_gate_opened_event_payload(gate=gate)
        gate_decision_payload = build_compliance_gate_decision_event_payload(gate=gate)
        call_payload = build_call_scheduled_event_payload(call=call)
        attendance_payload = build_call_attendance_recorded_event_payload(record=attendance, call=call)

        self.assertEqual(request_payload["external_request_id"], "301")
        self.assertEqual(request_payload["external_contribution_id"], "201")
        self.assertEqual(request_payload["sla_target_hours"], 8)
        self.assertEqual(due_payload["due_at"], "2026-03-17T09:00:00+00:00")
        self.assertEqual(received_payload["response_time_hours"], 6.0)
        self.assertTrue(received_payload["within_sla_target"])
        self.assertEqual(review_started_payload["external_review_cycle_id"], "401")
        self.assertEqual(review_completed_payload["cycle_time_hours"], 18.0)
        self.assertEqual(rework_requested_payload["severity"], "high")
        self.assertEqual(rework_resolved_payload["resolution_time_hours"], 3.0)
        self.assertEqual(gate_opened_payload["external_gate_id"], "601")
        self.assertEqual(gate_decision_payload["status"], "passed")
        self.assertEqual(call_payload["external_call_session_id"], "701")
        self.assertEqual(attendance_payload["attendance_status"], "attended")


class LifecyclePayloadBuilderTests(unittest.TestCase):
    def test_tender_sync_payload_preserves_lifecycle_metadata(self) -> None:
        tender = Tender(
            id=17,
            title="Lifecycle Tender",
            client="ACME",
            status=TenderStatus.ACTIVE,
            metadata_json={
                "lifecycle": {
                    "decision": {"decision": "go", "decided_at": "2026-03-19T09:00:00Z"},
                    "submission_status": {"submission_status": "acknowledged"},
                }
            },
        )
        tender.requirements = []
        tender.proposals = []

        payload = build_tender_sync_payload(tender)

        self.assertEqual(payload["metadata"]["lifecycle"]["decision"]["decision"], "go")
        self.assertEqual(payload["metadata"]["lifecycle"]["submission_status"]["submission_status"], "acknowledged")

    def test_lifecycle_event_payload_builders_keep_expected_shape(self) -> None:
        decided_at = datetime(2026, 3, 19, 9, 0, tzinfo=timezone.utc)
        clarified_at = datetime(2026, 3, 20, 11, 30, tzinfo=timezone.utc)

        decision_payload = build_tender_decision_event_payload(
            decision="go",
            decided_at=decided_at,
            reason_code="strategic_fit",
            notes="Proceed with bid",
        )
        plan_payload = build_bid_plan_event_payload(
            plan_status="approved",
            planned_at=decided_at,
            owner_user_ids=[7, 9],
            milestone_count=4,
            notes="Core team assigned",
        )
        team_payload = build_bid_team_assigned_event_payload(
            assigned_at=decided_at,
            owner_user_ids=[7, 9],
            notes="Core team assigned",
        )
        assignment_payload = build_contribution_assignment_confirmed_event_payload(
            occurred_at=decided_at,
            external_contribution_id="201",
            owner_user_id=7,
            external_request_id="301",
            notes="Assignment confirmed",
        )
        draft_payload = build_draft_integrated_ready_event_payload(
            ready_at=clarified_at,
            proposal_id=41,
            approved_section_count=8,
            total_section_count=10,
            blocking_rework_count=0,
        )
        clarification_payload = build_clarification_event_payload(
            request_id="clar-1",
            status="requested",
            occurred_at=clarified_at,
            request_summary="Explain staffing model",
            deadline_at=clarified_at,
            source_label="buyer_portal",
        )
        coordination_payload = build_coordination_risk_raised_event_payload(
            occurred_at=clarified_at,
            external_rework_id="rw-admin-1",
            external_contribution_id="201",
            severity="high",
            reason_code="missing_owner_alignment",
            notes="Coordination gap opened.",
        )
        coordination_recovery_payload = build_rework_reescalated_to_coordination_event_payload(
            occurred_at=clarified_at,
            external_rework_id="rw-admin-1",
            external_contribution_id="201",
            severity="high",
            reason_code="owner_alignment_restored",
            notes="Back to coordination.",
        )
        gate_rework_payload = build_compliance_gate_rework_requested_event_payload(
            occurred_at=clarified_at,
            external_gate_id="gate-1",
            gate_name="Auto compliance readiness",
            external_rework_id="gate-rw-1",
            reason_code="compliance_gap_reopened",
            notes="Another blocking fix is required.",
        )
        submission_payload = build_submission_status_event_payload(
            submission_status="failed",
            occurred_at=clarified_at,
            channel="buyer_portal",
            error_code="timeout",
            error_message="Gateway timeout",
        )
        terminal_payload = build_terminal_lifecycle_event_payload(
            outcome="withdrawn",
            recorded_at=clarified_at,
            reason_code="budget_change",
            notes="Tender withdrawn",
        )
        gate_stop_payload = build_tender_stopped_at_gate_event_payload(
            recorded_at=clarified_at,
            external_gate_id="gate-1",
            gate_name="Auto compliance readiness",
            reason_code="compliance_gap_reopened",
            notes="Stop at gate.",
        )

        self.assertEqual(decision_payload["decision"], "go")
        self.assertEqual(plan_payload["owner_user_ids"], [7, 9])
        self.assertEqual(team_payload["owner_count"], 2)
        self.assertEqual(assignment_payload["external_request_id"], "301")
        self.assertEqual(draft_payload["readiness_ratio"], 80.0)
        self.assertEqual(clarification_payload["request_id"], "clar-1")
        self.assertEqual(coordination_payload["external_rework_id"], "rw-admin-1")
        self.assertEqual(coordination_recovery_payload["resolved_at"], clarified_at.isoformat())
        self.assertEqual(gate_rework_payload["external_gate_id"], "gate-1")
        self.assertEqual(submission_payload["error_code"], "timeout")
        self.assertEqual(terminal_payload["outcome"], "withdrawn")
        self.assertEqual(gate_stop_payload["outcome"], "stopped")
