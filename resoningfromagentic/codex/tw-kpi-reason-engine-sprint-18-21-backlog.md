# Backlog Esecutivo Sprint 18-21

## Scopo

Questo backlog trasforma il residuo ancora non rilasciato della visione finale del `KPI Reason Engine` in un piano esecutivo completo.

Obiettivo esplicito:

- portare in `gia rilasciato` tutte le voci oggi ancora `parzialmente rilasciate` o `non rilasciate`;
- non lasciare nessuna capability finale fuori perimetro;
- chiudere il gap tra la release attuale e la versione finale pensata in specifica.

Documenti di riferimento:

- `D:\tender\tenderwriter\kpi-reason-engine\docs\KPIReasonEngine.md`
- `D:\tender\tenderwriter\kpi-reason-engine\docs\tw-kpi-reason-engine-final-spec.md`
- `D:\tender\tenderwriter\kpi-reason-engine\docs\kpi_engine_gap_analysis.md`
- `D:\tender\tenderwriter\resoningfromagentic\codex\tw-kpi-reason-engine-next-steps-sprint-backlog.md`
- `D:\tender\tenderwriter\resoningfromagentic\codex\tw-kpi-reason-engine-jira-backlog.md`
- `D:\tender\tenderwriter\resoningfromagentic\codex\2016-03-19-KPI.md`

## Convenzioni

- ID card: `S{Sprint}-T{Task}`
- Owner suggerito: `Product`, `BE-Core`, `BE-Platform`, `FE-Admin`, `AI/Data`, `QA`, `Ops`, `Security`
- Stato iniziale: `Todo`
- Priorita':
  - `P0` = blocca gli sprint successivi o il rilascio finale
  - `P1` = molto importante ma non blocca l'intera sequenza
  - `P2` = rifinitura o hardening finale
- Formato board consigliato: una card per task

## Percorso Critico

Ordine da rispettare:

1. telemetria canonica completa del lifecycle
2. semantic engine finale `A1..A4`
3. Markov full journey + decision support
4. hardening production-grade e chiusura finale

## Vincolo di Perimetro

Questo backlog copre integralmente i seguenti residui:

- telemetria canonica completa
- lifecycle post-submission
- outcome taxonomy finale
- admin cockpit azionabile
- replay e backfill maturi
- `A1`, `A2`, `A3`, `A4` semantici ufficiali
- `Q/E` ufficiali finali
- prompt governance completa
- explainability completa
- Markov full lifecycle
- forecast calibrato e backtested
- retrospective intelligence cross-tender
- motore `next-best action`
- alerting esterno di produzione
- osservabilita tecnica completa del servizio
- golden dataset e test end-to-end finali
- versioning completo di formule, prompt, modelli e output
- separazione architetturale piena del servizio KPI

Out of scope: nessuno.

## Sprint 18 - Lifecycle Canonico Completo

### Obiettivo sprint

Chiudere tutti i buchi di lifecycle ancora presenti tra la specifica finale e il prodotto reale, rendendo `S0..S13` molto piu osservabili e governabili da admin.

### S18-T1
- Titolo: Congelare il catalogo eventi canonici finale `S0..S13`
- Owner: `Product`
- Priorita': `P0`
- Dipendenze: nessuna
- Descrizione: formalizzare il catalogo finale degli eventi di lifecycle ancora mancanti, con schema minimo, source, idempotency, stato target e uso nel KPI engine.
- Done when: esiste un artefatto ufficiale approvato che include almeno `go_decision_recorded`, `no_bid_decision_recorded`, `bid_plan_created`, `bid_plan_approved`, `bid_team_assigned`, `contribution_request_wave_opened`, `contribution_assignment_confirmed`, `draft_integrated_ready`, `clarification_requested`, `clarification_response_drafted`, `clarification_submitted`, `clarification_closed`, `submission_acknowledged`, `submission_failed`, `award_confirmed`, `award_details_recorded`, `loss_reason_recorded`, `tender_excluded`, `tender_withdrawn`, `tender_stopped`.

### S18-T2
- Titolo: Implementare decision lifecycle `Go / No-Bid`
- Owner: `BE-Core`
- Priorita': `P0`
- Dipendenze: `S18-T1`
- Descrizione: introdurre persistence, API e domain events per la decisione iniziale del tender.
- Done when: l'admin puo registrare `go` e `no_bid` con motivazione, il backend pubblica gli eventi dedicati e il KPI engine li ingerisce senza ricostruzioni indirette.

### S18-T3
- Titolo: Implementare `Bid Planning` e ownership canonica
- Owner: `BE-Core`
- Priorita': `P0`
- Dipendenze: `S18-T1`, `S18-T2`
- Descrizione: introdurre eventi e dati espliciti per `S2`, con piano di gara, milestone, assegnazione team e owner.
- Done when: `S2` non e piu derivato da proxy generici ma da `bid_plan_created`, `bid_plan_approved` e `bid_team_assigned` osservabili.

### S18-T4
- Titolo: Canonicalizzare `Request Contributi` e wave di assegnazione
- Owner: `BE-Core`
- Priorita': `P0`
- Dipendenze: `S18-T1`, `S18-T3`
- Descrizione: rendere esplicito `S3` con wave di richiesta, conferma assegnazioni, SLA e copertura dei dipartimenti attesi.
- Done when: il sistema emette `contribution_request_wave_opened` e `contribution_assignment_confirmed`, e il KPI engine puo distinguere `S3` da `S4`.

### S18-T5
- Titolo: Normalizzare review outcome e readiness del draft integrato
- Owner: `BE-Core`
- Priorita': `P0`
- Dipendenze: `S18-T1`
- Descrizione: completare il cuore del loop operativo con outcome review espliciti e predicate robusta di `draft_integrated_ready`.
- Done when: `review_approved`, `review_changes_requested` e `draft_integrated_ready` sono emessi in modo affidabile e `S7` diventa osservabile.

### S18-T6
- Titolo: Implementare il ciclo completo `Submission Reliability + Clarifications`
- Owner: `BE-Core`
- Priorita': `P0`
- Dipendenze: `S18-T1`, `S18-T5`
- Descrizione: modellare `submission_acknowledged`, `submission_failed`, `clarification_requested`, `clarification_response_drafted`, `clarification_submitted` e `clarification_closed`.
- Done when: il post-submission e un sottosistema reale con persistence, timeline, deadline e distinzione robusta tra `S9` e `S10`.

### S18-T7
- Titolo: Implementare outcome taxonomy finale e closure del tender
- Owner: `BE-Core`
- Priorita': `P0`
- Dipendenze: `S18-T1`, `S18-T2`
- Descrizione: introdurre outcome terminali strutturati e distinguere pienamente `win`, `loss`, `excluded`, `withdrawn`, `no_bid`, `stopped`.
- Done when: `S11`, `S12`, `S13` sono classificabili da eventi canonici, con `award_confirmed`, `award_details_recorded`, `loss_reason_recorded`, `tender_excluded`, `tender_withdrawn`, `tender_stopped`.

### S18-T8
- Titolo: Estendere admin cockpit con azioni di governo del lifecycle
- Owner: `FE-Admin`
- Priorita': `P0`
- Dipendenze: `S18-T2`, `S18-T3`, `S18-T4`, `S18-T5`, `S18-T6`, `S18-T7`
- Descrizione: aggiungere superfici admin per decisioni, planning, assignment, clarification, submission reliability e terminal outcomes.
- Done when: l'admin puo governare il lifecycle finale senza uscire dal cockpit e ogni azione lascia audit trail visibile.

### S18-T9
- Titolo: Aggiornare ingestion, transitions, replay e backfill sul lifecycle esteso
- Owner: `BE-Platform`
- Priorita': `P0`
- Dipendenze: `S18-T2`, `S18-T3`, `S18-T4`, `S18-T5`, `S18-T6`, `S18-T7`
- Descrizione: estendere il KPI engine per ingerire tutti i nuovi eventi, supportare replay storico, distinguere `observed/inferred/reconstructed` e riallineare le transizioni.
- Done when: il dataset di lifecycle esteso e replayabile, versionato e usabile da diagnostics e forecast senza corruzione del dato osservato.

### S18-T10
- Titolo: Costruire regression pack del lifecycle finale
- Owner: `QA`
- Priorita': `P1`
- Dipendenze: `S18-T8`, `S18-T9`
- Descrizione: introdurre test automatici su eventi, mapping stato, timeline, replay e admin actions.
- Done when: esiste una suite che protegge `S1`, `S2`, `S3`, `S7`, `S10`, `S13` e fallisce se il lifecycle finale ricade in inferenze fragili.

## Sprint 19 - Semantic Engine Finale

### Obiettivo sprint

Portare il layer qualitativo da `proxy + shadow` a scoring ufficiale completo, benchmarkato e spiegabile.

### S19-T1
- Titolo: Congelare il contract finale dei KPI qualitativi `A1..A4`
- Owner: `Product`
- Priorita': `P0`
- Dipendenze: `S18-T9`
- Descrizione: fissare input, output, sottocriteri, regole di promotion, fallback e ruolo di ogni KPI qualitativo nel motore finale.
- Done when: esiste un contract ufficiale che chiude ambiguita tra `A1` vs `A4`, definisce `A2` e `A3`, e stabilisce come gli score alimentano `Q` e i gate analitici.

### S19-T2
- Titolo: Costruire evaluation e golden set annotato per `A1..A4`
- Owner: `AI/Data`
- Priorita': `P0`
- Dipendenze: `S19-T1`
- Descrizione: preparare dataset annotato da review umana per benchmark, regressione e promozione del semantic scoring.
- Done when: esiste un dataset versionato con casi rappresentativi, evidenze attese, score target e note di adjudication per `A1`, `A2`, `A3`, `A4`.

### S19-T3
- Titolo: Promuovere `A1` e `A4` da shadow a scoring ufficiale
- Owner: `AI/Data`
- Priorita': `P0`
- Dipendenze: `S19-T1`, `S19-T2`
- Descrizione: sostituire il ruolo attuale solo osservativo di `A1/A4` con scoring semantico ufficiale, mantenendo confronto con proxy come fallback o controllo.
- Done when: `A1` e `A4` entrano nello snapshot come score ufficiali, con policy di fallback esplicita e provenienza chiara.

### S19-T4
- Titolo: Implementare `A2` semantic scoring ufficiale
- Owner: `AI/Data`
- Priorita': `P0`
- Dipendenze: `S19-T1`, `S19-T2`
- Descrizione: introdurre pipeline semantica su chiarezza e qualita redazionale con sottocriteri, output strutturato e benchmark.
- Done when: `A2` produce score ufficiale, diagnostic summary, criticalities, recommendation e confidence con stabilita misurata.

### S19-T5
- Titolo: Implementare `A3` semantic scoring ufficiale
- Owner: `AI/Data`
- Priorita': `P0`
- Dipendenze: `S19-T1`, `S19-T2`
- Descrizione: introdurre pipeline semantica su pertinenza, specificita, distintivita e competitivita tecnica.
- Done when: `A3` produce score ufficiale, evidenze e motivazione difendibile rispetto ai requisiti di gara.

### S19-T6
- Titolo: Completare governance di prompt, modelli, schema output e fallback
- Owner: `BE-Platform`
- Priorita': `P0`
- Dipendenze: `S19-T3`, `S19-T4`, `S19-T5`
- Descrizione: introdurre versioning sistematico di `prompt_version`, `model_version`, `output_schema_version`, retry, parse guard e `analysis_failed`.
- Done when: ogni job semantico e completamente tracciato, versionato, rollbackabile e degradabile senza ambiguita.

### S19-T7
- Titolo: Riallineare `Q`, `health` ed explainability al layer qualitativo finale
- Owner: `BE-Core`
- Priorita': `P0`
- Dipendenze: `S19-T3`, `S19-T4`, `S19-T5`, `S19-T6`
- Descrizione: fare in modo che `Q` e la classificazione qualitativa usino gli score semantici finali, con spiegazione completa dei driver.
- Done when: `Q` non dipende piu da placeholder o shadow logic e ogni KPI qualitativo e spiegabile a livello score/evidence/version.

### S19-T8
- Titolo: Esporre drilldown admin finale su evidenze e requirement coverage
- Owner: `FE-Admin`
- Priorita': `P1`
- Dipendenze: `S19-T7`
- Descrizione: aggiungere nella UI un drilldown requirement-level e evidence-level per `A1..A4`, distinguendo score ufficiale, fallback e confidence.
- Done when: l'admin puo vedere coperture mancanti, rischi, evidenze, motivazione del punteggio e versioni analitiche usate.

### S19-T9
- Titolo: Validare semantic engine con benchmark e reviewer agreement
- Owner: `QA`
- Priorita': `P0`
- Dipendenze: `S19-T7`, `S19-T8`
- Descrizione: introdurre regressioni automatiche e review comparativa tra engine, proxy e valutazione umana.
- Done when: esiste un report stabile su accuracy, disagreement rate, parse failure, fallback rate e condizioni di promozione rispettate.

## Sprint 20 - Markov Full Journey + Decision Support

### Obiettivo sprint

Estendere il forecast dal `core loop` al journey completo `S0..S13`, collegando dinamica di stato, KPI finali e supporto decisionale.

### S20-T1
- Titolo: Congelare il modello Markov full-lifecycle
- Owner: `AI/Data`
- Priorita': `P0`
- Dipendenze: `S18-T9`, `S19-T7`
- Descrizione: formalizzare stati, transizioni, assorbimenti, segmentazioni e regole di conteggio per il modello Markov esteso.
- Done when: esiste una definizione ufficiale di `S0..S13`, degli stati assorbenti e delle regole di estrazione coerente con la specifica finale.

### S20-T2
- Titolo: Costruire dataset di transizione full journey e matrici empiriche
- Owner: `AI/Data`
- Priorita': `P0`
- Dipendenze: `S20-T1`
- Descrizione: generare il dataset Markov finale su tutto il lifecycle, sfruttando la telemetria canonica introdotta in `Sprint 18`.
- Done when: il sistema produce matrici di transizione rigenerabili per full journey, con supporto dati e copertura esplicitati.

### S20-T3
- Titolo: Integrare `Markov full journey` nel motore forecast
- Owner: `BE-Core`
- Priorita': `P0`
- Dipendenze: `S20-T2`
- Descrizione: sostituire o promuovere il modello `core loop` con un forecast che considera l'intero percorso `S0..S13`.
- Done when: il forecast ufficiale usa il modello esteso, dichiara la versione del bundle e mantiene fallback esplicito e sicuro.

### S20-T4
- Titolo: Calibrare e backtestare il forecast finale
- Owner: `AI/Data`
- Priorita': `P0`
- Dipendenze: `S20-T3`
- Descrizione: eseguire backtesting su storico chiuso, misurare accuracy, drift, stability e quality of confidence.
- Done when: esiste un report ufficiale con metriche per esito, fase, segmento e condizioni di insufficienza del dato.

### S20-T5
- Titolo: Collegare KPI finali e driver di forecast al journey completo
- Owner: `BE-Core`
- Priorita': `P0`
- Dipendenze: `S19-T7`, `S20-T3`
- Descrizione: far pesare nel forecast i driver finali di qualita, rischio e operativita, evitando scorciatoie troppo euristiche.
- Done when: il forecast spiega driver come `A1`, `A4`, `B1`, `B2`, `B4`, stato corrente e transizioni osservate.

### S20-T6
- Titolo: Implementare retrospective intelligence cross-tender
- Owner: `AI/Data`
- Priorita': `P1`
- Dipendenze: `S20-T2`, `S20-T4`
- Descrizione: introdurre analytics comparative tra gare, dipartimenti, cause di loss, churn, non conformita e stop strategici.
- Done when: esistono viste e dataset che permettono analisi cross-tender coerenti con outcome taxonomy e telemetria finale.

### S20-T7
- Titolo: Costruire motore `next-best action`
- Owner: `AI/Data`
- Priorita': `P1`
- Dipendenze: `S20-T4`, `S20-T5`
- Descrizione: derivare suggerimenti operativi dal forecast e dai KPI finali per indicare l'azione piu utile nel punto corrente del tender.
- Done when: il sistema propone azioni prioritarie spiegate, con driver, confidence e impatto atteso sulla traiettoria.

### S20-T8
- Titolo: Portare l'admin cockpit alla versione decisionale finale
- Owner: `FE-Admin`
- Priorita': `P1`
- Dipendenze: `S20-T3`, `S20-T5`, `S20-T6`, `S20-T7`
- Descrizione: completare la UI con portfolio intelligence, bottleneck analysis, driver del forecast e suggerimenti azionabili.
- Done when: il cockpit admin mostra journey completo, confidence, driver, bottleneck e `next-best action` in modo leggibile e operativo.

### S20-T9
- Titolo: Proteggere il forecast finale con regression e drift suite
- Owner: `QA`
- Priorita': `P1`
- Dipendenze: `S20-T4`, `S20-T8`
- Descrizione: creare test automatici e controlli di coerenza per modello, fallback, confidence e suggerimenti.
- Done when: il forecast finale non puo degradare silenziosamente senza essere intercettato da suite o benchmark.

## Sprint 21 - Production Final Closure

### Obiettivo sprint

Chiudere il perimetro `10/10` del servizio KPI come componente di produzione autonoma, osservabile, sicura e governabile.

### S21-T1
- Titolo: Definire `SLO`, alerting esterno e policy di escalation
- Owner: `Ops`
- Priorita': `P0`
- Dipendenze: `S20-T3`
- Descrizione: formalizzare metriche di disponibilita e alert esterni per error rate, timeout, job backlog, parse failure, fallback rate e drift.
- Done when: esistono soglie ufficiali, destinazioni di alert, runbook di escalation e coverage dei failure mode principali.

### S21-T2
- Titolo: Implementare osservabilita tecnica completa del servizio KPI
- Owner: `Ops`
- Priorita': `P0`
- Dipendenze: `S21-T1`
- Descrizione: completare metriche applicative, healthcheck, readiness, tracing, structured logging e dashboard operative.
- Done when: il servizio KPI e monitorabile end-to-end e ogni failure mode critico lascia segnali osservabili fuori dalla sola UI admin.

### S21-T3
- Titolo: Finalizzare golden dataset, replay e backfill governati
- Owner: `AI/Data`
- Priorita': `P0`
- Dipendenze: `S18-T9`, `S19-T9`, `S20-T4`
- Descrizione: creare golden dataset finale, policy di aggiornamento, replay certificato e backfill governato senza contaminazione del dato osservato.
- Done when: esistono dataset gold ufficiali, runbook di replay/backfill e verifiche che preservano `observed`, `inferred`, `reconstructed`.

### S21-T4
- Titolo: Costruire test end-to-end completi sui flussi chiave
- Owner: `QA`
- Priorita': `P0`
- Dipendenze: `S18-T10`, `S19-T9`, `S20-T9`
- Descrizione: coprire con E2E i flussi di lifecycle, semantic scoring, forecast, admin actions, replay e degradazione.
- Done when: i flussi chiave da `S0` a esito terminale sono coperti da test end-to-end affidabili e ripetibili.

### S21-T5
- Titolo: Chiudere la governance completa di versioni e release
- Owner: `BE-Platform`
- Priorita': `P0`
- Dipendenze: `S19-T6`, `S20-T3`
- Descrizione: governare in modo sistematico `formula_version`, `prompt_version`, `model_version`, `output_schema_version`, bundle di forecast e policy di rollback.
- Done when: ogni snapshot e forecast dichiara versioni complete e il team puo fare release/rollback senza ambiguita sul motore attivo.

### S21-T6
- Titolo: Completare sicurezza, audit log e confini di rete del servizio
- Owner: `Security`
- Priorita': `P0`
- Dipendenze: `S18-T8`, `S21-T2`
- Descrizione: chiudere autenticazione service-to-service, audit log per azioni admin sensibili, segreti dedicati, accesso solo interno e hardening dei confini.
- Done when: il servizio KPI rispetta i requisiti di sicurezza della spec finale e tutte le azioni sensibili sono auditabili.

### S21-T7
- Titolo: Portare il servizio KPI a separazione architetturale piena
- Owner: `BE-Platform`
- Priorita': `P1`
- Dipendenze: `S21-T2`, `S21-T5`, `S21-T6`
- Descrizione: completare autonomia di deploy, schema/credenziali dedicate, isolamento operativo e disciplina di migrazione del servizio KPI.
- Done when: il servizio KPI e deployabile e governabile come sottosistema realmente autonomo, senza dipendenze opache dal backend transazionale.

### S21-T8
- Titolo: Eseguire audit finale di acceptance e sign-off `10/10`
- Owner: `Product`
- Priorita': `P0`
- Dipendenze: `S21-T3`, `S21-T4`, `S21-T5`, `S21-T6`, `S21-T7`
- Descrizione: verificare una per una le condizioni della specifica finale, dei documenti di gap e del backlog, certificando che il residuo sia chiuso.
- Done when: esiste un sign-off finale che dichiara tutte le capability in `gia rilasciato`, senza eccezioni o residui aperti.

## Sequenza di Delivery Consigliata

Ordine consigliato:

1. `Sprint 18`
2. `Sprint 19`
3. `Sprint 20`
4. `Sprint 21`

Motivo:

- `Sprint 18` rende vero il lifecycle finale e crea la telemetria necessaria.
- `Sprint 19` completa il motore qualitativo finale sopra una base dati credibile.
- `Sprint 20` estende il forecast all'intero journey e aggiunge il supporto decisionale.
- `Sprint 21` chiude tutto il perimetro production-grade e l'accettazione finale.

## Matrice di Copertura del Perimetro

| Capability residua | Sprint / Task di chiusura |
|---|---|
| `telemetria canonica completa` | `S18-T1`, `S18-T2`, `S18-T3`, `S18-T4`, `S18-T5`, `S18-T6`, `S18-T7`, `S18-T9` |
| `lifecycle post-submission` | `S18-T6`, `S18-T8`, `S18-T9`, `S18-T10` |
| `outcome taxonomy finale` | `S18-T7`, `S18-T8`, `S18-T9` |
| `admin cockpit azionabile` | `S18-T8`, `S20-T8` |
| `replay e backfill maturi` | `S18-T9`, `S21-T3` |
| `A1 semantic ufficiale` | `S19-T1`, `S19-T2`, `S19-T3`, `S19-T6`, `S19-T7`, `S19-T9` |
| `A4 semantic ufficiale` | `S19-T1`, `S19-T2`, `S19-T3`, `S19-T6`, `S19-T7`, `S19-T9` |
| `A2 semantic ufficiale` | `S19-T1`, `S19-T2`, `S19-T4`, `S19-T6`, `S19-T7`, `S19-T9` |
| `A3 semantic ufficiale` | `S19-T1`, `S19-T2`, `S19-T5`, `S19-T6`, `S19-T7`, `S19-T9` |
| `Q/E ufficiali finali` | `S19-T7` |
| `prompt governance completa` | `S19-T6`, `S21-T5` |
| `explainability completa` | `S19-T7`, `S19-T8`, `S20-T8`, `S21-T5` |
| `Markov full lifecycle` | `S20-T1`, `S20-T2`, `S20-T3` |
| `forecast calibrato e backtested` | `S20-T4`, `S20-T9` |
| `retrospective intelligence cross-tender` | `S20-T6`, `S20-T8` |
| `motore next-best action` | `S20-T7`, `S20-T8`, `S20-T9` |
| `alerting esterno di produzione` | `S21-T1`, `S21-T2` |
| `osservabilita tecnica completa` | `S21-T1`, `S21-T2` |
| `golden dataset e E2E finali` | `S21-T3`, `S21-T4` |
| `versioning completo formula/prompt/model/output` | `S19-T6`, `S21-T5` |
| `separazione architetturale piena del servizio KPI` | `S21-T7` |
| `sign-off finale 10/10` | `S21-T8` |

## Definition of Done Trasversale

Una capability si considera davvero passata in `gia rilasciato` solo se:

- esiste codice funzionante nei moduli coinvolti;
- esiste persistenza coerente dove richiesta;
- il backend e il frontend la espongono in modo leggibile;
- il KPI engine la usa davvero, se fa parte del motore analitico;
- esistono test automatici o benchmark adeguati;
- provenance, versioni e fallback sono espliciti;
- esiste copertura operativa o runbook se la capability tocca produzione;
- non resta dipendente da placeholder, shadow-only, proxy fragile o inferenza non dichiarata.
