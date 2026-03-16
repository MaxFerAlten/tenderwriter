# TenderWriter KPI Reason Engine - esplicitazione dei prossimi passi

## Scopo

Questo documento esplicita i punti chiave del piano dei prossimi passi in tre dimensioni distinte:

- cosa significano come funzionalita di prodotto
- cosa significano come integrazione nel sistema TenderWriter
- cosa significano in termini di aderenza al documento di specifica originario

Documenti di riferimento:

- `D:\tender\tenderwriter\kpi-reason-engine\docs\KPIReasonEngine.md`
- `D:\tender\tenderwriter\resoningfromagentic\codex\tw-kpi-reason-engine-next-steps-plan.md`
- `D:\tender\tenderwriter\resoningfromagentic\codex\tw-kpi-reason-engine-next-steps-analysis.md`
- `D:\tender\tenderwriter\resoningfromagentic\codex\tw-kpi-reason-engine-retrospettiva.md`
- `D:\tender\tenderwriter\resoningfromagentic\codex\tw-kpi-reason-engine-retrospettiva-manageriale.md`

## Premessa

I punti che ho elencato non sono semplici task tecnici. Ognuno corrisponde a un salto di maturita del motore.

La logica corretta e questa:

- alcuni punti servono a dare un significato stabile al motore
- altri servono a dare affidabilita statistica ai dati
- altri ancora servono a rendere il motore piu fedele alla tua specifica originaria

Per questo vanno letti come livelli progressivi di evoluzione e non come lista piatta di attivita.

## 1. KPI contract v1

## Cosa significa come funzionalita

Vuol dire trasformare il KPI Reason Engine da insieme di regole utili ma parzialmente eterogenee a sistema con un contratto ufficiale e stabile.

In pratica significa decidere una volta sola e in modo esplicito:

- quale scala usa il sistema
- come si calcolano `Q` ed `E`
- come si determinano le classi Green / Amber / Red
- quali output deve produrre ogni KPI
- quali stati analitici sono ufficialmente supportati dal motore

Dal punto di vista funzionale, questo non aggiunge subito un nuovo bottone in UI, ma aggiunge qualcosa di piu importante: rende coerente il significato di tutto cio che l'admin legge.

In altre parole, questo step serve a far si che quando l'admin vede:

- un punteggio KPI
- una classe di salute
- una previsione
- una fase analitica

stia leggendo un sistema definito in modo univoco e non un insieme di approssimazioni nate in momenti diversi.

## Cosa significa come integrazione

L'integrazione riguarda almeno 5 livelli:

### 1. Reason engine

Serve riallineare:

- formule interne
- soglie health
- versioning del bundle formula/model/prompt
- payload di snapshot e metadata

### 2. Backend BFF

Serve garantire che il backend esponga all'admin le stesse definizioni usate dal motore.

### 3. Frontend admin

Serve chiarire come presentare:

- score grezzi
- score sintetici
- stato health
- eventuali conversioni di scala

### 4. Documentazione

Serve eliminare il disallineamento tra:

- `KPIReasonEngine.md`
- documenti di retrospettiva
- comportamento reale del codice

### 5. Test

Servono test che validino non solo che il motore "giri", ma che applichi davvero il contratto canonico.

## Cosa significa in termini di aderenza alla specifica

Questo step non realizza ancora la parte piu ambiziosa della tua specifica, ma e il prerequisito per rispettarla davvero.

Perche?

Perche la tua specifica definisce chiaramente:

- KPI A1-A4 e B1-B4
- indici sintetici `Q` ed `E`
- classi di salute
- relazione tra stato del processo e qualita/esecuzione

Oggi TenderWriter e vicino allo spirito di questa specifica, ma non ancora completamente aderente nella semantica ufficiale.

Quindi:

- oggi l'aderenza e parziale
- con `KPI contract v1` l'aderenza diventa esplicita e governata

### Effetto sulla specifica

Questo step corrisponde alla formalizzazione del linguaggio del tuo modello.

Senza questo step, il resto del percorso rischia di poggiare su definizioni instabili.

## 2. Event and transition audit / data foundation

## Cosa significa come funzionalita

Vuol dire verificare se il motore sta davvero raccogliendo dati sufficienti, coerenti e ricostruibili per capire come il tender si muove nel tempo.

Funzionalmente significa costruire la capacita del sistema di dire non solo:

- dove si trova ora il tender

ma anche:

- come ci e arrivato
- quali transizioni sono avvenute davvero
- quali transizioni sono solo inferite
- quali dati sono abbastanza affidabili per sostenere un modello probabilistico

Questo step e il passaggio da "osservabilita utile" a "base empirica affidabile".

## Cosa significa come integrazione

Qui l'integrazione e soprattutto tra dominio operativo e reason engine.

### 1. Eventi dal backend al motore

Serve verificare che gli eventi chiave del core loop arrivino in modo completo e consistente:

- review started / completed
- rework requested / resolved
- gate opened / passed / failed
- tender submitted
- outcome finale

### 2. Ricostruzione storica

Serve distinguere chiaramente tra:

- dato osservato direttamente
- dato inferito dal motore
- dato ricostruito via backfill

### 3. Transizioni persistite

Serve qualificare `kpi_phase_transitions` come base analitica vera, non solo narrativa diagnostica.

### 4. Qualita dei timestamp e dei payload

Per un Markov reale non basta avere un evento; serve anche che il suo significato sia univoco e il suo timestamp sia affidabile.

## Cosa significa in termini di aderenza alla specifica

La tua specifica ideata e molto chiara nel postulare una dinamica markoviana e una stima del tipo:

- `P_ij = N(i -> j) / sum_j N(i -> j)`

Questa formula implica un fatto fortissimo:

- devono esistere transizioni osservabili o ricostruibili in modo coerente

Quindi questo step e il ponte tra:

- specifica teorica del Markov
- possibilita reale di stimare la matrice sui dati TenderWriter

### Effetto sulla specifica

Questo step non implementa ancora il Markov, ma rende finalmente possibile implementarlo in modo aderente alla specifica senza inventare probabilita a mano.

## 3. Semantic scoring MVP per A1 e A4

## Cosa significa come funzionalita

Vuol dire far fare al motore qualcosa che oggi non fa ancora davvero: leggere il contenuto e valutarlo semanticamente, invece di dedurlo solo da proxy strutturali.

Per `A1` significa:

- capire se i requisiti della gara sono davvero coperti nel contenuto
- produrre evidenze su requisiti coperti, parziali o mancanti

Per `A4` significa:

- capire se nel contenuto ci sono rischi di non conformita, vaghezze, claim non verificabili, mancanze rispetto ai vincoli

Questa e la prima vera introduzione nel prodotto della parte piu "reasoning" della tua idea originaria.

## Cosa significa come integrazione

### 1. Integrazione con il contenuto

Serve collegare il motore KPI a:

- requirement context
- proposal content
- section content o contributi testuali utili

### 2. Integrazione con il job system

Lo scoring semantico non deve bloccare il flusso operativo. Va quindi integrato nel sistema job/snapshot in modo asincrono.

### 3. Integrazione con gli snapshot

Gli snapshot devono iniziare a contenere non solo il punteggio, ma anche:

- evidenze
- criticita
- confidence
- tipo sorgente del punteggio

### 4. Integrazione con la UI admin

L'admin deve poter leggere il perche del punteggio, non solo il numero.

## Cosa significa in termini di aderenza alla specifica

Questo e il punto con il piu alto valore di aderenza alla tua specifica originaria.

Nel documento `KPIReasonEngine.md` hai definito in modo molto preciso:

- i 4 KPI qualitativi
- i loro obiettivi
- gli input necessari
- gli output attesi
- i prompt LLM da usare

Oggi il motore non realizza ancora davvero questa parte; usa proxy deterministici.

Quindi:

- oggi l'aderenza a questa sezione della specifica e bassa o media
- con `A1/A4 semantic scoring MVP` si comincia ad aderire davvero al cuore qualitativo della tua ideazione

### Perche partire da A1 e A4

Perche sono i KPI piu importanti e piu verificabili:

- A1 realizza il concetto di copertura requisiti
- A4 realizza il concetto di rischio di non conformita

Sono anche quelli piu vicini alla tua logica di gate e readiness.

## 4. Markov core loop v1

## Cosa significa come funzionalita

Vuol dire sostituire la previsione attuale, ancora euristica, con una previsione basata sul comportamento osservato dei tender nel sistema.

Funzionalmente significa che il motore non dira piu solo:

- "questo tender sembra a rischio"

ma potra dire qualcosa di piu forte:

- "dato che siamo in questa fase, con questa storia di transizioni, la probabilita empirica di rework, submission o stop e questa"

Questo e il passaggio dal forecast narrativo al forecast basato su transizioni reali.

## Cosa significa come integrazione

### 1. Integrazione con il log storico

Serve leggere e aggregare lo storico delle transizioni.

### 2. Integrazione con snapshot e health

Serve decidere se il Markov v1 usa:

- solo la fase
- oppure anche la salute come stato esteso

La raccomandazione iniziale e usare solo la fase nel core loop.

### 3. Integrazione con il motore forecast esistente

Il nuovo Markov non deve necessariamente rimpiazzare subito tutto. Può convivere inizialmente con l'euristico per confronto e validazione.

### 4. Integrazione con UI e governance

Serve mostrare chiaramente all'admin se il forecast e:

- heuristic
- calibrated / Markov v1

## Cosa significa in termini di aderenza alla specifica

Questo e il punto con il piu alto valore di aderenza alla parte dinamica e matematica della tua specifica.

Le immagini e i documenti che hai ideato definiscono chiaramente:

- proprieta markoviana
- matrice empirica delle transizioni
- stati assorbenti
- core loop `S4 -> S5 -> S6`
- gate `S8`
- esiti finali `S11 / S12 / S13`

Oggi TenderWriter usa questo schema come linguaggio analitico, ma non ancora come vero modello probabilistico calibrato.

Quindi:

- oggi l'aderenza e semantica e narrativa
- con `Markov core loop v1` l'aderenza diventa finalmente anche algoritmica

### Perche solo sul core loop

Perche il tuo modello teorico completo e corretto, ma il prodotto oggi osserva molto meglio il cuore operativo che non l'intera catena precocissima.

Partire dal core loop significa essere fedeli alla sostanza del tuo impianto, senza forzare precisione artificiale sugli stati meno osservabili.

## 5. Provenance, confidence e UX admin v2

## Cosa significa come funzionalita

Vuol dire far capire chiaramente all'admin cosa sta leggendo.

Oggi l'admin ha gia un cockpit utile. Il passo successivo e renderlo epistemicamente chiaro.

In pratica il sistema deve dire, per ogni elemento importante:

- questo e un dato osservato
- questo e un punteggio inferito
- questo e un punteggio semantico
- questa e una previsione probabilistica
- questa e la confidence del risultato
- questa e la versione del motore che lo ha prodotto

Funzionalmente non cambia solo la grafica. Cambia la qualita della fiducia che il sistema puo meritare.

## Cosa significa come integrazione

### 1. Reason engine

Serve far uscire in modo strutturato:

- source type
- confidence
- formula version
- model version
- prompt version

### 2. Backend BFF

Serve trasportare questi metadati senza schiacciarli o perderli.

### 3. Frontend admin

Serve visualizzarli in modo semplice ma chiaro, senza rendere la UI opaca o troppo tecnica.

## Cosa significa in termini di aderenza alla specifica

La tua specifica non e solo un modello matematico; e anche un modello di governo del processo.

Per essere davvero aderente, TenderWriter non deve solo "calcolare" bene. Deve anche:

- spiegare bene
- rendere leggibile il perche
- far capire il livello di affidabilita del risultato

Questo step e quindi molto aderente allo spirito manageriale e decisionale della tua specifica, anche se non e il cuore matematico del modello.

## 6. Perche l'ordine dei punti e questo

L'ordine non e arbitrario.

### Prima `KPI contract v1`

Perche senza semantica stabile:

- non puoi confrontare punteggi
- non puoi spiegare gli scarti
- non puoi addestrare o calibrare nulla in modo serio

### Poi `event and transition audit`

Perche il Markov non nasce dal desiderio di fare forecasting, ma dalla disponibilita di transizioni osservabili affidabili.

### Poi `semantic scoring A1/A4`

Perche li e piu alta l'aderenza alla tua specifica qualitativa e piu alta la verificabilita.

### Poi `Markov core loop v1`

Perche solo a quel punto il forecasting smette di essere un raffinamento euristico e diventa una vera implementazione del tuo modello.

### Infine `provenance/confidence in UX`

Perche la UI deve riflettere un motore che nel frattempo e diventato piu ricco, piu versionato e piu credibile.

## Lettura finale in termini di aderenza alla tua specifica

Se prendo la tua specifica come riferimento ideale, i punti si possono leggere cosi:

### Aderenza semantica del modello

Viene rafforzata da:

- `KPI contract v1`
- `semantic scoring A1/A4`

### Aderenza matematica / markoviana

Viene rafforzata da:

- `event and transition audit`
- `Markov core loop v1`

### Aderenza prodotto / governo admin

Viene rafforzata da:

- `provenance, confidence e UX admin v2`

### Sequenza complessiva di aderenza

Oggi TenderWriter e:

- forte nell'infrastruttura
- buono nella lettura operativa
- parziale nella fedelta semantica
- parziale nella fedelta markoviana

Con questi step, l'evoluzione attesa e:

1. prima coerenza semantica del motore
2. poi misurabilita affidabile delle transizioni
3. poi vera aderenza alla parte LLM / qualitative reasoning
4. poi vera aderenza alla parte Markov / probabilistic forecasting
5. infine piena leggibilita lato admin

## Conclusione

I punti che ho elencato non sono quindi semplicemente:

- manutenzione
- miglioramento tecnico
- rifinitura UX

Sono i 5 passaggi con cui TenderWriter puo passare da:

- ottimo motore operativo con retrospettiva forte

a:

- implementazione molto piu fedele al sistema che hai progettato nel documento di specifica

La loro funzione profonda e questa:

- il `contract` da il significato
- il `dataset audit` da la base empirica
- il `semantic scoring` da il reasoning sui contenuti
- il `Markov v1` da la dinamica probabilistica
- la `UX provenance` da la governabilita manageriale
