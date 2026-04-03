# Piano d'Azione Dettagliato — TenderWriter

Documento derivato dall'analisi in [Analisi-salute-2026-04-03.md](/D:/tender/tenderwriter/resoningfromagentic/analisi-critica-comparativa/Analisi-salute-2026-04-03.md).

## Obiettivo

Portare TenderWriter da uno stato di salute complessivo "giallo" con aree rosse critiche a uno stato "verde controllato" sui domini che oggi bloccano affidabilita', sicurezza e operativita' reale:

- ripristinare il comportamento Hybrid RAG reale, oggi degradato a Dense-only;
- abbattere la latenza QA end-to-end;
- chiudere le vulnerabilita' critiche gia' note;
- introdurre disciplina minima di rilascio, test e schema evolution;
- ridurre il rumore architetturale e repository-level che rallenta sviluppo e manutenzione.

## Sintesi Esecutiva

Le criticita' principali emerse dal report sono:

- Runtime RAG non affidabile: dense 12/12, sparse 0/12, graph 0/12.
- Latenza LLM molto alta: circa 60-167 secondi per query QA.
- Sicurezza applicativa esposta: servizi privilegiati con Docker socket, credenziali hardcoded, SSRF, endpoint OnlyOffice senza auth, XSS.
- Schema management fragile: migrazioni raw SQL all'avvio nel backend principale.
- Testing presente ma non governato: niente CI, niente coverage imposta, niente contract test.
- Repo hygiene debole: artefatti di reasoning nel main path, tag Docker `latest`, script operativi nel package applicativo.

## Principi di Esecuzione

1. Bloccare per 72 ore le feature non essenziali e trattare il piano come remediation sprint.
2. Chiudere prima gli elementi che falsano il comportamento reale del prodotto: RAG runtime, route LLM, vulnerabilita' critiche.
3. Ogni fix deve uscire con test o smoke check ripetibile.
4. Ogni correzione infrastrutturale deve lasciare una traccia operativa: runbook, alert, check in CI o migration versionata.
5. Nessuna ottimizzazione di performance prima di aver ripristinato correttezza, sicurezza e osservabilita'.

## Governance Operativa

### Team minimo suggerito

- `Technical Lead`: decisioni tecniche, priorita', tradeoff.
- `Backend Lead`: RAG runtime, auth, schema management.
- `Platform/DevOps`: CI/CD, secrets, Docker hardening, alerting.
- `Security Owner`: validazione remediation critiche e regression check.
- `QA/Validation`: benchmark, smoke test, evidenze di accettazione.

### Cadence suggerita

- Daily di 15 minuti focalizzata su blocchi e rischi.
- Checkpoint a 48 ore per validare chiusura P0.
- Demo tecnica a fine settimana con benchmark e prove di sicurezza.

## Piano d'Azione

## Fase 0 — Contenimento Immediato (0-72 ore)

### Obiettivo

Ridurre il rischio di incidente reale e ristabilire il controllo sul comportamento minimo della piattaforma.

### Azioni

1. Congelare merge non critici e aprire una board "remediation".
2. Mantenere il mount di `/var/run/docker.sock` fuori dal backend, confinandolo ai soli servizi privilegiati strettamente necessari e verificando se `mattermost-bootstrap` possa evitarlo.
3. Ruotare tutte le credenziali hardcoded e sostituire i placeholder sensibili.
4. Disabilitare o proteggere immediatamente l'endpoint OnlyOffice `files/{docKey}` con autenticazione.
5. Applicare il fix SSRF nell'anonymizer o, se non immediato, disabilitare temporaneamente i path vulnerabili.
6. Verificare e chiudere l'uso di `admin/admin` o imporre rotazione al primo accesso.
7. Correggere il bug Neo4j `query/topk` nel `GraphRetriever`.
8. Implementare il reload dell'indice BM25 da persistenza all'avvio.
9. Verificare perche' il route LLM va su `external_anonymized` e forzare il route locale se previsto dall'architettura target.

### Deliverable

- Patch di sicurezza urgente deployata in staging.
- Report di rotazione secrets completato.
- Smoke benchmark RAG post-fix con evidenza di sparse e graph non piu' a zero.
- Check di latenza QA comparativa pre/post fix.

### KPI di accettazione

- Nessun secret sensibile piu' presente in `docker-compose.yml`.
- Endpoint OnlyOffice non accessibile senza token/sessione valida.
- `GraphRetriever` con hit > 0 su benchmark smoke.
- `sparse_corpus_size > 0` dopo restart.
- Latenza median QA ridotta almeno del 50% rispetto al baseline documentato.

### Rischi

- Le fix rapide sul routing LLM potrebbero rivelare limiti del modello locale.
- Un hardening troppo aggressivo dei servizi privilegiati puo' rompere monitoraggio o bootstrap se `ops-agent` e `mattermost-bootstrap` non vengono riesaminati con test operativi.

## Fase 1 — Stabilizzazione di Sprint (Settimana 1-2)

### Obiettivo

Chiudere i bug noti a basso costo e introdurre le prime guardrail tecniche obbligatorie.

### Azioni

1. Chiudere i bug applicativi gia' noti:
- `BUG-01` commit mancante su `DELETE`.
- `BUG-03` XSS nella generazione PDF.
- `BUG-08` mutable defaults in dataclass.
- `BUG-09/10` gestione `datetime` naive/aware.

2. Fare audit sistematico delle route:
- verificare tutti i router FastAPI;
- applicare `Depends(get_current_user)` o equivalente;
- aggiungere controlli di ruolo dove necessario.

3. Installare e validare `unstructured` nel backend containerizzato.
4. Costruire una CI minima:
- `pytest --cov`;
- `vitest run --coverage`;
- fail sotto soglia minima;
- smoke test backend/frontend;
- lint essenziale.

5. Portare gli E2E da script standalone a job eseguibili in pipeline o in ambiente di test standardizzato.

### Deliverable

- Bug list critica azzerata o ridotta ai soli casi complessi.
- Workflow CI funzionante su branch e PR.
- Report coverage iniziale con baseline ufficiale.
- Lista route con stato auth/role enforcement.

### KPI di accettazione

- 100% dei bug P0/P1 documentati come fixati o con issue/owner/data.
- CI eseguita automaticamente su ogni PR.
- Coverage backend e frontend pubblicata.
- Nessuna route critica senza guardia auth.

## Fase 2 — Hardening Strutturale (Settimana 3-4)

### Obiettivo

Eliminare il debito tecnico che oggi rende il sistema fragile in rilascio e manutenzione.

### Azioni

1. Introdurre Alembic nel backend principale.
2. Mappare lo schema attuale e generare una baseline migration verificata.
3. Rimuovere gli `ALTER TABLE` imperativi dall'avvio applicativo.
4. Separare gli script operativi da `backend/app/` in una cartella dedicata come `tools/` o `scripts/ops/`.
5. Pinning esplicito delle immagini Docker e delle versioni runtime.
6. Introdurre contract test minimi per integrazioni critiche:
- backend <-> ops-agent;
- backend <-> gateway AI;
- backend <-> KPI reason engine.

### Deliverable

- Catena migration versionata e ripetibile.
- Package applicativo ripulito dagli script operativi.
- Compose riproducibile senza tag `latest`.
- Contract test iniziali in CI.

### KPI di accettazione

- Nessuna modifica schema eseguita implicitamente a runtime.
- Tutte le immagini Docker con tag esplicito.
- Almeno 3 contratti inter-servizio coperti da test automatici.

## Fase 3 — Performance e Affidabilita' Reale (Settimana 5-6)

### Obiettivo

Portare il prodotto a un comportamento misurabile coerente con la promessa architetturale.

### Azioni

1. Rifare il benchmark RAG su corpus realistico di gare, non su un solo documento accademico.
2. Definire benchmark standard con:
- hit rate dense;
- hit rate sparse;
- hit rate graph;
- MRR o metriche equivalenti;
- latenza p50/p95.

3. Spostare il rebuild BM25 fuori dal path sincrono:
- coda Celery per re-index;
- oppure valutazione OpenSearch/Elasticsearch.

4. Aggiungere resilience pattern nell'integrazione con KPI reason engine:
- timeout;
- retry mirati;
- circuit breaker;
- fallback chiaro.

5. Verificare la strategia LLM target:
- locale per default dove sostenibile;
- esterno solo per fallback o casi premium;
- osservabilita' del routing per richiesta.

### Deliverable

- Benchmark suite realistica e versionata.
- Piano di scaling del retriever sparse.
- Dashboard con metriche RAG e latenza LLM.

### KPI di accettazione

- Hybrid RAG reale con dense, sparse e graph tutti attivi.
- p95 QA sotto una soglia concordata dal team.
- Nessun rebuild BM25 bloccante nel path utente.

## Fase 4 — Razionalizzazione e Hygiene (Settimana 7-8)

### Obiettivo

Ridurre entropia del repository e migliorare la leggibilita' del production path.

### Azioni

1. Spostare `resoningfromagentic/` fuori dal repository principale oppure archiviarla in repo/wiki separato.
2. Correggere il naming errato della cartella se resta in vita.
3. Distinguere formalmente:
- codice runtime;
- documentazione di progetto;
- output di ricerca/agent reasoning;
- asset diagnostici.

4. Introdurre:
- `CHANGELOG.md`;
- convenzioni ADR leggere;
- ownership per area.

5. Rimuovere componenti dichiarati deprecated ma ancora nello stack se non servono.

### Deliverable

- Repository alleggerito e piu' navigabile.
- Convenzioni di documentazione adottate.
- Percorso di produzione chiaramente separato dal materiale di supporto.

### KPI di accettazione

- Riduzione netta dei file non runtime nel branch principale.
- Tempo medio di onboarding tecnico ridotto.
- Nessun componente deprecated senza decisione esplicita.

## Backlog Prioritizzato

### P0

- Docker socket confermato fuori dal backend e confinato ai soli servizi privilegiati necessari.
- Rotazione secrets e rimozione hardcoded.
- Fix SSRF.
- Protezione endpoint OnlyOffice.
- Fix GraphRetriever.
- Reload BM25 all'avvio.
- Correzione route LLM.

### P1

- Fix BUG-01, BUG-03, BUG-08, BUG-09/10.
- Audit route auth/role.
- CI minima con coverage.
- Installazione `unstructured`.

### P2

- Alembic nel backend principale.
- Contract testing inter-servizio.
- BM25 async o sostituzione sparse engine.
- Resilience pattern KPI engine.

### P3

- Repo hygiene.
- ADR, changelog, policy di documentazione.
- Revisione stack deprecated.

## Dipendenze Critiche

- Il routing LLM va chiarito prima di ogni lavoro serio di performance.
- La baseline Alembic va definita prima di nuove feature che toccano schema.
- La pulizia repo va fatta dopo la messa in sicurezza, non prima.
- I benchmark realistici richiedono un corpus vero di documenti di gara.

## Rischi di Esecuzione

- Fixare il route locale potrebbe ridurre la qualita' delle risposte se il modello locale non e' sufficientemente robusto.
- La migration ad Alembic richiede inventario preciso dello schema reale e dei dati in ambienti esistenti.
- La pulizia repository puo' rompere riferimenti informali a documenti e script usati dal team.

## Criteri di Successo a 30 Giorni

- Nessuna vulnerabilita' critica aperta tra quelle gia' documentate.
- Hybrid RAG ripristinato e verificato su benchmark reale.
- Latenza QA drasticamente ridotta e misurata.
- CI obbligatoria attiva con coverage e smoke test.
- Schema management versionato.
- Repository piu' leggibile e separato dal materiale di reasoning.

## Prossimo Passo Consigliato

Aprire immediatamente un `Remediation Sprint` con tre stream paralleli:

- `Security`: servizi privilegiati con Docker socket, secrets, SSRF, OnlyOffice auth.
- `RAG Runtime`: GraphRetriever, BM25 reload, route LLM, benchmark.
- `Engineering Guardrails`: CI, coverage, migration strategy, audit route auth.
