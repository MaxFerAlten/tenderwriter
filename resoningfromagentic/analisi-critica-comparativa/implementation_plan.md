# Piano d'Azione: Remediation Criticità (P0)

Questo piano d'azione affronta le criticità di livello P0 (Sicurezza e Runtime RAG) evidenziate nell'analisi architetturale di `Analisi-salute-2026-04-03.md`.

## Goal Description
L'obiettivo è stabilizzare la piattaforma affrontando immediatamente i problemi che invalidano la pipeline Hybrid RAG (degradata a Dense-only) e che espongono l'infrastruttura a vulnerabilità critiche (servizi privilegiati con accesso host-level tramite Docker socket, SSRF, endpoint aperti).

## User Review Required
> [!IMPORTANT]
> - Questo piano si focalizza **esclusivamente** sul Backlog P0 per un contenimento immediato (prime 72 ore).
> - Avrò bisogno di accedere a vari file del backend, gateway e compose per applicare questi fix.
> - Si prega di confermare se desideri procedere con questo primo blocco o se vuoi includere anche elementi P1 (es. unit testing in CI, fix BUG-01/-03).

## Proposed Changes

---
### Sicurezza & Infrastruttura (Security Remediation)

Le seguenti correzioni mirano a isolare l'ambiente backend e rimuovere l'esposizione di informazioni sensibili.

#### [MODIFY] `docker-compose.yml`
- **Confinamento Mount Socket**: Mantenere il mount `/var/run/docker.sock` fuori da `tw-backend` e limitarlo ai soli servizi privilegiati strettamente necessari.
- **Rotazione Secrets**: Sostituire password hardcoded (`DefaultPg2024Pass`, `DefaultNEO4J2024Pass`, `DefaultMinIO2024Pass`, `DefaultMM2024Pass`, `CHANGEME-mattermost-client-secret`) con variabili d'ambiente fornite esternamente (es. tramite un file `.env` validato o script di pre-avvio).

#### [MODIFY] Codice Backend (Route e Servizi operativi)
- **Rotta `ops-agent`**: Redirigere le chiamate di monitoring/system metrics che richiedono privilegi Docker verso l'`ops-agent`, assicurandosi che `ops-agent` includa nell'allowlist i comandi necessari.

#### [MODIFY] Anonymizer & OnlyOffice
- **Fix SSRF**: Intervenire sull'anonymizer per blindare la Server-Side Request Forgery verificando strict URL validation / whitelist di domini.
- **Protezione Endpoint**: Applicare la dipendenza di autenticazione (`Depends(get_current_user)` o analogo) agli endpoint OnlyOffice esposti (es. `files/{docKey}`).
- **Miglioramento Document Keys**: Sostituire la generazione MD5 debole (basata su ID+timestamp sequenziale) con hash o UUID crittograficamente sicuri.

---
### Runtime Hybrid RAG & LLM Routing

Le seguenti correzioni mirano a re-introdurre la componente Sparse e Graph, attualmente inutilizzate a runtime, e a risolvere l'alta latenza.

#### [MODIFY] `GraphRetriever`
- **Fix Cypher Query**: Correggere l'errore `Neo.ClientError.Statement.ParameterMissing`. Aggiungere i parametri `query` e `topk` al template Cypher utilizzato dal retriever Graph nel backend.

#### [MODIFY] Inizializzazione RAG (Backend)
- **Reload BM25**: Modificare il workflow di bootstrap (`build_index()`) in modo che legga i token già persistiti in PostgreSQL e rigeneri lo stato in memoria del BM25 all'avvio dell'applicazione.

#### [MODIFY] Gateway / Settings Routing
- **Routing LLM Locale**: Determinare perché la route attiva cade regolarmente su `external_anonymized` per il QA. Aggiornare le logiche o i default setting per forzare l'uso di `llama-server` locale, qualora compatibile e salubre.

## Open Questions
- Riguardo all'anonymizer, qual è la policy da adottare per il fix dell'SSRF? Validazione dominio contro un hardcoded hostname, o blocco per CIDR privati?
- Dove desideri memorizzare le variabili d'ambiente per il docker compose? C'è un `.env.example` preesistente o dobbiamo fare uno script di bootstrap?

## Verification Plan
L'esito dei fix implementati verrà comprovato in questo modo:

### Automated/Manual Verification
- Eseguire il container e testare che le funzionalità di "System Monitor" non cadano in errore.
- Effettuare richieste di `QA` e verificare che sia il Retriever Grafo (che non andrà più in errore) che il BM25 (indice > 0) partecipino attivamente.
- Assenza di hardcoded secrets analizzando i raw file.
- Verificare che il routing utilizzi il provider locale abbassando la latenza.
