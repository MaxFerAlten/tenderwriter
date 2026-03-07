# Flusso di Upload PDF e Ingestione nel RAG

Ecco l'analisi di come un PDF viene caricato e inserito nel sistema RAG (Retrieval-Augmented Generation) all'interno di Tenderwriter.

## 1. Caricamento e Ingestione (Passo-Passo)

Quando un utente carica un PDF per una specifica gara (Tender), il software esegue i seguenti passi:

1. **Chiamata API di Upload**: Il client invia il file tramite una richiesta `POST` all'endpoint `/api/tenders/{tender_id}/import` (gestito in [app/api/tenders.py](file:///d:/tender/tenderwriter/backend/app/api/tenders.py)).
2. **Salvataggio su MinIO (Object Storage)**: Il file originale viene caricato e salvato nel bucket MinIO sotto il percorso `tenders/{tender_id}/{filename}` per conservazione e riferimenti futuri.
3. **Avvio della Pipeline di Ingestione**: Il file viene letto e passato alla classe [IngestionPipeline](file:///d:/tender/tenderwriter/backend/app/ingestion/pipeline.py#21-349) ([app/ingestion/pipeline.py](file:///d:/tender/tenderwriter/backend/app/ingestion/pipeline.py)), che coordina l'elaborazione.
4. **Parsing del Documento**: 
   - La pipeline usa la libreria `unstructured` per analizzare il PDF, estraendo testo, titoli, tabelle e metadati (come il numero di pagina).
   - *Fallback*: Se `unstructured` fallisce o non è disponibile, usa `PyMuPDF` (fitz) per estrarre il testo grezzo pagina per pagina.
5. **Strutturazione del Testo**: Gli elementi estratti vengono ricombinati in un testo completo continuo e divisi per sezioni.
6. **Chunking (Frammentazione) ed Embedding**: 
   - Il motore ibrido (`HybridRAGEngine.chunk_and_embed`) usa un `SemanticChunker` per suddividere il testo lungo in frammenti più piccoli (chunks) preservando il significato semantico.
   - Ogni frammento viene convertito in un vettore matematico (embedding) tramite il modello di embedding configurato.
7. **Indicizzazione Multipla (Hybrid RAG)**:
   I frammenti vengono indicizzati in due motori di ricerca diversi dal metodo [index_chunks](file:///d:/tender/tenderwriter/backend/app/rag/engine.py#355-371):
   - **Dense Retriever (Qdrant)**: Salva i vettori per la ricerca semantica (permette di trovare concetti simili anche con parole diverse).
   - **Sparse Retriever (BM25)**: Indicizza le parole chiave per la ricerca esatta dei termini testuali.
8. **Knowledge Graph (Neo4j)** *(Opzionale)*: Se il documento è di un tipo supportato (es. CV o proposal), un LLM estrae entità strutturate (progetti, persone, competenze) e le inserisce nel Knowledge Graph per recuperare relazioni complesse.

---

## 2. Come effettuare le Ricerche nel Sistema RAG

Le ricerche nel sistema sono gestite dall'API `/api/rag/query` (in [app/api/rag.py](file:///d:/tender/tenderwriter/backend/app/api/rag.py)) e orchestrare dall'[HybridRAGEngine](file:///d:/tender/tenderwriter/backend/app/rag/engine.py#66-381) ([app/rag/engine.py](file:///d:/tender/tenderwriter/backend/app/rag/engine.py)).

Il motore di ricerca è **ibrido** perché combina più strategie per garantire il miglior risultato:

1. **Richiesta del Client**: Invia una query (es. "Quali sono i requisiti di sicurezza?") specificando se vuole solo cercare documenti (`mode="search"`) o generare una risposta (`mode="qa"`).
2. **Prima Fase - Recupero Parallelo**:
   - Il **Dense Retriever** cerca i vettori (chunks) più vicini al significato della domanda.
   - Lo **Sparse Retriever** cerca le porzioni di testo che contengono le stesse parole chiave della domanda.
   - Il **Graph Retriever** (se applicabile) cerca le entità relazionate nel grafo di Neo4j.
3. **Fusione (RRF - Reciprocal Rank Fusion)**: I risultati delle tre ricerche vengono uniti. È probabile che documenti trovati da più metodi salgano in cima alla lista.
4. **Re-Ranking (Riordinamento)**: Un modello *Cross-Encoder* prende le migliori `N` risposte fuse e le analizza una ad una insieme alla domanda, riordinandole in base alla reale pertinenza. Questo passaggio migliora enormemente la precisione.
5. **Fase di Generazione (opzionale)**: Se la modalità prevede una generazione ("qa", "write_section", ecc.), i testi dei documenti migliori trovati (il "contesto") vengono passati al modello LLM locale (Ollama) insieme alla domanda per generare una risposta discorsiva, basata *esclusivamente* sui documenti recuperati.
6. **Risposta**: Ritorna la risposta generata (o lo stream) assieme alle **fonti** (sources) utilizzate.
