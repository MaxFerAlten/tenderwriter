# Risoluzione problemi AI Search e LM Studio (chat del 2026-03-11 / 2026-03-12)

## Obiettivo
Documentare tutto quello che e stato fatto per risolvere i problemi emersi:

1. Differenza tra output LM Studio e output AI Search.
2. `AI Answer` a volte vuoto nonostante LM Studio generasse testo.
3. `% match` negativi (es. `-126%`) nella UI.
4. Errori intermittenti `500` su `POST /api/rag/query`.
5. Errori intermittenti `502` nel gateway verso upstream LLM.

---

## Problemi iniziali osservati

### 1) LM Studio generava testo, ma AI Search mostrava solo sorgenti/chunk
Dai log LM Studio:
- richiesta ricevuta su `/v1/completions`
- output presente in `choices[0].text`

Nel backend (prima della patch):
- parser leggeva solo `data.get("content")`
- quindi risposta finale poteva risultare vuota (`answer=""`) anche con generazione valida.

### 2) Punteggio match negativo in UI
La UI mostrava `(result.score * 100)` direttamente.
Il `score` proveniva dal cross-encoder reranker (non e una percentuale normalizzata, puo essere anche negativo).
Risultato: valori tipo `-111%`, `-126%`.

### 3) 500 intermittenti su /api/rag/query
Da log backend:
- `httpx.HTTPStatusError: 502 Bad Gateway` verso `http://tw-gateway:8080/completion`
- la eccezione risaliva fino all'endpoint API causando `500`.

### 4) Instabilita gateway/upstream
Da log gateway:
- chiamate `/completion` con esito alternato `502` e `200`.

---

## Analisi tecnica svolta

### Tracciamento flusso completo
Sono stati analizzati:
- `backend/app/rag/generator.py`
- `backend/app/rag/engine.py`
- `backend/app/api/rag.py`
- `gateway/app.py`
- `frontend/src/pages/Search.tsx`
- `frontend/src/pages/ProposalEditor.tsx`

### Verifica configurazione target gateway (DB)
Query su Postgres:

```sql
select id, route_key, provider, base_url, enabled, priority, timeout_ms
from ai_gateway_targets
order by priority, id;
```

Risultato chiave:
- target attivo `id=11`
- `route_key=tender`
- `provider=openai`
- `base_url=http://host.docker.internal:1234`

Con questa config, il gateway riscrive `/completion` -> `/v1/completions` (comportamento previsto nel codice).

---

## Modifiche applicate

## A) Backend - parser risposta LLM robusto
File modificato:
- `backend/app/rag/generator.py`

Interventi:
1. Aggiunti helper per parsing multiplo formato risposta:
   - supporto `content` (stile llama.cpp)
   - supporto `choices[0].text` / `choices[0].message.content` (stile OpenAI-compatible)
2. Aggiunta estrazione usage token multipla:
   - `tokens_evaluated` / `tokens_predicted`
   - fallback da `usage.prompt_tokens` / `usage.completion_tokens`
3. Stream parser reso robusto:
   - supporto linee SSE (`data: ...`)
   - gestione `[DONE]`
   - estrazione token da payload diversi (`content`, `choices[].text`, `choices[].delta.content`)
4. In `generate_stream` aggiunta inizializzazione parametri runtime (`max_tokens`, `temperature`, `stop_tokens`) per evitare uso variabile non inizializzata.

Effetto:
- `AI Answer` non viene piu perso quando upstream risponde in formato OpenAI-compatible.

---

## B) Frontend - normalizzazione match score
File modificato:
- `frontend/src/pages/Search.tsx`

Interventi:
1. Aggiunta funzione `normalizeMatchScore(score)`:
   - se score gia in `[0,1]`, lo mantiene
   - se fuori range (es. logit negativo), applica sigmoid
   - clamp finale in `[0,1]`
2. Applicata la normalizzazione in mapping risultati:
   - `score: normalizeMatchScore(s.score)`

Effetto:
- spariti i match negativi.
- visualizzazione coerente in percentuale (`0-100%`).

---

## C) Resilienza backend su errori upstream (evitare 500)
File modificato:
- `backend/app/rag/generator.py`
- `backend/app/rag/engine.py`

Interventi:
1. Retry nel generatore per richieste verso gateway:
   - 2 tentativi su `502/503/504`
   - retry anche su timeout/transport error
   - piccolo backoff (`asyncio.sleep`)
2. Fallback in `engine.py` per `mode=qa`:
   - se la generazione fallisce anche dopo retry, non viene piu propagato `500`
   - ritorna comunque `200` con risposta di fallback + sorgenti recuperate

Effetto:
- richiesta AI Search resta utilizzabile anche con upstream intermittente.

---

## D) Fix alla radice nel gateway (timeout per target + retry locale)
File modificato:
- `gateway/app.py`

Interventi:
1. Il gateway ora usa timeout per candidato:
   - legge `timeout_sec` dal candidato (se presente), altrimenti fallback a timeout globale.
2. Retry locale sullo stesso target:
   - prima di passare al candidato successivo
   - applicato a `502/503/504` e a timeout/transport error
3. Propagazione `timeout_sec` e `max_attempts` nei candidati:
   - candidati dinamici da backend (`timeout_ms` -> secondi)
   - fallback env / dmz / cloud.

Effetto:
- riduzione ulteriore delle cadute intermittenti del proxy.
- utilizzo reale del timeout configurato nel target dinamico.

---

## Deploy/riavvii eseguiti

Comandi principali eseguiti:

```powershell
docker compose up -d --build frontend
docker compose restart backend
docker compose up -d --build gateway
```

Sono stati verificati i bundle frontend serviti da nginx per assicurare che la UI aggiornata fosse realmente in produzione.

---

## Validazioni eseguite

### Validazione codice
- `python -m py_compile` su file Python modificati (ok).
- `npm --prefix frontend run build` (ok).

### Validazione funzionale
- test ripetuti su `/api/rag/query` in `mode=qa` con autenticazione.
- esiti osservati dopo le patch:
  - serie multiple di richieste tutte `200`
  - nessun nuovo `500` in AI Search.

### Validazione log
- prima: presenza di `500` backend causati da `502` upstream.
- dopo patch:
  - backend query in `200`
  - gateway con chiamate `/completion` stabilizzate (ultimo tratto verificato in `200`).

---

## Stato finale

Problemi risolti:
1. mismatch parser LM Studio/OpenAI -> risolto
2. `AI Answer` vuoto in caso di risposta OpenAI-compatible -> risolto
3. `% match` negativi in UI -> risolto
4. `500` intermittenti su AI Search -> mitigati con retry+fallback
5. instabilita gateway su timeout/retry candidato -> migliorata con patch gateway

Nota:
- Restano possibili warning non bloccanti in componenti non direttamente legate a questa issue (es. retrieval graph), ma non impattano la risoluzione del problema specifico AI Search/LM Studio affrontato in questa chat.
