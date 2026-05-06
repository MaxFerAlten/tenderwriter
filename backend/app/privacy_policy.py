from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import AIGatewayTarget, AppSettings


@dataclass(slots=True)
class EffectivePrivacyPolicy:
    route_key: str = "tender"
    tender_id: int | None = None
    mode: str = "internal_only"
    anonymizer_enabled: bool = False
    target_id: int | None = None
    target_kind: str | None = None
    target_provider: str | None = None
    target_base_url: str | None = None
    target_model: str | None = None
    target_api_key: str | None = None
    target_timeout_ms: int | None = None
    target_use_anonymizer: bool | None = None
    sources: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("target_api_key", None)
        return data


def _default_policy_payload() -> dict[str, Any]:
    return {
        "default": {},
        "routes": {},
        "tenders": {},
    }


def _is_external_target(target: AIGatewayTarget) -> bool:
    if (target.target_kind or "").strip().lower() in {"dmz", "cloud"}:
        return True
    provider = (target.provider or "").strip().lower()
    if provider and provider not in {"llama", "ollama"}:
        return True
    return target.base_url.rstrip("/") != settings.llama_server_url.rstrip("/")


def _effective_target_provider(target: AIGatewayTarget) -> str | None:
    provider = (target.provider or "").strip().lower()
    if provider:
        if provider == "llama" and "openrouter.ai" in (target.base_url or "").strip().lower():
            return "openrouter"
        return provider
    if "openrouter.ai" in (target.base_url or "").strip().lower():
        return "openrouter"
    return None


def _coerce_rule(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


async def load_privacy_policy_document(db: AsyncSession | Any) -> dict[str, Any]:
    if not hasattr(db, "execute"):
        return _default_policy_payload()
    result = await db.execute(select(AppSettings).limit(1))
    row = result.scalar_one_or_none()
    data = row.data if row and isinstance(row.data, dict) else {}
    policy = data.get("anonymizer_policy")
    if not isinstance(policy, dict):
        return _default_policy_payload()
    payload = _default_policy_payload()
    payload.update(policy)
    return payload


async def resolve_effective_privacy_policy(
    db: AsyncSession | Any,
    *,
    route_key: str = "tender",
    tender_id: int | None = None,
    anonymizer_enabled_override: bool | None = None,
) -> EffectivePrivacyPolicy:
    policy = EffectivePrivacyPolicy(route_key=route_key, tender_id=tender_id)
    source_notes: list[str] = []
    explicit_mode = False

    settings_result = None
    if hasattr(db, "execute"):
        settings_result = await db.execute(select(AppSettings).limit(1))
    settings_row = settings_result.scalar_one_or_none() if settings_result is not None else None
    settings_data = (
        settings_row.data if settings_row and isinstance(settings_row.data, dict) else {}
    )
    policy_doc = settings_data.get("anonymizer_policy")
    policy_doc = policy_doc if isinstance(policy_doc, dict) else _default_policy_payload()

    anonymizer_enabled = bool(settings_data.get("anonymizer_enabled", settings.anonymizer_enabled))
    if anonymizer_enabled_override is not None:
        anonymizer_enabled = bool(anonymizer_enabled_override)
        source_notes.append("query_override.anonymizer_enabled")

    target: AIGatewayTarget | None = None
    if hasattr(db, "execute"):
        stmt = (
            select(AIGatewayTarget)
            .where(AIGatewayTarget.enabled, AIGatewayTarget.route_key == route_key)
            .order_by(AIGatewayTarget.priority, AIGatewayTarget.id)
        )
        target_result = await db.execute(stmt)
        for item in target_result.scalars():
            if _is_external_target(item):
                target = item
                break

    if target is not None:
        policy.target_id = target.id
        policy.target_kind = target.target_kind
        policy.target_provider = _effective_target_provider(target)
        policy.target_base_url = target.base_url
        policy.target_model = target.model_name
        policy.target_api_key = target.api_key
        policy.target_timeout_ms = target.timeout_ms
        policy.target_use_anonymizer = target.use_anonymizer
        source_notes.append("gateway.active_target")
        if target.use_anonymizer:
            anonymizer_enabled = True
            source_notes.append("gateway.target_requires_anonymizer")
    elif settings.external_llm_url.strip():
        policy.target_provider = "external-config"
        policy.target_base_url = settings.external_llm_url
        policy.target_model = settings.external_llm_model or settings.llama_model
        policy.target_timeout_ms = int(settings.llama_timeout * 1000)
        source_notes.append("settings.external_llm")

    def apply_rule(rule: dict[str, Any], *, label: str) -> None:
        nonlocal explicit_mode
        nonlocal anonymizer_enabled
        mode = rule.get("mode")
        if isinstance(mode, str) and mode in {"internal_only", "external_anonymized"}:
            policy.mode = mode
            explicit_mode = True
            source_notes.append(f"{label}.mode")
        if "anonymizer_enabled" in rule and rule["anonymizer_enabled"] is not None:
            anonymizer_enabled = bool(rule["anonymizer_enabled"])
            source_notes.append(f"{label}.anonymizer_enabled")

    apply_rule(_coerce_rule(policy_doc.get("default")), label="policy.default")
    apply_rule(
        _coerce_rule((policy_doc.get("routes") or {}).get(route_key)),
        label=f"policy.route.{route_key}",
    )
    if tender_id is not None:
        apply_rule(
            _coerce_rule((policy_doc.get("tenders") or {}).get(str(tender_id))),
            label=f"policy.tender.{tender_id}",
        )

    policy.anonymizer_enabled = anonymizer_enabled
    if policy.mode != "internal_only" and not policy.target_base_url:
        policy.mode = "internal_only"
        source_notes.append("security.no_external_target_available")
    elif (
        not explicit_mode
        and policy.mode == "internal_only"
        and policy.target_base_url
        and policy.anonymizer_enabled
    ):
        policy.mode = "external_anonymized"
        source_notes.append("policy.default_external_anonymized")

    if policy.mode == "external_anonymized" and not policy.anonymizer_enabled:
        policy.mode = "internal_only"
        source_notes.append("security.cleartext_external_blocked")

    policy.sources = source_notes
    return policy
