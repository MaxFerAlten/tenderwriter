# Backlog Esecutivo Sprint 14-17

## Scopo

Questo backlog traduce il piano dei prossimi passi e la relativa analisi operativa in task eseguibili.

Documenti di riferimento:

- `D:\tender\tenderwriter\resoningfromagentic\codex\tw-kpi-reason-engine-next-steps-plan.md`
- `D:\tender\tenderwriter\resoningfromagentic\codex\tw-kpi-reason-engine-next-steps-analysis.md`
- `D:\tender\tenderwriter\resoningfromagentic\codex\tw-kpi-reason-engine-next-steps-explained.md`

## Convenzioni

- ID card: `S{Sprint}-T{Task}`
- Owner suggerito: `Product`, `BE-Core`, `BE-Platform`, `FE-Admin`, `AI/Data`, `QA`, `Ops`
- Stato iniziale: `Todo`
- Priorita':
  - `P0` = blocca i workstream successivi
  - `P1` = molto importante ma non blocca tutto
  - `P2` = rifinitura o consolidamento finale
- Formato board consigliato: una card per task

## Percorso critico

Ordine da rispettare:

1. `KPI contract v1`
2. `Transition audit e data quality`
3. `A1/A4 semantic scoring in shadow mode`
4. `Markov core loop v1`
5. `Provenance, confidence e rollout`

## Sprint 14 - KPI Contract e Transition Audit

### Obiettivo sprint

Chiudere il debito semantico del motore e qualificare il dataset che dovra sostenere scoring semantico e Markov.

### S14-T1
- Titolo: Formalizzare `KPI contract v1`
- Owner: `Product`
- Priorita': `P0`
- Dipendenze: nessuna
- Descrizione: fissare in un documento canonico scala ufficiale, formula di `Q` ed `E`, soglie health, schema output score, mapping stati supportati e regole di escalation.
- Done when: esiste un artefatto ufficiale approvato che risolve le divergenze tra specifica, retrospettiva e implementazione.

### S14-T2
- Titolo: Riallineare il motore al contract canonico
- Owner: `BE-Core`
- Priorita': `P0`
- Dipendenze: `S14-T1`
- Descrizione: allineare formule, scale, metadata e nomenclatura del reason engine al `KPI contract v1`, senza correzioni silenziose del passato.
- Done when: il motore espone scale, formule e classi health coerenti con il contract e versionate nel metadata.

### S14-T3
- Titolo: Standardizzare output schema e provenance dei KPI
- Owner: `BE-Core`
- Priorita': `P0`
- Dipendenze: `S14-T1`
- Descrizione: rendere obbligatori per ogni score i campi `score`, `evidences`, `criticalities`, `recommendations`, `confidence`, `source_type`, `formula_version`, `model_version`, `prompt_version`.
- Done when: ogni snapshot ha schema uniforme per KPI base e aggregati.

### S14-T4
- Titolo: Eseguire audit della tassonomia eventi sul core loop
- Owner: `BE-Core`
- Priorita': `P0`
- Dipendenze: nessuna
- Descrizione: mappare eventi effettivamente disponibili per `S4/S5/S6/S8/S9/S10` e verificarne payload, timestamp e consistenza semantica.
- Done when: esiste una matrice eventi -> stati/transizioni con campi richiesti e gap noti.

### S14-T5
- Titolo: Distinguere `observed`, `inferred`, `reconstructed` nel dataset storico
- Owner: `AI/Data`
- Priorita': `P0`
- Dipendenze: `S14-T4`
- Descrizione: classificare chiaramente i dati usati dal motore per evitare che forecast e analytics mescolino fatti osservati, inferenze e backfill.
- Done when: il dataset e i report di audit marcano esplicitamente il tipo sorgente dei dati storici.

### S14-T6
- Titolo: Produrre `transition quality report` sul core loop
- Owner: `AI/Data`
- Priorita': `P0`
- Dipendenze: `S14-T4`, `S14-T5`
- Descrizione: misurare copertura, buchi, coerenza timestamp e ricostruibilita' delle storie tender necessarie al Markov MVP.
- Done when: esiste un report che quantifica copertura delle transizioni e livello di affidabilita' del dataset.

### S14-T7
- Titolo: Test di regressione su contract e transizioni
- Owner: `QA`
- Priorita': `P1`
- Dipendenze: `S14-T2`, `S14-T3`, `S14-T6`
- Descrizione: introdurre test automatici su formula contract, schema output e ricostruzione di transizioni chiave.
- Done when: i test falliscono se il contract o la qualita' minima del dataset vengono violati.

## Sprint 15 - Semantic Scoring Shadow Mode

### Obiettivo sprint

Introdurre reasoning semantico su `A1` e `A4` senza rompere il motore proxy attuale.

### S15-T1
- Titolo: Costruire evaluation dataset annotato per `A1` e `A4`
- Owner: `AI/Data`
- Priorita': `P0`
- Dipendenze: `S14-T1`, `S14-T6`
- Descrizione: selezionare tender campione con requisiti, contributi e outcome sufficienti per confrontare proxy e semantic scoring.
- Done when: esiste un dataset campione versionato e riutilizzabile per benchmark interno.

### S15-T2
- Titolo: Versionare prompt bundle `A1` shadow mode
- Owner: `AI/Data`
- Priorita': `P0`
- Dipendenze: `S15-T1`
- Descrizione: implementare il prompt di copertura requisiti con output strutturato coerente col contract.
- Done when: `A1` produce score, evidenze, coperture parziali/mancanti, recommendation e confidence in formato stabile.

### S15-T3
- Titolo: Versionare prompt bundle `A4` shadow mode
- Owner: `AI/Data`
- Priorita': `P0`
- Dipendenze: `S15-T1`
- Descrizione: implementare il prompt di rischio di non conformita' con output strutturato coerente col contract.
- Done when: `A4` produce elenco non conformita', rischio, recommendation e confidence in formato stabile.

### S15-T4
- Titolo: Integrare pipeline async di semantic scoring in shadow mode
- Owner: `BE-Platform`
- Priorita': `P0`
- Dipendenze: `S14-T3`, `S15-T2`, `S15-T3`
- Descrizione: agganciare il semantic scoring ai job del motore senza sostituire il proxy, persistendo risultati e metadati in parallelo.
- Done when: `A1` e `A4` semantici vengono calcolati asincronamente e salvati come output shadow, separati dal proxy ufficiale.

### S15-T5
- Titolo: Salvare confronto `proxy vs semantic` nello snapshot
- Owner: `BE-Core`
- Priorita': `P1`
- Dipendenze: `S15-T4`
- Descrizione: aggiungere ai risultati del motore un confronto side-by-side tra score proxy e score semantico per tender campione.
- Done when: lo snapshot permette di vedere differenze, delta e source_type dei due approcci.

### S15-T6
- Titolo: Review interna di benchmark `A1/A4`
- Owner: `QA`
- Priorita': `P0`
- Dipendenze: `S15-T5`
- Descrizione: validare su casi reali convergenze, divergenze e soglie di fiducia tra proxy e semantic scoring.
- Done when: esiste un report interno che dice se, dove e come il semantic scoring e abbastanza affidabile per evoluzione futura.

### S15-T7
- Titolo: Esporre drilldown admin per risultati shadow
- Owner: `FE-Admin`
- Priorita': `P2`
- Dipendenze: `S15-T5`
- Descrizione: mostrare nell'admin un confronto leggibile tra output proxy e output semantico, marcato come `shadow`.
- Done when: l'admin puo' consultare il confronto senza confondere il motore sperimentale con quello ufficiale.

## Sprint 16 - Markov Core Loop v1

### Obiettivo sprint

Passare da forecast euristico a primo forecast empirico sui dati osservati del core loop.

### S16-T1
- Titolo: Formalizzare stati e regole di estrazione del Markov MVP
- Owner: `AI/Data`
- Priorita': `P0`
- Dipendenze: `S14-T1`, `S14-T6`
- Descrizione: chiudere la definizione operativa degli stati del Markov v1 su `S4/S5/S6/S8/S9/S10/S11/S12/S13` e delle regole di estrazione dalle transizioni storiche.
- Done when: esiste una definizione univoca degli stati del Markov MVP e delle regole di conteggio `N(i->j)`.

### S16-T2
- Titolo: Costruire builder della matrice di transizione empirica
- Owner: `AI/Data`
- Priorita': `P0`
- Dipendenze: `S16-T1`
- Descrizione: implementare il calcolo delle probabilita' empiriche dal log storico del core loop.
- Done when: il sistema produce una matrice di transizione verificabile e rigenerabile a partire dal dataset storico.

### S16-T3
- Titolo: Versionare e persistere il `Markov model bundle v1`
- Owner: `BE-Core`
- Priorita': `P0`
- Dipendenze: `S16-T2`
- Descrizione: rendere il modello Markov un artefatto versionato, persistito e richiamabile dal motore forecast.
- Done when: il forecast puo' dichiarare quale matrice e quale versione di modello sta usando.

### S16-T4
- Titolo: Integrare forecast Markov v1 in parallelo all'euristico
- Owner: `BE-Core`
- Priorita': `P0`
- Dipendenze: `S16-T3`
- Descrizione: far convivere forecast attuale ed empirico per confronto controllato, senza perdere fallback o degradazione sicura.
- Done when: il motore espone sia il forecast euristico sia il Markov v1 con provenance chiara.

### S16-T5
- Titolo: Backtesting su tender chiusi e stati assorbenti
- Owner: `AI/Data`
- Priorita': `P0`
- Dipendenze: `S16-T4`
- Descrizione: verificare il comportamento del Markov su tender chiusi e controllare assorbimento esplicito di `S11/S12/S13`.
- Done when: esiste un report di backtesting con accuratezza, limiti e casi di scostamento principali.

### S16-T6
- Titolo: Test di stabilita' e fallback del forecast
- Owner: `QA`
- Priorita': `P1`
- Dipendenze: `S16-T4`, `S16-T5`
- Descrizione: validare che il sistema degradi correttamente se il dataset non e sufficiente o il modello non e disponibile.
- Done when: il forecast non rompe il cockpit e segnala chiaramente quando ripiega sul motore euristico.

## Sprint 17 - Productization, Provenance e Rollout

### Obiettivo sprint

Rendere il nuovo motore leggibile, auditabile e rilasciabile in sicurezza lato admin.

### S17-T1
- Titolo: Esporre provenance e confidence complete via backend
- Owner: `BE-Core`
- Priorita': `P0`
- Dipendenze: `S15-T5`, `S16-T4`
- Descrizione: consolidare nel BFF i metadati necessari per spiegare score e forecast.
- Done when: backend admin espone `source_type`, `confidence`, `formula_version`, `model_version`, `prompt_version` e motore forecast attivo.

### S17-T2
- Titolo: Distinguere in UI `observed`, `inferred`, `predicted`, `shadow`, `calibrated`
- Owner: `FE-Admin`
- Priorita': `P0`
- Dipendenze: `S17-T1`
- Descrizione: aggiornare il cockpit admin affinche' l'utente capisca la natura epistemica di ogni dato mostrato.
- Done when: la UI rende leggibile il tipo di dato e il tipo di forecast senza ambiguita'.

### S17-T3
- Titolo: Introdurre feature flag e policy di rollout graduale
- Owner: `BE-Platform`
- Priorita': `P0`
- Dipendenze: `S16-T4`, `S17-T1`
- Descrizione: permettere attivazione progressiva di semantic scoring e Markov v1 per tenant, ambiente o modalita' shadow.
- Done when: il team puo' abilitare o disabilitare i nuovi componenti senza deploy invasivi.

### S17-T4
- Titolo: Creare monitoring e alert su scoring e forecast
- Owner: `Ops`
- Priorita': `P1`
- Dipendenze: `S17-T3`
- Descrizione: monitorare latenza, errori, parse failure, copertura dataset, fallback rate e scostamenti di benchmark.
- Done when: il servizio e osservabile anche nei suoi nuovi layer semantici e probabilistici.

### S17-T5
- Titolo: Costruire regression pack ufficiale del nuovo motore
- Owner: `QA`
- Priorita': `P0`
- Dipendenze: `S15-T6`, `S16-T5`, `S17-T2`
- Descrizione: creare suite di regressione su contract, semantic scoring shadow, forecast euristico e forecast Markov.
- Done when: il team ha una baseline automatica che protegge il contract e il comportamento del motore.

### S17-T6
- Titolo: Redigere runbook e release sign-off del nuovo ciclo KPI
- Owner: `Ops`
- Priorita': `P1`
- Dipendenze: `S17-T3`, `S17-T4`, `S17-T5`
- Descrizione: documentare rollout, rollback, fallback, limiti noti, troubleshooting e criteri di attivazione del nuovo motore.
- Done when: esiste materiale operativo sufficiente per rilasciare in sicurezza e con piena auditabilita'.

## Decisioni da chiudere prima di Sprint 14

### D-1
- Titolo: Scala ufficiale del motore
- Owner: `Product`
- Priorita': `P0`
- Descrizione: decidere ufficialmente se il motore mantiene 0-100 internamente e come presenta eventuale scala 1-10 verso l'esterno.
- Done when: la decisione e recepita nel `KPI contract v1`.

### D-2
- Titolo: Formula canonica di `Q` ed `E`
- Owner: `Product`
- Priorita': `P0`
- Descrizione: chiudere i pesi ufficiali e il versioning delle formule.
- Done when: non esistono piu divergenze tra documento canonico e implementazione attesa.

### D-3
- Titolo: Perimetro del Markov MVP
- Owner: `Product`
- Priorita': `P0`
- Descrizione: confermare che il primo Markov in produzione coprira' solo il core loop e gli stati terminali.
- Done when: la scelta e recepita nel piano e nel contract.

### D-4
- Titolo: Priorita' del semantic scoring
- Owner: `Product`
- Priorita': `P0`
- Descrizione: confermare l'ordine `A1`, `A4`, poi `A2`, `A3`.
- Done when: l'ordine e formalizzato nel backlog e nei deliverable AI/Data.

## Ordine di esecuzione raccomandato

1. Decisioni `D-1` -> `D-4`
2. Sprint 14
3. Sprint 15
4. Sprint 16
5. Sprint 17

## Priorita' trasversali

- `P0`: contract, audit dataset, A1/A4 shadow, Markov v1 core loop, provenance backend/UI, rollout controllato.
- `P1`: test di regressione estesi, monitoring avanzato, fallback hardening, backtesting strutturato.
- `P2`: rifiniture UI e comparazioni admin avanzate non bloccanti.

## Note di sequencing

- Non aprire Sprint 15 senza chiusura sostanziale di `S14-T1` e `S14-T6`.
- Non aprire Sprint 16 senza benchmark minimo su `A1/A4` e audit dataset qualificato.
- Non rilasciare output Markov come forecast ufficiale senza `S17-T1`, `S17-T2` e `S17-T3`.
