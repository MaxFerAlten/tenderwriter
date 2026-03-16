# Analisi Dettagliata del Modello Dati (TenderWriter & KPI Reason Engine)

Alla luce della retrospettiva manageriale ([tw-kpi-reason-engine-retrospettiva-manageriale.md](file:///d:/tender/tenderwriter/resoningfromagentic/codex/tw-kpi-reason-engine-retrospettiva-manageriale.md)) e dell'implementazione reale, il modello dati introdotto è strutturato in modo da disaccoppiare nettamente il **flusso operativo transazionale** dal **motore di analisi e inferenza (KPI Engine)**.

Il sistema sfrutta un'architettura a **doppio dominio data-driven**: 

1. **Backend Principale (PostgreSQL)**: Sorgente della verità per lo stato operativo e documentale. Registra minuziosamente "cosa succede e chi lo fa".
2. **KPI Reason Engine (SQLite)**: Sorgente della verità analitica. Elabora gli eventi e genera snapshot temporali e calcoli probabilistici sulla salute del tender.

Diseguito un'analisi dettagliata di queste due anime dell'architettura.

---

## 1. Modello Dati Operativo (Backend Principale)

Situato nel modulo [operational_observability.py](file:///d:/tender/tenderwriter/backend/app/models/operational_observability.py) e [__init__.py](file:///d:/tender/tenderwriter/backend/app/__init__.py), estende in modo radicale il classico modello transazionale "Tender-Proposal-Section" per introdurre una tracciabilità capillare del flusso di lavoro, trasformando azioni implicite (come mandare un'email) in eventi tipizzati a database.

Le novità più rilevanti includono:

### A. Elementi di Lavoro e Richieste (Contribution Flow)
- **[ContributionUnit](file:///d:/tender/tenderwriter/backend/app/models/operational_observability.py#57-77)**: Rappresenta il vero atomo operativo. Non è una semplice sezione della proposta (`proposal_section_id` è opzionale), ma è l'"unità d'impegno" di un dipartimento su un tender. Ha stati ben precisi (`OPEN`, `REQUESTED`, `IN_REVIEW`, `COMPLETED`, `BLOCKED`).
- **[ContributionRequest](file:///d:/tender/tenderwriter/backend/app/models/operational_observability.py#79-101)**: Traccia la richiesta esplicita (chi ha chiesto cosa, a chi, tramite quale canale) e gestisce anche i concetti di SLA (`sla_target_hours`, `sla_max_hours`).

### B. Cicli di Validazione ed Eccezioni (Review, Rework & Gate)
- **[ReviewCycle](file:///d:/tender/tenderwriter/backend/app/models/operational_observability.py#103-120)**: Formalizza le fasi di controllo qualitativo per un [ContributionUnit](file:///d:/tender/tenderwriter/backend/app/models/operational_observability.py#57-77).
- **[ReworkAction](file:///d:/tender/tenderwriter/backend/app/models/operational_observability.py#122-145)**: Estrae l'emergenza (rework) in un'entità propria persistente, dotata di `severity` e indicatore `is_blocking`. È il driver per segnali diagnostici "Amber/Red" sui Tender.
- **[ComplianceGate](file:///d:/tender/tenderwriter/backend/app/models/operational_observability.py#147-165)**: Milestones formali non per produrre testo, ma per prendere decisioni di business o di compliance (con `decision_notes` e status `PASSED`/`FAILED`).

### C. Collaborazione Sincrona (Calls & Attendance)
- **[CallSession](file:///d:/tender/tenderwriter/backend/app/models/operational_observability.py#167-183)** e **[AttendanceRecord](file:///d:/tender/tenderwriter/backend/app/models/operational_observability.py#185-200)**: Tengono traccia degli allineamenti sincroni, indicando chi è stato invitato e chi era materialmente presente (o assente ingiustificato). Utile per l'analisi comportamentale/operativa.

### D. Message Outbox pattern ([KpiDomainEvent](file:///d:/tender/tenderwriter/backend/app/models/__init__.py#410-432))
Per inviare queste informazioni, il backend usa il pattern Outbox. Tabella `kpi_domain_events` nel database PostgreSQL immagazzina gli eventi di dominio (`event_type`), il payload e attende che vengano recapitati (`KpiEventDeliveryStatus.PENDING` -> `DELIVERED`) al KPI Engine in differita/asincrono.

---

## 2. Modello Dati Analitico (KPI Reason Engine)

Il KPI Reason Engine possiede un database separato (SQLite, gestito in [store.py](file:///d:/tender/tenderwriter/kpi-reason-engine/app/store.py)) ottimizzato per le letture analitiche in modalità Event-Sourcing (non distruttiva). Usa una logica "append-only" e di storicizzazione (snapshot).

### A. Event Bus Integrato e Mirroring
- **`kpi_tenders`**: Tabella specchio del tender sul backend. Funge da hub di aggregazione per l'ID Tender esterno (es. `external_tender_id`). Mantiene uno stato locale della *salute matematica* e della *fase analitica* correnti.
- **`kpi_domain_events`**: Tabella append-only con hash anticollisione su payload (Envelope Hash). Memorizza tutti gli eventi passati dal Backend per garantirne la **Riproducibilità (Replay)**.

### B. Ciclo di Vita del Calcolo
- **`kpi_analysis_jobs`**: Registra richieste asincrone per i ricalcoli (diagnostica, snapshot o backfill storico). Supporta priorità. L'esecuzione è governata tramite job su cui la persistenza riflette lo status (`queued`, `running`, [succeeded](file:///d:/tender/tenderwriter/kpi-reason-engine/app/store.py#307-324)).

### C. Versionamento dei Modelli di Calcolo
- **`kpi_model_versions`**: Invece di fidarsi solo della logica definita a codice, il DB traccia versionamento dei "formula bundle" o dei "prompt bundle" (metadati del calcolo) nel momento in cui viene generato un dato. Permette audit post-calcolo a fronte di continue evoluzioni delle euristiche.

### D. Risultati del Ragionamento (Snapshot & Diagnosis)
- **`kpi_snapshots`**: Modello immutabile calcolato periodicamente o ad eventi puntuali. Contiene non solo un semaforo testuale (salute), ma la fotografia intera (`kpi_json` e `analysis_metadata_json`). È la base storica su cui applicare futuri modelli markoviani per capire tendenze (Forecast).
- **`kpi_findings`**: Esiti puntuali di diagnostica correlati allo snapshot (avvisi per testo es. "Rework ad alta priorità sul dipartimento Legale").
- **`kpi_phase_transitions`**: Log transazionali dell'analisi. Per ogni cambio fase rilevante archivia (`from_state`, `to_state`, `cause`), con lo `confidence_score`. Fondamentale per il forecast transitorio e le probabilità di successo finali.

---

## Sintesi e Considerazioni Architetturali

Il modello dati introdotto è estremamente robusto e coerente con la documentazione di retrospettiva ([tw-kpi-reason-engine-retrospettiva-manageriale.md](file:///d:/tender/tenderwriter/resoningfromagentic/codex/tw-kpi-reason-engine-retrospettiva-manageriale.md)):

1. **Tracciabilità Estrema**: Gli oggetti del _Backend_ risolvono formalmente i problemi del project management (Review, Rework, Attendance), garantendo una UI azionabile e non soltando un report visivo.
2. **Base Solida (Future-Proof)**: Le astrazioni nel _KPI Reason Engine_ gettano la spugna rispetto alla sovrascrittura in place (no `UPDATE row`). Grazie all'uso esclusivo di log immutati per [transitions](file:///d:/tender/tenderwriter/kpi-reason-engine/app/store.py#518-543) e [snapshots](file:///d:/tender/tenderwriter/kpi-reason-engine/app/store.py#615-623) con annessi riferimenti alla versione del modello, il team può passare nel prossimo sprint dalla fase puramente "Rule-based/Eurisitica" alla "Predittiva/Markoviana" su storico reale, come accennato dalla guida manageriale, in quanto la catena dei dati è predisposta da zero come vera Time-Series strutturata.


La scelta di utilizzare SQLite per il KPI Reason Engine, mantenendo invece PostgreSQL per il Backend Principale, è una decisione architetturale molto precisa che riflette perfettamente il pattern dei microservizi e la natura intrinseca del ragionamento sui dati.

Ecco i motivi principali architetturali e operativi dietro a questa scelta:

1. Isolamento Totale del Dominio (Microservices Pattern)
Il KPI Reason Engine è stato disegnato come un sistema totalmente autonomo e disaccoppiato dal backend principale. Usare SQLite significa che il container/servizio del motore porta con sé letteralmente il proprio database all'interno del file system (un semplice file .db). Non ha bisogno di condividere un'istanza PostgreSQL, non serve gestire credenziali di rete, permessi, o preoccuparsi che una query analitica pesante rallenti il database del TenderWriter principale.

2. Modello Dati ad "Aggiunta Continua" (Append-Only / Event Sourcing)
PostgreSQL brilla in scenari OLTP (Online Transaction Processing) dove ci sono transazioni concorrenti altamente complesse e scritture parallele sulla stessa riga (es. due utenti salvano un documento insieme). Il KPI Engine, al contrario, lavora in Event Sourcing:

Legge eventi dal passato.
Inserisce nuove righe (nuovi eventi in kpi_domain_events o nuovi snapshot in kpi_snapshots).
Non fa mai aggiornamenti (UPDATE) distruttivi. In 

store.py
 abbiamo infatti notato l'impostazione PRAGMA journal_mode=WAL;, che rende SQLite eccellente per gestire letture concorrenti e veloci scritture sequenziali, esattamente il carico di questo motore analitico.
3. Modello Dati "Piatto" (JSON Blobs)
Se guardiamo lo schema 

store.py
 del KPI Engine, notiamo che quasi tutte le tabelle memorizzano intere strutture dati come stringhe JSON (payload_json, kpis_json, metadata_json, notes_json). Il Reason Engine non ha quasi mai bisogno di fare JOIN relazionali complessi su 10 tabelle diverse per estrarre la salute di un tender; legge semplicemente il JSON dello snapshot. In altre parole, non utilizza il 90% delle funzionalità relazionali avanzate che rendono grande PostgreSQL (come indici GIN per JSONB avanzati, array nativi, check constraints complessi).

4. Velocità di Iterazione (Siamo in Sprint 1)
Come citato nella Retrospettiva Manageriale, il motore attuale (euristico) dovrà evolversi in un motore predittivo markoviano puro sui dati storici. Durante fasi di forte sperimentazione data-science/IA, gestire migrazioni di schema su PostgreSQL è tedioso. Con SQLite, i data scientist e gli sviluppatori possono letteralmente scaricarsi il file .db di produzione sul portatile, lanciare script Python locali in un Jupyter Notebook per testare nuovi prompt o logiche markoviane, senza alcun effort infrastrutturale.

5. Architettura a Coda di Elaborazione
Il sistema acquisisce richieste per ricalcoli asincroni (kpi_analysis_jobs). Molto probabilmente un worker (o una manciata di thread locali) pesca il job in coda e lancia l'LLM o il motore euristico. Finché il volume (il numero di tender elaborati al secondo) rientra in scenari B2B normali (anche migliaia di tender), un database embedded in-memory/file come SQLite processa i dati più in fretta della latenza di rete necessaria per parlare con un server PostgreSQL remoto.

In sintesi: PostgreSQL (backend) fa il "lavoro sporco" transazionale su cui lavorano decine di utenti nello stesso momento. SQLite (motore KPI) fa la funzione di Datalake/Brain locale per catturare eventi, storicizzarli passivamente e ricalcolare gli snapshot senza dipendere da nessun'altra componente dell'infrastruttura. È una mossa eccellente per contenere i costi e azzerare il debito infrastrutturale in questa fase.