ok adesso concentriamoci sul componente tw-anonymizer attualmente non fa nulla mi occorre pianificare una evoluzione. Questo componente dovrà se attivato tramite interfaccia admin nella sezione anonymizer (una pagina dedicata) attivare una sandbox in cui i valori chunk prelevati dal RAG per essere usati da un LLM esterni dovranno passare da un procedura di anonimizzazione ed esempio nomi di società oppure codice fiscale piva o altri dati sensibili devono essere oscurati.

Ho tutto il contesto necessario. Il gateway test rivela già il pattern corretto: `via_anonymizer: True` è già previsto nell'infrastruttura. Ora ecco il piano di evoluzione completo.​

---

# Piano di Evoluzione: `tw-anonymizer`

## Visione Architetturale

Il componente passa da **transparent forwarder** a **PII Sanitization Sandbox** che si interpone nel flusso RAG → LLM esterno. Il flusso diventa:

text

`RAG chunks  →  [backend: generator.py]                      ↓ (se anonymizer attivo)              [tw-anonymizer: /anonymize]                     ↓ anonymized chunks + session_token              [LLM esterno via gateway]                     ↓ response con placeholder              [tw-anonymizer: /deanonymize]  ← opzionale                     ↓ testo ripristinato              [backend: risposta utente]`

Il session token è la chiave della reverse mapping: la mappa `placeholder ↔ valore_originale` vive in Redis con TTL configurabile, mai persiste su DB.​

---

## Stack Tecnologico Scelto

|Layer|Tecnologia|Motivazione|
|---|---|---|
|NER + PII engine|**Microsoft Presidio** (`presidio-analyzer` + `presidio-anonymizer`)|Supporto nativo italiano, customizable recognizers, operato local/offline|
|NLP model|**spaCy `it_core_news_lg`**|Modello italiano per ORG, PER, LOC entity recognition|
|Strutturati IT|**Regex custom**|Codice Fiscale, P.IVA, IBAN — pattern deterministici, no ML needed|
|Reverse mapping|**Redis con TTL**|Ephemeral, mai su disco, TTL = durata sessione LLM|
|Admin API|**FastAPI** (già presente)|Nuovi endpoint sullo stesso servizio|
|Admin UI|**React + Tailwind** (pattern esistente)|Nuova pagina `/admin/anonymizer`|

---

## Fase 1 — Anonymizer Service (Backend)

## 1.1 Nuovi Recognizer Italiani

**`anonymizer/recognizers/italian.py`** — riconoscitori regex per entità strutturate italiane:

python

`""" TenderWriter Anonymizer — Italian PII Recognizers Regex-based recognizers for Italian structured identifiers. """ from presidio_analyzer import Pattern, PatternRecognizer class CodiceFiscaleRecognizer(PatternRecognizer):     """    Riconosce Codici Fiscali italiani.    Formato: 6 lettere + 2 cifre + 1 lettera + 2 cifre + 1 lettera + 3 cifre + 1 lettera    Es: RSSMRA85M01H501Z    """    PATTERNS = [        Pattern(            "CODICE_FISCALE_STRONG",            r"\b[A-Z]{6}[0-9]{2}[A-EHLMPRST]{1}[0-9]{2}[A-Z]{1}[0-9]{3}[A-Z]{1}\b",            score=0.95,        )    ]    CONTEXT = ["codice fiscale", "cf", "c.f.", "fiscal code"]     def __init__(self):        super().__init__(            supported_entity="IT_CODICE_FISCALE",            patterns=self.PATTERNS,            context=self.CONTEXT,        ) class PartitaIvaRecognizer(PatternRecognizer):     """    Riconosce Partite IVA italiane.    Formato: 11 cifre, opzionalmente prefissate da IT    Es: IT12345678901 oppure 12345678901    """    PATTERNS = [        Pattern(            "PIVA_WITH_PREFIX",            r"\bIT[0-9]{11}\b",            score=0.98,        ),        Pattern(            "PIVA_STANDALONE",            r"(?i)(?:p\.?\s*iva|partita\s+iva)\s*[:\-]?\s*([0-9]{11})\b",            score=0.90,        ),    ]    CONTEXT = ["partita iva", "p.iva", "piva", "vat number", "codice iva"]     def __init__(self):        super().__init__(            supported_entity="IT_PARTITA_IVA",            patterns=self.PATTERNS,            context=self.CONTEXT,        ) class IBANRecognizer(PatternRecognizer):     """    Riconosce IBAN italiani.    Formato: IT + 2 check digits + 1 lettera + 22 caratteri alfanumerici    Es: IT60X0542811101000000123456    """    PATTERNS = [        Pattern(            "IBAN_IT",            r"\bIT[0-9]{2}[A-Z][0-9]{10}[0-9A-Z]{12}\b",            score=0.97,        ),    ]    CONTEXT = ["iban", "conto corrente", "bonifico", "coordinate bancarie"]     def __init__(self):        super().__init__(            supported_entity="IT_IBAN",            patterns=self.PATTERNS,            context=self.CONTEXT,        ) class NumeroCivicoIndirizzoRecognizer(PatternRecognizer):     """    Riconosce pattern di indirizzi italiani.    Es: Via Roma 15, Piazza Garibaldi 3/A    """    PATTERNS = [        Pattern(            "INDIRIZZO_IT",            r"\b(?:via|viale|corso|piazza|largo|vicolo|strada|contrada|loc\.|localit[àa])\s+[A-Za-zÀ-ÿ\s\.\']{3,40}\s*,?\s*\d{1,5}[\/A-Za-z]{0,3}\b",            score=0.75,        ),    ]    CONTEXT = ["indirizzo", "sede legale", "sede operativa", "domicilio"]     def __init__(self):        super().__init__(            supported_entity="IT_ADDRESS",            patterns=self.PATTERNS,            context=self.CONTEXT,        )`

---

## 1.2 Core Anonymizer Engine

**`anonymizer/engine.py`** — motore principale con Presidio + reverse mapping Redis:

python

`""" TenderWriter Anonymizer — Core Engine Detects and replaces PII entities in text chunks using Presidio with Italian-specific recognizers. Maintains ephemeral reverse mapping in Redis for optional de-anonymization. """ from __future__ import annotations import hashlib import json import uuid from dataclasses import dataclass, field from typing import Callable import structlog logger = structlog.get_logger() # Entity types da anonimizzare, con il loro label nel testo sostitutivo ENTITY_LABELS: dict[str, str] = {     "IT_CODICE_FISCALE": "CF",    "IT_PARTITA_IVA": "PIVA",    "IT_IBAN": "IBAN",    "IT_ADDRESS": "INDIRIZZO",    "PERSON": "PERSONA",    "ORG": "ORGANIZZAZIONE",    "EMAIL_ADDRESS": "EMAIL",    "PHONE_NUMBER": "TELEFONO",    "URL": "URL",    "DATE_TIME": "DATA",       # opzionale — configurabile    "LOCATION": "LUOGO", } @dataclass class AnonymizedChunk:     original_text: str    anonymized_text: str    entities_found: list[dict]   # [{entity_type, start, end, score, placeholder}]    mapping: dict[str, str]      # {placeholder: original_value} @dataclass class AnonymizationSession:     session_token: str    reverse_map: dict[str, str]  # {placeholder: original_value}    chunks_count: int = 0    entities_count: int = 0 class AnonymizerEngine:     """    Orchestratore principale dell'anonimizzazione.         Pipeline:      1. Presidio AnalyzerEngine (NER + regex) → lista RecognizerResult      2. Presidio AnonymizerEngine → testo con placeholder      3. Reverse mapping → Redis con TTL    """     def __init__(self, config: dict):        self.config = config        self._analyzer = None        self._anonymizer = None        self._redis = None     def _build_analyzer(self):        """Lazy-init Presidio AnalyzerEngine con recognizer italiani."""        from presidio_analyzer import AnalyzerEngine, RecognizerRegistry        from presidio_analyzer.nlp_engine import NlpEngineProvider         from anonymizer.recognizers.italian import (            CodiceFiscaleRecognizer,            IBANRecognizer,            NumeroCivicoIndirizzoRecognizer,            PartitaIvaRecognizer,        )         # Configura spaCy con modello italiano        provider = NlpEngineProvider(nlp_configuration={            "nlp_engine_name": "spacy",            "models": [{"lang_code": "it", "model_name": "it_core_news_lg"}],        })        nlp_engine = provider.create_engine()         registry = RecognizerRegistry()        registry.load_predefined_recognizers(nlp_engine=nlp_engine)         # Aggiungi recognizer italiani custom        registry.add_recognizer(CodiceFiscaleRecognizer())        registry.add_recognizer(PartitaIvaRecognizer())        registry.add_recognizer(IBANRecognizer())         if self.config.get("anonymize_addresses", True):            registry.add_recognizer(NumeroCivicoIndirizzoRecognizer())         return AnalyzerEngine(            nlp_engine=nlp_engine,            registry=registry,            supported_languages=["it", "en"],        )     def _build_anonymizer(self):        from presidio_anonymizer import AnonymizerEngine as PresidioAnonymizer        return PresidioAnonymizer()     @property    def analyzer(self):        if self._analyzer is None:            self._analyzer = self._build_analyzer()        return self._analyzer     @property    def anonymizer(self):        if self._anonymizer is None:            self._anonymizer = self._build_anonymizer()        return self._anonymizer     def _get_active_entities(self) -> list[str]:        """Ritorna solo le entità abilitate dalla config admin."""        active = []        entity_config = self.config.get("entities", {})        for entity_type, label in ENTITY_LABELS.items():            # Default: tutte abilitate; l'admin può disabilitarne singole            if entity_config.get(entity_type, True):                active.append(entity_type)        return active     def anonymize_text(        self,        text: str,        language: str = "it",        session_map: dict[str, str] | None = None,    ) -> AnonymizedChunk:        """        Anonimizza un singolo testo.                 Returns AnonymizedChunk con testo anonimizzato e mapping locale.        Il caller è responsabile di aggregare i mapping nella sessione Redis.        """        from presidio_anonymizer.entities import OperatorConfig         session_map = session_map or {}        active_entities = self._get_active_entities()        min_score = self.config.get("min_confidence_score", 0.7)         # Step 1: analisi NER        results = self.analyzer.analyze(            text=text,            language=language,            entities=active_entities,            score_threshold=min_score,        )         if not results:            return AnonymizedChunk(                original_text=text,                anonymized_text=text,                entities_found=[],                mapping={},            )         # Step 2: costruisci operator config con placeholder deterministici        # Il placeholder è stabile: stesso valore originale → stesso placeholder        # Questo evita che la stessa azienda abbia placeholder diversi nello stesso doc.        chunk_mapping: dict[str, str] = {}        placeholder_counter: dict[str, int] = {}        operators: dict[str, OperatorConfig] = {}         def make_placeholder(entity_type: str, original_value: str) -> str:            label = ENTITY_LABELS.get(entity_type, entity_type)            # Controlla se questo valore è già stato visto nella sessione o nel chunk            combined_map = {**session_map, **chunk_mapping}            for placeholder, orig in combined_map.items():                if orig == original_value:                    return placeholder            # Nuovo valore: assegna progressivo            count = placeholder_counter.get(label, 0) + 1            placeholder_counter[label] = count            return f"[{label}_{count}]"         # Custom lambda operator per Presidio        def custom_operator(entity_type: str) -> OperatorConfig:            return OperatorConfig(                "custom",                {"lambda": lambda x: make_placeholder(entity_type, x)},            )         for entity_type in set(r.entity_type for r in results):            operators[entity_type] = custom_operator(entity_type)         # Step 3: anonimizza        anonymized = self.anonymizer.anonymize(            text=text,            analyzer_results=results,            operators=operators,        )         # Step 4: ricostruisci mapping placeholder→originale        # Estraiamo i valori originali dai risultati dell'analyzer        local_mapping: dict[str, str] = {}        for result in results:            original_value = text[result.start:result.end]            label = ENTITY_LABELS.get(result.entity_type, result.entity_type)            # Trova il placeholder corrispondente nella session            placeholder = make_placeholder(result.entity_type, original_value)            local_mapping[placeholder] = original_value         entities_found = [            {                "entity_type": r.entity_type,                "start": r.start,                "end": r.end,                "score": round(r.score, 3),                "original_value": text[r.start:r.end],            }            for r in results        ]         logger.debug(            "Text anonymized",            entities_count=len(results),            text_len=len(text),        )         return AnonymizedChunk(            original_text=text,            anonymized_text=anonymized.text,            entities_found=entities_found,            mapping=local_mapping,        )     def deanonymize_text(self, text: str, reverse_map: dict[str, str]) -> str:        """        Ripristina il testo originale dai placeholder.        Sostituisce ogni [LABEL_N] con il valore originale.        """        result = text        # Ordina per lunghezza decrescente per evitare sostituzioni parziali        for placeholder, original in sorted(            reverse_map.items(), key=lambda x: len(x[0]), reverse=True        ):            result = result.replace(placeholder, original)        return result`

---

## 1.3 API Endpoints Aggiornati

**`anonymizer/app.py`** — versione completa sostituisce il forwarder:

python

`""" TenderWriter — tw-anonymizer Service Servizio di anonimizzazione PII per chunk RAG destinati a LLM esterni. Espone endpoint per:   - /anonymize   : anonimizza lista di chunk, ritorna session_token  - /deanonymize : ripristina testo da session_token  - /config      : lettura/scrittura configurazione (solo admin interno)  - /health      : health check  - /stats       : statistiche ultime N anonimizzazioni  - /{path:path} : transparent forwarder (backward compat per gateway) """ from __future__ import annotations import json import uuid from datetime import datetime, timezone from typing import Any import httpx import redis.asyncio as aioredis import structlog from fastapi import FastAPI, HTTPException, Request, Response from fastapi.middleware.cors import CORSMiddleware from pydantic import BaseModel, Field from anonymizer.config import settings from anonymizer.engine import AnonymizerEngine logger = structlog.get_logger() app = FastAPI(     title="tw-anonymizer",    version="1.0.0",    docs_url="/docs",         # visibile solo internamente    redoc_url=None, ) app.add_middleware(     CORSMiddleware,    allow_origins=["http://tw-backend:8000"],    allow_methods=["POST", "GET"],    allow_headers=["*"], ) # --- Singleton engine (lazy init al primo utilizzo) --- _engine: AnonymizerEngine | None = None _redis: aioredis.Redis | None = None async def get_engine() -> AnonymizerEngine:     global _engine    if _engine is None:        config = await _load_config_from_redis()        _engine = AnonymizerEngine(config)    return _engine async def get_redis() -> aioredis.Redis:     global _redis    if _redis is None:        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)    return _redis async def _load_config_from_redis() -> dict:     """Carica la config admin da Redis (set dal backend admin API)."""    try:        r = await get_redis()        raw = await r.get("anonymizer:config")        if raw:            return json.loads(raw)    except Exception:        pass    return settings.default_config # ─── Schemas ───────────────────────────────────────────────────────────────── class AnonymizeRequest(BaseModel):     chunks: list[str] = Field(..., description="Lista di testi da anonimizzare")    language: str = Field("it", description="Lingua dei testi (it/en)")    session_ttl: int = Field(3600, description="TTL sessione Redis in secondi") class AnonymizeResponse(BaseModel):     session_token: str    anonymized_chunks: list[str]    stats: dict[str, Any] class DeanonymizeRequest(BaseModel):     session_token: str    texts: list[str] = Field(..., description="Testi con placeholder da ripristinare") class DeanonymizeResponse(BaseModel):     restored_texts: list[str] class ConfigUpdateRequest(BaseModel):     enabled: bool = True    min_confidence_score: float = Field(0.7, ge=0.0, le=1.0)    anonymize_addresses: bool = True    session_ttl_seconds: int = Field(3600, ge=60, le=86400)    entities: dict[str, bool] = Field(        default_factory=lambda: {            "IT_CODICE_FISCALE": True,            "IT_PARTITA_IVA": True,            "IT_IBAN": True,            "IT_ADDRESS": True,            "PERSON": True,            "ORG": True,            "EMAIL_ADDRESS": True,            "PHONE_NUMBER": True,            "URL": False,            "DATE_TIME": False,            "LOCATION": False,        }    ) # ─── Endpoints ─────────────────────────────────────────────────────────────── @app.get("/health") async def health():     r = await get_redis()    redis_ok = await r.ping()    return {        "status": "ok",        "redis": "connected" if redis_ok else "error",        "engine": "loaded" if _engine is not None else "lazy",        "timestamp": datetime.now(timezone.utc).isoformat(),    } @app.post("/anonymize", response_model=AnonymizeResponse) async def anonymize_chunks(request: AnonymizeRequest):     """    Riceve una lista di chunk testuali, anonimizza le entità PII,    salva la reverse mapping in Redis con TTL e ritorna:      - i chunk anonimizzati      - un session_token per eventuale de-anonimizzazione    """    engine = await get_engine()    r = await get_redis()     session_token = str(uuid.uuid4())    session_reverse_map: dict[str, str] = {}     anonymized_chunks: list[str] = []    total_entities = 0     for chunk_text in request.chunks:        result = engine.anonymize_text(            text=chunk_text,            language=request.language,            session_map=session_reverse_map,        )        anonymized_chunks.append(result.anonymized_text)        session_reverse_map.update(result.mapping)        total_entities += len(result.entities_found)     # Salva reverse mapping in Redis con TTL    redis_key = f"anonymizer:session:{session_token}"    await r.setex(        redis_key,        request.session_ttl,        json.dumps(session_reverse_map),    )     # Aggiorna statistiche    await _update_stats(r, total_entities, len(request.chunks))     logger.info(        "Anonymization complete",        session=session_token,        chunks=len(request.chunks),        entities=total_entities,    )     return AnonymizeResponse(        session_token=session_token,        anonymized_chunks=anonymized_chunks,        stats={            "chunks_processed": len(request.chunks),            "entities_found": total_entities,            "session_ttl": request.session_ttl,        },    ) @app.post("/deanonymize", response_model=DeanonymizeResponse) async def deanonymize_texts(request: DeanonymizeRequest):     """    Ripristina i placeholder nei testi usando la reverse mapping    della sessione Redis identificata da session_token.    La sessione viene mantenuta fino a TTL naturale (non consumata).    """    r = await get_redis()    redis_key = f"anonymizer:session:{request.session_token}"    raw = await r.get(redis_key)     if not raw:        raise HTTPException(            status_code=404,            detail="Session token not found or expired.",        )     reverse_map: dict[str, str] = json.loads(raw)    engine = await get_engine()     restored = [        engine.deanonymize_text(text, reverse_map)        for text in request.texts    ]     return DeanonymizeResponse(restored_texts=restored) @app.get("/config") async def get_config():     """Ritorna la configurazione attuale dell'anonymizer."""    r = await get_redis()    raw = await r.get("anonymizer:config")    if raw:        return json.loads(raw)    return settings.default_config @app.post("/config") async def update_config(config: ConfigUpdateRequest):     """    Aggiorna la configurazione dell'anonymizer.    Chiamato dal backend admin API — non esposto direttamente al frontend.    Resetta il singleton engine per forzare reload con nuova config.    """    global _engine    r = await get_redis()    config_dict = config.model_dump()    await r.set("anonymizer:config", json.dumps(config_dict))     # Reset engine per reload con nuova config    _engine = None     logger.info("Anonymizer config updated", config=config_dict)    return {"status": "updated", "config": config_dict} @app.get("/stats") async def get_stats():     """Statistiche aggregate delle ultime anonimizzazioni."""    r = await get_redis()    raw = await r.get("anonymizer:stats")    if raw:        return json.loads(raw)    return {"total_chunks": 0, "total_entities": 0, "sessions": 0} async def _update_stats(r: aioredis.Redis, entities: int, chunks: int):     raw = await r.get("anonymizer:stats")    stats = json.loads(raw) if raw else {"total_chunks": 0, "total_entities": 0, "sessions": 0}    stats["total_chunks"] += chunks    stats["total_entities"] += entities    stats["sessions"] += 1    stats["last_activity"] = datetime.now(timezone.utc).isoformat()    await r.set("anonymizer:stats", json.dumps(stats)) # ─── Transparent Forwarder (backward compat) ───────────────────────────────── @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"]) async def forward(path: str, request: Request) -> Response:     """Transparent forwarder: usato dal gateway per proxying verso LLM DMZ."""    target_url = request.headers.get("x-target-url")    if not target_url:        return Response(content=b"missing x-target-url header", status_code=400)     body = await request.body()    headers = {k: v for k, v in request.headers.items() if k.lower() != "x-target-url"}     async with httpx.AsyncClient(timeout=30) as client:        upstream_resp = await client.request(            request.method,            target_url,            params=request.query_params,            content=body,            headers=headers,        )     return Response(        content=upstream_resp.content,        status_code=upstream_resp.status_code,        headers={            k: v for k, v in upstream_resp.headers.items()            if k.lower() in {"content-type", "content-length"}        },    )`

---

## 1.4 Config e Requirements Aggiornati

**`anonymizer/config.py`** — nuova:

python

`from pydantic_settings import BaseSettings class AnonymizerSettings(BaseSettings):     redis_url: str = "redis://tw-redis:6379/0"    service_token: str = "changeme_anonymizer_token"     default_config: dict = {        "enabled": False,          # off di default, attivato da admin        "min_confidence_score": 0.7,        "anonymize_addresses": True,        "session_ttl_seconds": 3600,        "entities": {            "IT_CODICE_FISCALE": True,            "IT_PARTITA_IVA": True,            "IT_IBAN": True,            "IT_ADDRESS": True,            "PERSON": True,            "ORG": True,            "EMAIL_ADDRESS": True,            "PHONE_NUMBER": True,            "URL": False,            "DATE_TIME": False,            "LOCATION": False,        },    }     class Config:        env_prefix = "ANONYMIZER_" settings = AnonymizerSettings()`

**`anonymizer/requirements.txt`** — aggiornato:

text

`fastapi==0.111.0 uvicorn==0.29.0 httpx==0.27.0 redis[asyncio]==5.0.3 presidio-analyzer==2.2.354 presidio-anonymizer==2.2.354 spacy==3.7.4 structlog==24.1.0 pydantic-settings==2.2.1 # Modello spaCy italiano — installato nel Dockerfile # python -m spacy download it_core_news_lg`

**`anonymizer/Dockerfile`** — aggiornato:

text

`FROM python:3.11-slim ENV PYTHONUNBUFFERED=1 WORKDIR /app RUN apt-get update && apt-get install -y --no-install-recommends \     build-essential gcc \    && rm -rf /var/lib/apt/lists/* COPY requirements.txt . RUN pip install --no-cache-dir -r requirements.txt # Download modello spaCy italiano RUN python -m spacy download it_core_news_lg COPY . /app CMD ["python", "-m", "run"]`

---

## Fase 2 — Integrazione Backend (RAG Generator)

Il punto di intercettazione corretto è **`rag/generator.py`**, prima di inviare i chunk all'LLM esterno.

**`backend/app/rag/generator.py`** — aggiunta del metodo `_anonymize_context`:

python

`# In cima al file — aggiungi import import httpx from app.config import settings # Nel metodo generate() — aggiungi prima di assemblare il prompt async def _anonymize_context(     self,    chunks: list[str], ) -> tuple[list[str], str | None]:     """    Se l'anonymizer è abilitato nelle settings, invia i chunk    al servizio tw-anonymizer e ritorna i chunk anonimizzati    + session_token per eventuale de-anonimizzazione.         Returns (original_chunks, None) se anonymizer è disabilitato o non raggiungibile.    """    if not settings.anonymizer_enabled:        return chunks, None     try:        async with httpx.AsyncClient(timeout=10) as client:            resp = await client.post(                f"{settings.anonymizer_url}/anonymize",                json={                    "chunks": chunks,                    "language": "it",                    "session_ttl": 3600,                },            )            resp.raise_for_status()            data = resp.json()            return data["anonymized_chunks"], data["session_token"]     except Exception as e:        logger.warning(            "Anonymizer not reachable — using original chunks",            error=str(e),        )        return chunks, None  # fallback graceful: procede senza anonimizzazione`

Nella logica di `generate()`, dopo aver ottenuto i chunk reranked:

python

`# Prima di costruire il prompt context_texts = [r.text for r in reranked_results] context_texts, session_token = await self._anonymize_context(context_texts) # ... assembla prompt con context_texts anonimizzati # ... chiama LLM # opzionale: de-anonimizza risposta se session_token is not None`

---

## Fase 3 — Backend Admin API

**`backend/app/api/admin.py`** — aggiunta router `/anonymizer`:

python

`# Nuovi endpoint da aggiungere al router admin esistente @router.get("/anonymizer/config") async def get_anonymizer_config(current_user: UserResponse = Depends(require_admin)):     """Legge la config corrente dell'anonymizer service."""    async with httpx.AsyncClient(timeout=5) as client:        resp = await client.get(f"{settings.anonymizer_url}/config")        return resp.json() @router.post("/anonymizer/config") async def update_anonymizer_config(     config: AnonymizerConfigRequest,    current_user: UserResponse = Depends(require_admin), ):     """Aggiorna la config e persiste anche su AppSettings DB per reload."""    async with httpx.AsyncClient(timeout=5) as client:        resp = await client.post(            f"{settings.anonymizer_url}/config",            json=config.model_dump(),        )        resp.raise_for_status()    # Persiste anche su DB per recovery al restart    async with get_async_session() as db:        await _save_anonymizer_config_to_db(db, config.model_dump())    return {"status": "ok"} @router.get("/anonymizer/stats") async def get_anonymizer_stats(current_user: UserResponse = Depends(require_admin)):     """Statistiche operative dell'anonymizer."""    async with httpx.AsyncClient(timeout=5) as client:        resp = await client.get(f"{settings.anonymizer_url}/stats")        return resp.json() @router.post("/anonymizer/test") async def test_anonymizer(     body: AnonymizerTestRequest,    current_user: UserResponse = Depends(require_admin), ):     """    Endpoint di preview: anonimizza un testo di test e mostra    le entità rilevate senza salvare la sessione.    """    async with httpx.AsyncClient(timeout=15) as client:        resp = await client.post(            f"{settings.anonymizer_url}/anonymize",            json={"chunks": [body.text], "language": body.language, "session_ttl": 60},        )        data = resp.json()    return {        "original": body.text,        "anonymized": data["anonymized_chunks"][0],        "stats": data["stats"],    }`

---

## Fase 4 — Frontend Admin Page

**`frontend/src/pages/AnonymizerAdmin.tsx`** — struttura della pagina:

text

`┌──────────────────────────────────────────────────┐ │  🛡️  Anonymizer Sandbox                          │ │  Protezione dati sensibili verso LLM esterni     │ ├─────────────────────────┬────────────────────────┤ │  STATO                  │  STATISTICHE           │ │  ● Attivo / ○ Inattivo  │  Chunk processati: 142 │ │  [Toggle ON/OFF]        │  Entità oscurate: 318  │ │                         │  Sessioni attive: 7    │ ├─────────────────────────┴────────────────────────┤ │  ENTITÀ DA RILEVARE                              │ │  ☑ Codice Fiscale    ☑ Partita IVA   ☑ IBAN     │ │  ☑ Nomi Persone      ☑ Organizzazioni ☑ Email   │ │  ☑ Telefoni          ☑ Indirizzi     ☐ Date     │ │  ☐ URL               ☐ Luoghi                   │ ├──────────────────────────────────────────────────┤ │  SOGLIA CONFIDENZA   [0.70] ◄───────────► 1.0   │ │  TTL SESSIONE        [3600] secondi              │ ├──────────────────────────────────────────────────┤ │  🔬 AREA TEST                                    │ │  ┌────────────────────────────────────────────┐ │ │  │ Inserisci testo da testare...              │ │ │  └────────────────────────────────────────────┘ │ │  [TEST ANONIMIZZAZIONE]                          │ │                                                  │ │  Risultato:                                      │ │  "La società [ORGANIZZAZIONE_1] con P.IVA        │ │   [PIVA_1] ha sede in [INDIRIZZO_1]..."          │ └──────────────────────────────────────────────────┘`

---

## Fase 5 — Docker Compose

Aggiornamento al `docker-compose.yml`:

text

`tw-anonymizer:   build: ./anonymizer  container_name: tw-anonymizer  environment:    - ANONYMIZER_REDIS_URL=redis://tw-redis:6379/0    - ANONYMIZER_SERVICE_TOKEN=${ANONYMIZER_SERVICE_TOKEN:-changeme}  depends_on:    - tw-redis  networks:    - tw-internal  # NON esposto all'esterno — solo interno al network Docker  expose:    - "8090"  healthcheck:    test: ["CMD", "curl", "-f", "http://localhost:8090/health"]    interval: 30s    timeout: 10s    retries: 3`

In `tw-backend`, aggiungi:

text

`environment:   - ANONYMIZER_URL=http://tw-anonymizer:8090  - ANONYMIZER_ENABLED=false   # default off, attivato dall'admin`

---

## Roadmap di Implementazione

|Sprint|Deliverable|Priorità|
|---|---|---|
|**Sprint 1**|Recognizer italiani + engine base (CF/PIVA/IBAN regex)|🔴 Alta|
|**Sprint 1**|Endpoint `/anonymize` + Redis session|🔴 Alta|
|**Sprint 2**|spaCy NER (ORG/PERSON) + `it_core_news_lg`|🟡 Media|
|**Sprint 2**|Integrazione `generator.py` con fallback graceful|🔴 Alta|
|**Sprint 2**|Admin API `/anonymizer/config`, `/stats`, `/test`|🟡 Media|
|**Sprint 3**|Frontend `AnonymizerAdmin.tsx` con toggle e area test|🟡 Media|
|**Sprint 3**|Endpoint `/deanonymize` + UI opzionale|🟢 Bassa|
|**Sprint 4**|Test suite con golden dataset italiano|🟢 Bassa|

> **Nota critica**: il fallback graceful in `_anonymize_context` è fondamentale — se l'anonymizer è down il sistema deve comunque funzionare, semplicemente senza anonimizzazione. Questo va loggato come warning osservabile nel sistema di monitoring esistente.

Preparato usando Claude Sonnet 4.6 Thinking

se l'opzione di anonimizzare è attivata, ma il servizio non funziona il fallback per l'uso di llm è l'uso interno di llm su llma.cpp del componente tw-llama-tender

Ho il quadro completo. Il `generator.py` già gestisce sia llama.cpp (`tw-llama-tender`) che Ollama/external tramite branch `if "v1" in self.base_url`. La logica di fallback va progettata in modo **security-first**: se non puoi garantire la protezione del dato, il dato non esce.​

---

## Principio di Design: Security-First Fallback

Il fallback non è un "continua comunque senza anonimizzazione" — quello sarebbe un **data leak silenzioso**. La semantica corretta è:

text

`anonymizer_enabled = True         │        ▼   anonymizer OK?   ┌────┴─────┐  SÌ         NO   │           │   ▼           ▼ External LLM  Internal LLM     ← dati NON escono mai (anonimizzato) (tw-llama-tender)                + WARNING log               + evento osservabilità`

---

## Modifiche Necessarie

## 1. `backend/app/config.py` — Nuove variabili

python

`# Aggiungi a Settings # LLM Routing llama_server_url: str = "http://tw-llama-tender:8080/v1"   # interno (già esiste) external_llm_url: str = ""           # LLM esterno (OpenAI-compat, es. gateway cloud) external_llm_model: str = "gpt-4o" # Anonymizer anonymizer_enabled: bool = False anonymizer_url: str = "http://tw-anonymizer:8090" anonymizer_timeout: float = 8.0      # timeout stretto — fallback rapido`

---

## 2. `backend/app/rag/generator.py` — Routing LLM con fallback

La classe `Generator` riceve un `base_url` al momento della costruzione. Il `HybridRAGEngine` decide **quale** `Generator` istanziare in base al risultato dell'anonimizzazione.

python

`""" TenderWriter — RAG Generator (con Anonymizer Sandbox + LLM Routing) """ from __future__ import annotations import asyncio from enum import Enum import httpx import structlog from app.config import settings logger = structlog.get_logger() class LLMRoute(str, Enum):     """Traccia quale LLM è stato usato — utile per osservabilità."""    INTERNAL = "internal"          # tw-llama-tender — dati locali    EXTERNAL = "external"          # LLM esterno — richiede anonimizzazione    INTERNAL_FALLBACK = "internal_fallback"  # fallback per anonymizer KO class AnonymizerUnavailableError(RuntimeError):     """    Sollevata quando l'anonymizer è abilitato ma non raggiungibile.    Segnala al caller che deve usare il LLM interno.    Non è un errore applicativo — è una decisione di routing sicura.    """    pass async def anonymize_chunks(     chunks: list[str],    language: str = "it", ) -> tuple[list[str], str]:     """    Invia i chunk al servizio tw-anonymizer.         Returns:        (anonymized_chunks, session_token)         Raises:        AnonymizerUnavailableError: se il servizio non risponde entro timeout                                    o ritorna un errore HTTP.    """    try:        async with httpx.AsyncClient(timeout=settings.anonymizer_timeout) as client:            resp = await client.post(                f"{settings.anonymizer_url}/anonymize",                json={                    "chunks": chunks,                    "language": language,                    "session_ttl": 3600,                },            )            resp.raise_for_status()            data = resp.json()            return data["anonymized_chunks"], data["session_token"]     except (httpx.ConnectError, httpx.TimeoutException) as exc:        logger.warning(            "Anonymizer unreachable — routing to internal LLM",            error=str(exc),            anonymizer_url=settings.anonymizer_url,        )        raise AnonymizerUnavailableError(            f"Anonymizer service unavailable: {exc}"        ) from exc     except httpx.HTTPStatusError as exc:        logger.warning(            "Anonymizer returned HTTP error — routing to internal LLM",            status=exc.response.status_code,            body=exc.response.text[:200],        )        raise AnonymizerUnavailableError(            f"Anonymizer HTTP {exc.response.status_code}"        ) from exc`

---

## 3. `backend/app/rag/engine.py` — LLM Routing nel metodo `query()`

Questo è il punto centrale. Il `HybridRAGEngine.query()` decide il routing **prima** di costruire il prompt e invocare il `Generator`.

python

`async def _resolve_generator_and_context(     self,    context_chunks: list[str], ) -> tuple[Generator, list[str], LLMRoute, str | None]:     """    Risolve quale Generator usare e se i chunk vanno anonimizzati.     Logica:      - anonymizer_enabled=False  → external LLM, chunks originali      - anonymizer_enabled=True, anonymizer OK → external LLM, chunks anonimizzati      - anonymizer_enabled=True, anonymizer KO → internal LLM, chunks originali                                                  (dati non escono mai)     Returns:        (generator, chunks_to_use, llm_route, session_token_or_None)    """    if not settings.anonymizer_enabled:        # Admin ha scelto consapevolmente di non anonimizzare        generator = Generator(            base_url=settings.external_llm_url or settings.llama_server_url,            model=settings.external_llm_model or settings.llama_model,        )        return generator, context_chunks, LLMRoute.EXTERNAL, None     # Anonymizer abilitato: tenta anonimizzazione    try:        anonymized_chunks, session_token = await anonymize_chunks(context_chunks)        generator = Generator(            base_url=settings.external_llm_url,            model=settings.external_llm_model,        )        logger.info(            "Anonymizer active — using external LLM with sanitized context",            session_token=session_token,        )        return generator, anonymized_chunks, LLMRoute.EXTERNAL, session_token     except AnonymizerUnavailableError as exc:        # ⚠️ FALLBACK DI SICUREZZA: anonymizer KO → internal LLM obbligatorio        logger.warning(            "SECURITY FALLBACK: anonymizer unavailable — "            "enforcing internal LLM (tw-llama-tender). "            "No data will be sent to external services.",            reason=str(exc),        )        # Emetti evento osservabilità (non bloccante)        await self._emit_anonymizer_fallback_event(reason=str(exc))         generator = Generator(            base_url=settings.llama_server_url,   # tw-llama-tender            model=settings.llama_model,        )        return generator, context_chunks, LLMRoute.INTERNAL_FALLBACK, None async def _emit_anonymizer_fallback_event(self, reason: str) -> None:     """    Emette un evento di osservabilità quando scatta il fallback.    Non-blocking: usa fire-and-forget con timeout stretto.    Questo evento è visibile nel SystemMonitor del frontend.    """    try:        async with httpx.AsyncClient(timeout=2.0) as client:            await client.post(                f"{settings.kpi_reason_engine_base_url}/v1/events/system",                json={                    "event_type": "anonymizer.fallback",                    "reason": reason,                    "severity": "warning",                    "message": (                        "Anonymizer service unavailable. "                        "Request routed to internal LLM for data safety."                    ),                },                headers={"X-Service-Token": settings.kpi_reason_engine_service_token},            )    except Exception:        pass  # non deve mai bloccare la generazione`

Nel metodo `query()` principale dell'engine, il codice diventa:

python

`async def query(self, query: str, ...) -> RAGResult:     # ... retrieval e reranking esistenti ...         context_chunks = [r.text for r in reranked_results]     # ← NUOVO: risolvi generator e contesto (con routing sicuro)    generator, context_to_use, llm_route, session_token = (        await self._resolve_generator_and_context(context_chunks)    )     # Genera risposta con il generator risolto    result = await generator.generate(        template="general_qa",        variables={"context": "\n\n".join(context_to_use), "query": query},    )     logger.info(        "RAG query complete",        llm_route=llm_route.value,        anonymized=(session_token is not None),        session_token=session_token,    )     return RAGResult(        answer=result.text,        sources=reranked_results,        llm_route=llm_route.value,        # ← nuovo campo per frontend        anonymized=(session_token is not None),    )`

---

## 4. `backend/app/api/rag.py` — Esponi `llm_route` nella response

python

`class RAGQueryResponse(BaseModel):     answer: str    sources: list[SourceReference]    llm_route: str                    # "internal" | "external" | "internal_fallback"    anonymized: bool = False    # ... campi esistenti`

---

## 5. Frontend — Badge di avviso nel TenderChat

Quando `llm_route === "internal_fallback"`, mostra un banner informativo nell'interfaccia:

tsx

`{response.llm_route === "internal_fallback" && (   <div className="flex items-center gap-2 px-3 py-2                  bg-amber-50 border border-amber-200                  rounded-lg text-amber-800 text-sm">    <ShieldAlert className="w-4 h-4 text-amber-500" />    <span>      Il servizio di anonimizzazione non è disponibile.      La risposta è stata generata dal <strong>modello interno</strong> per proteggere i dati.    </span>  </div> )}`

---

## Matrice Comportamentale Completa

|`anonymizer_enabled`|Anonymizer status|LLM usato|Chunks inviati|`llm_route`|
|---|---|---|---|---|
|`false`|—|External|Originali|`external`|
|`true`|🟢 Online|External|**Anonimizzati**|`external`|
|`true`|🔴 Down|**Internal** (tw-llama-tender)|Originali|`internal_fallback`|
|`false`|—|Internal (se no external config)|Originali|`internal`|

---

## Aggiornamento `docker-compose.yml`

text

`# In tw-backend environment: - ANONYMIZER_ENABLED=false          # default off - ANONYMIZER_URL=http://tw-anonymizer:8090 - ANONYMIZER_TIMEOUT=8.0 - EXTERNAL_LLM_URL=                 # vuoto = mai LLM esterno fin che non configurato - LLAMA_SERVER_URL=http://tw-llama-tender:8080/v1   # già presente`

Il design garantisce che **finché `EXTERNAL_LLM_URL` non è configurato esplicitamente**, il sistema non può mai routing verso LLM esterni anche se `anonymizer_enabled=true`, aggiungendo un secondo layer di protezione involontaria durante lo sviluppo


sulla base di Anonimizzarore.md armonizza

Perfetto. Ho letto entrambe le fonti. La ricerca nel documento allegato aggiunge tre elementi preziosi rispetto al piano precedente:​

1. **`pii-rahna` (278M params)** — modello specializzato che batte Presidio+spaCy su italiano con 17 tipi di PII, gira su CPU​
    
2. **Fintizzazione** come alternativa alla sola redazione con placeholder​
    
3. **Framing AI Act / GDPR** formale che va documentato nell'architettura​
    

Ecco il documento armonizzato e definitivo:

---

# `tw-anonymizer` — Piano di Evoluzione Armonizzato

## Visione e Principi

Il componente è un **Privacy Gateway on-premise** conforme al GDPR e all'AI Act (Art. 9 — Risk Management). Il principio architetturale fondamentale è **security-first**: nessun dato sensibile lascia il perimetro aziendale senza essere prima sanitizzato. Il fallback di sicurezza — confermato — prevede che se il gateway non è disponibile, il sistema **non degrada verso LLM esterno**, ma commuta sul modello interno `tw-llama-tender`.​

---

## Flusso Completo Aggiornato

text

`RAG chunks  ──────────────────────────────────────────────────┐                                                                │                    anonymizer_enabled = TRUE                  │                                │                              │                    ┌───────────▼───────────┐                  │                    │   tw-anonymizer       │                  │                    │   Privacy Gateway     │                  │                    │                       │                  │                    │  [1] Regex IT         │                  │                    │   CF/PIVA/IBAN/TEL    │                  │                    │                       │                  │                    │  [2] pii-rahna 278M   │                  │                    │   NER: PER/ORG/ADDR   │                  │                    │   (17 tipi PII, IT)   │                  │                    │                       │                  │                    │  [3] Presidio         │                  │                    │   orchestratore       │                  │                    │                       │                  │                    │  Redis Vault (TTL)    │                  │                    │  placeholder ↔ orig.  │                  │                    └───────┬───────────────┘                  │                            │                                  │              ┌─────────────▼──────────────┐                   │              │      Anonymizer OK?        │                   │              └────┬───────────────┬───────┘                   │                  SÌ               NO                          │                   │                │                          │                   ▼                ▼                          │           External LLM     tw-llama-tender ◄──────────────────┘           (anonimizzato)   (interno, fallback)  anonymizer_enabled=FALSE                   │                │             oppure non configurato                   ▼                │           [De-anonimizza]          │           (opzionale)              │                   │                │                   └────────────────▼                        Risposta utente`

---

## Stack Tecnologico Definitivo (Armonizzato)

|Layer|Tecnologia Precedente|Aggiornamento da Analisi|Decisione Finale|
|---|---|---|---|
|NER structured IT|Regex custom|Confermato|✅ Regex (CF, PIVA, IBAN)|
|NER unstructured|spaCy `it_core_news_lg`|**`pii-rahna` 278M** (più preciso, 17 tipi, italiano nativo)|✅ **pii-rahna** come motore primario|
|Orchestratore|Presidio `AnalyzerEngine`|Confermato come framework|✅ Presidio (con pii-rahna come NER backend)|
|Strategia sostituzione|Placeholder `[ORG_1]`|+ **Fintizzazione** (dati fittizi verosimili)|✅ Entrambe (configurabile da admin)|
|Reverse mapping|Redis TTL|Confermato — vault ephemeral|✅ Redis TTL, zero persistenza su DB|
|Fallback|`internal_fallback` su tw-llama-tender|**Confermato e rafforzato**|✅ Nessun dato esce se anonymizer KO|
|Compliance|Non documentata|AI Act Art. 9, GDPR minimization|✅ Aggiunta sezione governance|

---

## Aggiornamento Architetturale Chiave: `pii-rahna` come NER Engine

La ricerca ha evidenziato che `pii-rahna` (`iiiorg/piiranha-v1-detect-personal-information`) con soli 278M parametri supera spaCy su testo italiano per PII detection, raggiungendo >98% di precisione su 17 categorie.​

## `anonymizer/engine.py` — Backend NER pluggabile

python

`class NERBackend(str, Enum):     SPACY = "spacy"    PIIRahna = "piiranha"    # ← default consigliato per italiano def _build_analyzer(self) -> AnalyzerEngine:     """    Costruisce il AnalyzerEngine con il backend NER configurato.         pii-rahna (default): 278M params, 17 tipi PII, ottimizzato italiano.    spacy: fallback se pii-rahna non è disponibile o per deployment leggeri.    """    from presidio_analyzer import AnalyzerEngine, RecognizerRegistry    from presidio_analyzer.nlp_engine import TransformersNlpEngine     ner_backend = self.config.get("ner_backend", NERBackend.PIIRahna)     if ner_backend == NERBackend.PIIRahna:        # pii-rahna via Transformers NLP engine        nlp_engine = TransformersNlpEngine(            models=[{                "lang_code": "it",                "model_name": "iiiorg/piiranha-v1-detect-personal-information",            }]        )    else:        # Fallback spaCy        from presidio_analyzer.nlp_engine import NlpEngineProvider        provider = NlpEngineProvider(nlp_configuration={            "nlp_engine_name": "spacy",            "models": [{"lang_code": "it", "model_name": "it_core_news_lg"}],        })        nlp_engine = provider.create_engine()     registry = RecognizerRegistry()    registry.load_predefined_recognizers(nlp_engine=nlp_engine)     # Recognizer italiani strutturati (CF/PIVA/IBAN) — sempre attivi    from anonymizer.recognizers.italian import (        CodiceFiscaleRecognizer,        PartitaIvaRecognizer,        IBANRecognizer,    )    registry.add_recognizer(CodiceFiscaleRecognizer())    registry.add_recognizer(PartitaIvaRecognizer())    registry.add_recognizer(IBANRecognizer())     return AnalyzerEngine(        nlp_engine=nlp_engine,        registry=registry,        supported_languages=["it", "en"],    )`

## `anonymizer/requirements.txt` — Aggiornato

text

`fastapi==0.111.0 uvicorn==0.29.0 httpx==0.27.0 redis[asyncio]==5.0.3 presidio-analyzer==2.2.354 presidio-anonymizer==2.2.354 # pii-rahna via transformers (278M params — nessuna GPU richiesta) transformers>=4.40.0 torch==2.2.2+cpu          # CPU-only, nessuna VRAM necessaria # Fallback spaCy spacy==3.7.4 structlog==24.1.0 pydantic-settings==2.2.1`

## `anonymizer/Dockerfile` — Aggiornato

text

`FROM python:3.11-slim ENV PYTHONUNBUFFERED=1 WORKDIR /app RUN apt-get update && apt-get install -y --no-install-recommends \     build-essential gcc \    && rm -rf /var/lib/apt/lists/* COPY requirements.txt . RUN pip install --no-cache-dir -r requirements.txt # Pre-download pii-rahna al build time (non a runtime) # Modello 278M — ~560MB su disco RUN python -c "\ from transformers import AutoTokenizer, AutoModelForTokenClassification; \ AutoTokenizer.from_pretrained('iiiorg/piiranha-v1-detect-personal-information'); \ AutoModelForTokenClassification.from_pretrained('iiiorg/piiranha-v1-detect-personal-information')" # Fallback spaCy italiano RUN python -m spacy download it_core_news_lg COPY . /app CMD ["python", "-m", "run"]`

---

## Nuova Feature: Fintizzazione (Synthetic Replacement)

Dalla ricerca emerge che la **sostituzione con dati fittizi ma plausibili** preserva meglio il contesto semantico per l'LLM esterno rispetto alla sola redazione con placeholder.​

python

`# anonymizer/strategies.py from enum import Enum class AnonymizationStrategy(str, Enum):     REDACTION = "redaction"       # [ORG_1] — default, massima privacy    FAKING = "faking"             # "Acme S.r.l." — dati fittizi verosimili # Dizionario di nomi fittizi per categoria (italiano) FAKE_POOL = {     "PERSON": [        "Luca Bianchi", "Marco Ferrari", "Sara Esposito",        "Giovanni Ricci", "Elena Conti", "Paolo Romano",    ],    "ORG": [        "Alfa Solutions S.r.l.", "Beta Consulting S.p.A.",        "Gamma Tech S.r.l.", "Delta Group S.p.A.",        "Epsilon Services S.r.l.", "Zeta Industries S.p.A.",    ],    "IT_PARTITA_IVA": [        "IT99887766554", "IT11223344556", "IT55667788990",    ],    "IT_CODICE_FISCALE": [        "TSTFKE99A01H501Z", "BNCMRC85B20F205X",    ],    "IT_IBAN": [        "IT60X0542811101000000123456", "IT40W0690601000000012345678",    ],    "LOCATION": [        "Via delle Magnolie 5, Milano",        "Corso Europa 22, Roma",        "Piazza della Repubblica 8, Torino",    ], } class FakingOperator:     """    Sostituisce PII con valori fittizi ma plausibili.    La stessa entità riceve sempre lo stesso fake nella sessione    (consistenza semantica nel documento).    """    def __init__(self):        self._entity_to_fake: dict[str, str] = {}        self._counters: dict[str, int] = {}     def get_fake(self, entity_type: str, original_value: str) -> str:        if original_value in self._entity_to_fake:            return self._entity_to_fake[original_value]         pool = FAKE_POOL.get(entity_type, [])        if pool:            idx = self._counters.get(entity_type, 0) % len(pool)            self._counters[entity_type] = idx + 1            fake = pool[idx]        else:            fake = f"[{entity_type}_ANONIMIZZATO]"         self._entity_to_fake[original_value] = fake        return fake`

Nella `ConfigUpdateRequest` admin, aggiungi:

python

`anonymization_strategy: str = Field(     "redaction",    description="'redaction' = placeholder [ORG_1], 'faking' = sostituzione con dati fittizi" )`

---

## Routing LLM (Confermato e Formalizzato)

python

`# backend/app/rag/engine.py async def _resolve_generator_and_context(     self,    context_chunks: list[str], ) -> tuple[Generator, list[str], LLMRoute, str | None]:     """    Matrice di routing sicura:     anonymizer_enabled=False  → LLM configurato, chunks originali    anonymizer=True + OK      → External LLM, chunks anonimizzati    anonymizer=True + KO      → tw-llama-tender (INTERNO), chunks originali                                 nessun dato esce — SEMPRE     Questo implementa il principio AI Act Art. 9:    il sistema di gestione del rischio interviene automaticamente.    """    if not settings.anonymizer_enabled:        generator = Generator(            base_url=settings.external_llm_url or settings.llama_server_url,            model=settings.external_llm_model or settings.llama_model,        )        route = LLMRoute.EXTERNAL if settings.external_llm_url else LLMRoute.INTERNAL        return generator, context_chunks, route, None     try:        anonymized_chunks, session_token = await anonymize_chunks(context_chunks)        generator = Generator(            base_url=settings.external_llm_url,            model=settings.external_llm_model,        )        return generator, anonymized_chunks, LLMRoute.EXTERNAL, session_token     except AnonymizerUnavailableError as exc:        # ⚠️  SECURITY FALLBACK — obbligatorio, non aggirabile        logger.warning(            "SECURITY FALLBACK ATTIVATO: anonymizer non disponibile. "            "Routing forzato su tw-llama-tender. "            "Nessun dato inviato a servizi esterni.",            reason=str(exc),        )        await self._emit_anonymizer_fallback_event(reason=str(exc))         generator = Generator(            base_url=settings.llama_server_url,   # http://tw-llama-tender:8080/v1            model=settings.llama_model,        )        return generator, context_chunks, LLMRoute.INTERNAL_FALLBACK, None`

---

## Matrice Comportamentale Completa (Aggiornata)

|Scenario|`anonymizer_enabled`|Anonymizer|Strategia|LLM usato|Dati inviati fuori|
|---|---|---|---|---|---|
|Default off|`false`|—|—|Internal (tw-llama-tender)|❌ No|
|Admin abilita senza ext LLM|`true`|🟢 OK|Redaction|Internal (no ext config)|❌ No|
|Regime normale|`true`|🟢 OK|Redaction/Faking|**External**|✅ Solo anonimizzati|
|Anonymizer down|`true`|🔴 KO|—|**Internal (fallback)**|❌ No — sicurezza garantita|
|Admin disabilita|`false`|—|—|Internal o External|Secondo config ext LLM|

---

## Compliance AI Act / GDPR — Note Architetturali

L'architettura risponde direttamente ai requisiti normativi identificati nell'analisi:​

- **Art. 9 AI Act — Risk Management**: il fallback automatico su LLM interno è il sistema di gestione del rischio che interviene senza intervento umano
    
- **GDPR Data Minimization**: il vault Redis è ephemeral (TTL = durata sessione), zero persistenza su DB; `pii-rahna` processa tutto on-premise
    
- **Auditabilità**: ogni evento di fallback genera un record nell'osservabilità (`/v1/events/system`) con timestamp, reason e `llm_route`
    
- **Data Sovereignty**: `pii-rahna` (278M) non richiede connessione esterna — scaricato al build time nel container​
    
- **Pseudonimizzazione reversibile**: la tabella di mappatura `placeholder ↔ originale` non lascia mai il perimetro, conforme allo standard "Golden Standard" AI Act identificato nell'analisi​
    

---

## Roadmap di Implementazione Aggiornata

| Sprint | Deliverable                                                            | Note                               |
| ------ | ---------------------------------------------------------------------- | ---------------------------------- |
| **S1** | Recognizer italiani regex (CF/PIVA/IBAN) + Presidio base               | Fondamenta certe                   |
| **S1** | Dockerfile con pii-rahna pre-scaricato al build                        | Chiave per performance             |
| **S1** | `/anonymize` + Redis vault + `/health`                                 | Core funzionale                    |
| **S2** | Integrazione `engine.py` — routing + `AnonymizerUnavailableError`      | Fallback sicuro su tw-llama-tender |
| **S2** | `LLMRoute` + evento osservabilità su fallback                          | Visibilità operativa               |
| **S2** | Admin API `/config`, `/stats`, `/test`                                 | Controllo da UI                    |
| **S3** | Frontend `AnonymizerAdmin.tsx` — toggle, entity selector, area test    | UX admin                           |
| **S3** | Strategia **Faking** configurabile da admin                            | Feature valore aggiunto            |
| **S3** | `/deanonymize` + badge `internal_fallback` nel TenderChat              | Completezza                        |
| **S4** | Golden dataset italiano (CF, PIVA, IBAN, nomi, indirizzi) + test suite | Regressione                        |
| **S4** | Documento compliance AI Act generato automaticamente dai log           | Governance                         |


