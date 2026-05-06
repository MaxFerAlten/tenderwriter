import base64
import enum
import importlib.metadata
import json
import os
import sys
import types
from dataclasses import dataclass, field
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

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


_TENDERS_MODULES = None
_AUTH_PROVIDER_MODULES = None
_MODELS_MODULE = None
_SERVICE_MODULES: dict[str, object] = {}
_RAG_API_MODULES = None


def _build_fake_pyjwt_module():
    fake_jwt = types.ModuleType("jwt")

    class _InvalidTokenError(Exception):
        pass

    def _default(value):
        if hasattr(value, "isoformat"):
            return {"__datetime__": value.isoformat()}
        raise TypeError(f"Unsupported value for fake jwt: {value!r}")

    def _encode(payload, secret, algorithm="HS256"):
        del secret, algorithm
        raw = json.dumps(payload, default=_default).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii")

    def _decode(token, secret, algorithms=None):
        del secret, algorithms
        try:
            raw = base64.urlsafe_b64decode(token.encode("ascii"))
            return json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise _InvalidTokenError(str(exc)) from exc

    fake_jwt.encode = _encode
    fake_jwt.decode = _decode
    fake_jwt.InvalidTokenError = _InvalidTokenError
    return fake_jwt


def _build_fake_jose_module():
    fake_jose = types.ModuleType("jose")

    class _JWTError(Exception):
        pass

    fake_jose.JWTError = _JWTError
    fake_jose.jwt = SimpleNamespace(
        encode=lambda payload, secret, algorithm="HS256": _build_fake_pyjwt_module().encode(
            payload, secret, algorithm
        ),
        decode=lambda token, secret, algorithms=None: _build_fake_pyjwt_module().decode(
            token, secret, algorithms
        ),
    )
    return fake_jose


def _payload_builder(*args, **kwargs):
    payload = dict(kwargs)
    if args:
        payload["_args"] = list(args)
    return payload


def _fake_async_noop(*args, **kwargs):
    del args, kwargs
    return None


def _build_fake_minio_module():
    fake_minio = types.ModuleType("minio")

    class _FakeMinio:
        def __init__(self, *args, **kwargs):
            pass

        def bucket_exists(self, bucket_name):
            del bucket_name
            return True

        def make_bucket(self, bucket_name):
            del bucket_name
            return None

        def put_object(self, *args, **kwargs):
            return None

    fake_minio.Minio = _FakeMinio
    return fake_minio


def _build_fake_auth_dependency_module():
    fake_auth = types.ModuleType("app.api.auth")

    async def _fake_get_current_user():
        return SimpleNamespace(id=1, role="admin", email="tester@example.com", name="Tester")

    class _FakeUserResponse:
        pass

    fake_auth.get_current_user = _fake_get_current_user
    fake_auth.UserResponse = _FakeUserResponse
    return fake_auth


def _build_fake_chat_module():
    fake_chat = types.ModuleType("app.services.chat")
    fake_chat.ensure_official_chat_room = AsyncMock(side_effect=_fake_async_noop)
    fake_chat.sync_chat_members_from_tender_permissions = AsyncMock(side_effect=_fake_async_noop)
    return fake_chat


def _build_fake_kpi_module():
    fake_kpi = types.ModuleType("app.services.kpi_reason_engine")
    for name in (
        "build_bid_plan_event_payload",
        "build_bid_team_assigned_event_payload",
        "build_clarification_event_payload",
        "build_compliance_gate_rework_requested_event_payload",
        "build_contribution_wave_event_payload",
        "build_coordination_risk_raised_event_payload",
        "build_rework_reescalated_to_coordination_event_payload",
        "build_requirements_extracted_event_payload",
        "build_tender_created_event_payload",
        "build_tender_decision_event_payload",
        "build_tender_document_ingested_event_payload",
        "build_tender_outcome_recorded_event_payload",
        "build_terminal_lifecycle_event_payload",
    ):
        setattr(fake_kpi, name, _payload_builder)
    fake_kpi.build_tender_stopped_at_gate_event_payload = lambda *args, **kwargs: {
        "outcome": "stopped",
        **_payload_builder(*args, **kwargs),
    }
    fake_kpi.publish_domain_event = AsyncMock(side_effect=_fake_async_noop)
    fake_kpi.publish_tender_sync = AsyncMock(side_effect=_fake_async_noop)
    fake_kpi.sync_tender_and_publish_event = AsyncMock(side_effect=_fake_async_noop)
    return fake_kpi


def _build_fake_compliance_module(models_module=None):
    fake_compliance = types.ModuleType("app.services.compliance_observability")

    @dataclass
    class _ComplianceRequirementCoverage:
        id: int
        requirement_text: str
        category: str | None
        priority: str
        compliance_status: object
        proposal_section_id: int | None = None
        proposal_section_title: str | None = None
        coverage_source: str = "legacy"

    def _source_payloads(metadata_json):
        if not isinstance(metadata_json, dict):
            return []
        payloads = []
        primary_source = metadata_json.get("primary_source")
        if isinstance(primary_source, dict):
            payloads.append(primary_source)
        payloads.extend(
            source for source in metadata_json.get("sources") or [] if isinstance(source, dict)
        )
        return payloads

    def _coverage_from_legacy(requirement):
        mapped_section = getattr(requirement, "proposal_section", None)
        return _ComplianceRequirementCoverage(
            id=int(getattr(requirement, "id", 0) or 0),
            requirement_text=str(getattr(requirement, "requirement_text", "") or ""),
            category=getattr(requirement, "category", None),
            priority=str(getattr(requirement, "priority", None) or "medium"),
            compliance_status=getattr(requirement, "compliance_status", None),
            proposal_section_id=getattr(requirement, "proposal_section_id", None),
            proposal_section_title=getattr(mapped_section, "title", None)
            if mapped_section
            else None,
            coverage_source="legacy",
        )

    def _build_compliance_requirement_coverage(tender):
        legacy_requirements = list(getattr(tender, "requirements", None) or [])
        active_consolidated = [
            requirement
            for requirement in list(getattr(tender, "consolidated_requirements", None) or [])
            if str(getattr(requirement, "graph_state", None) or "active").casefold() == "active"
        ]
        if not any(
            str(getattr(requirement, "review_state", None) or "pending").casefold() == "approved"
            for requirement in active_consolidated
        ):
            return [_coverage_from_legacy(requirement) for requirement in legacy_requirements]

        legacy_by_id = {
            int(requirement.id): requirement
            for requirement in legacy_requirements
            if getattr(requirement, "id", None) is not None
        }
        not_addressed = getattr(
            models_module, "ComplianceStatus", SimpleNamespace(NOT_ADDRESSED="not_addressed")
        ).NOT_ADDRESSED
        coverage_items = []
        for requirement in active_consolidated:
            is_approved = (
                str(getattr(requirement, "review_state", None) or "pending").casefold()
                == "approved"
            )
            legacy_requirement = None
            for payload in _source_payloads(getattr(requirement, "metadata_json", None)):
                legacy_id = payload.get("legacy_requirement_id")
                if legacy_id is not None and int(legacy_id) in legacy_by_id:
                    legacy_requirement = legacy_by_id[int(legacy_id)]
                    break
            mapped_section = (
                getattr(legacy_requirement, "proposal_section", None)
                if legacy_requirement
                else None
            )
            coverage_items.append(
                _ComplianceRequirementCoverage(
                    id=int(getattr(requirement, "id", 0) or 0),
                    requirement_text=str(getattr(requirement, "canonical_text", "") or ""),
                    category=getattr(requirement, "category", None)
                    or (
                        getattr(legacy_requirement, "category", None)
                        if legacy_requirement
                        else None
                    ),
                    priority=str(
                        getattr(requirement, "priority", None)
                        or (
                            getattr(legacy_requirement, "priority", None)
                            if legacy_requirement
                            else "medium"
                        )
                    ),
                    compliance_status=(
                        getattr(legacy_requirement, "compliance_status", None)
                        if is_approved and legacy_requirement is not None
                        else not_addressed
                    ),
                    proposal_section_id=getattr(legacy_requirement, "proposal_section_id", None)
                    if is_approved and legacy_requirement
                    else None,
                    proposal_section_title=getattr(mapped_section, "title", None)
                    if is_approved and mapped_section
                    else None,
                    coverage_source="consolidated_approved"
                    if is_approved
                    else "consolidated_review_pending",
                )
            )
        return coverage_items

    fake_compliance.ComplianceRequirementCoverage = _ComplianceRequirementCoverage
    fake_compliance.build_compliance_requirement_coverage = Mock(
        side_effect=_build_compliance_requirement_coverage
    )
    fake_compliance.sync_requirement_compliance_and_gate = AsyncMock(return_value=[])
    return fake_compliance


def _build_fake_tender_requirements_module():
    fake_module = types.ModuleType("app.services.tender_requirements")
    fake_module.apply_extracted_requirement_candidates = Mock(return_value=[])
    fake_module.sync_tender_requirements_to_graph = AsyncMock(return_value=False)
    return fake_module


def _build_fake_requirement_candidates_module():
    fake_module = types.ModuleType("app.services.requirement_candidates")
    fake_module.stage_extracted_requirement_candidates = AsyncMock(return_value=(None, []))
    fake_module.list_staged_requirement_candidate_runs = AsyncMock(return_value=[])
    return fake_module


def _build_fake_requirement_consolidation_module():
    fake_module = types.ModuleType("app.services.requirement_consolidation")
    fake_module.list_consolidated_requirements = AsyncMock(return_value=[])
    fake_module.list_requirement_relations = AsyncMock(return_value=[])
    fake_module.rebuild_consolidated_requirements_from_staging = AsyncMock(return_value=[])
    return fake_module


def _build_fake_requirement_review_module():
    fake_module = types.ModuleType("app.services.requirement_review")
    fake_module.get_consolidated_requirement_for_tender = AsyncMock(return_value=None)
    fake_module.list_consolidated_requirements_for_review = AsyncMock(return_value=[])
    fake_module.apply_requirement_review = AsyncMock(return_value=(None, None))
    return fake_module


def _build_fake_requirement_relation_review_module():
    fake_module = types.ModuleType("app.services.requirement_relation_review")
    fake_module.get_requirement_relation_for_tender = AsyncMock(return_value=None)
    fake_module.list_requirement_relations_for_review = AsyncMock(return_value=[])
    fake_module.apply_requirement_relation_review = AsyncMock(return_value=(None, None))
    return fake_module


def load_tenders_test_modules():
    global _TENDERS_MODULES
    if _TENDERS_MODULES is not None:
        return _TENDERS_MODULES

    models_module = load_models_test_module()

    fake_modules = {
        "minio": _build_fake_minio_module(),
        "app.api.auth": _build_fake_auth_dependency_module(),
        "app.services.chat": _build_fake_chat_module(),
        "app.services.kpi_reason_engine": _build_fake_kpi_module(),
        "app.services.compliance_observability": _build_fake_compliance_module(models_module),
        "app.services.requirement_candidates": _build_fake_requirement_candidates_module(),
        "app.services.requirement_consolidation": _build_fake_requirement_consolidation_module(),
        "app.services.requirement_review": _build_fake_requirement_review_module(),
        "app.services.requirement_relation_review": _build_fake_requirement_relation_review_module(),
        "app.services.tender_requirements": _build_fake_tender_requirements_module(),
    }

    with (
        patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=Mock(name="engine")),
        patch.dict(sys.modules, fake_modules),
    ):
        sys.modules.pop("app.api.tenders", None)
        tenders_module = import_module("app.api.tenders")

    _TENDERS_MODULES = SimpleNamespace(
        models=models_module,
        tenders=tenders_module,
    )
    return _TENDERS_MODULES


def load_models_test_module():
    global _MODELS_MODULE
    if _MODELS_MODULE is not None:
        return _MODELS_MODULE

    sys.modules.pop("app.db.database", None)
    with patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=Mock(name="engine")):
        _MODELS_MODULE = import_module("app.models")
    return _MODELS_MODULE


def load_service_test_module(module_name: str):
    cached = _SERVICE_MODULES.get(module_name)
    if cached is not None:
        return cached

    load_models_test_module()
    with patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=Mock(name="engine")):
        module = import_module(module_name)
    _SERVICE_MODULES[module_name] = module
    return module


def load_auth_provider_test_modules():
    global _AUTH_PROVIDER_MODULES
    if _AUTH_PROVIDER_MODULES is not None:
        return _AUTH_PROVIDER_MODULES

    original_version = importlib.metadata.version

    def _fake_version(package_name: str) -> str:
        if package_name == "email-validator":
            return "2.0.0"
        return original_version(package_name)

    fake_modules = {
        "jose": _build_fake_jose_module(),
    }

    models_module = load_models_test_module()

    with (
        patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=Mock(name="engine")),
        patch("importlib.metadata.version", side_effect=_fake_version),
        patch("pydantic.networks.version", side_effect=_fake_version, create=True),
        patch.dict(sys.modules, fake_modules),
    ):
        sys.modules.pop("app.auth.legacy", None)
        sys.modules.pop("app.auth.provider", None)
        legacy_module = import_module("app.auth.legacy")
        provider_module = import_module("app.auth.provider")

    _AUTH_PROVIDER_MODULES = SimpleNamespace(
        models=models_module,
        legacy=legacy_module,
        provider=provider_module,
    )
    return _AUTH_PROVIDER_MODULES


def load_rag_api_test_modules():
    global _RAG_API_MODULES
    if _RAG_API_MODULES is not None:
        return _RAG_API_MODULES

    fake_auth = _build_fake_auth_dependency_module()

    fake_privacy_audit = types.ModuleType("app.privacy_audit")
    fake_privacy_audit.persist_privacy_audit = AsyncMock(side_effect=_fake_async_noop)

    fake_privacy_policy = types.ModuleType("app.privacy_policy")

    @dataclass(slots=True)
    class _FakeEffectivePrivacyPolicy:
        route_key: str = "tender"
        tender_id: int | None = None
        anonymizer_enabled: bool = False
        target_base_url: str | None = None
        target_model: str | None = None
        target_provider: str | None = None
        target_api_key: str | None = None
        target_id: str | None = None
        target_timeout_ms: int | None = None
        mode: str = "internal"

        def as_dict(self) -> dict[str, object]:
            return {"mode": self.mode}

    async def _fake_resolve_effective_privacy_policy(*args, **kwargs):
        del args, kwargs
        return _FakeEffectivePrivacyPolicy()

    fake_privacy_policy.EffectivePrivacyPolicy = _FakeEffectivePrivacyPolicy
    fake_privacy_policy.resolve_effective_privacy_policy = _fake_resolve_effective_privacy_policy

    fake_rag_engine = types.ModuleType("app.rag.engine")

    class _QueryMode(str, enum.Enum):
        SEARCH = "search"
        QA = "qa"
        WRITE_SECTION = "write_section"
        EXEC_SUMMARY = "exec_summary"
        ANALYZE_REQS = "analyze_reqs"
        COMPLIANCE = "compliance"

    @dataclass(slots=True)
    class _RAGQuery:
        text: str
        mode: _QueryMode
        filters: dict = field(default_factory=dict)
        top_k: int | None = None
        retrieval_top_k: int | None = None
        temperature: float = 0.3
        retrievers: dict[str, bool] = field(default_factory=dict)
        fusion_weights: dict[str, float] = field(default_factory=dict)
        anonymizer_enabled_override: bool | None = None
        route_key: str = "tender"
        tender_id: int | None = None
        external_target_url: str | None = None
        external_target_model: str | None = None
        external_target_provider: str | None = None
        external_target_api_key: str | None = None
        external_target_id: str | None = None
        external_target_timeout_ms: int | None = None
        sampler_overrides: dict | None = None
        planning_coverage_config: dict | None = None
        guardrail_config: dict | None = None

    fake_rag_engine.QueryMode = _QueryMode
    fake_rag_engine.RAGQuery = _RAGQuery

    fake_tenders = types.ModuleType("app.api.tenders")
    fake_tenders.check_tender_access = AsyncMock(side_effect=_fake_async_noop)

    load_models_test_module()
    fake_modules = {
        "app.api.auth": fake_auth,
        "app.api.tenders": fake_tenders,
        "app.privacy_audit": fake_privacy_audit,
        "app.privacy_policy": fake_privacy_policy,
        "app.rag.engine": fake_rag_engine,
    }

    with (
        patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=Mock(name="engine")),
        patch.dict(sys.modules, fake_modules),
    ):
        sys.modules.pop("app.api.rag", None)
        rag_module = import_module("app.api.rag")

    _RAG_API_MODULES = SimpleNamespace(
        rag=rag_module,
        engine=fake_rag_engine,
        models=load_models_test_module(),
    )
    return _RAG_API_MODULES
