# Backlog Esecutivo Sprint 9-13

## Convenzioni
- ID card: `S{Sprint}-T{Task}`
- Owner suggerito: `BE-Core`, `BE-Platform`, `FE-Admin`, `AI/Data`, `QA`, `Ops`
- Stato iniziale: `Todo`
- Formato Trello consigliato: una card per task

## Sprint 9 - Storage Hardening

### S9-T1
- Titolo: Introdurre migrazioni reali nel servizio KPI
- Owner: `BE-Platform`
- Priorita': `Must`
- Dipendenze: nessuna
- Descrizione: aggiungere framework migrazioni e baseline schema per `tw-kpi-reason-engine`.
- Done when: il servizio crea e aggiorna lo schema via migration versionata.

### S9-T2
- Titolo: Modellare tabelle persistenti per snapshot, findings, transitions e model versions
- Owner: `BE-Core`
- Priorita': `Must`
- Dipendenze: `S9-T1`
- Descrizione: stabilizzare il modello dati analitico superando lo store leggero attuale.
- Done when: esistono tabelle persistenti dedicate e repository coerenti.

### S9-T3
- Titolo: Rifattorizzare store KPI su repository persistenti
- Owner: `BE-Core`
- Priorita': `Must`
- Dipendenze: `S9-T2`
- Descrizione: spostare la logica critica di persistenza su access layer stabile.
- Done when: snapshot, findings e transitions vengono letti e scritti senza dipendere da shortcut locali.

### S9-T4
- Titolo: Rafforzare idempotenza su ingestione eventi e tender sync
- Owner: `BE-Core`
- Priorita': `Must`
- Dipendenze: `S9-T2`
- Descrizione: consolidare chiavi idempotenti, deduplica e retry-safe behavior.
- Done when: reinvio dello stesso evento non altera lo stato funzionale.

### S9-T5
- Titolo: Test di persistenza e regressione storage KPI
- Owner: `QA`
- Priorita': `Must`
- Dipendenze: `S9-T3`, `S9-T4`
- Descrizione: coprire bootstrap schema, ingestione, snapshot e riavvio servizio.
- Done when: test verdi su persistenza, riavvio e deduplica.

## Sprint 10 - Async Jobs e Recompute

### S10-T1
- Titolo: Attivare queue e worker per analysis jobs
- Owner: `BE-Platform`
- Priorita': `Must`
- Dipendenze: `S9-T5`
- Descrizione: collegare `analysis-jobs` a una pipeline async reale.
- Done when: un job viene accodato, eseguito e tracciato.

### S10-T2
- Titolo: Completare lifecycle job `queued/running/success/failed`
- Owner: `BE-Core`
- Priorita': `Must`
- Dipendenze: `S10-T1`
- Descrizione: rendere affidabile il tracking di ricalcolo e replay.
- Done when: ogni job ha stato finale, timestamps ed errore serializzato se fallisce.

### S10-T3
- Titolo: Esportare endpoint backend admin `recompute`
- Owner: `BE-Core`
- Priorita': `Must`
- Dipendenze: `S10-T2`
- Descrizione: esporre via BFF il trigger di ricalcolo KPI.
- Done when: `tw-backend` accetta richiesta admin e la inoltra al motore KPI.

### S10-T4
- Titolo: Integrare azione `recompute` nella dashboard admin
- Owner: `FE-Admin`
- Priorita': `Should`
- Dipendenze: `S10-T3`
- Descrizione: aggiungere CTA, feedback di loading e stato job nella UI admin.
- Done when: l'admin puo' lanciare un ricalcolo e vedere l'esito.

### S10-T5
- Titolo: Graceful degradation tra backend e KPI engine
- Owner: `BE-Core`
- Priorita': `Must`
- Dipendenze: `S10-T3`
- Descrizione: gestire timeout, fallback e risposte degradate senza rompere l'admin.
- Done when: il backend risponde in modo controllato anche se il motore KPI e' indisponibile.

### S10-T6
- Titolo: Test di integrazione su recompute async
- Owner: `QA`
- Priorita': `Must`
- Dipendenze: `S10-T4`, `S10-T5`
- Descrizione: coprire flusso admin -> backend -> worker -> snapshot aggiornato.
- Done when: il flusso di ricalcolo e' verificato automaticamente.

## Sprint 11 - KPI Quality ed Explainability

### S11-T1
- Titolo: Implementare KPI `A2` con output strutturato
- Owner: `AI/Data`
- Priorita': `Must`
- Dipendenze: `S10-T6`
- Descrizione: valutare chiarezza e qualita' redazionale con schema JSON stabile.
- Done when: `A2` produce score, evidence, recommendation e confidence.

### S11-T2
- Titolo: Implementare KPI `A3` con output strutturato
- Owner: `AI/Data`
- Priorita': `Must`
- Dipendenze: `S10-T6`
- Descrizione: valutare competitivita' e valore tecnico dell'offerta.
- Done when: `A3` produce score, evidence, recommendation e confidence.

### S11-T3
- Titolo: Hardening `A1` e `A4`
- Owner: `AI/Data`
- Priorita': `Must`
- Dipendenze: `S10-T6`
- Descrizione: completare output strutturato, severita', recommendation e stabilita' parsing.
- Done when: `A1` e `A4` sono persistiti con finding e schema coerente.

### S11-T4
- Titolo: Consolidare `Q` ed `E` finali con provenance e confidence
- Owner: `BE-Core`
- Priorita': `Must`
- Dipendenze: `S11-T1`, `S11-T2`, `S11-T3`
- Descrizione: completare indici sintetici con distinzione `measured/inferred/reconstructed`.
- Done when: ogni snapshot espone `Q`, `E`, provenance e confidence.

### S11-T5
- Titolo: Versionare prompt, formule e model metadata
- Owner: `BE-Core`
- Priorita': `Must`
- Dipendenze: `S11-T4`
- Descrizione: salvare `prompt_version`, `formula_version`, `model_version`.
- Done when: ogni score analitico e' confrontabile e riproducibile.

### S11-T6
- Titolo: Mostrare explainability completa in admin
- Owner: `FE-Admin`
- Priorita': `Should`
- Dipendenze: `S11-T5`
- Descrizione: visualizzare evidence, findings, provenance e recommendation.
- Done when: il drilldown tender rende leggibile il perche' di ogni score.

## Sprint 12 - Forecast e History

### S12-T1
- Titolo: Completare persistenza storica delle transizioni
- Owner: `BE-Core`
- Priorita': `Must`
- Dipendenze: `S11-T5`
- Descrizione: storicizzare in modo affidabile cambi fase e health.
- Done when: la timeline analitica e' consultabile e persistita.

### S12-T2
- Titolo: Implementare forecast rule-based iniziale
- Owner: `AI/Data`
- Priorita': `Should`
- Dipendenze: `S12-T1`
- Descrizione: stimare `submit/rework/stop` con regole iniziali del modello.
- Done when: il servizio espone scenari, probability e confidence.

### S12-T3
- Titolo: Esporre forecast completo via backend proxy
- Owner: `BE-Core`
- Priorita': `Should`
- Dipendenze: `S12-T2`
- Descrizione: consolidare query forecast nel BFF admin.
- Done when: il frontend legge forecast dal backend in modo stabile.

### S12-T4
- Titolo: Completare vista admin `Transitions & Forecast`
- Owner: `FE-Admin`
- Priorita': `Should`
- Dipendenze: `S12-T3`
- Descrizione: rendere leggibile il percorso probabile e i driver principali.
- Done when: la vista combina timeline, stato e forecast.

### S12-T5
- Titolo: Implementare replay e backfill storico
- Owner: `AI/Data`
- Priorita': `Should`
- Dipendenze: `S12-T1`, `S11-T4`
- Descrizione: ricostruire snapshot passati marcando il dato come `reconstructed`.
- Done when: il motore puo' ripopolare storico senza confondere dati osservati e ricostruiti.

### S12-T6
- Titolo: Testare scenari chiave di stato e forecast
- Owner: `QA`
- Priorita': `Should`
- Dipendenze: `S12-T2`, `S12-T5`
- Descrizione: coprire casi `healthy`, `rework`, `compliance risk`, `excluded`.
- Done when: i casi chiave hanno expected outputs verificati.

## Sprint 13 - Release Readiness

### S13-T1
- Titolo: Costruire golden dataset KPI ufficiale
- Owner: `QA`
- Priorita': `Must`
- Dipendenze: `S11-T5`, `S12-T1`
- Descrizione: definire casi campione con output attesi e baseline condivisa.
- Done when: il team ha un dataset di regressione stabile.

### S13-T2
- Titolo: Test end-to-end completi sul flusso KPI
- Owner: `QA`
- Priorita': `Must`
- Dipendenze: `S13-T1`, `S10-T6`
- Descrizione: coprire ingestione, scoring, query backend e rendering admin.
- Done when: esistono test automatici E2E sui flussi KPI principali.

### S13-T3
- Titolo: Aggiungere metriche, dashboard e alert del servizio KPI
- Owner: `Ops`
- Priorita': `Must`
- Dipendenze: `S10-T1`
- Descrizione: misurare latenza, error rate, backlog, parse failure e recompute failure.
- Done when: il servizio KPI e' osservabile in produzione.

### S13-T4
- Titolo: Scrivere runbook operativo del modulo KPI
- Owner: `Ops`
- Priorita': `Should`
- Dipendenze: `S13-T3`, `S12-T5`
- Descrizione: documentare deploy, rollback, replay, troubleshooting e limiti del forecast.
- Done when: il team dispone di una guida operativa completa.

### S13-T5
- Titolo: Rifinire audit trail ed error model admin
- Owner: `BE-Core`
- Priorita': `Must`
- Dipendenze: `S10-T5`, `S11-T6`
- Descrizione: completare tracciamento di azioni admin e risposta errori coerente.
- Done when: le azioni admin sono auditabili e gli errori sono consistenti.

### S13-T6
- Titolo: Release checklist e sign-off finale
- Owner: `BE-Core`
- Priorita': `Must`
- Dipendenze: `S13-T2`, `S13-T3`, `S13-T4`, `S13-T5`
- Descrizione: chiudere checklist di rilascio del modulo KPI.
- Done when: esiste evidenza di readiness tecnica e operativa.

## Ordine di Esecuzione Raccomandato
1. Sprint 9
2. Sprint 10
3. Sprint 11
4. Sprint 12
5. Sprint 13

## Priorita' Trasversali
- `Must`: storage robusto, async jobs, KPI qualitativi completi, provenance/confidence, fallback, E2E, metriche.
- `Should`: forecast, replay/backfill, azioni admin leggere complete, runbook.
- `Later`: forecast data-driven avanzato, ottimizzazioni UX supplementari, separazione fisica completa del DB KPI.
