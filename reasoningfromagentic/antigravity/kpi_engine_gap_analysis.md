# Analisi di Aderenza: Specifica vs Implementazione (KPI Reason Engine)

Questa analisi confronta la specifica di design originale ([KPIReasonEngine.md](file:///D:/tender/tenderwriter/kpi-reason-engine/docs/KPIReasonEngine.md)) con quanto effettivamente sviluppato e riflettuto nel modello dati e nella retrospettiva manageriale ([tw-kpi-reason-engine-retrospettiva-manageriale.md](file:///d:/tender/tenderwriter/resoningfromagentic/codex/tw-kpi-reason-engine-retrospettiva-manageriale.md)).

---

## 1. Quanto è aderente il modello implementato? (Cosa c'è già)

L'architettura attuale ha implementato con eccellente successo **l'impalcatura infrastrutturale e di tracciamento** prevista dal documento teorico. In particolare:

### La Macchina a Stati del Processo Bid (S0 -> S13)
Nel modello dati operazionale ([operational_observability.py](file:///d:/tender/tenderwriter/backend/app/models/operational_observability.py)), la gestione del flusso riproduce fedelmente i nodi critici della specifica markoviana:
- **S4 (Coordinamento & Ricezione)** è modellato attraverso [ContributionUnit](file:///d:/tender/tenderwriter/backend/app/models/operational_observability.py#57-77) e [ContributionRequest](file:///d:/tender/tenderwriter/backend/app/models/operational_observability.py#79-101), raccogliendo i timestamp necessari per misurare B1 (Deadline) e B2 (Responsività). L'entità [AttendanceRecord](file:///d:/tender/tenderwriter/backend/app/models/operational_observability.py#185-200) supporta B3 (Call). 
- **S5 / S6 (Review e Rework)** sono supportati nativamente dalle entità [ReviewCycle](file:///d:/tender/tenderwriter/backend/app/models/operational_observability.py#103-120) e [ReworkAction](file:///d:/tender/tenderwriter/backend/app/models/operational_observability.py#122-145) con il concetto di `severity` e `is_blocking`. Questo quantifica in modo inequivocabile le metriche B4 (Stabilità / Rework iterativo) immaginate nel PDF e i loop markoviani transitori.
- **S8 (Gate Compliance)** è servito dell'entità [ComplianceGate](file:///d:/tender/tenderwriter/backend/app/models/operational_observability.py#147-165).

### Il Meccanismo Distaccato di Ragionamento
Dal `2026-03-29` il motore KPI non usa piu SQLite in runtime. La separazione resta logica, non piu tecnologica:
- `tw-backend` continua a usare il proprio modello transazionale;
- `tw-kpi-reason-engine` persiste in PostgreSQL ma dentro uno schema dedicato `kpi_engine`;
- snapshot, eventi, findings e transizioni restano isolati dal dominio transazionale pur vivendo sulla stessa piattaforma dati.

Questa scelta mantiene l'idea di **Datalake passivo** prevista dal disegno originario, ma con un assetto piu operabile in produzione: backup centralizzati, migrazioni versionate, tipi `jsonb`/`timestamptz`, nessun volume locale da preservare per il runtime ordinario.

Nel file [schemas.py](file:///d:/tender/tenderwriter/kpi-reason-engine/app/schemas.py) troviamo la base pronta per raccogliere la semantica prescritta:
- L'enumeratore `HealthClass` contiene esattamente `green`, `amber` e `red`.
- [KpiScore](file:///d:/tender/tenderwriter/kpi-reason-engine/app/schemas.py#154-169) modella l'aggregazione numerica dei parametri, la motivazione (`recommendation`) e la confidenza, rispecchiando l'output obbligatorio richiesto dai prompt LLM documentati nella specifica. 

---

## 2. Quanto manca da fare? (Il Gap Diagnostico)

Sebbene il "telaio operativo" e l'"involucro dati" siano presenti al 100%, l'"intelligenza algoritmica" e il popolamento semantico dei dati descritti in [KPIReasonEngine.md](file:///D:/tender/tenderwriter/kpi-reason-engine/docs/KPIReasonEngine.md) non sono ancora pienamente attivati.

### A. Popolamento dei Prompt Qualitative (A1-A4) tramite LLM 
La specifica definisce l'uso estensivo dell'Intelligenza Artificiale (LLM) per analizzare il testo in input valutando la copertura requisiti (A1), la qualità redazionale (A2), il valore tecnico (A3) e il rischio non conformità (A4). 
**Stato Attuale:** Come indica la *retrospettiva manageriale*, la derivazione oggi *"è rule-based" / "deterministic_proxy"*. Non c'è ancora un vero callout sistematico ai prompt LLM descritti per riempire passivamente lo snapshot.

### B. Standardizzazione Scalare & Indici di Rischio `Q` ed `E`
La specifica indica di generare due indici cardinali: 
- `Q` (Qualità: 30% A1 + 15% A2 + 30% A3 + 25% A4)
- `E` (Esecuzione: 30% B1 + 30% B2 + 15% B3 + 25% B4)

**Stato Attuale:** Nonostante sia predisposta la tabella di database (`kpi_snapshots` > `kpis_json`), oggi manca il motore algebrico che ricalibra le scale asimmetriche (alcune decimali, altre 1-10) in uno standard unificato per generare concretamente questi due macro-indici. 

### C. Motore Markoviano Matematico (Matrici di Probabilità)
La documentazione descrive una matrice `Markov-Chain` concreta dove la transizione di probabilità es. S4 -> S5 = 0.75 dipende dalla salute del nodo (es. se A4 > 7).
**Stato Attuale:** Come la retrospettiva sottolinea, *"il forecast è euristico: le probabilità sono aggiustate tramite regole, non stimate dal comportamento storico reale"*. L'infrastruttura attuale salva correttamente i log in `kpi_phase_transitions` nello schema PostgreSQL `kpi_engine` e puo fungere da dataset di *training*. Bisognerà estrarre i trend aggregati passati dai log per alimentare un modello Data Science reale (il Layer 3 & 4 menzionato nel manuale), rimuovendo la dipendenza dalle attuali stime "pre-impostate a mano".

---

## Conclusioni
L'aderenza tecnica sui layer **1 (Tracciamento)** e **2 (Classificazione)** è praticamente totale. L'adeguamento formale e algoritmico sui layer **3 (Markov)** e sull'integrazione semantica dei prompt originali **LLM** è lo step mancante che chiuderà la forbice tra MVP di primo livello e Visione architetturale finale.

## Addendum Operativo 2026-03-29
- Gap chiuso sul fronte storage runtime: il motore KPI e ora `PostgreSQL-only`.
- Gap chiuso sul fronte operability: niente volume locale `/app/data`, backup centralizzato lato PostgreSQL e migrazioni versionate.
- Gap chiuso sul fronte tipo dati: JSON e timestamp principali sono nativi PostgreSQL (`jsonb`, `timestamptz`).
- Restano aperti i gap algoritmici e semantici descritti sopra, non quelli infrastrutturali.
