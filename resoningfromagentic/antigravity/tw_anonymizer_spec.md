# TW-Anonymizer — Specifica Tecnica Definitiva

> **Data**: 21 Marzo 2026  
> **Progetto**: TenderWriter — Privacy Gateway per RAG Pipeline  
> **Stato**: PRONTA PER IMPLEMENTAZIONE  
> **Decisioni architetturali**: Tutte confermate dal product owner

---

## 0. Decisioni Confermate

| Domanda | Risposta |
|---|---|
| Modalità operativa | **Globale** — on/off per tutto il sistema |
| Strategia default | **REDACTION** (`[PERSONA_1]`, `[ORG_1]`, etc.) |
| De-anonimizzazione | **Sì** — per l'utente finale che usa il software |
| CIG (Codice Gara) | **Oscurare** quando possibile |
| Punto di integrazione | **[engine.py](file:///media/marco/DATA2/progettiAi/tenderwriter/backend/app/rag/engine.py)** — metodo [query()](file:///media/marco/DATA2/progettiAi/tenderwriter/backend/app/rag/engine.py#140-286) |
| Ruolo del gateway | **Solo LLM routing** — backend chiama anonymizer direttamente |

---

## 1. Architettura del Flusso

### 1.1 Pipeline Corrente (engine.py)
```
Query → Dense Retrieval → Sparse Retrieval → Graph Retrieval
     → Fusion → Rerank → [context_texts] → Generator → Risposta
```

### 1.2 Pipeline Target
```
Query → Dense Retrieval → Sparse Retrieval → Graph Retrieval
     → Fusion → Rerank → [context_texts]
     → ── NEW: Anonymize (se enabled) ──────
     → Generator (LLM interno o esterno)
     → ── NEW: De-anonymize (se session_token) ──
     → Risposta utente
```

### 1.3 Matrice Comportamentale

| Scenario | `anonymizer_enabled` | Anonymizer | LLM usata | Dati escono? |
|---|---|---|---|---|
| Default (off) | `false` | Non invocato | `tw-llama-tender` (interno) | ❌ No |
| Anonymizer ON + OK | `true` | ✅ Online | LLM esterna configurata | ✅ Solo anonimizzati |
| Anonymizer ON + KO | `true` | ❌ Down | `tw-llama-tender` (fallback) | ❌ No — Security fallback |
| Anonymizer ON + no External LLM | `true` | ✅ Online | `tw-llama-tender` (interno) | ❌ No |

> [!CAUTION]
> **Invariante di sicurezza**: Se `anonymizer_enabled=true` e l'anonymizer non è raggiungibile, il sistema **DEVE** fare fallback su `tw-llama-tender` interno. MAI inviare dati in chiaro a LLM esterne.

---

## 2. Componente `anonymizer/` — Struttura File

### 2.1 Struttura Target

```
anonymizer/
├── app.py                    # FastAPI app (evolve il proxy attuale)
├── engine.py                 # ← NUOVO: core anonimizzazione con Presidio
├── recognizers/
│   ├── __init__.py
│   └── italian.py            # ← NUOVO: CF, PIVA, IBAN, CIG
├── strategies.py             # ← NUOVO: REDACTION / FAKING
├── vault.py                  # ← NUOVO: Redis reverse mapping
├── config.py                 # ← NUOVO: settings via env
├── requirements.txt          # aggiornato
├── Dockerfile                # aggiornato (pre-download modelli)
├── run.py                    # invariato
└── test_anonymizer.py        # espanso
```

### 2.2 `anonymizer/config.py`

```python
"""TW-Anonymizer — Configuration"""
from pydantic_settings import BaseSettings


class AnonymizerSettings(BaseSettings):
    redis_url: str = "redis://tw-redis:6379/1"  # DB 1, separato da Celery (DB 0)
    host: str = "0.0.0.0"
    port: int = 8090
    log_level: str = "INFO"

    # NER engine: "piiranha" | "spacy"
    ner_backend: str = "piiranha"

    # Default config (override da admin via Redis)
    default_config: dict = {
        "enabled": False,
        "strategy": "redaction",           # "redaction" | "faking"
        "min_confidence_score": 0.7,
        "session_ttl_seconds": 3600,       # 1 ora
        "entities": {
            "IT_CODICE_FISCALE": True,
            "IT_PARTITA_IVA": True,
            "IT_IBAN": True,
            "IT_CIG": True,               # Codice Identificativo Gara
            "PERSON": True,
            "ORG": True,
            "EMAIL_ADDRESS": True,
            "PHONE_NUMBER": True,
            "LOCATION": False,
            "DATE_TIME": False,
            "URL": False,
        },
    }

    class Config:
        env_prefix = "ANONYMIZER_"


settings = AnonymizerSettings()
```

### 2.3 `anonymizer/recognizers/italian.py`

Custom recognizer per entità italiane strutturate.

```python
"""TW-Anonymizer — Italian PII Recognizers

Regex-based recognizers for Italian structured identifiers:
- Codice Fiscale (IT_CODICE_FISCALE)
- Partita IVA (IT_PARTITA_IVA)
- IBAN italiano (IT_IBAN)
- CIG — Codice Identificativo Gara (IT_CIG)
"""

from presidio_analyzer import Pattern, PatternRecognizer


class CodiceFiscaleRecognizer(PatternRecognizer):
    """
    Codice Fiscale italiano.
    Formato: 6 lettere + 2 cifre + 1 lettera + 2 cifre + 1 lettera + 3 cifre + 1 lettera
    Es: RSSMRA85M01H501Z
    """
    PATTERNS = [
        Pattern(
            "CODICE_FISCALE_STRONG",
            r"\b[A-Z]{6}[0-9]{2}[A-EHLMPRST]{1}[0-9]{2}[A-Z]{1}[0-9]{3}[A-Z]{1}\b",
            score=0.95,
        )
    ]
    CONTEXT = ["codice fiscale", "cf", "c.f.", "fiscal code"]

    def __init__(self):
        super().__init__(
            supported_entity="IT_CODICE_FISCALE",
            patterns=self.PATTERNS,
            context=self.CONTEXT,
        )


class PartitaIvaRecognizer(PatternRecognizer):
    """
    Partita IVA italiana.
    Formato: 11 cifre, opzionalmente prefissate da IT
    Es: IT12345678901 oppure 12345678901
    """
    PATTERNS = [
        Pattern(
            "PIVA_WITH_PREFIX",
            r"\bIT[0-9]{11}\b",
            score=0.98,
        ),
        Pattern(
            "PIVA_STANDALONE",
            r"(?i)(?:p\.?\s*iva|partita\s+iva)\s*[:\-]?\s*([0-9]{11})\b",
            score=0.90,
        ),
    ]
    CONTEXT = ["partita iva", "p.iva", "piva", "vat number"]

    def __init__(self):
        super().__init__(
            supported_entity="IT_PARTITA_IVA",
            patterns=self.PATTERNS,
            context=self.CONTEXT,
        )


class IBANRecognizer(PatternRecognizer):
    """
    IBAN italiano.
    Formato: IT + 2 check digits + 1 lettera + 22 caratteri
    Es: IT60X0542811101000000123456
    """
    PATTERNS = [
        Pattern(
            "IBAN_IT",
            r"\bIT[0-9]{2}[A-Z][0-9]{10}[0-9A-Z]{12}\b",
            score=0.97,
        ),
    ]
    CONTEXT = ["iban", "conto corrente", "bonifico", "coordinate bancarie"]

    def __init__(self):
        super().__init__(
            supported_entity="IT_IBAN",
            patterns=self.PATTERNS,
            context=self.CONTEXT,
        )


class CIGRecognizer(PatternRecognizer):
    """
    CIG — Codice Identificativo Gara (ANAC).
    Formato: 10 caratteri alfanumerici.
    Es: Z2B1234567 oppure 8765432109
    """
    PATTERNS = [
        Pattern(
            "CIG_ANAC",
            r"\b[A-Z0-9]{10}\b",
            score=0.60,  # score basso, contesto necessario
        ),
    ]
    CONTEXT = ["cig", "codice gara", "codice identificativo gara", "gara d'appalto"]

    def __init__(self):
        super().__init__(
            supported_entity="IT_CIG",
            patterns=self.PATTERNS,
            context=self.CONTEXT,
        )
```

### 2.4 `anonymizer/strategies.py`

```python
"""TW-Anonymizer — Anonymization Strategies

REDACTION: Sostituisce con placeholder tipizzati [PERSONA_1], [ORG_1], etc.
FAKING:   Sostituisce con dati sintetici plausibili (future use).
"""

from enum import Enum


class AnonymizationStrategy(str, Enum):
    REDACTION = "redaction"     # [ORG_1] — default, massima privacy
    FAKING = "faking"           # "Alfa Solutions S.r.l." — dati sintetici


# Label italiani per i placeholder
ENTITY_LABELS: dict[str, str] = {
    "IT_CODICE_FISCALE": "CF",
    "IT_PARTITA_IVA": "PIVA",
    "IT_IBAN": "IBAN",
    "IT_CIG": "CIG",
    "PERSON": "PERSONA",
    "ORG": "ORG",
    "EMAIL_ADDRESS": "EMAIL",
    "PHONE_NUMBER": "TELEFONO",
    "URL": "URL",
    "DATE_TIME": "DATA",
    "LOCATION": "LUOGO",
}


# Pool per strategia FAKING (fase futura)
FAKE_POOL: dict[str, list[str]] = {
    "PERSON": [
        "Luca Bianchi", "Marco Ferrari", "Sara Esposito",
        "Giovanni Ricci", "Elena Conti", "Paolo Romano",
    ],
    "ORG": [
        "Alfa Solutions S.r.l.", "Beta Consulting S.p.A.",
        "Gamma Tech S.r.l.", "Delta Group S.p.A.",
    ],
    "IT_PARTITA_IVA": [
        "IT99887766554", "IT11223344556",
    ],
    "IT_CODICE_FISCALE": [
        "TSTFKE99A01H501Z", "BNCMRC85B20F205X",
    ],
    "IT_IBAN": [
        "IT60X0542811101000000123456",
    ],
    "LOCATION": [
        "Via delle Magnolie 5, Milano",
        "Corso Europa 22, Roma",
    ],
}


class FakingOperator:
    """
    Sostituisce PII con valori fittizi plausibili.
    Stessa entità → stesso fake in tutta la sessione (consistenza).
    """
    def __init__(self):
        self._entity_to_fake: dict[str, str] = {}
        self._counters: dict[str, int] = {}

    def get_fake(self, entity_type: str, original_value: str) -> str:
        if original_value in self._entity_to_fake:
            return self._entity_to_fake[original_value]

        pool = FAKE_POOL.get(entity_type, [])
        if pool:
            idx = self._counters.get(entity_type, 0) % len(pool)
            self._counters[entity_type] = idx + 1
            fake = pool[idx]
        else:
            label = ENTITY_LABELS.get(entity_type, entity_type)
            fake = f"[{label}_ANONIMIZZATO]"

        self._entity_to_fake[original_value] = fake
        return fake
```

### 2.5 `anonymizer/vault.py`

```python
"""TW-Anonymizer — Redis Vault

Ephemeral reverse mapping storage.
session_token → {placeholder: original_value}
TTL configurabile, non persiste mai su DB.
"""

from __future__ import annotations

import json

import redis.asyncio as aioredis

from anonymizer.config import settings


_redis: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def store_session(
    session_token: str,
    reverse_map: dict[str, str],
    ttl: int = 3600,
) -> None:
    """Store reverse mapping in Redis with TTL."""
    r = await get_redis()
    key = f"anonymizer:session:{session_token}"
    await r.setex(key, ttl, json.dumps(reverse_map))


async def get_session(session_token: str) -> dict[str, str] | None:
    """Retrieve reverse mapping from Redis by session token."""
    r = await get_redis()
    key = f"anonymizer:session:{session_token}"
    raw = await r.get(key)
    if raw:
        return json.loads(raw)
    return None


async def load_config() -> dict:
    """Load admin config from Redis, fallback to defaults."""
    try:
        r = await get_redis()
        raw = await r.get("anonymizer:config")
        if raw:
            return json.loads(raw)
    except Exception:
        pass
    return settings.default_config


async def save_config(config: dict) -> None:
    """Persist admin config to Redis."""
    r = await get_redis()
    await r.set("anonymizer:config", json.dumps(config))


async def update_stats(entities: int, chunks: int) -> None:
    """Aggregate anonymization statistics."""
    r = await get_redis()
    raw = await r.get("anonymizer:stats")
    stats = json.loads(raw) if raw else {
        "total_chunks": 0, "total_entities": 0, "sessions": 0
    }
    stats["total_chunks"] += chunks
    stats["total_entities"] += entities
    stats["sessions"] += 1
    await r.set("anonymizer:stats", json.dumps(stats))


async def get_stats() -> dict:
    """Get aggregated statistics."""
    r = await get_redis()
    raw = await r.get("anonymizer:stats")
    if raw:
        return json.loads(raw)
    return {"total_chunks": 0, "total_entities": 0, "sessions": 0}
```

### 2.6 `anonymizer/engine.py`

```python
"""TW-Anonymizer — Core Anonymization Engine

Pipeline:
  1. Presidio AnalyzerEngine (NER + regex) → RecognizerResult list
  2. Replace entities with typed placeholders [PERSONA_1], [ORG_1], etc.
  3. Build reverse mapping {placeholder: original_value}
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import structlog

from anonymizer.strategies import ENTITY_LABELS, AnonymizationStrategy, FakingOperator

logger = structlog.get_logger()


class NERBackend(str, Enum):
    SPACY = "spacy"
    PIIRANHA = "piiranha"


@dataclass
class AnonymizedChunk:
    original_text: str
    anonymized_text: str
    entities_found: list[dict]
    mapping: dict[str, str]  # {placeholder: original_value}


class AnonymizerEngine:
    """
    Core engine that detects and replaces PII in text.

    Supports pluggable NER backends:
    - piiranha (default): 278M params, >98% precision on Italian
    - spacy: fallback, it_core_news_lg
    """

    def __init__(self, config: dict):
        self.config = config
        self._analyzer = None
        self._anonymizer = None

    def _build_analyzer(self):
        """Build Presidio AnalyzerEngine with Italian recognizers."""
        from presidio_analyzer import AnalyzerEngine, RecognizerRegistry

        ner_backend = self.config.get("ner_backend", NERBackend.PIIRANHA)

        if ner_backend == NERBackend.PIIRANHA:
            from presidio_analyzer.nlp_engine import TransformersNlpEngine
            nlp_engine = TransformersNlpEngine(
                models=[{
                    "lang_code": "it",
                    "model_name": "iiiorg/piiranha-v1-detect-personal-information",
                }]
            )
        else:
            from presidio_analyzer.nlp_engine import NlpEngineProvider
            provider = NlpEngineProvider(nlp_configuration={
                "nlp_engine_name": "spacy",
                "models": [{"lang_code": "it", "model_name": "it_core_news_lg"}],
            })
            nlp_engine = provider.create_engine()

        registry = RecognizerRegistry()
        registry.load_predefined_recognizers(nlp_engine=nlp_engine)

        # Custom Italian recognizers
        from anonymizer.recognizers.italian import (
            CodiceFiscaleRecognizer,
            PartitaIvaRecognizer,
            IBANRecognizer,
            CIGRecognizer,
        )
        registry.add_recognizer(CodiceFiscaleRecognizer())
        registry.add_recognizer(PartitaIvaRecognizer())
        registry.add_recognizer(IBANRecognizer())
        registry.add_recognizer(CIGRecognizer())

        return AnalyzerEngine(
            nlp_engine=nlp_engine,
            registry=registry,
            supported_languages=["it", "en"],
        )

    @property
    def analyzer(self):
        if self._analyzer is None:
            self._analyzer = self._build_analyzer()
        return self._analyzer

    def _get_active_entities(self) -> list[str]:
        """Return only admin-enabled entity types."""
        entity_config = self.config.get("entities", {})
        return [
            entity_type
            for entity_type in ENTITY_LABELS
            if entity_config.get(entity_type, True)
        ]

    def anonymize_text(
        self,
        text: str,
        language: str = "it",
        session_map: dict[str, str] | None = None,
        strategy: str = "redaction",
    ) -> AnonymizedChunk:
        """
        Anonymize a single text.

        Args:
            text: Text to anonymize.
            language: Language code ("it" or "en").
            session_map: Existing mapping from previous chunks (for consistency).
            strategy: "redaction" or "faking".

        Returns:
            AnonymizedChunk with anonymized text and local mapping.
        """
        session_map = session_map or {}
        active_entities = self._get_active_entities()
        min_score = self.config.get("min_confidence_score", 0.7)

        # Step 1: NER analysis
        results = self.analyzer.analyze(
            text=text,
            language=language,
            entities=active_entities,
            score_threshold=min_score,
        )

        if not results:
            return AnonymizedChunk(
                original_text=text,
                anonymized_text=text,
                entities_found=[],
                mapping={},
            )

        # Step 2: Sort results by position (reverse) to replace from end
        results = sorted(results, key=lambda r: r.start, reverse=True)

        # Step 3: Build replacements
        local_mapping: dict[str, str] = {}
        placeholder_counter: dict[str, int] = {}
        faking_operator = FakingOperator() if strategy == "faking" else None

        anonymized = text
        entities_found = []

        for result in results:
            original_value = text[result.start:result.end]
            label = ENTITY_LABELS.get(result.entity_type, result.entity_type)

            # Check if this exact value already has a placeholder in session or local
            combined = {**session_map, **local_mapping}
            existing_placeholder = None
            for ph, orig in combined.items():
                if orig == original_value:
                    existing_placeholder = ph
                    break

            if existing_placeholder:
                placeholder = existing_placeholder
            elif strategy == "faking" and faking_operator:
                placeholder = faking_operator.get_fake(
                    result.entity_type, original_value
                )
            else:
                # REDACTION: generate [LABEL_N] placeholder
                count = placeholder_counter.get(label, 0) + 1
                placeholder_counter[label] = count
                # Check session_map for max existing counter
                import re
                pattern = rf"\[{re.escape(label)}_(\d+)\]"
                for ph in combined:
                    m = re.match(pattern, ph)
                    if m:
                        count = max(count, int(m.group(1)) + 1)
                        placeholder_counter[label] = count
                placeholder = f"[{label}_{count}]"

            local_mapping[placeholder] = original_value

            # Replace in text
            anonymized = anonymized[:result.start] + placeholder + anonymized[result.end:]

            entities_found.append({
                "entity_type": result.entity_type,
                "start": result.start,
                "end": result.end,
                "score": round(result.score, 3),
                "placeholder": placeholder,
            })

        logger.debug(
            "Text anonymized",
            entities_count=len(results),
            text_len=len(text),
        )

        return AnonymizedChunk(
            original_text=text,
            anonymized_text=anonymized,
            entities_found=entities_found,
            mapping=local_mapping,
        )

    def deanonymize_text(self, text: str, reverse_map: dict[str, str]) -> str:
        """
        Restore original text from placeholders.
        Sort by length (longest first) to avoid partial replacements.
        """
        result = text
        for placeholder, original in sorted(
            reverse_map.items(), key=lambda x: len(x[0]), reverse=True
        ):
            result = result.replace(placeholder, original)
        return result
```

### 2.7 [anonymizer/app.py](file:///media/marco/DATA2/progettiAi/tenderwriter/anonymizer/app.py) — Evoluzione

```python
"""
TW-Anonymizer — Privacy Gateway Service

Endpoints:
  POST /v1/anonymize     — anonymize list of text chunks
  POST /v1/deanonymize   — restore text from session token
  GET  /v1/config        — read current anonymizer config
  POST /v1/config        — update config (called by backend admin API)
  GET  /v1/stats         — anonymization statistics
  GET  /health           — health check
  /{path:path}           — transparent forwarder (backward compat)
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import httpx
import structlog
from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, Field

from anonymizer.config import settings
from anonymizer.engine import AnonymizerEngine
from anonymizer import vault

logger = structlog.get_logger()

app = FastAPI(
    title="tw-anonymizer",
    version="1.0.0",
    docs_url="/docs",
    redoc_url=None,
)

# --- Singleton engine (lazy init) ---
_engine: AnonymizerEngine | None = None


async def get_engine() -> AnonymizerEngine:
    global _engine
    if _engine is None:
        config = await vault.load_config()
        _engine = AnonymizerEngine(config)
    return _engine


# ─── Schemas ────────────────────────────────────────────────

class AnonymizeRequest(BaseModel):
    chunks: list[str] = Field(..., description="Text chunks to anonymize")
    language: str = Field("it", description="Language (it/en)")
    session_ttl: int = Field(3600, description="Redis TTL in seconds")


class AnonymizeResponse(BaseModel):
    session_token: str
    anonymized_chunks: list[str]
    stats: dict[str, Any]


class DeanonymizeRequest(BaseModel):
    session_token: str
    texts: list[str] = Field(..., description="Texts with placeholders to restore")


class DeanonymizeResponse(BaseModel):
    restored_texts: list[str]


class ConfigUpdateRequest(BaseModel):
    enabled: bool = True
    strategy: str = Field("redaction", description="'redaction' | 'faking'")
    min_confidence_score: float = Field(0.7, ge=0.0, le=1.0)
    session_ttl_seconds: int = Field(3600, ge=60, le=86400)
    entities: dict[str, bool] = Field(default_factory=dict)


# ─── Endpoints ──────────────────────────────────────────────

@app.get("/health")
async def health():
    try:
        r = await vault.get_redis()
        redis_ok = await r.ping()
    except Exception:
        redis_ok = False
    return {
        "status": "ok",
        "redis": "connected" if redis_ok else "error",
        "engine": "loaded" if _engine is not None else "lazy",
    }


@app.post("/v1/anonymize", response_model=AnonymizeResponse)
async def anonymize_chunks(request: AnonymizeRequest):
    """
    Anonymize text chunks, store reverse mapping in Redis.
    Returns anonymized chunks + session_token for deanonymization.
    """
    engine = await get_engine()
    session_token = str(uuid.uuid4())
    session_reverse_map: dict[str, str] = {}
    anonymized_chunks: list[str] = []
    total_entities = 0

    config = await vault.load_config()
    strategy = config.get("strategy", "redaction")

    for chunk_text in request.chunks:
        result = engine.anonymize_text(
            text=chunk_text,
            language=request.language,
            session_map=session_reverse_map,
            strategy=strategy,
        )
        anonymized_chunks.append(result.anonymized_text)
        session_reverse_map.update(result.mapping)
        total_entities += len(result.entities_found)

    # Store in Redis vault
    await vault.store_session(
        session_token, session_reverse_map, request.session_ttl
    )

    # Update stats
    await vault.update_stats(total_entities, len(request.chunks))

    logger.info(
        "Anonymization complete",
        session=session_token,
        chunks=len(request.chunks),
        entities=total_entities,
    )

    return AnonymizeResponse(
        session_token=session_token,
        anonymized_chunks=anonymized_chunks,
        stats={
            "chunks_processed": len(request.chunks),
            "entities_found": total_entities,
            "session_ttl": request.session_ttl,
        },
    )


@app.post("/v1/deanonymize", response_model=DeanonymizeResponse)
async def deanonymize_texts(request: DeanonymizeRequest):
    """Restore original text using session token."""
    reverse_map = await vault.get_session(request.session_token)
    if not reverse_map:
        raise HTTPException(
            status_code=404,
            detail="Session token not found or expired.",
        )

    engine = await get_engine()
    restored = [
        engine.deanonymize_text(text, reverse_map)
        for text in request.texts
    ]
    return DeanonymizeResponse(restored_texts=restored)


@app.get("/v1/config")
async def get_config():
    return await vault.load_config()


@app.post("/v1/config")
async def update_config(config: ConfigUpdateRequest):
    global _engine
    config_dict = config.model_dump()
    await vault.save_config(config_dict)
    _engine = None  # Force reload with new config
    logger.info("Anonymizer config updated", config=config_dict)
    return {"status": "updated", "config": config_dict}


@app.get("/v1/stats")
async def get_stats():
    return await vault.get_stats()


# ─── Transparent Forwarder (backward compat) ─────────────

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def forward(path: str, request: Request) -> Response:
    """Transparent forwarder for backward compatibility with gateway."""
    # Skip our own versioned endpoints
    if path.startswith("v1/") or path in ("health", "docs", "openapi.json"):
        raise HTTPException(status_code=404)

    target_url = request.headers.get("x-target-url")
    if not target_url:
        return Response(
            content=b"missing x-target-url header",
            status_code=400,
            media_type="text/plain",
        )

    body = await request.body()
    headers = {
        k: v for k, v in request.headers.items()
        if k.lower() != "x-target-url"
    }

    async with httpx.AsyncClient(timeout=30) as client:
        upstream_resp = await client.request(
            request.method, target_url,
            params=request.query_params,
            content=body, headers=headers,
        )

    return Response(
        content=upstream_resp.content,
        status_code=upstream_resp.status_code,
        headers={
            k: v for k, v in upstream_resp.headers.items()
            if k.lower() in {"content-type", "content-length"}
        },
    )
```

### 2.8 [anonymizer/requirements.txt](file:///media/marco/DATA2/progettiAi/tenderwriter/anonymizer/requirements.txt)

```text
fastapi==0.111.0
uvicorn==0.29.0
httpx==0.27.0
redis[asyncio]==5.0.3
presidio-analyzer==2.2.354
presidio-anonymizer==2.2.354
# pii-rahna via transformers (278M params, CPU-only)
transformers>=4.40.0
torch==2.2.2+cpu
# spaCy fallback
spacy==3.7.4
structlog==24.1.0
pydantic-settings==2.2.1
```

### 2.9 [anonymizer/Dockerfile](file:///media/marco/DATA2/progettiAi/tenderwriter/anonymizer/Dockerfile)

```dockerfile
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download pii-rahna model at build time (~560MB)
RUN python -c "\
from transformers import AutoTokenizer, AutoModelForTokenClassification; \
AutoTokenizer.from_pretrained('iiiorg/piiranha-v1-detect-personal-information'); \
AutoModelForTokenClassification.from_pretrained('iiiorg/piiranha-v1-detect-personal-information')"

# Fallback spaCy Italian model
RUN python -m spacy download it_core_news_lg

COPY . /app

HEALTHCHECK --interval=10s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8090/health || exit 1

CMD ["python", "-m", "run"]
```

---

## 3. Modifiche al Backend

### 3.1 [backend/app/config.py](file:///media/marco/DATA2/progettiAi/tenderwriter/backend/app/config.py) — Nuove variabili

Aggiungere nella classe [Settings](file:///media/marco/DATA2/progettiAi/tenderwriter/frontend/src/pages/Settings.tsx#30-703):

```python
    # --- Anonymizer ---
    anonymizer_enabled: bool = False
    anonymizer_url: str = "http://tw-anonymizer:8090"
    anonymizer_timeout: float = 8.0

    # --- External LLM (used when anonymizer is ON) ---
    external_llm_url: str = ""       # OpenAI-compatible endpoint
    external_llm_model: str = ""     # e.g. "gpt-4o"
```

### 3.2 [backend/app/rag/engine.py](file:///media/marco/DATA2/progettiAi/tenderwriter/backend/app/rag/engine.py) — Modifiche al metodo [query()](file:///media/marco/DATA2/progettiAi/tenderwriter/backend/app/rag/engine.py#140-286)

#### 3.2.1 Nuovi import e tipi

Aggiungere in cima al file:

```python
from enum import Enum
import httpx

# ... existing imports ...

class LLMRoute(str, Enum):
    """Tracks which LLM was used — for observability."""
    INTERNAL = "internal"
    EXTERNAL = "external"
    INTERNAL_FALLBACK = "internal_fallback"


class AnonymizerUnavailableError(RuntimeError):
    """Raised when anonymizer is enabled but unreachable."""
    pass
```

#### 3.2.2 Nuova funzione `anonymize_chunks()`

Aggiungere come funzione module-level o metodo di [HybridRAGEngine](file:///media/marco/DATA2/progettiAi/tenderwriter/backend/app/rag/engine.py#66-406):

```python
async def _anonymize_chunks(
    chunks: list[str],
    language: str = "it",
) -> tuple[list[str], str]:
    """
    Send chunks to tw-anonymizer service.

    Returns: (anonymized_chunks, session_token)
    Raises: AnonymizerUnavailableError if service is down.
    """
    try:
        async with httpx.AsyncClient(timeout=settings.anonymizer_timeout) as client:
            resp = await client.post(
                f"{settings.anonymizer_url}/v1/anonymize",
                json={
                    "chunks": chunks,
                    "language": language,
                    "session_ttl": 3600,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data["anonymized_chunks"], data["session_token"]

    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        logger.warning(
            "Anonymizer unreachable — security fallback to internal LLM",
            error=str(exc),
        )
        raise AnonymizerUnavailableError(str(exc)) from exc

    except httpx.HTTPStatusError as exc:
        logger.warning(
            "Anonymizer HTTP error — security fallback to internal LLM",
            status=exc.response.status_code,
        )
        raise AnonymizerUnavailableError(
            f"HTTP {exc.response.status_code}"
        ) from exc


async def _deanonymize_text(
    text: str,
    session_token: str,
) -> str:
    """
    Send text to tw-anonymizer for deanonymization.
    Falls back to returning original text if deanonymize fails.
    """
    try:
        async with httpx.AsyncClient(timeout=settings.anonymizer_timeout) as client:
            resp = await client.post(
                f"{settings.anonymizer_url}/v1/deanonymize",
                json={
                    "session_token": session_token,
                    "texts": [text],
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data["restored_texts"][0]
    except Exception as exc:
        logger.warning("Deanonymization failed, returning raw text", error=str(exc))
        return text
```

#### 3.2.3 Modifica a `HybridRAGEngine.query()`

Il metodo [query()](file:///media/marco/DATA2/progettiAi/tenderwriter/backend/app/rag/engine.py#140-286) attuale ha questa struttura alle righe 233-285.
La modifica si inserisce **tra la costruzione di `context_texts` (riga 246) e lo Step 4 (riga 248)**.

**PRIMA** (riga 246, codice attuale):
```python
        context = "\n\n---\n\n".join(context_texts)

        # ─── Step 4: Search-only mode ───
```

**DOPO** (codice modificato):
```python
        # ─── Step 3.5: Anonymize (if enabled) ───
        session_token = None
        llm_route = LLMRoute.INTERNAL
        active_generator = self.generator  # default: internal LLM

        if settings.anonymizer_enabled:
            try:
                anon_chunks, session_token = await _anonymize_chunks(context_texts)
                context_texts = anon_chunks
                llm_route = LLMRoute.EXTERNAL
                # Switch to external LLM generator
                if settings.external_llm_url:
                    active_generator = Generator(
                        base_url=settings.external_llm_url,
                        model=settings.external_llm_model,
                    )
                logger.info(
                    "Anonymizer active — using external LLM",
                    session_token=session_token,
                    llm_route=llm_route.value,
                )
            except AnonymizerUnavailableError:
                # SECURITY FALLBACK: stay on internal LLM
                llm_route = LLMRoute.INTERNAL_FALLBACK
                logger.warning(
                    "SECURITY FALLBACK: anonymizer unavailable. "
                    "Using internal LLM. No data sent externally.",
                )

        context = "\n\n---\n\n".join(context_texts)

        # ─── Step 4: Search-only mode ───
```

E alla fine del metodo, **PRIMA** della return finale (riga 280):
```python
        # ─── Step 5.5: De-anonymize response (if session active) ───
        if session_token and generation_result:
            generation_result = GenerationResult(
                text=await _deanonymize_text(
                    generation_result.text, session_token
                ),
                model=generation_result.model,
                prompt_tokens=generation_result.prompt_tokens,
                completion_tokens=generation_result.completion_tokens,
                template_used=generation_result.template_used,
            )
```

#### 3.2.4 Modifica a `HybridRAGEngine._generate()`

Il metodo deve usare `active_generator` invece di `self.generator`. L'approccio più pulito è passare il generator come parametro:

```python
    async def _generate(
        self,
        rag_query: RAGQuery,
        context: str,
        generator: Generator | None = None,
    ) -> GenerationResult:
        """Generate LLM response based on the query mode."""
        template, variables = self._resolve_template(rag_query, context)
        gen = generator or self.generator
        return await gen.generate(
            template=template,
            variables=variables,
            temperature=rag_query.temperature,
        )
```

### 3.3 [backend/app/rag/engine.py](file:///media/marco/DATA2/progettiAi/tenderwriter/backend/app/rag/engine.py) — Modifica a [RAGResponse](file:///media/marco/DATA2/progettiAi/tenderwriter/backend/app/rag/engine.py#57-64)

Aggiungere campi per osservabilità:

```python
@dataclass
class RAGResponse:
    """Output from the RAG pipeline."""
    answer: str
    sources: list[dict]
    mode: QueryMode
    generation_result: GenerationResult | None = None
    llm_route: str = "internal"          # NEW
    anonymized: bool = False             # NEW
```

### 3.4 `backend/app/api/anonymizer_admin.py` — NUOVO

```python
"""TW Backend — Anonymizer Admin API

Proxies admin requests to the tw-anonymizer service.
Only accessible by admin users.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
import httpx
import structlog

from app.api.auth import get_current_user, UserResponse
from app.config import settings

logger = structlog.get_logger()
router = APIRouter()


def _require_admin(current_user: UserResponse):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return current_user


# ── Schemas ──

class AnonymizerConfigRequest(BaseModel):
    enabled: bool = True
    strategy: str = "redaction"
    min_confidence_score: float = Field(0.7, ge=0.0, le=1.0)
    session_ttl_seconds: int = Field(3600, ge=60, le=86400)
    entities: dict[str, bool] = Field(default_factory=dict)


class AnonymizerTestRequest(BaseModel):
    text: str
    language: str = "it"


# ── Routes ──

@router.get("/config")
async def get_anonymizer_config(
    current_user: UserResponse = Depends(get_current_user),
):
    """Read current anonymizer configuration."""
    _require_admin(current_user)
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{settings.anonymizer_url}/v1/config")
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Anonymizer service unreachable: {e}",
        )


@router.post("/config")
async def update_anonymizer_config(
    config: AnonymizerConfigRequest,
    current_user: UserResponse = Depends(get_current_user),
):
    """Update anonymizer configuration."""
    _require_admin(current_user)
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.post(
                f"{settings.anonymizer_url}/v1/config",
                json=config.model_dump(),
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Anonymizer service unreachable: {e}",
        )


@router.get("/stats")
async def get_anonymizer_stats(
    current_user: UserResponse = Depends(get_current_user),
):
    """Get anonymizer statistics."""
    _require_admin(current_user)
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{settings.anonymizer_url}/v1/stats")
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Anonymizer service unreachable: {e}",
        )


@router.post("/test")
async def test_anonymizer(
    body: AnonymizerTestRequest,
    current_user: UserResponse = Depends(get_current_user),
):
    """Preview: anonymize test text without saving session."""
    _require_admin(current_user)
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{settings.anonymizer_url}/v1/anonymize",
                json={
                    "chunks": [body.text],
                    "language": body.language,
                    "session_ttl": 60,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "original": body.text,
                "anonymized": data["anonymized_chunks"][0],
                "stats": data["stats"],
            }
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Anonymizer test failed: {e}",
        )
```

### 3.5 [backend/app/main.py](file:///media/marco/DATA2/progettiAi/tenderwriter/backend/app/main.py) — Registrazione router

Aggiungere:

```python
from app.api import anonymizer_admin

# In register_routes():
app.include_router(
    anonymizer_admin.router,
    prefix="/api/anonymizer",
    tags=["Anonymizer"],
)
```

---

## 4. Modifiche alla Configurazione

### 4.1 [.env](file:///media/marco/DATA2/progettiAi/tenderwriter/.env) — Nuove variabili

```env
# --- Anonymizer ---
ANONYMIZER_ENABLED=false
ANONYMIZER_URL=http://tw-anonymizer:8090
ANONYMIZER_TIMEOUT=8

# --- External LLM (only used when anonymizer is ON) ---
EXTERNAL_LLM_URL=
EXTERNAL_LLM_MODEL=
```

### 4.2 [docker-compose.yml](file:///media/marco/DATA2/progettiAi/tenderwriter/docker-compose.yml) — Aggiornamento servizio `anonymizer`

```yaml
  # --- Anonymizer (PII Privacy Gateway) ---
  anonymizer:
    build:
      context: ./anonymizer
      dockerfile: Dockerfile
    container_name: tw-anonymizer
    restart: unless-stopped
    environment:
      ANONYMIZER_REDIS_URL: redis://tw-redis:6379/1
      ANONYMIZER_NER_BACKEND: ${ANONYMIZER_NER_BACKEND:-piiranha}
      ANONYMIZER_LOG_LEVEL: ${LOG_LEVEL:-INFO}
    depends_on:
      redis:
        condition: service_healthy
    ports:
      - "8090:8090"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8090/health"]
      interval: 10s
      timeout: 5s
      retries: 3
```

Aggiungere al servizio `backend`:
```yaml
    environment:
      # ... existing vars ...
      ANONYMIZER_URL: ${ANONYMIZER_URL:-http://tw-anonymizer:8090}
      ANONYMIZER_ENABLED: ${ANONYMIZER_ENABLED:-false}
      ANONYMIZER_TIMEOUT: ${ANONYMIZER_TIMEOUT:-8}
      EXTERNAL_LLM_URL: ${EXTERNAL_LLM_URL:-}
      EXTERNAL_LLM_MODEL: ${EXTERNAL_LLM_MODEL:-}
```

---

## 5. Frontend — Admin UI

### 5.1 [frontend/src/api/client.ts](file:///media/marco/DATA2/progettiAi/tenderwriter/frontend/src/api/client.ts) — Nuove API

```typescript
// ── Anonymizer Admin ──

export const anonymizerApi = {
    getConfig: () => request<any>('/anonymizer/config'),
    updateConfig: (data: AnonymizerConfig) =>
        request<any>('/anonymizer/config', { method: 'POST', body: data }),
    getStats: () => request<any>('/anonymizer/stats'),
    test: (data: { text: string; language?: string }) =>
        request<any>('/anonymizer/test', { method: 'POST', body: data }),
};

export interface AnonymizerConfig {
    enabled: boolean;
    strategy: 'redaction' | 'faking';
    min_confidence_score: number;
    session_ttl_seconds: number;
    entities: Record<string, boolean>;
}
```

### 5.2 Card Anonymizer in [Settings.tsx](file:///media/marco/DATA2/progettiAi/tenderwriter/frontend/src/pages/Settings.tsx)

Aggiungere una nuova card nella pagina Settings con:

- **Toggle ON/OFF** per `enabled`
- **Strategia** selector (redaction/faking)
- **Slider confidenza** (0.0 → 1.0, default 0.7)
- **TTL sessione** input numerico (default 3600s)
- **Checkboxes entità**: CF, PIVA, IBAN, CIG, PERSONA, ORG, EMAIL, TELEFONO, LUOGO, DATA, URL
- **Statistiche**: chunks processati, entità oscurate, sessioni attive
- **Area test**: textarea + bottone "Test Anonimizzazione" + risultato preview

---

## 6. Categorie PII Supportate

| Categoria | Recognizer | Label Placeholder | Default |
|---|---|---|---|
| Codice Fiscale | Regex custom | `[CF_1]` | ✅ ON |
| Partita IVA | Regex custom | `[PIVA_1]` | ✅ ON |
| IBAN | Regex custom | `[IBAN_1]` | ✅ ON |
| CIG (Codice Gara) | Regex custom + contesto | `[CIG_1]` | ✅ ON |
| Persone | pii-rahna / spaCy NER | `[PERSONA_1]` | ✅ ON |
| Organizzazioni | pii-rahna / spaCy NER | `[ORG_1]` | ✅ ON |
| Email | Presidio built-in | `[EMAIL_1]` | ✅ ON |
| Telefono | Presidio built-in | `[TELEFONO_1]` | ✅ ON |
| Luoghi | pii-rahna / spaCy NER | `[LUOGO_1]` | ❌ OFF |
| Date | pii-rahna NER | `[DATA_1]` | ❌ OFF |
| URL | Presidio built-in | `[URL_1]` | ❌ OFF |

---

## 7. Dipendenze e Rischi

### Dipendenze

| Dipendenza | Tipo | Azione |
|---|---|---|
| `pii-rahna` | Modello HuggingFace | Verificare licenza Apache 2.0 per uso commerciale |
| `presidio-analyzer` | Libreria Python | Aggiungere a [anonymizer/requirements.txt](file:///media/marco/DATA2/progettiAi/tenderwriter/anonymizer/requirements.txt) |
| `presidio-anonymizer` | Libreria Python | Aggiungere a [anonymizer/requirements.txt](file:///media/marco/DATA2/progettiAi/tenderwriter/anonymizer/requirements.txt) |
| `torch` CPU-only | Libreria Python | Build più pesante per container |
| `redis` DB 1 | Infrastruttura | Già nello stack, usare DB 1 (separato da Celery su DB 0) |

### Rischi

| Rischio | Prob. | Impatto | Mitigazione |
|---|---|---|---|
| pii-rahna non disponibile su HuggingFace | Bassa | Alto | Fallback automatico su spaCy |
| False negative (PII non rilevata) | Media | Alto | Regex strutturati sempre attivi, audit periodico |
| False positive (testo utile mascherato) | Media | Medio | Soglia configurabile, entity toggle per admin |
| Latenza anonymizer > 500ms | Media | Medio | Batch processing, timeout stretto (8s) |
| Docker image size aumenta (~2GB per modelli) | Alta | Basso | Multi-stage build, pre-download a build time |

---

## 8. Ordine di Implementazione

### Sprint 1: Foundation (Core Anonymizer Service)
1. `anonymizer/config.py`
2. `anonymizer/recognizers/__init__.py` + `italian.py`
3. `anonymizer/strategies.py`
4. `anonymizer/vault.py`
5. `anonymizer/engine.py`
6. [anonymizer/app.py](file:///media/marco/DATA2/progettiAi/tenderwriter/anonymizer/app.py) (evoluzione)
7. [anonymizer/requirements.txt](file:///media/marco/DATA2/progettiAi/tenderwriter/anonymizer/requirements.txt) aggiornato
8. [anonymizer/Dockerfile](file:///media/marco/DATA2/progettiAi/tenderwriter/anonymizer/Dockerfile) aggiornato
9. Test unitari su recognizer italiani
10. Test di integrazione endpoint `/v1/anonymize`

### Sprint 2: Backend Integration
1. [backend/app/config.py](file:///media/marco/DATA2/progettiAi/tenderwriter/backend/app/config.py) — nuove variabili
2. [backend/app/rag/engine.py](file:///media/marco/DATA2/progettiAi/tenderwriter/backend/app/rag/engine.py) — `_anonymize_chunks()`, `_deanonymize_text()`, modifica [query()](file:///media/marco/DATA2/progettiAi/tenderwriter/backend/app/rag/engine.py#140-286)
3. `backend/app/api/anonymizer_admin.py` — nuovo router admin
4. [backend/app/main.py](file:///media/marco/DATA2/progettiAi/tenderwriter/backend/app/main.py) — registrazione router
5. [.env](file:///media/marco/DATA2/progettiAi/tenderwriter/.env) aggiornamenti
6. [docker-compose.yml](file:///media/marco/DATA2/progettiAi/tenderwriter/docker-compose.yml) aggiornamenti
7. Test end-to-end: RAG query → anonymizer → LLM → deanonymize

### Sprint 3: Admin UI + Hardening
1. [frontend/src/api/client.ts](file:///media/marco/DATA2/progettiAi/tenderwriter/frontend/src/api/client.ts) — `anonymizerApi`
2. Card Anonymizer in [Settings.tsx](file:///media/marco/DATA2/progettiAi/tenderwriter/frontend/src/pages/Settings.tsx)
3. Area test anonimizzazione
4. Badge `internal_fallback` nel TenderChat
5. Test di carico (N chunk, target <200ms p95)
6. Documentazione `anonymizer/README.md`

---

## 9. Nota sulla [query_stream()](file:///media/marco/DATA2/progettiAi/tenderwriter/backend/app/rag/engine.py#287-314)

Il metodo [query_stream()](file:///media/marco/DATA2/progettiAi/tenderwriter/backend/app/rag/engine.py#287-314) in [engine.py](file:///media/marco/DATA2/progettiAi/tenderwriter/backend/app/rag/engine.py) (riga 287-313) NON è coperto da questa specifica iniziale. Per lo streaming:
- L'anonimizzazione dei chunk avviene PRIMA della generazione (OK, same flow)
- La de-anonimizzazione dello stream token-by-token è COMPLESSA (i placeholder arrivano frammentati)
- **Decisione**: Sprint 3+ — accumulare lo stream in un buffer, de-anonimizzare alla fine, poi restituire

---

*Specifica generata dall'analisi di 3 proposte (ChatGPT, Gemini, Claude) + analisi diretta del codebase TenderWriter — Marzo 2026*
