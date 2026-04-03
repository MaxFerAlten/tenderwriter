from __future__ import annotations

import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient
from httpx import Response

from anonymizer._test_support import import_local_module, load_anonymizer_app_module

anonymizer_app = load_anonymizer_app_module()
Settings = import_local_module("config").Settings
_engine_module = import_local_module("engine")
AnonymizerEngine = _engine_module.AnonymizerEngine
Detection = _engine_module.Detection
RedisVault = import_local_module("vault").RedisVault

ADMIN_HEADERS = {"x-anonymizer-admin-token": "tw-anonymizer-admin-token-change-me"}


def test_rejects_loopback_target_url() -> None:
    with TestClient(anonymizer_app.app) as client:
        response = client.get(
            "/v1/models",
            headers={"x-target-url": "http://127.0.0.1:8000/internal"},
        )

    assert response.status_code == 400
    assert response.text == "invalid x-target-url header"


def test_forwards_allowed_target_url(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> Response:
        seen["url"] = str(request.url)
        return Response(200, content=b"ok", headers={"content-type": "text/plain"})

    class PatchedAsyncClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(anonymizer_app.httpx, "AsyncClient", PatchedAsyncClient)

    with TestClient(anonymizer_app.app) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"x-target-url": "https://api.openai.com/v1/chat/completions"},
            content=b'{"messages":[]}',
        )

    assert response.status_code == 200
    assert response.text == "ok"
    assert seen["url"] == "https://api.openai.com/v1/chat/completions"


def test_engine_anonymize_simple_text() -> None:
    settings = Settings()
    vault = RedisVault(redis_url="memory://", default_ttl_seconds=60)
    engine = AnonymizerEngine(settings=settings, vault=vault)

    result = asyncio.run(
        engine.anonymize_text(
            "Mario Rossi ha CF RSSMRA85M01H501Z e IBAN IT60X0542811101000000123456."
        )
    )

    assert "[PERSONA_1]" in result["chunk"]["anonymized_text"]
    assert "[CF_1]" in result["chunk"]["anonymized_text"]
    assert "[IBAN_1]" in result["chunk"]["anonymized_text"]
    assert result["mapping"]["[PERSONA_1]"] == "Mario Rossi"
    assert result["mapping"]["[CF_1]"] == "RSSMRA85M01H501Z"
    assert result["mapping"]["[IBAN_1]"] == "IT60X0542811101000000123456"


def test_same_value_keeps_same_placeholder_across_session() -> None:
    settings = Settings()
    vault = RedisVault(redis_url="memory://", default_ttl_seconds=60)
    engine = AnonymizerEngine(settings=settings, vault=vault)

    first = asyncio.run(engine.anonymize_text("CF RSSMRA85M01H501Z", session_id="sessione-1"))
    second = asyncio.run(
        engine.anonymize_text("Ancora RSSMRA85M01H501Z", session_id="sessione-1")
    )

    assert "[CF_1]" in first["chunk"]["anonymized_text"]
    assert "[CF_1]" in second["chunk"]["anonymized_text"]
    assert second["mapping"]["[CF_1]"] == "RSSMRA85M01H501Z"


def test_session_expired_is_not_restored() -> None:
    settings = Settings(default_ttl_seconds=1)
    vault = RedisVault(redis_url="memory://", default_ttl_seconds=1)
    asyncio.run(vault.store_session("expired", {"[CF_1]": "RSSMRA85M01H501Z"}, ttl_seconds=0))

    session = asyncio.run(vault.get_session("expired"))

    assert session is None


def test_overlapping_entities_keep_longest_match() -> None:
    engine = AnonymizerEngine(settings=Settings(), vault=RedisVault(redis_url="memory://"))
    detections = [
        Detection(
            entity_type="CODICE_FISCALE",
            start=0,
            end=16,
            text="RSSMRA85M01H501Z",
            score=0.95,
            source="regex:cf",
        ),
        Detection(
            entity_type="PERSON",
            start=0,
            end=11,
            text="RSSMRA85M01",
            score=0.40,
            source="spacy:PER",
        ),
    ]

    filtered = engine._deduplicate("RSSMRA85M01H501Z", detections)

    assert len(filtered) == 1
    assert filtered[0].entity_type == "CODICE_FISCALE"


def test_italian_recognizers_are_exposed_via_api() -> None:
    with TestClient(anonymizer_app.app) as client:
        response = client.post(
            "/v1/anonymize",
            json={
                "text": (
                    "Mario Rossi CF RSSMRA85M01H501Z, PIVA 12345678901, "
                    "IBAN IT60X0542811101000000123456"
                )
            },
        )

    assert response.status_code == 200
    payload = response.json()
    anonymized = payload["chunk"]["anonymized_text"]
    assert "[CF_1]" in anonymized
    assert "[PIVA_1]" in anonymized
    assert "[IBAN_1]" in anonymized


def test_api_deanonymize_roundtrip() -> None:
    with TestClient(anonymizer_app.app) as client:
        anonymize_response = client.post(
            "/v1/anonymize",
            json={"text": "CF RSSMRA85M01H501Z"},
        )
        payload = anonymize_response.json()
        session_id = payload["session_id"]
        deanonymize_response = client.post(
            "/v1/deanonymize",
            json={
                "text": payload["chunk"]["anonymized_text"],
                "session_id": session_id,
            },
            headers=ADMIN_HEADERS,
        )

    assert deanonymize_response.status_code == 200
    assert deanonymize_response.json()["text"] == "CF RSSMRA85M01H501Z"


def test_api_config_roundtrip() -> None:
    with TestClient(anonymizer_app.app) as client:
        initial = client.get("/v1/config", headers=ADMIN_HEADERS)
        response = client.post(
            "/v1/config",
            json={"ttl_seconds": 120, "mask_cig": True, "min_confidence": 0.5},
            headers=ADMIN_HEADERS,
        )
        stored = client.get("/v1/config", headers=ADMIN_HEADERS)

    assert initial.status_code == 200
    assert initial.json()["strategy"] == "redaction"
    assert response.status_code == 200
    assert response.json()["ttl_seconds"] == 120
    assert response.json()["mask_cig"] is True
    assert response.json()["min_confidence"] == 0.5
    assert stored.status_code == 200
    assert stored.json()["ttl_seconds"] == 120
    assert stored.json()["mask_cig"] is True


def test_api_stats_track_requests() -> None:
    with TestClient(anonymizer_app.app) as client:
        anonymize_response = client.post(
            "/v1/anonymize",
            json={"text": "Mario Rossi ha CF RSSMRA85M01H501Z"},
        )
        payload = anonymize_response.json()
        deanonymize_response = client.post(
            "/v1/deanonymize",
            json={
                "text": payload["chunk"]["anonymized_text"],
                "session_id": payload["session_id"],
            },
            headers=ADMIN_HEADERS,
        )
        stats = client.get("/v1/stats", headers=ADMIN_HEADERS)

    assert anonymize_response.status_code == 200
    assert deanonymize_response.status_code == 200
    assert stats.status_code == 200
    assert stats.json()["requests"] == 1
    assert stats.json()["sessions"] == 1
    assert stats.json()["entities_detected"] >= 1
    assert stats.json()["deanonymize_requests"] == 1


def test_api_rejects_too_many_chunks() -> None:
    with TestClient(anonymizer_app.app) as client:
        response = client.post(
            "/v1/anonymize",
            json={"chunks": ["x"] * 33},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "too many chunks"


def test_api_rejects_too_large_text() -> None:
    with TestClient(anonymizer_app.app) as client:
        response = client.post(
            "/v1/anonymize",
            json={"text": "x" * 12001},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "text exceeds max_chunk_chars"


def test_api_denies_protected_endpoints_without_admin_token() -> None:
    with TestClient(anonymizer_app.app) as client:
        config_response = client.get("/v1/config")
        stats_response = client.get("/v1/stats")
        deanonymize_response = client.post(
            "/v1/deanonymize",
            json={"text": "[PERSONA_1]", "session_id": "missing"},
        )

    assert config_response.status_code == 403
    assert stats_response.status_code == 403
    assert deanonymize_response.status_code == 403


def test_engine_faking_strategy_produces_synthetic_values() -> None:
    settings = Settings()
    vault = RedisVault(redis_url="memory://", default_ttl_seconds=60)
    engine = AnonymizerEngine(settings=settings, vault=vault)

    result = asyncio.run(
        engine.anonymize_text(
            "Mario Rossi ha CF RSSMRA85M01H501Z",
            config={"strategy": "faking", "entities": ["PERSON", "CODICE_FISCALE"]},
        )
    )

    anonymized = result["chunk"]["anonymized_text"]
    assert "Mario Rossi" not in anonymized
    assert "RSSMRA85M01H501Z" not in anonymized
    assert "[PERSONA_1]" not in anonymized


def test_cig_is_masked_only_when_enabled() -> None:
    settings = Settings()
    vault = RedisVault(redis_url="memory://", default_ttl_seconds=60)
    engine = AnonymizerEngine(settings=settings, vault=vault)

    disabled = asyncio.run(
        engine.anonymize_text(
            "CIG A1B2C3D4E5",
            config={"mask_cig": False, "entities": ["CIG"]},
        )
    )
    enabled = asyncio.run(
        engine.anonymize_text(
            "CIG A1B2C3D4E5",
            config={"mask_cig": True, "entities": ["CIG"]},
        )
    )

    assert "A1B2C3D4E5" in disabled["chunk"]["anonymized_text"]
    assert "[CIG_1]" in enabled["chunk"]["anonymized_text"]
