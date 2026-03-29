# OpenRouter, LM Studio e Fix Max Context

## Contesto

In questa sessione ho lavorato sul flusso AI di TenderWriter, in particolare su:

- integrazione di provider esterni OpenRouter senza rompere il metodo esistente
- supporto corretto a LM Studio / endpoint OpenAI-compatible
- correzione di alcuni blocchi lato frontend e servizi di supporto
- miglioramento delle risposte lunghe nel RAG quando l'utente chiede esplicitamente un numero di parole elevato

L'obiettivo principale era eliminare i fallback del tipo:

> Il modello e temporaneamente non disponibile. Mostro solo le fonti recuperate.

e fare in modo che una richiesta come:

> riassumimi il problema di assegnamento con 1000 parole

producesse davvero una risposta lunga e coerente.

## Problemi individuati

### 1. OpenRouter configurato ma non realmente supportato

Il sistema trattava `https://openrouter.ai/api/v1` come backend `llama.cpp`, quindi:

- inviava payload nel formato sbagliato
- usava endpoint sbagliati
- non passava correttamente la `Authorization` per provider esterni
- salvava target con `provider=llama`, creando comportamenti ambigui

### 2. Mancanza di scelta esplicita tra metodo attuale e OpenRouter

Nel pannello Settings non esisteva una distinzione chiara tra:

- metodo attuale locale / `llama.cpp`
- provider esterno OpenRouter

Mancava anche un campo per la API key, quindi i provider esterni non potevano essere configurati in modo completo.

### 3. Refuso nel salvataggio del Base URL

Inserendo:

`https://openrouter.ai/api/v1/chat/completions`

il sistema salvava:

`https://openrouter.ai/api/v1`

per via di una normalizzazione introdotta in precedenza per compatibilita con LM Studio.

### 4. Errore `missing x-target-url header`

L'errore non dipendeva dal frontend: il container `tw-anonymizer` stava girando con una build vecchia che non esponeva i nuovi endpoint `/v1/anonymize`, `/v1/config`, `/v1/stats`.

Di conseguenza ogni chiamata passava nel relay generico che richiedeva `x-target-url`.

### 5. Timeout Keycloak in incognito

In modalita `hybrid`, il frontend rimaneva bloccato su `Loading...` a causa del timeout:

`Timeout when waiting for 3rd party check iframe message`

### 6. LM Studio raggiungibile ma interpretato in modo errato

Per target come:

`http://127.0.0.1:1234/v1/chat/completions`

il backend costruiva URL sbagliati come:

`.../chat/completions/completion`

Inoltre `127.0.0.1` dentro Docker puntava al container stesso, non all'host Windows dove gira LM Studio.

### 7. Risposte troppo corte per richieste lunghe

Anche dopo aver ripristinato il routing corretto, il RAG rispondeva con testi troppo brevi rispetto alla richiesta dell'utente.

Caso osservato:

- richiesta: `riassumimi il problema di assegnamento con 1000 parole`
- risposta effettiva iniziale: circa `315` parole

## Modifiche applicate

### OpenRouter come opzione aggiuntiva

Ho implementato il supporto OpenRouter come opzione separata, senza sostituire il metodo esistente.

#### Backend / gateway

- riconoscimento target OpenRouter
- normalizzazione corretta degli URL
- conversione verso `/chat/completions`
- gestione corretta della `Authorization: Bearer ...`
- fallback ai target successivi anche in casi di errori esterni rilevanti

#### Settings frontend

- tendina `Metodo`
- opzioni distinte:
  - metodo attuale (`llama.cpp / LM Studio`)
  - OpenRouter
- campo `API key`
- validazioni per bloccare target OpenRouter incompleti

### Fix sul Base URL

Ho corretto la logica di salvataggio in modo che il `base_url` resti esattamente quello inserito dall'utente.

Quindi ora:

- se inserisci `/api/v1/chat/completions`, viene salvato cosi
- se inserisci `/api/v1`, viene salvato cosi

Il sistema continua comunque a riconoscere le due forme come equivalenti per il controllo dei duplicati logici.

### Fix del servizio anonymizer

Ho verificato che il problema `missing x-target-url header` dipendeva da una build legacy del container.

Azioni effettuate:

- rebuild di `tw-anonymizer`
- restart di `tw-backend`
- aggiunto un messaggio backend piu chiaro per segnalare build outdated del servizio

### Fix bootstrap auth / Keycloak

Ho corretto il bootstrap auth frontend per evitare che una sessione valida restasse bloccata da `Keycloak.init()` in modalita `hybrid`.

Interventi principali:

- validazione del token gia salvato prima del bootstrap Keycloak
- distinzione della provenienza sessione con `auth_source`
- riduzione timeout del silent check
- degradazione da errore bloccante a warning non invasivo

### Supporto corretto LM Studio / OpenAI-compatible

Ho corretto backend e gateway per gestire in modo corretto:

- `/v1`
- `/v1/chat/completions`
- `/v1/completions`

In piu:

- riscrittura automatica `localhost/127.0.0.1 -> host.docker.internal` quando il backend gira in Docker
- niente piu concatenazione errata verso `/completion`
- compatibilita con target salvati come metodo attuale ma in realta puntati a LM Studio

### Fix risposte lunghe / max context

Questo e stato il fix piu importante lato esperienza utente.

Ho modificato il motore RAG per:

- rilevare richieste esplicite di lunghezza come `1000 parole`
- aumentare dinamicamente il budget di generazione iniziale
- aggiungere vincoli espliciti sulla lunghezza nella prompt
- estendere la risposta con un secondo passaggio solo quando necessario
- non fare fallback totale se fallisce l'estensione, ma conservare comunque la prima risposta valida
- pulire il testo finale da heading meta tipo `Continuazione della risposta`
- rimuovere finali palesemente troncati

In pratica il flusso ora e:

1. prima generazione con `max_tokens` coerente con la lunghezza richiesta
2. estensione solo se la risposta e ancora troppo corta
3. pulizia finale dell'output

## Verifiche eseguite

### OpenRouter

- verifica key valida tramite endpoint `/models`
- verifica model ID validi / invalidi
- verifica salvataggio URL completo
- verifica presenza campo API key e metodo selezionabile da Settings

### Anonymizer

- `GET /api/anonymizer/config` -> `200`
- `GET /api/anonymizer/stats` -> `200`
- `POST /api/anonymizer/test` -> `200`

### Frontend auth

- rebuild frontend
- test in incognito su `/settings`
- eliminato il blocco permanente su `Loading...`

### LM Studio / RAG

- test diretto dal container backend verso LM Studio con URL OpenAI-compatible
- query end-to-end su `/api/rag/query`
- verifica che non venga piu restituito il fallback di indisponibilita modello per il caso corretto

### Risposta lunga

Verifica reale finale:

- query: `riassumimi il problema di assegnamento con 1000 parole`
- risposta ottenuta: `1174` parole
- nessun heading meta residuo `Continuazione della risposta`

## Test eseguiti

Test confermati durante la sessione:

- `python -m pytest gateway/test_gateway.py -q` -> `6 passed`
- `docker exec -w /app tw-backend python -m unittest tests.test_rag_anonymizer_routing -q` -> `OK`
- `npm run build` frontend -> `OK`

Nota: nel container backend non e installato `pytest`, quindi per i test Python del motore RAG ho usato `unittest` dove possibile.

## File principali toccati

- `backend/app/rag/engine.py`
- `backend/app/rag/generator.py`
- `backend/app/api/gateway_admin.py`
- `backend/app/api/anonymizer_admin.py`
- `backend/app/db/database.py`
- `backend/app/models/__init__.py`
- `frontend/src/pages/Settings.tsx`
- `frontend/src/api/client.ts`
- `frontend/src/contexts/AuthContext.tsx`
- `frontend/src/auth/keycloak.ts`
- `gateway/app.py`
- `gateway/test_gateway.py`
- `backend/tests/test_rag_anonymizer_routing.py`
- `backend/app/test_openrouter_support.py`

## Stato finale

Alla fine della sessione:

- OpenRouter e supportato come opzione esplicita
- la API key puo essere configurata
- il `base_url` non viene piu alterato in modo inatteso
- LM Studio funziona correttamente tramite endpoint OpenAI-compatible
- il bug `missing x-target-url header` e stato risolto tramite rebuild del servizio corretto
- il blocco Keycloak in incognito non lascia piu la UI appesa
- il RAG ora riesce a produrre risposte lunghe coerenti con richieste da `1000 parole`

## Residui noti

Resta separato un warning Neo4j:

- `Expected parameter(s): query, top_k`

Non blocca piu la generazione delle risposte, ma andrebbe sistemato in un intervento dedicato sul `GraphRetriever`.
