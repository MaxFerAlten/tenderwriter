# tw-anonymizer

Privacy gateway per TenderWriter. In V1 svolge due compiti:

- anonimizza testo o chunk prima dell'invio a LLM esterne
- mantiene il relay HTTP legacy con protezione SSRF

## Endpoint

- `GET /health`
- `POST /v1/anonymize`
- `POST /v1/deanonymize`
- `GET /v1/config`
- `POST /v1/config`
- `GET /v1/stats`
- `/{path:path}` relay trasparente, richiede header `X-Target-Url`

## Contratto rapido

`POST /v1/anonymize`

```json
{
  "text": "Mario Rossi ha CF RSSMRA85M01H501Z"
}
```

oppure

```json
{
  "chunks": ["chunk 1", "chunk 2"]
}
```

Risposta:

```json
{
  "session_id": "abc123",
  "config": {
    "entities": ["PERSON", "CODICE_FISCALE", "PARTITA_IVA", "IBAN"],
    "ttl_seconds": 3600,
    "strategy": "redaction",
    "min_confidence": 0.35,
    "mask_cig": false
  },
  "chunks": [
    {
      "text": "Mario Rossi ha CF RSSMRA85M01H501Z",
      "anonymized_text": "[PERSONA_1] ha CF [CF_1]",
      "detections": [],
      "replacements": {}
    }
  ]
}
```

Per il caso `text`, la risposta contiene `chunk` invece di `chunks`.

`POST /v1/deanonymize`

```json
{
  "text": "[PERSONA_1] ha CF [CF_1]",
  "session_id": "abc123"
}
```

## Variabili ambiente principali

- `ANONYMIZER_REDIS_URL`: default `memory://`, in produzione usare Redis dedicato
- `ANONYMIZER_DEFAULT_TTL_SECONDS`: TTL reverse mapping
- `ANONYMIZER_DEFAULT_MIN_CONFIDENCE`
- `ANONYMIZER_ENABLE_CIG_BY_DEFAULT`
- `ANONYMIZER_MAX_CHUNKS`: guardrail dimensione batch
- `ANONYMIZER_MAX_CHUNK_CHARS`: guardrail dimensione chunk
- `ANONYMIZER_RELAY_TIMEOUT_SECONDS`: timeout del relay legacy

## Deployment Notes

- Usare Redis DB separato da Celery. Nel compose di progetto: `redis://redis:6379/1`.
- Il backend V1 applica timeout stretto e circuit breaker leggero verso `tw-anonymizer`.
- Se `ANONYMIZER_ENABLED=true` e l'anonymizer non risponde, il backend devia su LLM interna.
- Se non esiste `EXTERNAL_LLM_URL`, il backend resta su route interna e non prova ad anonimizzare.

## Limiti V1

- `query_stream()` nel backend non usa ancora il ciclo anonymize/deanonymize; il flusso viene forzato su route interna.
- Il deanonymize è pensato per uso server-side/admin/debug, non per il flusso utente standard.
