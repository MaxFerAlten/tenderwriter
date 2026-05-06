La sintesi è questa:

**rispetto a quanto abbiamo discusso in chat, TenderWriter ha implementato già circa l’80–85% della roadmap.**  
Il grosso del lavoro è stato fatto. Quello che resta è soprattutto **rifinitura, integrazione finale e hardening**, non più “greenfield”.

## Stima per wave

|Area discussa|Stato stimato|
|---|---|
|Wave 1 — ontology + tool foundation|**95%**|
|Wave 2 — agent + explainability + lifecycle graph|**80–85%**|
|Wave 3 — personas + rehearsal + manual rework conversion|**75–80%**|
|PR-10 / forecast enrichment finale|**40–60%**|
|**Totale roadmap discussa**|**80–85%**|

## Cosa risulta già fatto

### 1) Wave 1 è sostanzialmente atterrata

Nel file compaiono davvero:

- `backend/app/intelligence/ontology.py`
- `tool_registry.py`
- i tool `coverage_analyzer.py`, `evidence_auditor.py`, `compliance_panorama.py`
- il router `backend/app/api/intelligence.py`
- la UI `frontend/src/pages/TenderIntelligence.tsx` e `frontend/src/features/intelligence/RehearsalPanel.tsx`.

In pratica la parte “MiroFish → tool espliciti invece di chat generica” è stata recepita bene: il registry costruisce davvero i tool di Wave 1 e 2, non è solo scaffolding.

### 2) Wave 2 è stata implementata in modo serio

Nel package `backend/app/intelligence/` sono presenti:

- `agent.py`
- `graph_path_explainer.py`
- `contradiction_finder.py`
- `lifecycle_projector.py`
- `result_models.py`
- `prompts.py`.

Inoltre `operational_workflow.py` importa già `project_workflow_events`, quindi la projection del lifecycle non è rimasta teorica: è stata almeno agganciata al workflow reale delle sezioni/contribution/review.

Questo significa che il “cervello investigativo” stile MiroFish è stato portato in TenderWriter:

- tool grounded,
- agent read-only,
- explain path,
- contradiction scan,
- lifecycle projection.

### 3) Wave 3 è atterrata molto più di quanto mi aspettassi

Nel repo ci sono davvero:

- `personas.py`
- `persona_catalog.py`
- `rehearsal.py`
- `rehearsal_runner.py`
- `rehearsal_converter.py`
- `rehearsal_summary.py`
- `backend/app/models/rehearsal.py`
- migrazione `20260419_0012_add_rehearsal_tables.py`.

E lato API il router intelligence espone già:

- `POST /query`
- tool endpoints
- `POST /rehearsals`
- `GET /rehearsals/{id}`
- `POST /rehearsals/{id}/recommendations/{rec_id}/accept`
- `POST /rehearsals/{id}/recommendations/{rec_id}/dismiss`
- `GET /tenders/{tender_id}/rehearsal-summary`.

Questa è una prova forte che:

- il rehearsal è reale,
- i reviewer sintetici sono stati modellati,
- la conversione manuale recommendation → rework è stata pensata nel modo giusto,
- il sistema blocca il rehearsal su tender già `submitted/won/lost/cancelled`, quindi la governance è coerente con quanto avevamo stabilito.

### 4) La copertura test è ampia

Nel file compaiono test specifici per:

- ontologia,
- intelligence tools,
- intelligence agent,
- wave 2 tools,
- lifecycle projector,
- rehearsal API,
- rehearsal runner,
- rehearsal converter,
- rehearsal summary.

Questo è importante: non stiamo guardando solo a file “messi lì”, ma a una feature branch che ha anche test dedicati.

---

## Cosa è stato fatto “bene” rispetto alla chat

Qui TenderWriter ha recepito il meglio di MiroFish **senza copiarne i punti deboli**:

### Bene

- tool espliciti al posto della sola chat;
- agent orchestratore read-only;
- personas deterministiche e non “romanzate”;
- rehearsal come layer separato e persistito;
- conversione recommendation → rework **solo manuale**;
- lifecycle projector agganciato al workflow;
- niente IPC file-based, niente polling su cartelle stile MiroFish.

Questa è esattamente la direzione che avevamo discusso.

---

## Cosa manca ancora

Qui sta il 15–20% residuo.

### 1) Forecast enrichment finale: **parziale / non ancora chiuso**

Vedo chiaramente il servizio `rehearsal_summary.py` e i test `test_rehearsal_summary.py`, quindi la parte backend locale del summary esiste.

Però, nel materiale che ho potuto verificare, **non emerge in modo altrettanto chiaro** l’integrazione completa del blocco `rehearsal_summary` dentro il `kpi-reason-engine/app/forecasting.py` e nel render attuale di `ForecastTab.tsx`. Il `ForecastTab` che si vede continua a mostrare summary, confidence, forecast signal, scenarios, ma non compare nel frammento un pannello esplicito rehearsal-aware.

La mia lettura quindi è:

- **backend summary locale: fatto**
- **forecast engine / FE surfacing finale: parziale o non ancora consolidato**

### 2) Lifecycle projector: **implementato, ma da hardenizzare**

Il projector c’è e l’aggancio al workflow c’è.  
Quello che non posso certificare dal pack è quanto sia già:

- completo su tutti gli eventi canonici,
- robusto ai retry,
- coerente in tutti i casi edge,
- allineato su lunga catena section → contribution → review → rework → gate.

Quindi la feature è presente, ma probabilmente è ancora in una fase “works + tests”, non ancora “battle-hardened”.

### 3) Rehearsal: **molto avanti, ma da industrializzare**

Il blocco rehearsal è già vero. Però restano tre lavori tipici di chiusura:

- tuning dei reviewer per ridurre feedback generico,
- caching/costi,
- validazione qualitativa su tender reali.

In altre parole: **c’è il motore**, ma serve ancora calibrazione per farlo diventare affidabile come strumento quotidiano.

### 4) ProposalWriterAgent / scrittura agentica delle sezioni: **non la vedo**

Nella roadmap iniziale avevamo anche ipotizzato un livello più spinto, tipo `ProposalWriterAgent`/ReACT applicato alla generazione delle sezioni proposta.

Nel file non vedo un modulo equivalente dedicato a questo. Vedo intelligence, explainability, rehearsal e conversione a rework, ma **non vedo ancora un agente di scrittura proposta veramente separato dal flusso classico**.

Questa è una delle parti principali ancora mancanti, se vuoi arrivare alla visione “TenderWriter non solo valuta, ma scrive/riscrive in modo agentico”.

### 5) UI finale unificata: **presente ma probabilmente non ancora rifinita**

La pagina `TenderIntelligence.tsx` esiste e usa `RehearsalPanel`, tool buttons, query libera e risultati multipli.  
Quindi la feature è atterrata davvero.

Però non ho evidenza nel pack che:

- tutto sia già perfettamente innestato dentro le viste observability esistenti,
- il forecast tab sia già arricchito fino in fondo,
- il flusso utente completo sia già “production polished”.

---

## Valutazione finale per blocco

### Implementato davvero

- ontology tagging
- tool registry
- coverage/evidence/compliance tools
- contradiction finder
- graph path explainer
- intelligence agent
- lifecycle projector
- personas catalog
- rehearsal persistence
- rehearsal API
- accept/dismiss recommendation
- FE intelligence page
- test pack dedicato

Tutto questo risulta **concreto nel repo**, non solo pianificato.

### Parziale / da chiudere

- integrazione rehearsal → forecast end-to-end
- maturità runtime del lifecycle projector
- qualità/costo/calibrazione dei reviewer sintetici
- UX finale cross-observability
- eventuale proposal-writer agent

---

## La mia stima più onesta

Se prendo come baseline **tutto quello che abbiamo discusso in chat**, la situazione oggi è:

- **fatto:** circa **80–85%**
- **da fare:** circa **15–20%**

Ma il punto importante è un altro:

**non manca più l’architettura. Manca la rifinitura operativa.**

La parte difficile — modellare intelligence, tool, lifecycle, personas, rehearsal e conversione controllata verso il workflow — è già entrata nel codice. Quello che resta è soprattutto:

- chiudere l’arricchimento forecast,
- testare meglio i loop reali,
- migliorare UX e affidabilità,
- decidere se spingere anche sulla scrittura agentica della proposta.

Se vuoi, nel prossimo messaggio ti faccio una **matrice “fatto / parziale / mancante” file-per-file**, così vedi precisamente dove collocare ogni modulo del piano rispetto a `tenderwriter2.md`.

si

Verifico due punti prima di chiudere la matrice: forecast/rehearsal end-to-end e presenza o meno di uno strato di scrittura agentica della proposta, così il quadro “fatto/parziale/mancante” resta preciso.

Thought for 1m 26s

Sì. Ti faccio una **matrice affondo “fatto / parziale / mancante”** rispetto a quanto avevamo discusso, usando `tenderwriter2.md` come baseline reale del codebase. Il quadro che emerge è migliore di quanto sembrava prima: la roadmap è **molto avanti**, ma con una divergenza importante su PR-10 e con un blocco ancora assente, cioè il **ProposalWriterAgent**.

## Valutazione sintetica aggiornata

Se considero la roadmap discussa in chat come composta da:

- Wave 1: ontology + tool foundation
- Wave 2: agent + explainability + lifecycle graph
- Wave 3: personas + rehearsal + recommendation → rework
- PR-10: forecast enrichment finale
- extra opzionale: ProposalWriterAgent / scrittura agentica proposta

allora la stima aggiornata è:

- **fatto:** ~**85–90%**
- **da fare:** ~**10–15%**

Se invece includo anche il **ProposalWriterAgent** come obiettivo pieno, allora scendi a circa:

- **fatto:** ~**80–85%**
- **da fare:** ~**15–20%**

La differenza sta tutta lì: il nucleo intelligence/rehearsal c’è, la scrittura agentica vera della proposta no.

---

# Matrice file-per-file / blocco-per-blocco

## 1) `backend/app/intelligence/ontology.py`

**Stato:** **FATTO**

Perché:

- il file esiste;
- l’ontologia è deterministica, keyword/rule based, con `RequirementOntologyTag`, domini stabili e `ONTOLOGY_VERSION`;
- il servizio espone `tag_text`, `tag_candidate` e `attach_ontology_to_candidates`, cioè esattamente il layer ontology-first che avevamo discusso.

**Conclusione:** Wave 1 lato ontologia è sostanzialmente chiusa.

---

## 2) `backend/app/intelligence/tool_registry.py`

**Stato:** **FATTO**

Perché:

- esiste il registry;
- `build_default_tool_registry()` registra davvero i tool Wave 1 e 2: `CoverageAnalyzer`, `EvidenceAuditor`, `CompliancePanorama`, `GraphPathExplainer`, `ContradictionFinder`.

**Conclusione:** il pattern MiroFish “tool-first” è stato portato davvero.

---

## 3) `backend/app/intelligence/tools/coverage_analyzer.py`

**Stato:** **FATTO**

Perché:

- il tool esiste;
- riusa `build_compliance_requirement_coverage`, quindi non crea una seconda semantica;
- produce summary, by_domain e gaps, cioè esattamente il coverage audit che avevamo progettato.

---

## 4) `backend/app/intelligence/tools/evidence_auditor.py`

**Stato:** **FATTO**

Perché:

- il tool esiste;
- classifica `strong / weak / missing`;
- è esplicitamente read-only e grounded su stato sezione/citation metadata, come avevamo richiesto.

---

## 5) `backend/app/intelligence/tools/compliance_panorama.py`

**Stato:** **FATTO**

Perché:

- il tool esiste;
- fa da adapter verso KPI reason engine e non ricostruisce la logica in proprio;
- consolida health, analytical phase, gate summary e top risks.

---

## 6) `backend/app/api/intelligence.py`

**Stato:** **FATTO**

Perché:

- espone davvero tutti gli endpoint Wave 1/2/3:
    - `/tools/*`
    - `/query`
    - `/rehearsals`
    - `/rehearsals/{id}`
    - accept/dismiss recommendation
    - `/tenders/{tender_id}/rehearsal-summary`
- contiene anche il guard admin per accept/dismiss e il blocco che impedisce rehearsal su tender `submitted/won/lost/cancelled`.

**Conclusione:** l’API surface è molto più completa di una semplice scaffolding.

---

## 7) `backend/app/intelligence/agent.py`

**Stato:** **FATTO**

Perché:

- il file esiste;
- implementa davvero il loop controllato:
    - classify intent
    - select tools
    - run tools
    - synthesize answer
- il contratto è read-only, con `recommended_actions` solo suggerite.

**Conclusione:** Wave 2 lato agent è atterrata.

---

## 8) `backend/app/intelligence/tools/graph_path_explainer.py`

**Stato:** **FATTO**

Perché:

- il tool esiste;
- ricostruisce la catena requirement → section → contribution → review/rework/gate;
- è deterministic/LLM-free, cioè in linea con la filosofia che avevamo stabilito.

---

## 9) `backend/app/intelligence/tools/contradiction_finder.py`

**Stato:** **FATTO**

Perché:

- esiste;
- rileva le 3 famiglie di contraddizione che avevamo discusso:
    - requirement vs proposal
    - proposal vs evidence
    - requirement vs requirement.

---

## 10) `backend/app/intelligence/lifecycle_projector.py`

**Stato:** **FATTO, ma da hardenizzare**

Perché:

- il file esiste;
- espone `project_requirement_event`, `refresh_requirement_snapshot`, `explain_requirement_path`, `project_workflow_events`, `project_gate_event`;
- quindi la projection del lifecycle nel grafo non è più teorica.

Perché non dico “chiuso al 100%”:

- dal pack vedo implementazione + test dedicato, ma non posso certificare da qui tutta la robustezza runtime in scenari edge / retry / sync tardiva.
- la migration associata aggiunge `last_projected_at` su `tender_requirements`, quindi c’è anche un minimo di osservabilità della projection lag.

**Conclusione:** funzione presente e ben impostata, ma è una delle aree più sensibili da consolidare.

---

## 11) `backend/migrations/versions/20260419_0011_requirement_lifecycle_projection.py`

**Stato:** **FATTO**

Perché:

- la migration c’è davvero;
- aggiunge `last_projected_at` come colonna osservativa per capire se la riga canonica è stata riproiettata nel grafo.

---

## 12) `backend/app/intelligence/personas.py` + `persona_catalog.py`

**Stato:** **FATTO**

Perché:

- il modello persona esiste;
- il catalogo deterministico esiste con i reviewer che avevamo previsto:
    - formalista amministrativo
    - valutatore tecnico
    - compliance officer
    - economico-finanziario
    - RUP simulato.

**Conclusione:** ottimo recepimento della parte “persona generation mirata”, ma in forma controllata e non social-style.

---

## 13) `backend/app/models/rehearsal.py`

**Stato:** **FATTO**

Perché:

- il modello c’è;
- dal resto del codice e dalla migration si vede che supporta `rehearsal_runs`, `rehearsal_persona_results`, `rehearsal_recommendations`.

---

## 14) `backend/migrations/versions/20260419_0012_add_rehearsal_tables.py`

**Stato:** **FATTO**

Perché:

- la migration esiste davvero;
- crea l’infrastruttura persistente della Wave 3.

---

## 15) `backend/app/intelligence/rehearsal.py`

**Stato:** **FATTO**

Perché:

- `TenderRehearsalService` esiste;
- il file descrive chiaramente il flusso:
    - create run
    - execute run
    - shared tool execution
    - persona evaluation
    - recommendations
    - persistence in `report_json`.

Questo è esattamente il trapianto della parte più preziosa di MiroFish: il rehearsal multi-view, ma su architettura persistita e non file-based.

---

## 16) `backend/app/intelligence/rehearsal_runner.py`

**Stato:** **FATTO**

Perché:

- il runner esiste;
- la valutazione persona-specifica è deterministic e tool-grounded, non un LLM swarm libero;
- ci sono score, findings, questions, metrics.

---

## 17) `backend/app/intelligence/rehearsal_converter.py`

**Stato:** **FATTO**

Perché:

- accetta/dismiss recommendation;
- converte recommendation → `ReworkAction` solo su azione esplicita;
- preserva il principio “no mutation automatica del workflow”.

---

## 18) `backend/app/tasks.py` / Celery per rehearsal

**Stato:** **PARZIALE**

Perché:

- nel router intelligence `_enqueue_rehearsal()` chiama davvero `run_rehearsal_task.delay(...)`, quindi il disegno asincrono via Celery è stato pensato.
- però nel frammento di `backend/app/api/tasks.py` che vedo compaiono solo task index/generate/export/health, non vedo lì direttamente la definizione del task rehearsal.

Interpretazione corretta:

- **l’integrazione task c’è quasi certamente**, ma da questo snapshot non la posso marcare “completamente verificata file-per-file” senza vedere tutto `backend/app/tasks.py`.

**Conclusione:** molto probabilmente fatto, ma lo classifico prudenzialmente **parziale verificato**.

---

## 19) `frontend/src/pages/TenderIntelligence.tsx` + `frontend/src/features/intelligence/RehearsalPanel.tsx`

**Stato:** **FATTO**

Perché:

- i file esistono nel pack;
- `tenderwriter2.md` segnala anche che il refactor FE è stato eseguito e che `RehearsalPanel.tsx` è stato estratto, con vitest verde.

---

## 20) `backend/app/api/kpi_admin.py` + `backend/app/intelligence/rehearsal_summary.py`

**Stato:** **FATTO MA CON DIVERGENZA ARCHITETTURALE**

Questo è il punto più delicato.

### Cosa c’è

- `rehearsal_summary.py` esiste davvero e produce il blocco summary.
- i test dimostrano che `get_kpi_tender_forecast()` in `app.api.kpi_admin` allega `rehearsal_summary` quando il flag è acceso, usa fallback vuoto quando `None`, e lo omette quando il flag è spento.

### Cosa manca rispetto al target iniziale

- `tenderwriter2.md` dice esplicitamente che PR-10 è stata implementata **nel wrapper backend `app.api.kpi_admin`**, non dentro `kpi-reason-engine/app/forecasting.py`, e la considera una divergenza architetturale ancora aperta.
- in più, il `ForecastTab.tsx` mostrato nel materiale continua a renderizzare summary/confidence/scenarios ma non evidenzia nel frammento un blocco `rehearsal_summary`.

**Conclusione:**  
funzionalmente il forecast enrichment **esiste**, ma architetturalmente è **parziale** rispetto al disegno ideale discusso in chat.

---

## 21) `kpi-reason-engine/app/forecasting.py`

**Stato:** **MANCANTE rispetto al target discusso**

Perché:

- il file c’è, ma nel materiale visibile resta centrato sulla struttura forecast originaria e non emerge l’innesto nativo del rehearsal.
- la nota di stato in `tenderwriter2.md` dice esplicitamente che il lavoro è stato fatto nel backend wrapper, non nel servizio remoto KPI.

**Conclusione:** qui hai ancora debito tecnico architetturale.

---

## 22) `frontend/src/features/observability/views/ForecastTab.tsx`

**Stato:** **PARZIALE / probabilmente mancante il render finale rehearsal-aware**

Perché:

- nel frammento visibile vedo rendering di forecast summary, confidence, scenarios, ma non un blocco chiaro dedicato a `rehearsal_summary`.
- `tenderwriter2.md` prevedeva esplicitamente quel render come obiettivo di PR-10.

**Conclusione:** o non è ancora stato completato, o non è verificabile dal materiale estratto. Ai fini della roadmap lo considero **parziale**.

---

## 23) ProposalWriterAgent / scrittura agentica della proposta

**Stato:** **MANCANTE**

Qui il verdetto è netto.

Perché:

- nella directory `backend/app/intelligence/` non compare alcun file tipo `proposal_writer_agent.py` o equivalente.
- l’API task standard continua a esporre `generate-section` nel modo classico, tramite `generate_proposal_section_task`, senza segni di un nuovo layer di scrittura agentica separato.

**Conclusione:**  
se vuoi completare anche questa parte della visione, è uno dei blocchi principali ancora da costruire.

---

# Riassunto finale in forma compatta

## FATTO

- ontologia
- tool registry
- coverage/evidence/compliance tools
- graph path explainer
- contradiction finder
- intelligence agent
- lifecycle projector
- migrations lifecycle + rehearsal
- personas catalog
- rehearsal service
- rehearsal runner
- rehearsal persistence
- rehearsal API
- accept/dismiss recommendation
- Tender Intelligence FE
- test pack dedicato molto ampio

## PARZIALE

- task/Celery verification completa del rehearsal
- lifecycle projector hardening runtime
- PR-10 forecast enrichment nella forma architetturalmente corretta
- render FE finale del `rehearsal_summary` in `ForecastTab`

## MANCANTE

- integrazione nativa del rehearsal nel `kpi-reason-engine/app/forecasting.py`
- ProposalWriterAgent / scrittura agentica delle proposal sections

---

# Giudizio conclusivo

La cosa più importante è questa:

**TenderWriter2 non è più “piano”. È già una prima implementazione sostanziale della convergenza TenderWriter + MiroFish.**

Hai già dentro:

- ontology-first enrichment,
- tool-driven intelligence,
- explainability,
- lifecycle-aware graph projection,
- personas,
- rehearsal,
- conversione controllata verso il workflow reale.

Quello che resta è soprattutto:

1. **chiudere bene PR-10** nel posto giusto;
2. **rifinire il surfacing FE forecast**;
3. decidere se vuoi anche il **ProposalWriterAgent**.

Se vuoi, nel prossimo messaggio ti faccio una tabella ancora più operativa con 4 colonne:

**file / stato / evidenza / next action**

così diventa direttamente una mini-gap-analysis eseguibile.

si

Sto verificando i punti più sensibili direttamente nel file completo: stato delle wave, PR-10 forecast/rehearsal, lifecycle projection e assenza/presenza di uno strato di scrittura agentica della proposta.

Thought for 1m 20s

Sì. Ecco la **mini gap-analysis eseguibile** in formato **file / stato / evidenza / next action**.

**Valutazione complessiva aggiornata:**  
sulla base di `tenderwriter2.md`, la roadmap discussa in chat è **realizzata per circa l’85–90%**. La parte già costruita è soprattutto il blocco **ontology + tools + agent + lifecycle + rehearsal**; ciò che resta è soprattutto **chiudere bene PR-10** e decidere se introdurre anche un vero **ProposalWriterAgent**.

|File / blocco|Stato|Evidenza|Next action|
|---|---|---|---|
|`backend/app/intelligence/ontology.py`|**Fatto**|Il file esiste nel package `backend/app/intelligence/` e implementa il tagging ontologico deterministico previsto dalla Wave 1.|Nessuna azione strutturale. Solo tuning del mapping e verifica qualità su tender reali.|
|`backend/app/intelligence/tool_registry.py`|**Fatto**|Il registry esiste e `build_default_tool_registry()` registra davvero `coverage_analyzer`, `evidence_auditor`, `compliance_panorama`, `graph_path_explainer`, `contradiction_finder`.|Solo manutenzione e aggiunta eventuale di tool futuri.|
|`backend/app/intelligence/tools/coverage_analyzer.py`|**Fatto**|Il tool esiste ed è parte del registry Wave 1/2.|Nessuna azione architetturale; solo calibrazione coverage su casi reali.|
|`backend/app/intelligence/tools/evidence_auditor.py`|**Fatto**|Il tool esiste ed è parte del registry; la logica Wave 1 è presente.|Migliorare eventuali euristiche di “strong/weak/missing” se emergono falsi positivi.|
|`backend/app/intelligence/tools/compliance_panorama.py`|**Fatto**|Il tool esiste ed è registrato come adapter verso il panorama KPI.|Nessuna azione strutturale; solo hardening contratti con KPI service.|
|`backend/app/api/intelligence.py`|**Fatto**|Espone tool endpoints, `/query`, `/rehearsals`, accept/dismiss recommendation e `/tenders/{id}/rehearsal-summary`; blocca inoltre il rehearsal su tender terminali.|Nessuna azione strutturale. Solo review sicurezza/permessi e polish UX/errori.|
|`backend/app/intelligence/agent.py`|**Fatto**|Il file esiste e implementa il loop controllato tool-driven con `intent`, `tools_used`, `answer`, `findings`, `recommended_actions`, coerente con PR-04.|Tuning intent routing e quality review delle risposte.|
|`backend/app/intelligence/tools/graph_path_explainer.py`|**Fatto**|Il tool esiste e ricostruisce la catena requirement → section → contribution → review/rework/gate, come previsto in PR-05.|Hardening query/path edge cases.|
|`backend/app/intelligence/tools/contradiction_finder.py`|**Fatto**|Il tool esiste e copre requirement↔proposal, proposal↔evidence, requirement↔requirement.|Ridurre rumore/falsi positivi con tuning su fixture reali.|
|`backend/app/intelligence/lifecycle_projector.py`|**Fatto, ma da hardenizzare**|Il file esiste e la roadmap interna lo descrive come projection di eventi canonici nel requirement graph; è supportato anche dalla migration dedicata.|Fare hardening runtime: retry, reconciliation, monitor projection lag, validazione end-to-end su tutti i path review/rework/gate.|
|`backend/migrations/versions/20260419_0011_requirement_lifecycle_projection.py`|**Fatto**|La migration esiste davvero e introduce il tracking `last_projected_at` per la projection lifecycle.|Nessuna azione strutturale; usare la colonna per osservabilità e backfill.|
|`backend/app/intelligence/personas.py` + `persona_catalog.py`|**Fatto**|I file esistono e il catalogo deterministico con reviewer tipo `formalista_amministrativo`, `valutatore_tecnico`, `compliance_officer`, `economico_finanziario`, `rup_simulato` è presente nella roadmap implementata.|Solo tuning dei reviewer su gare reali.|
|`backend/app/models/rehearsal.py` + migration `20260419_0012_add_rehearsal_tables.py`|**Fatto**|Il modello e la migration esistono; la migration documenta `rehearsal_runs`, `rehearsal_persona_results`, `rehearsal_recommendations`.|Nessuna azione strutturale.|
|`backend/app/intelligence/rehearsal.py` + `rehearsal_runner.py`|**Fatto**|La roadmap implementata segna PR-08 come realizzata; il runner valuta le personas sui tool outputs e il service orchestration/persistenza è presente.|Calibrare score, persona divergence e recommendation quality.|
|`backend/app/intelligence/rehearsal_converter.py`|**Fatto**|PR-09 risulta implementata con admin gate e conversione manuale recommendation → rework, coerente col vincolo “mai automatica”.|Solo hardening su idempotenza e audit.|
|`backend/app/tasks.py` / Celery rehearsal path|**Quasi fatto / verificato indirettamente**|La roadmap implementata dichiara PR-08 “implementato” e il router chiama `run_rehearsal_task.delay(run.id)`; però nel frammento di `api/tasks.py` che si vede compaiono solo index/generate/export/health, quindi il wiring Celery è confermato più dai file e dai test che da uno snippet completo del task.|Verifica finale end-to-end del task worker in ambiente runtime e test di retry/failure semantics.|
|`frontend/src/pages/TenderIntelligence.tsx` + `frontend/src/features/intelligence/RehearsalPanel.tsx`|**Fatto**|`tenderwriter2.md` segnala il refactor FE completato, con `RehearsalPanel.tsx` estratto e Vitest `95/95 passed`.|Solo UX polish.|
|`backend/app/intelligence/rehearsal_summary.py`|**Fatto**|Il file esiste e dichiara esplicitamente che produce il blocco `rehearsal_summary` consumato dal forecast view.|Nessuna azione strutturale locale.|
|`backend/app/api/kpi_admin.py` (forecast enrichment)|**Fatto, ma con divergenza architetturale**|`tenderwriter2.md` dice chiaramente che PR-10 è implementata **lato `app.api.kpi_admin`** e non nel `kpi-reason-engine`, con flag `rehearsal_summary_enabled` e test dedicati.|Decidere se accettare questa scelta pragmatica o spostare davvero la logica nel servizio remoto KPI.|
|`kpi-reason-engine/app/forecasting.py`|**Mancante rispetto al target originario**|La roadmap iniziale voleva modificare `kpi-reason-engine/app/forecasting.py`, ma lo stato finale dice che il lavoro è rimasto nel wrapper backend e che nel servizio remoto non c’è ancora esposizione rehearsal.|**Task residuo principale**: portare `rehearsal_summary` nel servizio KPI vero, con flag/contract corretti.|
|`frontend/src/features/observability/views/ForecastTab.tsx`|**Parziale / non chiuso al 100% nel materiale disponibile**|La roadmap di PR-10 prevedeva modifiche a `ForecastTab.tsx`, ma lo stato finale documentato mette l’accento soprattutto su backend wrapper + test FE intelligence; nel materiale disponibile non emerge una conferma altrettanto netta del render finale `rehearsal_summary` in ForecastTab.|Chiudere il surfacing FE del blocco rehearsal nel tab Forecast e verificarlo con test dedicato.|
|`backend/app/tasks.py` + `generate_proposal_section_task`|**Esiste, ma non è ProposalWriterAgent**|Oggi la generazione sezione resta il task classico `generate_proposal_section_task` che usa `HybridRAGEngine`/`RAGQuery` in `WRITE_SECTION`; non si vede un modulo separato tipo `ProposalWriterAgent`.|Se vuoi completare la visione “TenderWriter + MiroFish”, qui manca ancora un **ProposalWriterAgent** vero, tool-driven e rehearsal-aware.|

## Cosa significa in pratica

Le parti **davvero ancora aperte** sono poche e chiare:

1. **chiudere PR-10 nel posto giusto**, cioè nel `kpi-reason-engine`, non solo nel wrapper backend;
2. **completare/verificare il render FE del `rehearsal_summary` nel ForecastTab**;
3. **hardenizzare lifecycle projector e rehearsal runtime**;
4. **decidere se costruire anche il ProposalWriterAgent**, che oggi non risulta presente come blocco autonomo.

## Priorità che ti consiglierei

Ordine netto:

1. **PR-10 vero nel `kpi-reason-engine`**
2. **ForecastTab rehearsal-aware end-to-end**
3. **hardening runtime di lifecycle projector + rehearsal task**
4. **solo dopo, ProposalWriterAgent**

Se vuoi, nel prossimo messaggio ti trasformo questa tabella in una **todo list residua ordinata per priorità, effort e rischio**.