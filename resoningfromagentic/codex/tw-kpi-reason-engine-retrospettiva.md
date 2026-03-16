# TenderWriter KPI Reason Engine - retrospettiva sincera

## Obiettivo

Questo documento confronta:

- quanto descritto nei documenti di pianificazione `tw-kpi-reason-engine-backlog.md`, `tw-kpi-reason-engine-plan.md`, `tw-kpi-reason-engine-sprint-backlog.md`, `tw-kpi-reason-engine-final-spec.md`
- quanto descritto nel PDF `D:\tender\KPIReasonEngine.pdf`
- quanto oggi e realmente integrato nel progetto TenderWriter

L'obiettivo non e celebrare il rilascio, ma chiarire con onesta:

- cosa e stato recepito molto bene
- cosa e stato implementato in forma adattata o semplificata
- cosa manca ancora per dire che TenderWriter realizza davvero il modello del PDF

## Sintesi esecutiva

La funzionalita rilasciata in `main` ha portato in TenderWriter un blocco importante e strutturato:

- esiste davvero un servizio dedicato `kpi-reason-engine`
- esiste davvero una integrazione backend come BFF verso il motore KPI
- esiste davvero una UI admin dedicata per osservare KPI, transizioni, forecast e workspace operativo
- esiste davvero un modello dati operativo che rende osservabili request, review, rework, gate e call
- esiste davvero una catena eventi che alimenta il motore lungo il ciclo del tender

Quello che NON e ancora vero fino in fondo e che TenderWriter abbia implementato il modello del PDF in modo pienamente fedele.

La soluzione attuale e:

- molto forte come sistema di osservabilita operativa e KPI explainable
- abbastanza coerente come rappresentazione di stati tipo `S4 -> S5 -> S6 -> S8 -> S9`
- solo parzialmente fedele al modello Markoviano teorico del PDF
- decisamente non ancora equivalente a un motore semantico/LLM per il calcolo qualitativo dei KPI

In una formula semplice:

- aderenza architetturale al piano: alta
- aderenza funzionale all'uso admin: alta
- aderenza metodologica al PDF: media

## Cosa e stato recepito davvero

### 1. Parti recepite in modo coerente e solido

Le seguenti idee del piano/spec sono entrate davvero in progetto:

- separazione tra sistema transazionale TenderWriter e motore KPI dedicato
- alimentazione event-driven del motore KPI a partire dal flusso reale del tender
- distinzione tra stato business del tender e stato analitico del motore
- KPI A1..A4, B1..B4, indice aggregato `Q`, indice aggregato `E`
- salute sintetica Green/Amber/Red
- spiegabilita del risultato tramite findings, driver, transizioni e forecast
- dashboard admin per portfolio overview, bottleneck, snapshot, diagnostica e timeline delle transizioni
- workspace operativo admin per agire su contributi, richieste, review, rework, gate e call
- funzioni operative di recupero: recompute, history backfill, portfolio resync
- degradazione controllata lato backend quando il motore KPI non risponde

Detto diversamente: la feature non e un mock, ma una integrazione reale, profonda e gia utile.

### 2. Parti recepite ma adattate

Qui c'e il primo punto di sincerita: molta logica del PDF e stata recepita come approssimazione operativa, non come replica scientifica.

Le principali adattazioni sono:

- il motore KPI attuale e dichiaratamente `deterministic_proxy`, non un motore LLM-semantico
- i KPI non lavorano sulla scala 1..10 del PDF/spec finale, ma di fatto su una scala 0..100
- il calcolo di `Q` non usa esattamente i pesi del final spec
- il forecast non nasce da una matrice Markov appresa o calibrata su dati, ma da euristiche con probabilita base e aggiustamenti rule-based
- la catena `S0..S13` e usata come vocabolario analitico e narrativo, ma non come catena markoviana completa persistita nel motore
- la UX admin non permette un override diretto dello stato analitico; permette invece di generare/chiudere gli eventi operativi che poi muovono i KPI

Questa scelta rende il sistema piu robusto e piu implementabile nel breve periodo, ma meno fedele alla visione teorica del PDF.

### 3. Parti ancora mancanti o divergenti

Le divergenze principali rispetto al PDF e ai documenti di spec sono queste:

- non esiste oggi un vero modello Markov con matrice di transizione persistita e aggiornata sui dati
- non esiste oggi un vero scoring semantico dei KPI A1..A4 tramite prompt/modelli
- `Q` usa pesi diversi dal final spec: in codice `A2=0.20` e `A3=0.25`, mentre nello spec finale `A2=0.15` e `A3=0.30`
- alcuni stati del PDF non sono davvero derivati in modo nativo dal motore, in particolare `S1` e `S10`
- il forecast esiste, ma non e memorizzato come storico dedicato separato
- la persistenza del motore e su SQLite, non su un repository analitico piu vicino al disegno enterprise iniziale
- la documentazione runtime del servizio e rimasta indietro rispetto alla realta implementata

Il punto piu importante da non nascondere e questo:

TenderWriter oggi NON implementa ancora la catena markoviana del PDF come modello matematico completo; ne implementa una traduzione pratica, spiegabile e utile alla gestione.

## Modello dati reale

Il modello dati reale e diviso in due livelli.

### Livello 1 - dominio TenderWriter

Questo e il livello transazionale e operativo del prodotto.

Entita principali:

- `Tender`: tender, deadline, stato corrente, outcome finale
- `Proposal`: proposta collegata al tender
- `ProposalSection`: sezioni della proposta, con stato, owner, avanzamento
- `Requirement` e contesto requisiti: estrazione, mappatura e stato di copertura/compliance

Entita operative introdotte dalla feature KPI:

- `ContributionUnit`
  - unita di lavoro osservabile collegata a un tender e opzionalmente a una sezione
  - rappresenta il "pezzo di contributo" da ottenere o governare
- `ContributionRequest`
  - richiesta inviata verso owner o dipartimento
  - contiene `requested_at`, `due_at`, SLA target/max, `response_received_at`
- `ReviewCycle`
  - ciclo di review per un contributo
  - contiene stage, reviewer, start/completion, outcome
- `ReworkAction`
  - azione di rework aperta a valle di una review o di un problema di contenuto
  - distingue anche il carattere `blocking`
- `ComplianceGate`
  - gate di controllo sul tender o su una contribution
  - puo essere `open`, `passed`, `failed`
- `CallSession`
  - sessione di call/meeting pianificata
- `AttendanceRecord`
  - traccia la presenza/assenza/invito per la call

### Livello 2 - mirror analitico del motore KPI

Questo e il livello letto dal servizio `kpi-reason-engine`.

Entita principali:

- `kpi_tenders`
  - mirror del tender e del suo contesto essenziale
- `kpi_domain_events`
  - stream eventi che racconta la storia analitica del tender
- `kpi_document_contexts`
  - contesto documentale e requirement context resi disponibili al motore
- `kpi_analysis_jobs`
  - job asincroni di analisi/recompute/backfill
- `kpi_model_versions`
  - versioni logiche di formule/modelli bundle
- `kpi_snapshots`
  - snapshot KPI con fase, salute, KPI score e metadata analitici
- `kpi_findings`
  - finding spiegabili emersi dallo snapshot
- `kpi_phase_transitions`
  - transizioni diagnostiche ricostruite o osservate

### Relazione tra i due livelli

La relazione e questa:

1. TenderWriter resta la sorgente di verita operativa.
2. Ogni evento importante sincronizza il tender verso il motore KPI.
3. Lo stesso evento viene pubblicato come domain event.
4. Il motore ricostruisce uno snapshot analitico leggendo mirror + eventi + contesto documentale.
5. L'admin legge il risultato via backend BFF.

In pratica:

- TenderWriter produce fatti
- il motore KPI li interpreta
- la UI admin li rende osservabili e azionabili

## Come la parte KPI interagisce con il flusso del tender

### Catena principale del flusso

Il flusso reale oggi e questo:

1. viene creato il tender
2. il documento tender viene caricato/ingestito
3. vengono estratti i requisiti
4. viene creata la proposal
5. vengono create/aggiornate le proposal section
6. le section generano o aggiornano automaticamente contribution unit e richieste operative
7. review, rework, gate e call producono ulteriori eventi osservabili
8. il motore KPI ricostruisce KPI, fase, salute, transizioni e forecast
9. l'admin osserva e interviene
10. la submission e l'outcome finale chiudono il percorso

### Dove nasce davvero il movimento KPI

Il motore KPI non vive "a lato", ma viene mosso da tre famiglie di segnali:

- eventi di lifecycle del tender
  - tender creato, documento ingestito, requisiti estratti, proposal creata, section aggiornata, tender submitted, outcome registrato
- eventi operativi admin
  - request create/receive, review start/complete, rework open/resolve, gate open/decision, call scheduled, attendance recorded
- automazioni di allineamento
  - se la section cambia stato, il workflow operativo viene riallineato automaticamente
  - se la compliance dei requirement cambia, viene aggiornato anche il gate automatico di readiness

### Punto cruciale: automazione del workflow da proposal section

Questa e una parte molto forte dell'implementazione attuale.

Quando una `ProposalSection` cambia stato o assegnatario, TenderWriter:

- puo cancellare richieste aperte obsolete
- puo creare automaticamente una nuova richiesta per il nuovo owner
- puo marcare come ricevuta la richiesta quando la section entra in review
- puo aprire automaticamente una review
- puo chiudere automaticamente una review come approved quando la section diventa approved
- puo aprire automaticamente un rework quando la section esce da review tornando in lavoro
- puo risolvere automaticamente rework aperti quando la section rientra in review o viene approvata

Questo significa che la parte KPI non e solo osservazione passiva: e agganciata al ciclo di vita reale della scrittura della proposal.

### Punto cruciale: gate automatico di compliance

Esiste anche un gate automatico chiamato `Auto compliance readiness`.

Il suo comportamento reale e:

- `open` se esistono requirement ancora non completamente chiusi
- `passed` se tutti i requirement mappati risultano pienamente indirizzati
- `failed` se la deadline passa con requirement ancora irrisolti

Questo e uno dei punti piu coerenti con il PDF, perche rende visibile nel prodotto la pressione del controllo `S8`.

## Come l'UX admin si sposa con la catena markoviana del PDF

### Dove c'e coerenza

L'UX admin e coerente con la catena del PDF in questi sensi:

- rende visibile la fase analitica come stato corrente del tender
- rende visibile la salute Green/Amber/Red come overlay operativo
- rende leggibile il loop `S4 -> S5 -> S6` attraverso review e rework
- rende leggibile il passaggio `S7 -> S8` attraverso i compliance gate
- rende leggibile il passaggio verso `S9` in seguito alla submission
- rende osservabili gli stati terminali di outcome
- espone un forecast a tre traiettorie coerenti con l'idea del PDF:
  - `submit_on_time`
  - `extended_rework`
  - `pause_or_stop`
- espone i driver di transizione, quindi l'admin puo capire non solo "dove siamo", ma "perche ci siamo arrivati"

Questa e una traduzione molto pragmatica della catena markoviana:

- non mostra una matrice
- mostra i fatti che spingono il tender da uno stato all'altro

### Dove la coerenza si ferma

Qui serve onesta piena.

L'UX admin non espone un vero motore markoviano in senso stretto, perche il motore sottostante non lo e.

In particolare:

- la probabilita dei rami non nasce da stima statistica sulla matrice di transizione, ma da regole hard-coded
- la derivazione di fase e rule-based
- non tutti gli stati del PDF sono realmente derivati dal motore
- l'admin non governa la catena impostando direttamente `Sx`; governa gli eventi operativi che poi spostano la lettura analitica

Questa scelta ha un vantaggio:

- evita override arbitrari e mantiene il sistema piu auditabile

Ma ha anche un limite:

- l'aderenza al modello teorico del PDF resta semantica e funzionale, non matematica

### Punto molto importante: submission e stato `S9`

Nel codice attuale, quando il tender risulta submitted, la fase analitica va direttamente a `S9`.

Quindi, se anche esistono ancora segnali rossi o gate problematici, il motore puo:

- collocare il tender in `S9`
- ma mantenere health/findings sfavorevoli

Questo e un comportamento utile dal lato "workflow registrato", ma meno rigoroso dal lato della logica markoviana ideale del PDF.

## Valutazione sincera del risultato

### Giudizio breve

Se la domanda e:

"Abbiamo integrato in TenderWriter una funzione KPI davvero importante?"

La risposta e:

- si, senza dubbio

Se la domanda e:

"Abbiamo implementato fedelmente il motore del PDF?"

La risposta e:

- non ancora, solo in parte

### Giudizio articolato

Come retrospettiva sincera direi:

- 8/10 come integrazione prodotto
- 8/10 come osservabilita amministrativa e controllabilita del flusso
- 6/10 come fedelta al modello KPI/Markov del PDF
- 5/10 come fedelta al layer semantico/LLM ipotizzato nella specifica

La parte rilasciata e quindi:

- molto valida come "operational KPI reason engine"
- ancora incompleta come "formal Markov + semantic reasoning engine"

## Catalogo dei casi d'uso del flusso tender

Di seguito i casi d'uso possibili, distinguendo il flusso tender e il flusso admin.

### A. Casi d'uso del tender dal percorso semplice fino alla submission

#### UC-T01 - Tender creato, documento ingestito, requisiti disponibili

- il tender viene creato
- il documento viene ingestito
- i requirement vengono estratti
- il motore KPI riceve mirror ed eventi iniziali
- il tender entra in uno stato iniziale di preparazione analitica

Esito atteso:

- snapshot disponibile
- A1 inizia a diventare misurabile
- il tender si colloca in una fase precoce del ciclo

#### UC-T02 - Documento ingestito ma requirement non ancora estratti

- il tender esiste
- il documento e stato caricato
- l'estrazione requirement non e ancora disponibile o e incompleta

Esito atteso:

- fase precoce
- A1/A4 deboli o incompleti
- l'admin vede che il problema e a monte, non nella review

#### UC-T03 - Requirement estratti ma proposal non ancora strutturata

- i requirement ci sono
- la proposal non ha ancora section utili o movimento reale

Esito atteso:

- il motore riconosce contesto ma non ancora lavoro strutturato
- i KPI qualitativi restano parziali

#### UC-T04 - Proposal creata con section e contribution auto-generate

- viene creata la proposal
- le section esistono
- il workflow operativo assicura la presenza delle `ContributionUnit`

Esito atteso:

- il tender passa nella fase di lavoro sostanziale
- inizia la misurazione di coverage e avanzamento sezione

#### UC-T05 - Assegnazione della section a un owner

- una section riceve o cambia assegnatario
- il sistema puo cancellare richieste obsolete e crearne di nuove

Esito atteso:

- nasce una `ContributionRequest`
- il ciclo operativo e ora osservabile
- B1/B2 diventano misurabili nel tempo

#### UC-T06 - Richiesta contributo con due date e SLA

- l'owner riceve richiesta
- viene impostata una scadenza
- vengono registrati SLA target/max

Esito atteso:

- il motore inizia a misurare disciplina esecutiva
- il tender resta in fase di lavorazione, non ancora review

#### UC-T07 - Contributo ricevuto

- la richiesta viene marcata come ricevuta
- la contribution passa a stato `received`

Esito atteso:

- B1/B2 migliorano se i tempi sono buoni
- il tender puo prepararsi al passaggio in review

#### UC-T08 - Review avviata

- parte un `ReviewCycle`
- la contribution passa a `in_review`

Esito atteso:

- il tender entra nella logica `S5`
- la timeline delle transizioni lo rende visibile

#### UC-T09 - Review approvata

- la review viene completata con outcome `approved`
- la contribution passa a `completed`
- la section puo risultare approved/integrata

Esito atteso:

- il tender si avvicina alla bozza integrata
- A2/A3/A4 tendono a salire
- la pressione rework diminuisce

#### UC-T10 - Review con cambi richiesti e apertura rework

- una section esce dalla review tornando a `todo` o `in_progress`
- il workflow operativo crea un `ReworkAction`

Esito atteso:

- il tender entra nel loop `S5 -> S6`
- il driver del problema e esplicito

Nota:

- questo ramo e fortemente coerente con la visione del PDF

#### UC-T11 - Rework blocking aperto

- il rework e `blocking`
- il contributo resta bloccante per il flusso

Esito atteso:

- il motore evidenzia `S6`
- il forecast aumenta `extended_rework`

#### UC-T12 - Rework risolto

- il rework viene chiuso
- la contribution rientra verso review/integrazione

Esito atteso:

- il tender puo tornare da `S6` a `S5`
- il forecast puo migliorare

#### UC-T13 - Requirement ancora incompleti e gate automatico aperto

- esistono section, ma i requirement non sono ancora tutti pienamente indirizzati
- il gate automatico `Auto compliance readiness` resta aperto

Esito atteso:

- il tender puo essere letto come pressione `S8`
- A4 e health soffrono

#### UC-T14 - Gate manuale aperto dall'admin

- l'admin apre un `ComplianceGate` manuale
- il gate puo essere generale o legato a una contribution

Esito atteso:

- il tender entra in controllo di compliance esplicito
- il motore registra la pressione di gate

#### UC-T15 - Gate fallito

- un gate aperto viene deciso come `failed`

Esito atteso:

- forte segnale negativo su readiness
- crescita del rischio `extended_rework` o `pause_or_stop`
- il tender resta o rientra in una dinamica tipo `S8`

#### UC-T16 - Gate passato

- un gate aperto viene deciso come `passed`

Esito atteso:

- si riduce la pressione `S8`
- il tender puo tornare verso integrazione/submission readiness

#### UC-T17 - Call operativa pianificata

- viene pianificata una call
- si registra il coordinamento del tender

Esito atteso:

- B3 puo diventare informativo
- il workspace operativo acquisisce traccia di sincronizzazione del team

#### UC-T18 - Attendance registrata

- si registra presenza, assenza, invito o excused

Esito atteso:

- il motore ha un ulteriore segnale su efficienza e coordinamento

#### UC-T19 - Submission lineare di un tender semplice

Scenario:

- requirement estratti
- section mappate
- contribution ricevute
- review chiuse positivamente
- gate allineati
- tender marcato submitted

Esito atteso:

- passaggio a `S9`
- forecast dominato da `submit_on_time`
- tender pronto al tratto finale

#### UC-T20 - Submission con rischio residuo ancora presente

Scenario:

- il tender viene comunque marcato submitted
- ma restano segnali di salute scarsa, gate recenti o requisiti fragili

Esito atteso:

- fase `S9` per registrazione del fatto di submission
- health/findings ancora critici

Questo e uno dei casi dove il prodotto attuale e piu workflow-driven che markov-driven.

#### UC-T21 - Outcome win

- il tender viene chiuso come vinto

Esito atteso:

- transizione a stato terminale positivo
- la parte forecast si blocca su outcome finale

#### UC-T22 - Outcome loss

- il tender viene chiuso come perso

Esito atteso:

- stato terminale negativo
- i driver restano utili per retrospettiva e apprendimento

#### UC-T23 - Outcome cancelled / no-bid / stop

- il tender viene fermato o cancellato

Esito atteso:

- stato terminale di stop
- scenario coerente con il ramo `pause_or_stop`

#### UC-T24 - KPI service degradato ma flusso business ancora vivo

- TenderWriter continua a lavorare
- il backend admin riceve fallback o dati ridotti dal motore

Esito atteso:

- il flusso tender non si rompe
- la lettura KPI diventa temporaneamente incompleta

#### UC-T25 - Ricostruzione storica dopo gap di eventi o allineamento tardivo

- si lancia recompute o backfill
- eventualmente si usa portfolio resync

Esito atteso:

- il motore ricostruisce snapshot e storia analitica
- la lettura KPI torna coerente con lo stato del tender

### B. Casi d'uso admin di osservazione e intervento

#### UC-A01 - Osservare il portfolio KPI

- l'admin apre la pagina dedicata
- vede overview, salute e distribuzione sintetica del portfolio

Obiettivo:

- capire dove concentrare attenzione

#### UC-A02 - Osservare i bottleneck di portfolio

- l'admin legge i principali colli di bottiglia emergenti

Obiettivo:

- capire se il problema e di compliance, review, rework o execution discipline

#### UC-A03 - Aprire lo snapshot di un tender

- l'admin seleziona un tender
- vede KPI, health, phase, findings e metadata di analisi

Obiettivo:

- capire lo stato corrente reale del tender

#### UC-A04 - Leggere il drilldown di compliance

- l'admin vede requirement coverage, stato di mapping e gate automatico

Obiettivo:

- capire se il tender e fragile per motivi di copertura/compliance

#### UC-A05 - Leggere la timeline delle transizioni

- l'admin vede transizioni e driver

Obiettivo:

- capire da quale evento il tender e stato spinto verso review, rework o gate

#### UC-A06 - Leggere il forecast

- l'admin vede i tre scenari:
  - `submit_on_time`
  - `extended_rework`
  - `pause_or_stop`

Obiettivo:

- decidere se accelerare, stabilizzare o fermare

#### UC-A07 - Rilanciare un recompute

- l'admin forza il ricalcolo del tender

Obiettivo:

- riallineare il motore KPI allo stato piu recente

#### UC-A08 - Lanciare replay/backfill della history

- l'admin chiede la ricostruzione storica degli eventi

Obiettivo:

- recuperare traiettoria e transizioni quando il dato corrente non basta

#### UC-A09 - Eseguire portfolio resync

- l'admin riallinea in batch il portfolio verso il motore KPI

Obiettivo:

- sanare drift o allineamenti incompleti

#### UC-A10 - Creare manualmente una contribution

- l'admin semina una `ContributionUnit` anche prima che il ciclo automatico la generi

Obiettivo:

- rendere osservabile un pezzo di lavoro critico

#### UC-A11 - Creare manualmente una richiesta contributo

- l'admin crea una `ContributionRequest`
- puo indicare owner, canale, due date e SLA

Obiettivo:

- attivare concretamente il flusso operativo e renderlo misurabile

#### UC-A12 - Marcare una richiesta come ricevuta

- l'admin registra la ricezione del contributo

Obiettivo:

- sbloccare il passaggio verso review
- alimentare B1/B2 con dato reale

#### UC-A13 - Avviare una review

- l'admin crea un `ReviewCycle`

Obiettivo:

- spostare il tender nella fase di controllo qualitativo

#### UC-A14 - Completare una review come approved dalla UI

- la UI oggi espone un quick action di approvazione

Obiettivo:

- chiudere il ramo review e favorire l'integrazione

Nota sincera:

- la UI non espone un editor completo di esiti review; espone almeno il ramo rapido "approved"

#### UC-A15 - Gestire una review non approvata

- questo e possibile via flusso section-driven o via API
- quando la section rientra in lavoro, il sistema apre il rework

Obiettivo:

- rientrare consapevolmente nel loop `S5 -> S6`

#### UC-A16 - Creare un rework

- l'admin apre una `ReworkAction`
- puo indicare severity, due date e se e blocking

Obiettivo:

- registrare formalmente un blocco o un ciclo di correzione

#### UC-A17 - Risolvere un rework

- l'admin chiude il rework

Obiettivo:

- riportare il tender verso review o integrazione

#### UC-A18 - Aprire un compliance gate

- l'admin crea un gate manuale

Obiettivo:

- introdurre un controllo formale prima di avanzare

#### UC-A19 - Marcare un gate come passed

- l'admin chiude positivamente il gate

Obiettivo:

- liberare il tender dalla pressione `S8`

#### UC-A20 - Marcare un gate come failed

- l'admin chiude negativamente il gate

Obiettivo:

- bloccare l'avanzamento e rendere esplicito il rischio

#### UC-A21 - Pianificare una call

- l'admin apre una `CallSession`

Obiettivo:

- coordinare il team e produrre telemetria di execution

#### UC-A22 - Registrare attendance

- l'admin registra partecipazione, assenza o invito

Obiettivo:

- alimentare il segnale di coordinamento operativo

#### UC-A23 - Osservare il gate automatico di compliance

- l'admin non deve per forza crearlo: il sistema puo gia generarlo

Obiettivo:

- capire se il tender e davvero pronto oppure solo apparentemente avanzato

#### UC-A24 - Far avanzare il flusso indirettamente

- l'admin non imposta direttamente `S4`, `S5`, `S6` o `S8`
- l'admin agisce sugli eventi reali del lavoro

Obiettivo:

- muovere il tender in modo auditabile e coerente con i fatti

Questo e probabilmente il principio UX piu sano della feature.

## Conclusione

La feature rilasciata e decisiva per TenderWriter perche:

- porta finalmente il tender dentro una lettura strutturata di qualita, efficienza, pressione di review e rischio di compliance
- collega in modo forte il mondo proposal al mondo operativo
- da all'admin un cockpit vero, non solo un report

Ma la retrospettiva sincera e questa:

- abbiamo costruito un motore KPI operativo molto buono
- non abbiamo ancora costruito il motore markoviano-semantico completo del PDF

La base per il passo successivo pero c'e gia tutta:

- event sourcing sufficiente
- data model osservabile
- UI admin coerente
- diagnostica, forecast e backfill gia operativi

Il prossimo salto di maturita non richiede ripartire da zero.
Richiede rendere piu fedele il layer di scoring e il layer probabilistico rispetto al modello originario.
