"""Unit tests for the Wave-4 :class:`ProposalWriterAgent`.

Covers preview/apply semantics, mode behaviour, tool failure isolation,
and the API route registration. DB and RAG engine are stubbed; the
agent's contract is that it never mutates any section row when
``apply=False``.
"""

from __future__ import annotations

import os
import unittest
from typing import Any
from unittest.mock import AsyncMock

from test_module_loaders import load_models_test_module, load_service_test_module

_TEST_ENV = {
    "APP_SECRET_KEY": "alpha-key-123456789012345678901234567890",
    "ADMIN_PASSWORD": "test-admin-password-1234567890",
    "DATABASE_URL": "postgresql+asyncpg://tester:securepass@localhost:5432/tenderwriter",
    "NEO4J_PASSWORD": "test-neo4j-password-1234567890",
    "MINIO_SECRET_KEY": "test-minio-password-1234567890",
    "ONLYOFFICE_JWT_SECRET": "office-jwt-token-12345678901234567890",
}
for _key, _value in _TEST_ENV.items():
    os.environ.setdefault(_key, _value)


_MODELS = load_models_test_module()
_AGENT_MODULE = load_service_test_module("app.intelligence.proposal_writer_agent")
_MODELS_REQUEST = load_service_test_module("app.intelligence.proposal_writer_models")
_API_MODULE = load_service_test_module("app.api.intelligence")


ProposalWriterAgent = _AGENT_MODULE.ProposalWriterAgent
ProposalWriterError = _AGENT_MODULE.ProposalWriterError
ProposalWriterRequest = _MODELS_REQUEST.ProposalWriterRequest
ProposalSection = _MODELS.ProposalSection
Proposal = _MODELS.Proposal
Tender = _MODELS.Tender
SectionStatus = _MODELS.SectionStatus


class _StubResult:
    def __init__(self, value: Any) -> None:
        self._value = value

    def scalar_one_or_none(self) -> Any:
        return self._value

    def scalars(self) -> _StubScalars:
        if self._value is None:
            return _StubScalars([])
        if isinstance(self._value, list):
            return _StubScalars(self._value)
        return _StubScalars([self._value])


class _StubScalars:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def all(self) -> list[Any]:
        return list(self._rows)


def _make_session(
    *,
    section: ProposalSection | None,
    proposal: Proposal | None,
    tender: Tender | None,
    recommendations: list[Any] | None = None,
):
    """Build a minimal AsyncSession-like stub.

    The agent issues two execute() calls (section lookup, recommendations
    lookup when rehearsal context is requested) and two get() calls
    (proposal fallback, tender). The stub routes by SQL fragment.
    """

    section_calls = {"value": section}
    rec_calls = {"value": recommendations or []}

    async def execute(stmt):  # pragma: no cover - exercised in tests
        text = str(stmt).lower()
        if "from proposal_sections" in text:
            return _StubResult(section_calls["value"])
        if "from rehearsal_recommendations" in text:
            return _StubResult(rec_calls["value"])
        return _StubResult(None)

    async def get(model, identifier):  # pragma: no cover - exercised in tests
        if getattr(model, "__name__", "") == "Tender":
            return tender
        if getattr(model, "__name__", "") == "Proposal":
            return proposal
        return None

    flush_mock = AsyncMock()
    session = type("_FakeSession", (), {})()
    # Assign as instance attrs to avoid descriptor binding turning the
    # plain async functions into bound methods.
    session.execute = execute
    session.get = get
    session.flush = flush_mock
    return session


def _build_chain(
    *,
    section_content: Any | None = None,
    section_status: SectionStatus = SectionStatus.TODO,
):
    tender = Tender(id=42)
    proposal = Proposal(id=601, tender_id=42)
    section = ProposalSection(
        id=701,
        proposal_id=601,
        title="Architettura tecnica",
        content=section_content if section_content is not None else {},
        status=section_status,
    )
    section.proposal = proposal
    return section, proposal, tender


class _StubRegistry:
    def __init__(self, *, available: dict[str, Any], failing: set[str] | None = None):
        self._available = available
        self._failing = failing or set()
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def contains(self, name: str) -> bool:
        return name in self._available or name in self._failing

    async def run(self, name: str, *, db, inputs):
        self.calls.append((name, dict(inputs)))
        if name in self._failing:
            raise RuntimeError(f"tool {name} crashed")
        return self._available.get(name, {})


class _StubRagEngine:
    def __init__(self, answer: str = "TESTO GENERATO"):
        self.answer = answer
        self.queries: list[Any] = []
        self.ensure_initialized = AsyncMock(return_value=None)

    async def query(self, rag_query):
        self.queries.append(rag_query)
        return type("RAGResp", (), {"answer": self.answer})()


class _CrashingRagEngine:
    def __init__(self):
        self.ensure_initialized = AsyncMock(return_value=None)

    async def query(self, rag_query):
        raise RuntimeError("upstream LLM down")


class PreviewModeTests(unittest.IsolatedAsyncioTestCase):
    async def test_draft_preview_does_not_mutate_section(self) -> None:
        section, proposal, tender = _build_chain()
        original_content = section.content
        original_status = section.status
        session = _make_session(section=section, proposal=proposal, tender=tender)
        registry = _StubRegistry(
            available={
                "coverage_analyzer": {"summary": {"open_gaps": 2}, "gaps": []},
                "evidence_auditor": {"summary": {"missing_refs": 0}, "findings": []},
                "contradiction_finder": {"summary": {}, "findings": []},
            }
        )
        rag = _StubRagEngine(answer="Bozza generata.")
        agent = ProposalWriterAgent(registry=registry, rag_engine=rag)

        request = ProposalWriterRequest(
            tender_id=42,
            proposal_id=601,
            section_id=701,
            mode="draft",
            apply=False,
            instruction="Prepara prima bozza",
        )
        result = await agent.execute(session, request)

        self.assertFalse(result.applied)
        self.assertEqual(result.draft_text, "Bozza generata.")
        self.assertEqual(result.coverage_summary, {"open_gaps": 2})
        self.assertIs(section.content, original_content)
        self.assertEqual(section.status, original_status)
        session.flush.assert_not_awaited()

    async def test_warning_when_engine_unavailable(self) -> None:
        section, proposal, tender = _build_chain()
        session = _make_session(section=section, proposal=proposal, tender=tender)
        registry = _StubRegistry(available={})
        agent = ProposalWriterAgent(registry=registry, rag_engine=None)

        request = ProposalWriterRequest(
            tender_id=42,
            proposal_id=601,
            section_id=701,
            mode="draft",
            use_coverage_analyzer=False,
            use_evidence_audit=False,
            use_contradiction_check=False,
            use_rehearsal_summary=False,
        )
        result = await agent.execute(session, request)

        self.assertFalse(result.applied)
        self.assertTrue(
            any("rag_engine unavailable" in w for w in result.warnings),
            result.warnings,
        )
        # Prompt skeleton echoes section title.
        self.assertIn("Architettura tecnica", result.draft_text)


class ApplyModeTests(unittest.IsolatedAsyncioTestCase):
    async def test_apply_writes_content_and_status_with_audit(self) -> None:
        section, proposal, tender = _build_chain()
        session = _make_session(section=section, proposal=proposal, tender=tender)
        registry = _StubRegistry(
            available={
                "coverage_analyzer": {"summary": {}, "gaps": []},
                "evidence_auditor": {"summary": {}, "findings": []},
                "contradiction_finder": {"summary": {}, "findings": []},
            }
        )
        rag = _StubRagEngine(answer="Paragrafo uno.\n\nParagrafo due con dettagli.")
        agent = ProposalWriterAgent(registry=registry, rag_engine=rag)

        request = ProposalWriterRequest(
            tender_id=42,
            proposal_id=601,
            section_id=701,
            mode="draft",
            apply=True,
        )
        result = await agent.execute(session, request)

        self.assertTrue(result.applied)
        self.assertEqual(section.status, SectionStatus.IN_PROGRESS)
        self.assertIsInstance(section.content, dict)
        self.assertEqual(section.content["type"], "doc")
        self.assertEqual(len(section.content["content"]), 2)
        audit = section.content["attrs"]["_proposal_writer_audit"]
        self.assertEqual(audit["agent"], "tw-proposal-writer-v1")
        self.assertEqual(audit["mode"], "draft")
        session.flush.assert_awaited()

    async def test_apply_skipped_when_draft_text_is_empty(self) -> None:
        section, proposal, tender = _build_chain()
        original_content = section.content
        session = _make_session(section=section, proposal=proposal, tender=tender)
        registry = _StubRegistry(available={})
        rag = _StubRagEngine(answer="   ")
        agent = ProposalWriterAgent(registry=registry, rag_engine=rag)

        request = ProposalWriterRequest(
            tender_id=42,
            proposal_id=601,
            section_id=701,
            mode="draft",
            apply=True,
            use_coverage_analyzer=False,
            use_evidence_audit=False,
            use_contradiction_check=False,
            use_rehearsal_summary=False,
        )
        result = await agent.execute(session, request)
        self.assertFalse(result.applied)
        self.assertIs(section.content, original_content)


class ChainValidationTests(unittest.IsolatedAsyncioTestCase):
    async def test_section_missing_raises(self) -> None:
        session = _make_session(section=None, proposal=None, tender=None)
        registry = _StubRegistry(available={})
        agent = ProposalWriterAgent(registry=registry, rag_engine=None)
        request = ProposalWriterRequest(tender_id=42, proposal_id=601, section_id=701)
        with self.assertRaises(ProposalWriterError) as ctx:
            await agent.execute(session, request)
        self.assertIn("not found", str(ctx.exception))

    async def test_proposal_tender_mismatch_raises(self) -> None:
        section, proposal, tender = _build_chain()
        proposal.tender_id = 999  # mismatch
        session = _make_session(section=section, proposal=proposal, tender=tender)
        registry = _StubRegistry(available={})
        agent = ProposalWriterAgent(registry=registry, rag_engine=None)
        request = ProposalWriterRequest(tender_id=42, proposal_id=601, section_id=701)
        with self.assertRaises(ProposalWriterError) as ctx:
            await agent.execute(session, request)
        self.assertIn("does not belong to tender", str(ctx.exception))


class ToolFailureTests(unittest.IsolatedAsyncioTestCase):
    async def test_tool_crash_is_isolated_into_warnings(self) -> None:
        section, proposal, tender = _build_chain()
        session = _make_session(section=section, proposal=proposal, tender=tender)
        registry = _StubRegistry(
            available={
                "evidence_auditor": {"summary": {}, "findings": []},
                "contradiction_finder": {"summary": {}, "findings": []},
            },
            failing={"coverage_analyzer"},
        )
        rag = _StubRagEngine(answer="OK")
        agent = ProposalWriterAgent(registry=registry, rag_engine=rag)

        request = ProposalWriterRequest(
            tender_id=42,
            proposal_id=601,
            section_id=701,
            mode="draft",
            use_rehearsal_summary=False,
        )
        result = await agent.execute(session, request)
        self.assertFalse(result.applied)
        self.assertEqual(result.coverage_summary, {})
        self.assertTrue(
            any("coverage_analyzer" in w for w in result.warnings),
            result.warnings,
        )

    async def test_engine_query_failure_falls_back_to_prompt(self) -> None:
        section, proposal, tender = _build_chain()
        session = _make_session(section=section, proposal=proposal, tender=tender)
        registry = _StubRegistry(
            available={
                "coverage_analyzer": {"summary": {}, "gaps": []},
                "evidence_auditor": {"summary": {}, "findings": []},
                "contradiction_finder": {"summary": {}, "findings": []},
            }
        )
        agent = ProposalWriterAgent(registry=registry, rag_engine=_CrashingRagEngine())
        request = ProposalWriterRequest(
            tender_id=42,
            proposal_id=601,
            section_id=701,
            mode="draft",
            use_rehearsal_summary=False,
        )
        result = await agent.execute(session, request)
        self.assertTrue(
            any("rag_engine generation failed" in w for w in result.warnings),
            result.warnings,
        )
        self.assertIn("Architettura tecnica", result.draft_text)


class AddressRehearsalFindingsTests(unittest.IsolatedAsyncioTestCase):
    async def test_warns_when_no_rehearsal_summary_present(self) -> None:
        section, proposal, tender = _build_chain()
        session = _make_session(section=section, proposal=proposal, tender=tender)
        registry = _StubRegistry(
            available={
                "coverage_analyzer": {"summary": {}, "gaps": []},
                "evidence_auditor": {"summary": {}, "findings": []},
                "contradiction_finder": {"summary": {}, "findings": []},
            }
        )

        async def empty_summary(db, *, tender_id, proposal_id):
            return None

        original = _AGENT_MODULE.build_rehearsal_summary
        _AGENT_MODULE.build_rehearsal_summary = empty_summary
        try:
            agent = ProposalWriterAgent(registry=registry, rag_engine=_StubRagEngine(answer="X"))
            request = ProposalWriterRequest(
                tender_id=42,
                proposal_id=601,
                section_id=701,
                mode="address_rehearsal_findings",
                use_rehearsal_summary=True,
            )
            result = await agent.execute(session, request)
        finally:
            _AGENT_MODULE.build_rehearsal_summary = original

        self.assertTrue(
            any("no completed rehearsal" in w for w in result.warnings),
            result.warnings,
        )
        self.assertIsNone(result.rehearsal_context)


class ImproveModeContextTests(unittest.IsolatedAsyncioTestCase):
    async def test_improve_mode_surfaces_gaps_and_evidence_in_prompt(self) -> None:
        section, proposal, tender = _build_chain(
            section_content={
                "type": "doc",
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": "Bozza preliminare incompleta."}],
                    }
                ],
            }
        )
        session = _make_session(section=section, proposal=proposal, tender=tender)
        registry = _StubRegistry(
            available={
                "coverage_analyzer": {
                    "summary": {"open_gaps": 3},
                    "gaps": [
                        {
                            "requirement_id": "R-1",
                            "priority": "high",
                            "summary": "Manca SLA 99,9%.",
                        }
                    ],
                },
                "evidence_auditor": {
                    "summary": {"missing_refs": 1},
                    "findings": [
                        {
                            "requirement_id": "R-1",
                            "summary": "Nessuna evidenza per certificazione ISO.",
                        }
                    ],
                },
                "contradiction_finder": {"summary": {}, "findings": []},
            }
        )
        rag = _StubRagEngine(answer="Versione migliorata.")
        agent = ProposalWriterAgent(registry=registry, rag_engine=rag)

        request = ProposalWriterRequest(
            tender_id=42,
            proposal_id=601,
            section_id=701,
            mode="improve",
            use_rehearsal_summary=False,
        )
        result = await agent.execute(session, request)
        self.assertEqual(result.coverage_summary, {"open_gaps": 3})
        self.assertEqual(result.evidence_summary, {"missing_refs": 1})
        # Prompt that reached the engine must include both the gap and
        # the missing-evidence summary so the LLM can address them.
        self.assertEqual(len(rag.queries), 1)
        prompt_text = rag.queries[0].text
        self.assertIn("Manca SLA 99,9%.", prompt_text)
        self.assertIn("Nessuna evidenza per certificazione ISO.", prompt_text)
        # Existing section text must be in the prompt so the model
        # actually rewrites it instead of starting from scratch.
        self.assertIn("Bozza preliminare incompleta.", prompt_text)


class ContradictionSurfacingTests(unittest.IsolatedAsyncioTestCase):
    async def test_contradiction_findings_appear_in_result(self) -> None:
        section, proposal, tender = _build_chain()
        session = _make_session(section=section, proposal=proposal, tender=tender)
        contradictions = [
            {
                "summary": "SLA dichiarato 99,9% ma altrove 99,5%.",
                "scope_type": "requirement",
                "scope_id": "R-7",
                "severity": "high",
            }
        ]
        registry = _StubRegistry(
            available={
                "coverage_analyzer": {"summary": {}, "gaps": []},
                "evidence_auditor": {"summary": {}, "findings": []},
                "contradiction_finder": {
                    "summary": {"count": 1},
                    "findings": contradictions,
                },
            }
        )
        rag = _StubRagEngine(answer="OK")
        agent = ProposalWriterAgent(registry=registry, rag_engine=rag)

        request = ProposalWriterRequest(
            tender_id=42,
            proposal_id=601,
            section_id=701,
            mode="draft",
            use_rehearsal_summary=False,
        )
        result = await agent.execute(session, request)
        self.assertEqual(result.contradictions, contradictions)
        self.assertIn("Contraddizioni rilevate", rag.queries[0].text)


class PermissionWiringTests(unittest.TestCase):
    def test_route_dependency_chain_includes_check_tender_access(self) -> None:
        # Inspect handler source so we can prove the route requires
        # tender access without mounting FastAPI.
        import inspect

        handler = next(
            r.endpoint
            for r in _API_MODULE.router.routes
            if getattr(r, "path", "") == "/proposal-writer/draft"
        )
        source = inspect.getsource(handler)
        self.assertIn("check_tender_access", source)
        self.assertIn("payload.tender_id", source)


class ApiWiringTests(unittest.TestCase):
    def test_proposal_writer_route_registered(self) -> None:
        paths = {route.path for route in _API_MODULE.router.routes}
        self.assertIn("/proposal-writer/draft", paths)

    def test_proposal_writer_route_is_post(self) -> None:
        matching = [r for r in _API_MODULE.router.routes if r.path == "/proposal-writer/draft"]
        methods = {m for r in matching for m in (r.methods or set())}
        self.assertIn("POST", methods)

    def test_set_proposal_writer_agent_for_testing_swaps(self) -> None:
        sentinel = object()
        _API_MODULE.set_proposal_writer_agent_for_testing(sentinel)
        self.assertIs(_API_MODULE._proposal_writer_agent, sentinel)
        _API_MODULE.set_proposal_writer_agent_for_testing(None)
        self.assertIsNone(_API_MODULE._proposal_writer_agent)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
