# Backlog Tecnico Numerato: `tw-kpi-reason-engine`

## Convenzioni
- Priorita': `P0`, `P1`, `P2`
- Tipo: `Infra`, `Backend`, `Frontend`, `Data`, `AI`, `QA`, `Ops`
- Stato iniziale: `Todo`

## Epic 1: Fondazione e Contratti

### Issue 1
- Titolo: Congelare glossario di dominio KPI
- Priorita': `P0`
- Tipo: `Backend`
- Descrizione: Formalizzare significato di `ContributionUnit`, `Department`, `ReviewCycle`, `ComplianceGate`, `TenderOutcome`.
- Done when: esiste documento condiviso e referenziato da backend e KPI engine.

### Issue 2
- Titolo: Congelare catalogo eventi canonici
- Priorita': `P0`
- Tipo: `Backend`
- Descrizione: Definire eventi, payload, campi obbligatori, schema version e idempotency strategy.
- Dipendenze: `Issue 1`
- Done when: tutti gli eventi hanno schema JSON e naming definitivo.

### Issue 3
- Titolo: Definire contratti API `v1` del servizio KPI
- Priorita': `P0`
- Tipo: `Backend`
- Descrizione: Formalizzare endpoint ingestione e query con request/response contract.
- Dipendenze: `Issue 2`
- Done when: esiste OpenAPI iniziale approvata.

## Epic 2: Bootstrap del Servizio KPI

### Issue 4
- Titolo: Creare skeleton `tw-kpi-reason-engine`
- Priorita': `P0`
- Tipo: `Infra`
- Descrizione: Nuovo servizio FastAPI con struttura base, config, logging, healthcheck e Dockerfile.
- Dipendenze: `Issue 3`
- Done when: il container sale e risponde a `/health`.

### Issue 5
- Titolo: Introdurre DB dedicato e migrazioni reali
- Priorita': `P0`
- Tipo: `Data`
- Descrizione: Configurare schema o DB dedicato e framework migrazioni.
- Dipendenze: `Issue 4`
- Done when: una migration iniziale crea lo schema del servizio KPI.

### Issue 6
- Titolo: Configurare autenticazione service-to-service
- Priorita': `P0`
- Tipo: `Infra`
- Descrizione: Aggiungere token condiviso o meccanismo equivalente per chiamate `tw-backend` -> KPI engine.
- Dipendenze: `Issue 4`
- Done when: le API KPI rifiutano richieste non autenticate.

### Issue 7
- Titolo: Aggiungere queue e worker per analysis jobs
- Priorita': `P1`
- Tipo: `Infra`
- Descrizione: Configurare Redis e worker dedicato per job di scoring e replay.
- Dipendenze: `Issue 4`
- Done when: un job demo puo' essere accodato ed eseguito.

## Epic 3: Storage Analitico

### Issue 8
- Titolo: Implementare tabella `kpi_tenders`
- Priorita': `P0`
- Tipo: `Backend`
- Descrizione: Mirror locale dei tender con campi minimi e metadati segmento.
- Dipendenze: `Issue 5`
- Done when: il servizio puo' creare/aggiornare mirror di tender.

### Issue 9
- Titolo: Implementare event store `kpi_domain_events`
- Priorita': `P0`
- Tipo: `Backend`
- Descrizione: Persistenza append-only degli eventi con supporto idempotenza.
- Dipendenze: `Issue 5`
- Done when: un evento duplicato non genera doppio record funzionale.

### Issue 10
- Titolo: Implementare `kpi_analysis_jobs`
- Priorita': `P1`
- Tipo: `Backend`
- Descrizione: Persistenza e tracking dei job asincroni.
- Dipendenze: `Issue 7`
- Done when: ogni ricalcolo ha lifecycle `queued/running/success/failed`.

### Issue 11
- Titolo: Implementare `kpi_snapshots` e `kpi_findings`
- Priorita': `P0`
- Tipo: `Backend`
- Descrizione: Persistenza snapshot KPI, findings, confidence, model versions e diagnostica.
- Dipendenze: `Issue 5`
- Done when: un tender puo' avere snapshot multipli versionati.

### Issue 12
- Titolo: Implementare `kpi_phase_transitions`
- Priorita': `P1`
- Tipo: `Backend`
- Descrizione: Memorizzare cambi di fase analitica e salute con cause e confidence.
- Dipendenze: `Issue 11`
- Done when: ogni variazione di stato produce transizione storicizzata.

## Epic 4: Integrazione da `tw-backend`

### Issue 13
- Titolo: Creare `kpi_reason_engine_client` in `tw-backend`
- Priorita': `P0`
- Tipo: `Backend`
- Descrizione: Client interno con timeout, retry corto, auth header e correlation id.
- Dipendenze: `Issue 6`
- Done when: il backend puo' invocare in sicurezza le API del servizio KPI.

### Issue 14
- Titolo: Pubblicare evento `tender_created`
- Priorita': `P0`
- Tipo: `Backend`
- Descrizione: Emissione dal punto di creazione tender.
- Dipendenze: `Issue 13`
- Done when: la creazione tender sincronizza il mirror nel servizio KPI.

### Issue 15
- Titolo: Pubblicare eventi `tender_document_ingested` e `requirements_extracted`
- Priorita': `P0`
- Tipo: `Backend`
- Descrizione: Emissione dall'import del documento tender.
- Dipendenze: `Issue 14`
- Done when: il motore riceve contesto gara e puo' iniziare analisi A-family.

### Issue 16
- Titolo: Pubblicare eventi `proposal_created` e `proposal_section_updated`
- Priorita': `P0`
- Tipo: `Backend`
- Descrizione: Emissione dai punti di creazione e modifica proposal/sections.
- Dipendenze: `Issue 13`
- Done when: il motore riceve aggiornamenti strutturati del contenuto offerta.

### Issue 17
- Titolo: Pubblicare evento `tender_submitted`
- Priorita': `P0`
- Tipo: `Backend`
- Descrizione: Emissione al submit della proposta/tender.
- Dipendenze: `Issue 16`
- Done when: il motore riconosce passaggio verso `S9/S10`.

### Issue 18
- Titolo: Pubblicare `tender_outcome_recorded`
- Priorita': `P1`
- Tipo: `Backend`
- Descrizione: Emissione su `won/lost/cancelled/no-bid` con motivo ed esito.
- Dipendenze: `Issue 17`
- Done when: gli stati assorbenti del modello sono alimentati da eventi espliciti.

## Epic 5: Nuova Telemetria Operativa

### Issue 19
- Titolo: Introdurre entita' `ContributionUnit`
- Priorita': `P0`
- Tipo: `Backend`
- Descrizione: Modellare deliverable richiesto a owner/dipartimento con mapping a sezioni e allegati.
- Dipendenze: `Issue 1`
- Done when: un tender puo' avere contribution units tracciate.

### Issue 20
- Titolo: Introdurre `ContributionRequest` e `ContributionSubmission`
- Priorita': `P0`
- Tipo: `Backend`
- Descrizione: Tracciare richieste, scadenze, SLA e ricezione contributi.
- Dipendenze: `Issue 19`
- Done when: si possono misurare tempi pianificati vs reali e response time.

### Issue 21
- Titolo: Introdurre `ReviewCycle` e `ReviewFinding`
- Priorita': `P0`
- Tipo: `Backend`
- Descrizione: Tracciare review, esiti, gap e non conformita'.
- Dipendenze: `Issue 19`
- Done when: rework e qualita' hanno una fonte dati strutturata.

### Issue 22
- Titolo: Introdurre `ReworkAction`
- Priorita': `P0`
- Tipo: `Backend`
- Descrizione: Tracciare richieste di integrazione bloccanti e risoluzioni.
- Dipendenze: `Issue 21`
- Done when: si puo' calcolare `B4` su base osservata.

### Issue 23
- Titolo: Introdurre `ComplianceGate`
- Priorita': `P1`
- Tipo: `Backend`
- Descrizione: Modellare apertura, esito e motivazioni del gate compliance.
- Dipendenze: `Issue 21`
- Done when: il motore puo' distinguere `S8` in modo affidabile.

### Issue 24
- Titolo: Introdurre `CallSession` e `AttendanceRecord`
- Priorita': `P1`
- Tipo: `Backend`
- Descrizione: Tracciare call pianificate e presenza/assenza dipartimenti.
- Dipendenze: `Issue 19`
- Done when: `B3` e' alimentabile da dati osservati.

### Issue 25
- Titolo: Pubblicare eventi operativi KPI
- Priorita': `P0`
- Tipo: `Backend`
- Descrizione: Emissione di `contribution_request_created`, `contribution_received`, `rework_requested`, `call_attendance_recorded`, `compliance_gate_*`.
- Dipendenze: `Issue 20`, `Issue 21`, `Issue 22`, `Issue 23`, `Issue 24`
- Done when: il motore KPI riceve il ciclo operativo completo del contributo.

## Epic 6: Motore KPI

### Issue 26
- Titolo: Implementare ingestione eventi idempotente
- Priorita': `P0`
- Tipo: `Backend`
- Descrizione: Endpoint KPI per registrare eventi e sincronizzare mirror tender.
- Dipendenze: `Issue 8`, `Issue 9`, `Issue 13`
- Done when: il servizio accetta eventi senza generare incoerenze o duplicazioni.

### Issue 27
- Titolo: Implementare `A1` con output strutturato
- Priorita': `P0`
- Tipo: `AI`
- Descrizione: Valutare copertura requisiti con elenco uncovered/partial e score.
- Dipendenze: `Issue 15`, `Issue 16`, `Issue 26`
- Done when: il KPI restituisce JSON valido e findings persistiti.

### Issue 28
- Titolo: Implementare `A2` con output strutturato
- Priorita': `P1`
- Tipo: `AI`
- Descrizione: Valutare chiarezza, struttura, complessita' linguistica e ambiguita'.
- Dipendenze: `Issue 16`, `Issue 26`
- Done when: il KPI produce score, evidenze e recommendation.

### Issue 29
- Titolo: Implementare `A3` con output strutturato
- Priorita': `P1`
- Tipo: `AI`
- Descrizione: Valutare pertinenza, specificita' e competitivita' tecnica.
- Dipendenze: `Issue 15`, `Issue 16`, `Issue 26`
- Done when: il KPI produce score con spiegazione competitiva.

### Issue 30
- Titolo: Implementare `A4` con output strutturato
- Priorita': `P0`
- Tipo: `AI`
- Descrizione: Individuare non conformita', rischio e score sintetico.
- Dipendenze: `Issue 15`, `Issue 16`, `Issue 26`
- Done when: il KPI produce lista di non conformita' con severita'.

### Issue 31
- Titolo: Implementare `B1` deterministico
- Priorita': `P0`
- Tipo: `Backend`
- Descrizione: Calcolare rispetto deadline su date pianificate vs reali.
- Dipendenze: `Issue 20`, `Issue 25`
- Done when: il KPI distingue puntuale, anticipato e ritardo con score coerente.

### Issue 32
- Titolo: Implementare `B2` deterministico
- Priorita': `P0`
- Tipo: `Backend`
- Descrizione: Calcolare responsivita' su SLA target e SLA max.
- Dipendenze: `Issue 20`, `Issue 25`
- Done when: il KPI produce score `0..10` e classifica responses.

### Issue 33
- Titolo: Implementare `B3` deterministico
- Priorita': `P1`
- Tipo: `Backend`
- Descrizione: Calcolare partecipazione call su presenze/assenze.
- Dipendenze: `Issue 24`, `Issue 25`
- Done when: il KPI misura presenza e assenze non giustificate.

### Issue 34
- Titolo: Implementare `B4` deterministico
- Priorita': `P0`
- Tipo: `Backend`
- Descrizione: Calcolare stabilita' del contributo da rework bloccanti osservati.
- Dipendenze: `Issue 22`, `Issue 25`
- Done when: il KPI misura churn documentale e cause del rework.

### Issue 35
- Titolo: Calcolare indici `Q` ed `E`
- Priorita': `P0`
- Tipo: `Backend`
- Descrizione: Implementare formule aggregate e versionamento formula.
- Dipendenze: `Issue 27`, `Issue 28`, `Issue 29`, `Issue 30`, `Issue 31`, `Issue 32`, `Issue 33`, `Issue 34`
- Done when: ogni snapshot contiene indici sintetici e formula version.

### Issue 36
- Titolo: Implementare `confidence model`
- Priorita': `P0`
- Tipo: `Data`
- Descrizione: Distinguere dati `measured`, `inferred`, `reconstructed` e assegnare confidence.
- Dipendenze: `Issue 11`, `Issue 35`
- Done when: ogni KPI e snapshot espone confidence e data provenance.

## Epic 7: Stato Analitico e Forecast

### Issue 37
- Titolo: Implementare classificazione `Green/Amber/Red`
- Priorita': `P0`
- Tipo: `Backend`
- Descrizione: Applicare le soglie base del PDF su `Q`, `E`, `A4`.
- Dipendenze: `Issue 35`
- Done when: ogni snapshot ha una health class consistente.

### Issue 38
- Titolo: Implementare state classifier `S0..S13`
- Priorita': `P0`
- Tipo: `Backend`
- Descrizione: Derivare fase analitica dal mix di eventi, stato prodotto e KPI.
- Dipendenze: `Issue 25`, `Issue 35`, `Issue 37`
- Done when: ogni tender ha `current_phase` e `current_extended_state`.

### Issue 39
- Titolo: Persistenza transizioni di fase
- Priorita': `P1`
- Tipo: `Backend`
- Descrizione: Scrivere in storico ogni cambio stato/health.
- Dipendenze: `Issue 38`, `Issue 12`
- Done when: la timeline di transizione e' interrogabile.

### Issue 40
- Titolo: Forecast rule-based iniziale
- Priorita': `P1`
- Tipo: `Data`
- Descrizione: Stimare `submit/rework/stop` con matrice iniziale da regole del PDF.
- Dipendenze: `Issue 38`, `Issue 39`
- Done when: il servizio espone probabilita' e confidence del forecast.

### Issue 41
- Titolo: Versionare modello di transizione
- Priorita': `P2`
- Tipo: `Data`
- Descrizione: Salvare matrice, segmento e periodo di validita' del forecast.
- Dipendenze: `Issue 40`
- Done when: il forecast usa una `model_version` esplicita.

## Epic 8: Backend Query e Proxy Admin

### Issue 42
- Titolo: Implementare endpoint proxy admin snapshot/overview
- Priorita': `P0`
- Tipo: `Backend`
- Descrizione: Esporre da `tw-backend` query verso il motore KPI con RBAC admin.
- Dipendenze: `Issue 13`, `Issue 26`, `Issue 35`
- Done when: il frontend admin puo' leggere overview portfolio e tender snapshot.

### Issue 43
- Titolo: Implementare endpoint proxy diagnostics/transitions/forecast
- Priorita': `P1`
- Tipo: `Backend`
- Descrizione: Esporre dettaglio KPI, transizioni e forecast.
- Dipendenze: `Issue 40`, `Issue 42`
- Done when: il frontend admin puo' fare drill-down completo.

### Issue 44
- Titolo: Implementare endpoint `recompute` admin
- Priorita': `P1`
- Tipo: `Backend`
- Descrizione: Consentire trigger di ricalcolo via `tw-backend`.
- Dipendenze: `Issue 10`, `Issue 42`
- Done when: l'admin puo' richiedere re-analysis senza accesso diretto al servizio KPI.

## Epic 9: Frontend Admin

### Issue 45
- Titolo: Aggiungere voce sidebar `Observability KPI`
- Priorita': `P0`
- Tipo: `Frontend`
- Descrizione: Inserire nuova rotta admin nel perimetro di [App.tsx](D:/tender/tenderwriter/frontend/src/App.tsx).
- Dipendenze: `Issue 42`
- Done when: la navigazione admin espone la nuova pagina.

### Issue 46
- Titolo: Costruire vista `Portfolio`
- Priorita': `P0`
- Tipo: `Frontend`
- Descrizione: Mostrare distribuzione tender per stato analitico e salute.
- Dipendenze: `Issue 42`, `Issue 45`
- Done when: l'admin vede overview portfolio aggiornata da API backend.

### Issue 47
- Titolo: Costruire vista `Tender Drilldown`
- Priorita': `P0`
- Tipo: `Frontend`
- Descrizione: Mostrare KPI, findings, evidenze, salute e trend per singolo tender.
- Dipendenze: `Issue 43`, `Issue 45`
- Done when: l'admin puo' aprire un tender e leggerne la diagnostica completa.

### Issue 48
- Titolo: Costruire vista `Transitions & Forecast`
- Priorita': `P1`
- Tipo: `Frontend`
- Descrizione: Mostrare timeline transizioni, stato esteso e percorso probabile.
- Dipendenze: `Issue 43`, `Issue 45`
- Done when: il forecast e la timeline sono leggibili e spiegati.

### Issue 49
- Titolo: Aggiungere azioni admin leggere
- Priorita': `P1`
- Tipo: `Frontend`
- Descrizione: Pulsanti `recompute`, export, note e acknowledge risk.
- Dipendenze: `Issue 44`, `Issue 47`
- Done when: l'admin puo' agire senza alterare la sorgente di verita' del workflow.

## Epic 10: Explainability, Test e Hardening

### Issue 50
- Titolo: Versionare prompt, formule e model metadata
- Priorita': `P0`
- Tipo: `AI`
- Descrizione: Salvare `prompt_version`, `formula_version`, `model_version` in ogni snapshot.
- Dipendenze: `Issue 27`, `Issue 28`, `Issue 29`, `Issue 30`, `Issue 35`
- Done when: ogni score e' riproducibile e confrontabile.

### Issue 51
- Titolo: Costruire golden dataset KPI
- Priorita': `P0`
- Tipo: `QA`
- Descrizione: Preparare scenari attesi per tender sano, rework, rischio compliance ed esclusione.
- Dipendenze: `Issue 35`, `Issue 38`
- Done when: il motore puo' essere confrontato contro expected outputs noti.

### Issue 52
- Titolo: Test end-to-end `tw-backend` -> KPI engine -> frontend admin
- Priorita': `P0`
- Tipo: `QA`
- Descrizione: Coprire ingestione evento, snapshot e rendering dashboard.
- Dipendenze: `Issue 47`
- Done when: esistono test automatici sui flussi chiave.

### Issue 53
- Titolo: Implementare graceful degradation lato backend
- Priorita': `P0`
- Tipo: `Backend`
- Descrizione: Gestire timeout, errori KPI e UI fallback senza rompere l'admin area.
- Dipendenze: `Issue 13`, `Issue 42`
- Done when: il backend risponde in modo controllato anche se il servizio KPI e' down.

### Issue 54
- Titolo: Aggiungere metriche, dashboard e alert
- Priorita': `P0`
- Tipo: `Ops`
- Descrizione: Monitorare latenza, error rate, backlog queue, parse failures, recompute failures.
- Dipendenze: `Issue 7`, `Issue 26`
- Done when: il servizio KPI e' osservabile in produzione.

### Issue 55
- Titolo: Implementare replay e backfill storico
- Priorita': `P1`
- Tipo: `Data`
- Descrizione: Ricalcolare snapshot storici e marcare i dati come `reconstructed`.
- Dipendenze: `Issue 26`, `Issue 35`, `Issue 36`
- Done when: il motore puo' ripopolare il passato senza confondere dati osservati e ricostruiti.

### Issue 56
- Titolo: Runbook operativo del servizio KPI
- Priorita': `P1`
- Tipo: `Ops`
- Descrizione: Documentare deploy, rollback, replay, troubleshooting e limiti del forecast.
- Dipendenze: `Issue 54`, `Issue 55`
- Done when: il team ha una guida operativa completa.

## Milestone Consigliate
- `M1`: Issue `1-18` chiuse
- `M2`: Issue `19-36` chiuse
- `M3`: Issue `37-49` chiuse
- `M4`: Issue `50-56` chiuse

## Definition of Ready per ogni issue
- scopo chiaro;
- dipendenze note;
- contratto tecnico definito;
- owner identificato;
- criterio di done testabile.

## Definition of Done per release `10/10`
- KPI A e B disponibili con provenance e confidence;
- stato analitico `S0..S13` disponibile e spiegabile;
- forecast disponibile con confidence e model version;
- dashboard admin completa;
- fallback backend attivo;
- metriche, alert, runbook e test end-to-end presenti.
