# Resoconto: Tentativi di stabilizzazione AI Search / Gara Toscana senza risultato finale soddisfacente

Data: 2026-04-14

---

## Obiettivo

L'obiettivo era ottenere una risposta **ampia, coerente, non troncata e priva di leakage di prompt** alla query sulla gara Toscana, partendo da un PDF ingestito nella pipeline RAG.

Il risultato voluto **non e stato ancora raggiunto in modo affidabile end-to-end**.

I sintomi osservati durante i tentativi sono cambiati nel tempo:

- risposte troppo corte e troncate
- leakage di prompt tipo `own answer`, `user question`
- degenerazione in loop tipo `owne owne` o `own own own`
- varianti ancora piu sporche tipo `s own language:// ...`
- in un passaggio successivo, dopo un filtro troppo aggressivo, **zero testo**

---

## Lavoro svolto

### 1. Riallineamento ingestion / retrieval / grafo

Intervento fatto per ridurre il degrado strutturale della pipeline, non solo quello generativo.

Modifiche principali:

- `backend/app/ingestion/pipeline.py`
- `backend/app/rag/chunker.py`
- `backend/app/rag/engine.py`
- `backend/app/rag/graph_retriever.py`
- `backend/app/tasks.py`

Azioni eseguite:

- il chunking non parte piu solo da `full_text`, ma da segmenti piu coerenti
- i chunk trasportano metadata piu ricchi (`tender_id`, `filename`, `source_document_ref`, `section_title`, `page_number`)
- il `tender_id` viene iniettato automaticamente nei filtri di retrieval
- il graph retrieval evita di mischiare nodi globali quando la query e scoped a una gara
- il task di ingestion passa anche `source_document_ref`

Test aggiunti:

- `backend/tests/test_ingestion_chunk_scope.py`
- `backend/tests/test_rag_scope_filters.py`

Nota:

- questa parte migliora la coerenza della conoscenza disponibile, ma **non ha risolto da sola il problema delle risposte degradate in AI Search**

---

### 2. Osservabilita vera dell'ingestion

Per capire dove si fermava la pipeline ho aggiunto osservabilita per stage reali nel task Celery.

File coinvolti:

- `backend/app/ingestion/observability.py`
- `backend/app/ingestion/pipeline.py`
- `backend/app/tasks.py`
- `backend/app/api/tenders.py`
- `backend/app/api/ingestions.py`
- `frontend/src/api/client.ts`
- `frontend/src/pages/IngestionMonitor.tsx`

Stage tracciati:

- `download`
- `parse`
- `requirement_extraction`
- `chunking`
- `index_qdrant`
- `sync_neo4j`
- `compliance`
- `completed`

Esito del monitoraggio reale sul PDF Toscana:

- upload accettato
- ingestion completata
- `chunk_count=1487`
- Qdrant popolato
- Neo4j popolato

Conclusione:

- il blocco non era il grafo
- il problema osservato in AI Search **non era spiegato da una ingestion fallita**

---

### 3. Fix per risposte troppo corte sulla gara Toscana

La query tipo:

```text
analizza tutti i dettagli della gara toscana
```

veniva interpretata male e non entrava nel ramo di overview dettagliata.

Intervento in:

- `backend/app/rag/engine.py`

Fix introdotti:

- ampliamento delle regex di intent detection (`analizza`, `dettagli`, `approfondita`, `esaustiva`, ecc.)
- retrieval query piu pulita e focalizzata sulla gara
- aumento automatico del budget di generazione per overview ampie
- boost di `retrieval_top_k` e `final_top_k` per overview strutturate

Test aggiunto:

- `backend/tests/test_rag_tender_overview_longform.py`

Verifica eseguita:

```bash
python3 -m unittest tests.test_rag_tender_overview_longform
```

Esito:

- test locale passato
- **ma in UI il problema non si e esaurito**, perche il degrado successivo si e manifestato come leakage e loop di prompt

---

### 4. Analisi del degradation loop in uscita

Dopo il fix sulla lunghezza, l'output ha iniziato a mostrare leakage piu esplicito:

Esempi osservati:

```text
own answer own answer own answer ...
user question ...
```

poi:

```text
s own own own own ...
```

poi:

```text
s own language:// a own own own ...
```

e in alcuni casi finali:

```text
}
}
}
```

Questo indicava che:

- il modello stava facendo echo di frammenti del prompt
- i filtri backend/frontend intercettavano solo una parte dei pattern
- alcuni casi avvenivano nello streaming e non solo nel testo finale

---

### 5. Primo ciclo di fix sui filtri di leakage

Interventi su:

- `backend/app/rag/engine.py`
- `frontend/src/pages/searchAnswerSanitizer.ts`
- `frontend/src/pages/searchAnswerSanitizer.test.ts`
- `backend/tests/test_rag_prompt_leakage_loop.py`

Pattern coperti nel primo ciclo:

- `own answer`
- `your answer`
- `user question`
- loop ripetuti su riga intera
- suffissi di leakage attaccati alla stessa riga del testo utile

Problemi trovati durante il debug:

- un match troppo permissivo lasciava dietro frammenti come `own`
- alcuni casi venivano spezzati a meta dall'inline sanitizer

Sono stati corretti con test mirati.

Verifica locale:

```bash
python3 -m unittest tests.test_rag_prompt_leakage_loop
```

Esito:

- i casi semplici di `own answer / user question` risultavano rimossi correttamente
- **ma il comportamento reale in UI ha continuato a mutare**

---

### 6. Gestione del pattern piu sporco: `s own own ...` e `s own language:// ...`

Ulteriore intervento sempre su:

- `backend/app/rag/engine.py`
- `frontend/src/pages/searchAnswerSanitizer.ts`

Nuovi fix introdotti:

- rimozione di prefissi tipo `s own own own...`
- rimozione di righe composte solo da `own` ripetuti
- pulizia di code tipo `}`
- rimozione di prefissi corrotti che richiamano il wrapper prompt (`same language`, `use only`, `output only`, ecc.)
- sanificazione anche del percorso di streaming backend, non solo del testo finale

In questa fase ho aggiunto logica per distinguere:

- prefisso spazzatura puro
- prefisso spazzatura seguito da una risposta vera

e per evitare di conservare residui tipo:

```text
fai dei test prima di concludere che va bene
```

quando fanno parte del prompt garbage e non della risposta.

---

### 7. Regressione introdotta: zero testo

Durante questo secondo ciclo di filtri, il sistema e diventato troppo aggressivo.

Ho riprodotto localmente che:

- `sulla base dei documenti forniti, ...` veniva azzerato
- `e prevista una cauzione definitiva...` veniva azzerato o tagliato

Questa regressione nasceva dal criterio usato per decidere se, dopo un prefisso sporco, il resto della riga fosse una risposta plausibile.

Correzione fatta:

- abbandonata una whitelist troppo stretta di inizi validi
- sostituita con una blacklist di inizi che sembrano chiaramente un comando utente (`fai`, `spiega`, `analizza`, `riassumi`, ecc.)
- aggiunta gestione corretta delle lettere accentate (`e`, `e prevista`, ecc.)

Test locali mirati eseguiti:

- il prefisso sporco seguito da risposta reale viene conservato
- il prefisso sporco seguito da testo tipo comando viene scartato

---

## Test eseguiti

Test backend eseguiti con successo:

```bash
python3 -m unittest tests.test_rag_prompt_leakage_loop tests.test_rag_tender_overview_longform
```

Esito finale locale:

- `9` test backend passati

Verifiche manuali locali fatte in Python:

- `s own language:// ... L'analisi della gara ...` -> ripulito correttamente
- `s own language:// ... sulla base dei documenti ...` -> ripulito correttamente
- `s own language:// ... e prevista una cauzione ...` -> ripulito correttamente
- `s own language:// ... fai dei test ...` -> scartato

Test frontend automatici:

- non eseguibili in questo ambiente, per mancanza di runtime/tooling `node`/`vitest`

Quindi il frontend e stato aggiornato, ma **non validato con esecuzione automatica locale**.

---

## Riavvii eseguiti / richiesti

Hai rilanciato:

```bash
sudo ./build_and_start.sh
```

Lo script e corretto come restart generale perche:

- builda `frontend`
- builda `backend`
- rialza i container

Tuttavia, molte patch sono state introdotte **dopo** i vari riavvii intermedi, quindi servivano restart successivi per testare ogni iterazione.

---

## Stato attuale reale

La situazione attuale e questa:

- la parte ingestion / retrieval e stata rafforzata
- la parte overview Toscana e stata migliorata sul routing
- i filtri anti-leakage sono stati estesi molto
- i test backend mirati passano

Ma il risultato voluto, cioe:

> una risposta reale in AI Search sulla gara Toscana, lunga, pulita, stabile e senza degrado

**non e ancora stato dimostrato come stabilmente ottenuto in produzione/UI**.

In particolare:

- i sintomi sono cambiati piu volte dopo i fix
- ogni fix ha corretto un pattern specifico ma ne ha fatto emergere un altro
- in un passaggio si e arrivati perfino a zero testo
- il comportamento reale dipende anche dal path di streaming e dal modello che continua a esporre frammenti di prompt

---

## Conclusione onesta

E stato fatto molto lavoro utile di diagnosi e hardening:

- osservabilita ingestion
- riallineamento chunking / filters / graph scope
- miglior routing per overview Toscana
- sanitizzazione backend e frontend molto piu ampia
- test backend mirati

Pero **non posso dire che il problema sia risolto**.

Quello che posso dire in modo corretto e:

- la superficie del problema e stata capita meglio
- sono stati rimossi molti pattern concreti di degradazione
- il sistema e piu osservabile e piu robusto di prima
- ma **non c'e ancora una prova end-to-end soddisfacente che AI Search risponda come desiderato sulla gara Toscana**

---

## Punto tecnico piu probabile ancora aperto

Il nodo residuo piu sospetto non e piu solo il sanitizer, ma il fatto che il modello / path di generazione continui a far trapelare frammenti del wrapper prompt.

Quindi la prossima indagine, se si vuole proseguire, dovrebbe concentrarsi su:

1. ridurre il leakage alla fonte nel generatore, non solo in post-processing
2. confrontare `generate()` e `generate_stream()` per verificare uniformita del wrapping prompt
3. loggare raw stream token-by-token in un caso di query Toscana reale
4. verificare se il modello o il server `llama.cpp` stanno riecheggiando il prompt chat wrapper
5. aggiungere un test end-to-end vero sulla route AI Search, non solo test di utility/sanitizer

---

*Resoconto redatto dopo i tentativi effettivamente svolti nella sessione del 2026-04-14, con esito parziale e senza conferma del risultato finale desiderato.*
