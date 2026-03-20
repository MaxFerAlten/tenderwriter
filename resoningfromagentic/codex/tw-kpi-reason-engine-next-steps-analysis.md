# TenderWriter KPI Reason Engine - analisi operativa dei prossimi passi

## Scopo

Questo documento non ripete il piano. Lo analizza.

L'obiettivo e chiarire:

- qual e il percorso critico reale
- quali dipendenze bloccano i workstream successivi
- quali rischi metodologici e di prodotto vanno evitati
- quale pacchetto iniziale di esecuzione conviene aprire subito

Documento di riferimento diretto:

- `D:\tender\tenderwriter\resoningfromagentic\codex\tw-kpi-reason-engine-next-steps-plan.md`

## Valutazione iniziale

Il piano e corretto nella direzione e nella sequenza logica.

La sua intuizione centrale e giusta:

- prima stabilizzare il contratto del modello
- poi rendere il dataset transizionale affidabile
- poi introdurre semantic scoring e Markov reale
- infine rifinire UX e rollout

Questa sequenza non e solo ordinata. E necessaria.

Se venisse invertita, i rischi principali sarebbero:

- metriche non comparabili tra versioni
- forecast apparentemente sofisticato ma metodologicamente fragile
- mismatch tra UI, documentazione e engine
- perdita di fiducia interna nel motore

## Diagnosi dei blocchi reali

## Blocco 1 - Manca ancora un contratto KPI davvero canonico

Questo e il blocco sistemico principale.

Dai documenti emerge che oggi convivono almeno quattro tensioni:

- specifica teorica su scala 1-10
- implementazione attuale di fatto su scala 0-100
- formula `Q` documentata con pesi diversi da quelli implementati
- output qualitativi non ancora standardizzati in modo unico

### Impatto

Finche questo punto non viene chiuso:

- non si puo confrontare in modo affidabile proxy vs semantic scoring
- non si puo spiegare bene all'admin cosa sta leggendo
- non si puo addestrare o calibrare un Markov con semantica stabile dello stato

### Giudizio

Questo e il vero `P0 assoluto`.

## Blocco 2 - Il dataset di transizione e promettente, ma non ancora certificato

Il modello dati e molto piu avanti del motore probabilistico. Questo e positivo, ma crea un rischio tipico: sovrastimare la prontezza dei dati solo perche il logging esiste.

Il fatto che esistano:

- `kpi_domain_events`
- `kpi_phase_transitions`
- `kpi_snapshots`
- history backfill

non significa automaticamente che il dataset sia gia adatto a stima empirica.

### Le domande che contano davvero

- gli eventi sono completi nel core loop?
- i timestamp sono consistenti?
- la tassonomia eventi e stabile?
- le transizioni inferite e quelle osservate sono distinguibili?
- i casi ricostruiti via backfill sono chiaramente marcati?

### Giudizio

Il dataset e probabilmente sufficiente per un Markov MVP, ma non ancora sufficientemente qualificato per essere trattato come base affidabile senza un audit dedicato.

## Blocco 3 - Il layer semantico e concettualmente pronto ma operativamente non governato

I documenti su KPI A e B sono ricchi e ben pensati, ma oggi descrivono molto meglio il framework ideale che non il contratto runtime effettivo del motore.

### Punti forti

- A1 e A4 sono gia abbastanza strutturabili
- B1-B4 hanno una base operativa solida e ben ancorata al modello dati
- il legame tra prompt, retrospective e governance e ben impostato

### Punti deboli

- A2 e A3 restano piu soggettivi e meno standardizzati
- gli output attesi non sono ancora uniformi
- non c'e ancora un disegno chiuso di evaluation set, benchmark e shadow comparison

### Giudizio

Il semantic scoring e pronto come sperimentazione controllata, non ancora come sostituto diretto del proxy.

## Blocco 4 - Il Markov teorico e piu maturo della sua base empirica

Le immagini e i documenti definiscono in modo chiaro:

- proprieta markoviana
- matrice di transizione empirica
- stato esteso `(Fase, ClasseSalute)`
- stati assorbenti

Questa parte concettuale e chiara.

Il problema non e la teoria. Il problema e il salto dalla teoria al motore di produzione.

### Rischio principale

Passare troppo presto a `(Fase, ClasseSalute)` senza aver prima validato il Markov sul solo livello `Fase` rischia di produrre:

- sparsita eccessiva
- matrici poco stabili
- probabilita rumorose
- overfitting narrativo su pochi casi

### Giudizio

La scelta giusta e quella gia implicita nel piano: Markov v1 su fase semplice e stati terminali, con salute come estensione successiva e non come prerequisito.

## Percorso critico reale

Il percorso critico reale non e composto da tutti i workstream. E composto solo da quelli senza i quali gli altri diventano esercizi fragili.

### Critical path raccomandato

1. `KPI contract v1`
2. `Event and transition audit`
3. `Transition-quality report sul core loop`
4. `Semantic scoring shadow mode per A1/A4`
5. `Markov core loop v1`
6. `UX provenance e rollout`

### Dipendenze forti

- `Semantic scoring MVP` dipende dal contract
- `Markov v1` dipende dal contract e soprattutto dal data audit
- `UX v2` dipende dalla disponibilita di provenance chiara dal motore

### Dipendenze deboli

- una parte della UX puo iniziare prima
- una parte del benchmark semantico puo essere preparata in parallelo al data audit

## Sequencing consigliato

## Fase A - Chiusura semantica del modello

### Cosa fare

- chiudere scala ufficiale
- chiudere formula ufficiale di `Q` ed `E`
- separare formalmente A1 da A4
- definire health e soglie di escalation
- definire output schema unico per score qualitativi e operativi

### Perche farlo ora

Perche questo trasforma il motore da insieme di euristiche utili a sistema con semantica governata.

### Cosa NON fare in questa fase

- non introdurre ancora chiamate LLM in produzione
- non cambiare la UI in modo sostanziale

## Fase B - Audit del dataset e qualifica delle transizioni

### Cosa fare

- misurare copertura eventi sul core loop
- distinguere `observed`, `inferred`, `reconstructed`
- valutare quante storie tender sono ricostruibili end-to-end
- identificare i buchi piu frequenti

### Perche farlo ora

Perche senza questa fase il Markov resta una raffinazione teorica, non un passo scientificamente credibile.

### Cosa NON fare in questa fase

- non stimare ancora matrici definitive
- non vendere ancora il forecast come calibrato sui dati

## Fase C - Semantic scoring in shadow mode

### Cosa fare

- partire da A1 e A4
- costruire prompt bundle versionato
- salvare evidenze strutturate
- confrontare proxy e semantic scoring su campione reale

### Perche partire da A1 e A4

Perche:

- sono i KPI piu strutturabili
- hanno maggiore impatto sul gate e sulla readiness
- consentono una validazione piu oggettiva di A2 e A3

### Cosa NON fare in questa fase

- non dismettere il proxy
- non usare il semantic score come unica base del forecast

## Fase D - Markov core loop v1

### Cosa fare

- stimare matrice su `S4/S5/S6/S8/S9/S10/S11/S12/S13`
- trattare gli stati finali come assorbenti
- fare backtesting semplice su tender chiusi
- confrontare output Markov vs forecast euristico attuale

### Perche cosi

Perche riduce il rischio di dispersione e massimizza la leggibilita dei primi risultati.

### Cosa NON fare in questa fase

- non aprire subito il livello stato esteso con tutte le combinazioni Green/Amber/Red
- non includere stati iniziali ancora debolmente osservabili solo per completezza teorica

## Fase E - Productization e UX v2

### Cosa fare

- mostrare provenance e confidence
- distinguere misurato, inferito, previsto
- segnalare tipo di motore attivo per il forecast
- esplicitare versione formula/modello/prompt

### Perche farlo alla fine

Perche questa parte ha senso solo quando il motore inizia davvero a portare output eterogenei e versionati.

## Rischi principali da governare

## R1 - Rischio di falsa precisione

Descrizione:

- il forecast viene percepito come scientifico prima che lo sia davvero

Mitigazione:

- etichettare chiaramente heuristic vs calibrated
- mostrare confidence e source type

## R2 - Rischio di rottura della serie storica

Descrizione:

- cambiando formula, scala o pesi si rende difficile comparare snapshot storici

Mitigazione:

- versionare ufficialmente formula bundle e score scale
- evitare overwrite semantici non compatibili senza metadata forti

## R3 - Rischio di conflitto tra proxy e semantic scoring

Descrizione:

- il team vede divergenze forti e perde fiducia nel nuovo motore

Mitigazione:

- shadow mode
- benchmark interno
- casi studio espliciti con review umana

## R4 - Rischio di sparsita del Markov

Descrizione:

- troppi stati e troppe combinazioni portano a matrici vuote o instabili

Mitigazione:

- partire dal core loop
- aggiungere salute solo in una seconda iterazione

## R5 - Rischio di espansione scope non necessaria

Descrizione:

- si prova a migliorare contemporaneamente motore, UI, reporting e dipartment-specific tuning

Mitigazione:

- mantenere scope stretto sul percorso critico

## Prima tranche di esecuzione consigliata

Se dovessi aprire subito il primo pacchetto operativo, consiglierei questo blocco.

## Pacchetto 1 - `Model contract + transition audit`

### Contenuto

- documento `KPI contract v1`
- decisione scala unica
- decisione formula `Q/E`
- output schema unico
- mapping stati supportati
- audit eventi core loop
- report di copertura transizioni
- definizione campi obbligatori per training/calibrazione

### Perche questo pacchetto e giusto

Perche produce in una sola tranche:

- chiarezza metodologica
- riduzione del debito semantico
- base reale per shadow mode e Markov

### Cosa abilita subito dopo

- A1/A4 semantic shadow mode
- Markov core loop v1
- UX provenance minimale

## Raccomandazioni decisionali

## Decisione raccomandata 1 - tenere 0-100 internamente

Motivo:

- e gia la realta dell'engine
- evita una riscrittura inutile del motore
- consente normalizzazione verso 1-10 solo dove serve comunicazione esterna

Condizione:

- va dichiarato ufficialmente e reso visibile come parte del contract

## Decisione raccomandata 2 - riallineare la formula ufficiale con versioning, non con correzione silenziosa

Motivo:

- il problema non e solo scegliere i pesi giusti
- il problema e garantire tracciabilita tra versioni di formula

Raccomandazione pratica:

- introdurre `formula_bundle_version` canonico per il nuovo contract
- non correggere il passato "come se fosse stato sempre cosi"

## Decisione raccomandata 3 - partire da A1 e A4 per il semantic MVP

Motivo:

- massimizzano valore e verificabilita
- sono piu utili di A2/A3 per il governo del rischio

## Decisione raccomandata 4 - Markov MVP solo sul core loop

Motivo:

- minimizza sparsita
- massimizza utilita pratica
- e coerente con cio che il prodotto osserva gia bene

## Decisione raccomandata 5 - introdurre provenance prima della messa in produzione del nuovo motore

Motivo:

- l'admin deve capire se sta leggendo proxy, inferenza o modello calibrato

## Segnali che indicheranno che siamo pronti a passare di livello

Si puo dire che il progetto e pronto a uscire dalla fase "motore operativo forte ma ancora incompleto" quando vedremo insieme questi segnali:

- contract KPI unico e stabile
- dataset transizionale qualificato con copertura alta sul core loop
- semantic scoring A1/A4 validato almeno in shadow mode
- forecast Markov v1 che batte o almeno spiega meglio l'euristico sui tender chiusi
- admin UX capace di mostrare provenance e confidence

## Conclusione

L'analisi conferma che il piano e sano, ma evidenzia anche una verita importante:

il prossimo salto non e principalmente di sviluppo feature, ma di disciplina del modello.

Il prodotto ha gia superato la fase "prototipo fragile".
Ora deve superare la fase "sistema utile ma semanticamente non ancora governato".

Per questo motivo il miglior investimento iniziale non e costruire subito piu intelligenza, ma chiudere prima le regole e la qualita dei dati su cui quell'intelligenza dovra poggiare.
