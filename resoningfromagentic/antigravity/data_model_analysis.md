# Analisi Dettagliata del Modello Dati (TenderWriter & KPI Reason Engine)

Alla luce della retrospettiva manageriale ([tw-kpi-reason-engine-retrospettiva-manageriale.md](file:///d:/tender/tenderwriter/resoningfromagentic/codex/tw-kpi-reason-engine-retrospettiva-manageriale.md)) e dell'implementazione reale, il modello dati introdotto è strutturato in modo da disaccoppiare nettamente il **flusso operativo transazionale** dal **motore di analisi e inferenza (KPI Engine)**.

Il sistema sfrutta un'architettura a **doppio dominio data-driven**: 

1. **Backend Principale (PostgreSQL)**: Sorgente della verità per lo stato operativo e documentale. Registra minuziosamente "cosa succede e chi lo fa".
2. **KPI Reason Engine (PostgreSQL, schema `kpi_engine`)**: Sorgente della verità analitica. Elabora gli eventi e genera snapshot temporali e calcoli probabilistici sulla salute del tender.

Diseguito un'analisi dettagliata di queste due anime dell'architettura.

## Addendum Operativo 2026-03-29

Le sezioni sotto sono state riallineate al runtime attuale:

- il KPI Reason Engine e ora `PostgreSQL-only`
- lo schema analitico dedicato e `kpi_engine`
- i payload strutturati usano `jsonb`
- i campi temporali usano `timestamp with time zone`
- il volume locale `/app/data` non fa piu parte del runtime ordinario
- eventuali riferimenti al precedente assetto SQLite vanno letti come contesto storico, non come stato corrente

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

Il KPI Reason Engine possiede uno store analitico separato a livello logico, oggi implementato in PostgreSQL con schema dedicato `kpi_engine` e gestito in [store.py](file:///d:/tender/tenderwriter/kpi-reason-engine/app/store.py). Mantiene una logica "append-only" e di storicizzazione (snapshot), ma con operabilita centralizzata, migrazioni versionate e backup coerenti con il resto della piattaforma.

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


Lo storico del progetto e nato con una giustificazione forte per SQLite, ma quello scenario e stato superato. Oggi la scelta architetturale consolidata e questa:

1. Isolamento del dominio analitico senza isolamento filesystem
Il KPI Reason Engine resta un servizio autonomo e disaccoppiato dal backend principale, ma lo fa tramite schema PostgreSQL dedicato invece che tramite file locale. Questo mantiene il boundary logico senza trascinarsi problemi operativi di backup, replica e gestione volume.

2. Event sourcing e append-only restano invariati
Il fatto che il motore lavori in append-only non dipende da SQLite. Anche su PostgreSQL il servizio continua a leggere eventi, inserire nuovi snapshot e storicizzare transizioni senza basarsi su update distruttivi come meccanismo principale.

3. Tipi nativi piu adatti all'operativita
Le strutture che in origine erano salvate come blob testuali sono state promosse a `jsonb`, mentre i timestamp analitici sono ora `timestamp with time zone`. Questo migliora auditabilita, queryability e coerenza temporale senza perdere flessibilita.

4. Backup e recovery centralizzati
Con PostgreSQL lo storage analitico entra nel perimetro operativo standard della piattaforma: dump di schema, restore controllato, migrazioni Alembic e niente dipendenza da `/app/data`.

5. Legacy SQLite relegato a recovery straordinario
Il vecchio formato SQLite non e piu parte del runtime ordinario. Resta solo come sorgente importabile in caso di recupero storico, con migrazione e validazione esplicite e disattivate di default.

In sintesi: PostgreSQL continua a fare il "lavoro sporco" transazionale del backend, ma ora ospita anche il repository analitico del KPI engine in uno schema dedicato `kpi_engine`. Il disaccoppiamento architetturale resta, mentre il debito operativo del volume locale e stato rimosso.
