# TenderWriter KPI Reason Engine - piano dei prossimi passi

## Scopo

Questo piano traduce i documenti di riferimento in una roadmap eseguibile per il prossimo ciclo evolutivo del KPI Reason Engine.

Fonti considerate:

- `D:\tender\tenderwriter\kpi-reason-engine\docs\KPIReasonEngine.md`
- `D:\tender\tenderwriter\kpi-reason-engine\docs\Pasted image 20260313233154.png`
- `D:\tender\tenderwriter\kpi-reason-engine\docs\Pasted image 20260313233307.png`
- `D:\tender\tenderwriter\kpi-reason-engine\docs\Pasted image 20260313233359.png`
- `D:\tender\tenderwriter\kpi-reason-engine\docs\Pasted image 20260313233419.png`
- `D:\tender\tenderwriter\kpi-reason-engine\docs\Pasted image 20260313233518.png`
- `D:\tender\tenderwriter\kpi-reason-engine\docs\Pasted image 20260313233602.png`
- `D:\tender\tenderwriter\resoningfromagentic\antigravity\data_model_analysis.md`
- `D:\tender\tenderwriter\resoningfromagentic\antigravity\kpi_engine_gap_analysis.md`
- `D:\tender\tenderwriter\resoningfromagentic\codex\tw-kpi-reason-engine-retrospettiva-manageriale.md`
- `D:\tender\tenderwriter\resoningfromagentic\codex\tw-kpi-reason-engine-retrospettiva.md`

## Lettura sintetica del punto in cui siamo

Il materiale converge su una diagnosi chiara:

- il telaio prodotto e gia forte
- il modello dati e gia abbastanza ricco per sostenere evoluzioni importanti
- il motore attuale e ancora prevalentemente `deterministic_proxy`
- il forecast attuale e euristico
- la distanza piu grande dalla visione originaria e nel layer semantico e nel layer markoviano

La priorita quindi non e aggiungere altre feature isolate, ma chiudere la forbice tra:

- buon motore operativo attuale
- motore KPI semanticamente e probabilisticamente piu fedele al modello target

## Principi guida per il prossimo ciclo

### 1. Non rompere cio che gia funziona

La UI admin e il loop operativo sono gia utili. Le prossime evoluzioni devono essere additive e controllate, non riscritture destabilizzanti.

### 2. Congelare prima il contratto KPI, poi cambiare il motore

Prima di introdurre LLM scoring o Markov calibrato, bisogna fissare una semantica ufficiale per:

- scala dei KPI
- pesi di `Q` ed `E`
- soglie health
- formato output/evidence
- mapping stati supportati

### 3. Prima misurare bene, poi prevedere

La formula `P_ij = N(i->j) / sum_j N(i->j)` richiede dati coerenti e ricostruibili. Senza dataset pulito, il Markov rischia di essere una falsa precisione.

### 4. Introdurre il reasoning semantico in shadow mode

Il passaggio da proxy deterministico a scoring semantico va fatto inizialmente in parallelo, per confronto e validazione, non sostituendo subito il motore attuale.

### 5. Concentrarsi sul core loop, non su tutta la catena completa al primo colpo

Per il Markov MVP il focus raccomandato e sul cuore del processo realmente osservabile:

- `S4 -> S5 -> S6 -> S8 -> S9`
- `S10 -> S11/S12/S13`

Gli stati molto precoci possono essere armonizzati dopo.

## Obiettivo del prossimo ciclo

Portare il KPI Reason Engine da:

- motore operativo explainable con forecast euristico

A:

- motore con contratto KPI ufficiale
- scoring qualitativo almeno parzialmente semantico
- forecast Markov v1 calibrato sui dati storici del core loop
- UX admin capace di distinguere tra dato osservato, inferenza e previsione

## Piano raccomandato per workstream

## Workstream 0 - KPI contract e governance del modello

### Obiettivo

Definire una base ufficiale e stabile per formule, scale, soglie e output.

### Problemi che risolve

- incoerenza tra 1-10 e 0-100
- mismatch tra formula documentata e formula implementata
- ambiguita tra A1 e A4
- output dei prompt non ancora sufficientemente normalizzati

### Deliverable

- documento canonico `KPI contract v1`
- definizione ufficiale di `Q`, `E`, health e soglie di escalation
- decisione esplicita su scala unica
- schema standard output per tutti i KPI:
  - score
  - evidenze
  - criticita
  - raccomandazioni
  - confidence
  - source type
- tabella di mapping tra stati teorici e stati realmente supportati nel prodotto

### Acceptance criteria

- esiste una sola definizione ufficiale di formula e soglie
- documentazione, backend e reason engine non si contraddicono piu
- le versioni formula/model/prompt sono governate come artefatti ufficiali

### Priorita

Massima. Questo deve avvenire prima di introdurre un Markov serio o un LLM scorer in produzione.

## Workstream 1 - Data foundation e qualita del dataset di transizione

### Obiettivo

Rendere i log e le transizioni abbastanza puliti da poter stimare davvero le probabilita di passaggio.

### Problemi che risolve

- forecast ancora basato su euristiche
- rischio di dataset incompleto o transizioni non ricostruibili
- impossibilita di stimare `N(i->j)` in modo affidabile

### Deliverable

- audit della tassonomia eventi attuale
- elenco campi obbligatori per ogni evento usato dal motore
- regole di ricostruzione storica per il core loop
- report di copertura delle transizioni osservabili
- job di validazione dataset prima del training/calibrazione

### Focus pratico

Il dataset minimo da rendere affidabile deve coprire almeno:

- review started / completed
- rework requested / resolved
- gate opened / passed / failed
- tender submitted
- outcome finale

### Acceptance criteria

- per il core loop, almeno l'80-90% dei tender analizzati deve avere una storia transizionale ricostruibile
- ogni snapshot puo essere ricondotto ai principali event driver
- `kpi_phase_transitions` e abbastanza affidabile da essere usato per calcolo statistico e non solo diagnostico

### Priorita

Massima, subito dopo il contract.

## Workstream 2 - Semantic scoring MVP per A1-A4

### Obiettivo

Portare almeno una parte dei KPI qualitativi da proxy strutturali a valutazione semantica vera.

### Strategia consigliata

Non partire con tutti i KPI allo stesso livello.

Ordine raccomandato:

1. `A1` e `A4`
2. `A2`
3. `A3`

### Motivo

- `A1` e `A4` sono i piu critici per coverage e compliance
- sono i piu ancorabili a output strutturati
- `A2` e `A3` sono piu soggettivi e richiedono piu evaluation

### Deliverable

- prompt bundle versionato per A1-A4
- pipeline asincrona di scoring in shadow mode
- dataset campione annotato per valutazione
- storage delle evidenze LLM nello snapshot
- confronto side-by-side tra score proxy e score semantico

### Acceptance criteria

- almeno A1 e A4 funzionano in shadow mode su un campione significativo di tender
- gli output sono standardizzati e confrontabili
- esiste una review interna che confronta proxy vs LLM su casi reali
- il sistema non sostituisce ancora in automatico il proxy senza evidenza sufficiente

### Priorita

Alta. E il ponte tra il motore attuale e la visione originaria.

## Workstream 3 - Markov engine v1 sul core loop

### Obiettivo

Sostituire il forecast puramente euristico con una prima stima empirica basata su storico reale.

### Strategia consigliata

Partire con una Markov chain ristretta, non con il grafo completo S0-S13.

Per il primo rilascio:

- stati core: `S4`, `S5`, `S6`, `S8`, `S9`, `S10`, `S11`, `S12`, `S13`
- stato esteso facoltativo in seconda battuta: `(Fase, ClasseSalute)`

### Deliverable

- builder delle matrici di transizione dal log storico
- matrice empirica per core loop
- confronto forecast euristico vs forecast Markov v1
- backtesting semplice su tender chiusi
- report di calibrazione per classi Green/Amber/Red

### Acceptance criteria

- il sistema calcola davvero `P_ij` dai dati osservati
- esiste una matrice persistita o rigenerabile per versione di modello
- il forecast admin mostra almeno uno scenario basato su dati reali
- i terminal state `S11/S12/S13` sono trattati come assorbenti in modo esplicito

### Priorita

Alta, ma solo dopo Workstream 1.

## Workstream 4 - Productization e UX admin v2

### Obiettivo

Rendere trasparente all'admin la differenza tra dato, inferenza e previsione.

### Problemi che risolve

- rischio di eccessiva fiducia nel forecast
- poca distinzione tra score osservato, score inferito e score semantico
- poca trasparenza sulla provenienza delle decisioni del motore

### Deliverable

- visualizzazione di `source type` per score e forecast
- esposizione chiara di `formula version`, `model version`, `prompt version`
- distinzione tra:
  - observed
  - inferred
  - predicted
- vista admin per confidence e driver principali
- segnalazione esplicita se un tender usa forecast euristico o Markov v1

### Acceptance criteria

- l'admin capisce con chiarezza cosa e misurato e cosa e stimato
- il cockpit resta utilizzabile anche durante il rollout graduale del nuovo motore

### Priorita

Media-alta. Va eseguita in parallelo finale alla productization del nuovo motore.

## Roadmap proposta per sprint

## Sprint 1 - Contract e data hardening

### Obiettivo

Mettere ordine nelle fondamenta prima di introdurre altra intelligenza.

### Scope

- chiusura `KPI contract v1`
- allineamento formule, scale e soglie
- separazione piu netta tra A1 e A4
- standard output schema per KPI
- audit eventi e copertura transizioni
- metriche di qualita dataset

### Outcome atteso

Al termine dello sprint il team sa esattamente:

- cosa misura ogni KPI
- come viene aggregato
- come si decide health
- quali transizioni sono davvero misurabili con i dati attuali

## Sprint 2 - Semantic scoring MVP in shadow mode

### Obiettivo

Aggiungere reasoning semantico senza rompere il comportamento attuale.

### Scope

- A1 e A4 in shadow mode
- salvataggio evidence strutturate
- evaluation set e confronto con proxy attuale
- scelta dei casi in cui LLM e affidabile e dei casi in cui non lo e

### Outcome atteso

Il team puo valutare con dati reali se e come iniziare a sostituire i proxy per i KPI qualitativi.

## Sprint 3 - Markov core loop v1

### Obiettivo

Passare da forecast euristico a forecast empirico per il cuore del processo tender.

### Scope

- estrazione matrici dal log storico
- stati assorbenti finali
- prime probabilita calibrate su `S4/S5/S6/S8/S9/S10`
- confronto col modello euristico attuale

### Outcome atteso

Esiste un forecast piu credibile, basato su osservazioni reali del processo.

## Sprint 4 - Rollout prodotto e admin UX v2

### Obiettivo

Rendere il nuovo motore leggibile, governabile e sicuro lato admin.

### Scope

- provenance visibile in UI
- confidence e driver migliorati
- distinzione tra shadow, heuristic e calibrated
- policy di rollout graduale

### Outcome atteso

Il team puo attivare i nuovi componenti senza perdere fiducia, auditabilita o controllabilita.

## Decisioni da prendere subito

Prima di avviare i lavori, consiglio di chiudere 5 decisioni esplicite.

### D1 - Qual e la scala ufficiale del sistema?

Opzioni realistiche:

- mantenere 0-100 internamente e mostrare 1-10 solo in presentazione
- riallineare tutto a 1-10 anche a livello engine

Raccomandazione:

- mantenere 0-100 nel motore e introdurre una presentazione normalizzata dove serve, ma dichiararlo ufficialmente

### D2 - Qual e la formula ufficiale di Q ed E?

Raccomandazione:

- scegliere una formula canonica e versionarla
- evitare di lasciare divergenza tra spec e implementazione

### D3 - Quali stati entrano nel Markov MVP?

Raccomandazione:

- partire dal core loop osservabile e dagli stati terminali
- non inseguire subito la catena completa teorica

### D4 - Quali KPI qualitativi passano prima a scoring semantico?

Raccomandazione:

- iniziare da A1 e A4

### D5 - Come gestiamo il rollout?

Raccomandazione:

- shadow mode
- confronto controllato
- attivazione progressiva per blocchi di funzionalita

## Cosa NON consiglio di fare ora

Per evitare dispersione, sconsiglio nel prossimo ciclo di:

- riscrivere tutta la UI admin
- inseguire subito il modello completo S0-S13 con salute estesa per ogni stato
- sostituire in produzione i proxy con LLM scoring senza benchmark interno
- presentare il forecast come statistico se ancora non deriva dai dati storici
- introdurre personalizzazioni per dipartimento prima di aver consolidato il modello base

## Criterio di successo del prossimo ciclo

Il prossimo ciclo puo dirsi riuscito se, a fine roadmap iniziale, TenderWriter dispone di:

- un contratto KPI unico e ufficiale
- almeno A1/A4 valutati in shadow mode con output strutturato
- un dataset di transizione affidabile sul core loop
- un forecast Markov v1 realmente stimato dai log
- una UX admin che distingue chiaramente dato, inferenza e previsione

## Conclusione

La cosa piu importante e questa:

il progetto non ha bisogno di cambiare direzione, ma di cambiare livello di rigore.

La base costruita finora e giusta. Il prossimo passo non e aggiungere complessita casuale, ma:

1. chiudere il contratto del modello
2. rendere affidabili i dati di transizione
3. introdurre scoring semantico dove ha piu valore
4. trasformare il forecast da euristica a stima empirica

Questa e la traiettoria piu solida per passare da un ottimo motore operativo a un vero KPI Reason Engine coerente con la visione originaria.
