# Analisi Flusso PDF & HybridRAG — Riepilogo Tecnico

Questo documento riassume l'analisi del flusso di caricamento documenti e i test di integrazione con il motore HybridRAG implementati nel progetto **TenderWriter**.

---

## 📑 1. Ciclo di Vita di un PDF nel Sistema (Step-by-Step)

Quando carichi un documento, il software esegue i seguenti passi:

1.  **Ingestion & Upload**:
    - Il file viene ricevuto dall'endpoint API.
    - Viene salvato fisicamente su **MinIO** (Object Storage) per garantire persistenza.
    - Viene creato un record nel database **PostgreSQL** con lo stato `PENDING`.

2.  **Preprocessing & Parsing**:
    - Utilizzo della libreria `unstructured` per estrarre testo, tabelle e metadati dal PDF.
    - Il testo viene pulito e normalizzato.

3.  **Chunking (Frammentazione)**:
    - Il documento viene diviso in piccoli frammenti (chunks) di circa 500-1000 caratteri.
    - Ogni chunk mantiene il riferimento al documento originale e al numero di pagina.

4.  **Triple Indexing (Il cuore del HybridRAG)**:
    - **Dense Indexing**: Ogni chunk viene convertito in un vettore numerico (embeddings) e salvato su **Qdrant**. Questo permette la ricerca semantica (concetti, non solo parole).
    - **Sparse Indexing**: Viene creato un indice BM25 (keyword-based) per trovare termini specifici o codici tecnici che la ricerca semantica potrebbe mancare.
    - **Knowledge Graph Indexing**: Le entità e i concetti chiave estratti dai chunk vengono collegati su **Neo4j**, creando relazioni tra gare diverse o requisiti simili.

---

## 🧪 2. Test di Certificazione Caricamento

Per certificare che il flusso funzioni correttamente, è stato predisposto uno script di test:
`backend/test_pdf_upload.py`

### Cosa verifica lo script:
- Connessione corretta a FastAPI.
- Capacità di inviare un file binario (PDF).
- Risposta positiva del server con ID del documento.
- (In ambiente dev) Verifica che il file sia effettivamente presente nel bucket MinIO.

**Comando per eseguirlo**:
```bash
docker exec -it tw-backend python3 test_pdf_upload.py
```

---

## 🔍 3. Come eseguire ricerche (RAG Search)

Il sistema offre un endpoint di ricerca ibrida che puoi interrogare così:

### Tramite API (cURL)
```bash
curl -X POST "http://localhost:8000/api/rag/search" \
     -H "Content-Type: application/json" \
     -d '{
       "query": "Quali sono i requisiti tecnici per la fornitura hardware?",
       "top_k": 5
     }'
```

### Tramite Frontend
1. Accedi alla dashboard.
2. Usa la **Search Bar** principale.
3. Il sistema restituirà i frammenti più rilevanti, indicando la fonte (nome file) e il punteggio di rilevanza (score ibrido).

---

## 📂 Documenti di Riferimento Generati
Durante questa sessione sono stati creati questi file di analisi dettagliata:
- `resoningfromagentic/rag_flow_analysis.md`: Dettaglio profondo dell'architettura di recupero.
- `resoningfromagentic/frontend_pdf_upload.md`: Guida all'implementazione della UI per l'upload.

---
*Documento di sintesi creato il 28/02/2026.*
