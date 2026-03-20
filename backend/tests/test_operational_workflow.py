import os
import unittest

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

from app.models import ContributionUnitStatus, SectionStatus
from app.services.operational_workflow import build_section_transition_plan, derive_contribution_status


class SectionTransitionPlanTests(unittest.TestCase):
    def test_assignment_in_todo_creates_request_plan(self) -> None:
        plan = build_section_transition_plan(
            previous_status=SectionStatus.TODO,
            new_status=SectionStatus.TODO,
            previous_assigned_to=None,
            new_assigned_to=18,
        )

        self.assertTrue(plan.ensure_request)
        self.assertFalse(plan.start_review)
        self.assertFalse(plan.complete_review)

    def test_entering_review_marks_request_received_and_starts_review(self) -> None:
        plan = build_section_transition_plan(
            previous_status=SectionStatus.IN_PROGRESS,
            new_status=SectionStatus.IN_REVIEW,
            previous_assigned_to=18,
            new_assigned_to=18,
        )

        self.assertTrue(plan.mark_request_received)
        self.assertTrue(plan.start_review)
        self.assertTrue(plan.resolve_rework)
        self.assertFalse(plan.open_rework)

    def test_leaving_review_opens_rework(self) -> None:
        plan = build_section_transition_plan(
            previous_status=SectionStatus.IN_REVIEW,
            new_status=SectionStatus.IN_PROGRESS,
            previous_assigned_to=18,
            new_assigned_to=18,
        )

        self.assertTrue(plan.complete_review)
        self.assertEqual(plan.review_outcome, "changes_requested")
        self.assertTrue(plan.open_rework)

    def test_direct_approval_does_not_create_synthetic_review(self) -> None:
        plan = build_section_transition_plan(
            previous_status=SectionStatus.IN_PROGRESS,
            new_status=SectionStatus.APPROVED,
            previous_assigned_to=18,
            new_assigned_to=18,
        )

        self.assertTrue(plan.mark_request_received)
        self.assertFalse(plan.start_review)
        self.assertFalse(plan.complete_review)
        self.assertIsNone(plan.review_outcome)

    def test_assignment_change_inside_review_does_not_create_new_request(self) -> None:
        plan = build_section_transition_plan(
            previous_status=SectionStatus.IN_REVIEW,
            new_status=SectionStatus.IN_REVIEW,
            previous_assigned_to=18,
            new_assigned_to=21,
        )

        self.assertTrue(plan.cancel_open_requests)
        self.assertFalse(plan.ensure_request)
        self.assertFalse(plan.mark_request_received)

    def test_assignment_from_unassigned_state_still_cancels_stray_open_requests(self) -> None:
        plan = build_section_transition_plan(
            previous_status=SectionStatus.TODO,
            new_status=SectionStatus.TODO,
            previous_assigned_to=None,
            new_assigned_to=21,
        )

        self.assertTrue(plan.cancel_open_requests)
        self.assertTrue(plan.ensure_request)


class ContributionStatusDerivationTests(unittest.TestCase):
    def test_open_rework_has_priority_over_section_status(self) -> None:
        status = derive_contribution_status(
            section_status=SectionStatus.IN_PROGRESS,
            assigned_to=18,
            has_open_rework=True,
        )

        self.assertEqual(status, ContributionUnitStatus.REWORK)

    def test_assigned_in_progress_maps_to_received(self) -> None:
        status = derive_contribution_status(
            section_status=SectionStatus.IN_PROGRESS,
            assigned_to=18,
            has_open_rework=False,
        )

        self.assertEqual(status, ContributionUnitStatus.RECEIVED)

    def test_unassigned_in_progress_maps_to_requested(self) -> None:
        status = derive_contribution_status(
            section_status=SectionStatus.IN_PROGRESS,
            assigned_to=None,
            has_open_rework=False,
        )

        self.assertEqual(status, ContributionUnitStatus.REQUESTED)

    def test_unassigned_todo_maps_to_open(self) -> None:
        status = derive_contribution_status(
            section_status=SectionStatus.TODO,
            assigned_to=None,
            has_open_rework=False,
        )

        self.assertEqual(status, ContributionUnitStatus.OPEN)

    def test_leaving_review_to_todo_does_not_open_rework(self) -> None:
        plan = build_section_transition_plan(
            previous_status=SectionStatus.IN_REVIEW,
            new_status=SectionStatus.TODO,
            previous_assigned_to=18,
            new_assigned_to=18,
        )

        self.assertFalse(plan.complete_review)
        self.assertFalse(plan.open_rework)
        self.assertIsNone(plan.review_outcome)


if __name__ == "__main__":
    unittest.main()



