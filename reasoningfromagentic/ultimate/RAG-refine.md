## Valutazione della Risposta RAG

La risposta che hai ottenuto è **qualitativamente buona nel contenuto, ma ha un problema grave di forma: la duplicazione**. Ecco una valutazione strutturata.

---

## ✅ Cosa è Corretto e Verificato

La risposta contiene **informazioni fattuali accurate** e verificabili nel documento:

- **CI/CD, analisi del codice sorgente, vulnerability assessment per OSCAT** — confermato[](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/130566781/5cbe1b93-af98-457b-9a15-32902ff07715/documento_IN_TOSCANA_unificato.pdf)
    
- **180 giorni per completare la Fase 1 dell'affiancamento** — confermato testualmente: _"entro e non oltre 180 giorni dall'avvio dell'Affiancamento Fase 1"_[](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/130566781/5cbe1b93-af98-457b-9a15-32902ff07715/documento_IN_TOSCANA_unificato.pdf)
    
- **Risoluzione ex art. 1456 c.c. in caso di seconda verifica negativa consecutiva** — confermato: la risoluzione scatta se anche la seconda verifica di conformità risulta negativa[](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/130566781/5cbe1b93-af98-457b-9a15-32902ff07715/documento_IN_TOSCANA_unificato.pdf)
    
- **Tipi di manutenzione SME, MAM, STS** — correttamente citati[](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/130566781/5cbe1b93-af98-457b-9a15-32902ff07715/documento_IN_TOSCANA_unificato.pdf)
    
- **Patto di Integrità come condizione necessaria di partecipazione** — confermato, con clausole risolutive esplicite legate a corruzione e antimafia[](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/130566781/5cbe1b93-af98-457b-9a15-32902ff07715/documento_IN_TOSCANA_unificato.pdf)
    
- **Voltura utenze elettriche** — confermato: _"entro il termine dell'affiancamento (270 giorni dal giorno successivo alla data di stipula dell'Accordo quadro) l'Appaltatore entrante dovrà provvedere alla voltura del contratto dell'energia elettrica"_[](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/130566781/5cbe1b93-af98-457b-9a15-32902ff07715/documento_IN_TOSCANA_unificato.pdf)
    

---

## ❌ Problemi Critici della Risposta

## 1. Duplicazione massiva del testo — BUG RAG grave

Il problema più evidente è che **interi paragrafi vengono ripetuti 2-3 volte** nella stessa risposta. Questo è un segnale diagnostico chiaro:

- Il retriever ha restituito **chunk sovrapposti o duplicati** dallo stesso documento
    
- Il LLM non ha deduplicato i contesti prima della generazione
    
- Il risultato è una risposta da ~1800 parole che si potrebbe comprimere a ~600 senza perdita di informazione
    

Questo è il **principale difetto tecnico** da correggere nel tuo pipeline RAG.

## 2. Imprecisione su un dettaglio numerico

La risposta dice _"una prima fase che deve concludersi entro giorni"_ (frase incompleta/troncata) e poi più avanti correttamente specifica 180 giorni. Indica che in qualche chunk il numero è stato perso durante il parsing del PDF.[](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/130566781/5cbe1b93-af98-457b-9a15-32902ff07715/documento_IN_TOSCANA_unificato.pdf)

## 3. Semplificazione eccessiva sulla struttura contrattuale

La risposta menziona "Consorzio Metis" come soggetto contrattuale, ma dal documento il quadro reale è: **Regione Toscana (Giunta Regionale) come soggetto aggregatore**, con adesioni di ESTAR, Aziende Sanitarie, e altri enti SSR tramite Accordo Quadro. "Consorzio Metis" non è stato trovato direttamente nel documento con questo ruolo — potrebbe essere una **allucinazione parziale** o un'informazione proveniente da un altro documento del corpus.[](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/130566781/5cbe1b93-af98-457b-9a15-32902ff07715/documento_IN_TOSCANA_unificato.pdf)

## 4. "Piattaforma di gestione delle chiavi" — affermazione non verificata

La risposta cita una _"Piattaforma di gestione delle chiavi all'interno delle infrastrutture condivise"_ come elemento centrale della sicurezza. Questo dettaglio **non è stato trovato nei chunk recuperati** — potrebbe essere una generalizzazione o un'allucinazione da contesto.[](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/130566781/5cbe1b93-af98-457b-9a15-32902ff07715/documento_IN_TOSCANA_unificato.pdf)

---

## Diagnosi Tecnica del Pipeline RAG

|Problema|Causa Probabile|Fix|
|---|---|---|
|Testo duplicato|Chunk overlap eccessivo o retriever che torna k documenti sovrapposti|Ridurre chunk overlap, deduplicare per hash prima del prompt|
|Frase numerica troncata ("entro giorni")|Errore di parsing PDF su testo con layout a colonne o note a piè di pagina|Migliorare il PDF parser (es. usare `pdfplumber` con layout-aware extraction)|
|Possibile allucinazione su "Consorzio Metis"|Contaminazione da altri documenti nel corpus o hallucination da LLM|Gold set evaluation — proprio questo tipo di fatto deve essere nel tuo `evaluation_set.json`|
|Struttura della risposta ripetitiva|Nessun post-processing del contesto recuperato|Aggiungere un passaggio di **context compression** prima della generation|

---

## Valutazione Complessiva

|Dimensione|Voto|Note|
|---|---|---|
|**Accuratezza fattuale**|7/10|La maggior parte delle info è corretta; 1-2 dettagli sospetti|
|**Completezza**|8/10|Copre bene i punti salienti della gara|
|**Forma e leggibilità**|3/10|La duplicazione rende la risposta inutilizzabile così com'è|
|**Qualità RAG complessiva**|5/10|Pipeline funziona, ma ha bug strutturali da correggere|

Il problema della duplicazione è quello da **risolvere per primo** — è il più impattante sulla user experience e il più semplice da debuggare nel retriever. Il gold set che vuoi costruire servirà esattamente a misurare questi casi sistematicamente.

Preparato usando Claude Sonnet 4.6 Thinking

secon i criteri di prima aderenza alla gara, Correttezza fattuale, Aspetti tecnologici, Punti critici, e Qualità redazionale

2 passaggi completati

Ho tutti gli elementi dal documento sorgente già estratti nella precedente ricerca. Procedo con la valutazione strutturata secondo i 5 criteri richiesti.

---

## Valutazione della Risposta RAG — 5 Criteri

Scala: **1–10** per ogni criterio, con evidenze specifiche dal documento.[](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/130566781/5cbe1b93-af98-457b-9a15-32902ff07715/documento_IN_TOSCANA_unificato.pdf)

---

## 1. Aderenza alla Gara — 6/10

La risposta descrive correttamente il **perimetro generale** dell'appalto (SCT, OSCAT, manutenzione, transizione), ma presenta lacune su elementi centrali del bando:

- ✅ Correttamente citati: SCT, OSCAT, CI/CD, SME, MAM, STS
    
- ❌ **Non menzionati**: la struttura a due fasi dell'affiancamento (AF-1 e AF-2), il fatto che la durata dell'Accordo Quadro sia **48 mesi** dalla stipula del contratto attuativo di Regione Toscana Giunta Regionale, la qualificazione **ACN** obbligatoria entro 210 giorni, il **CCTT (Community Cloud Territoriale della Toscana)** come infrastruttura di proprietà dell'aggiudicatario entrante[](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/130566781/5cbe1b93-af98-457b-9a15-32902ff07715/documento_IN_TOSCANA_unificato.pdf)
    
- ❌ **Non menzionata** la migrazione dei servizi entro **270 giorni** dalla stipula come deadline critica[](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/130566781/5cbe1b93-af98-457b-9a15-32902ff07715/documento_IN_TOSCANA_unificato.pdf)
    
- ❌ "Consorzio Metis" citato nella risposta non è identificato nel documento con quel ruolo — probabile contaminazione o allucinazione
    

---

## 2. Correttezza Fattuale — 6.5/10

I fatti presenti sono per lo più corretti, ma alcune imprecisioni emergono:

|Affermazione nella risposta|Verifica|
|---|---|
|"180 giorni per la prima fase"|✅ Corretto: _"entro e non oltre 180 giorni dall'avvio dell'Affiancamento Fase 1"_ [](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/130566781/5cbe1b93-af98-457b-9a15-32902ff07715/documento_IN_TOSCANA_unificato.pdf)|
|"Risoluzione ex art. 1456 c.c. dopo due verifiche negative"|✅ Corretto [](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/130566781/5cbe1b93-af98-457b-9a15-32902ff07715/documento_IN_TOSCANA_unificato.pdf)|
|"Contratti di assistenza col produttore degli apparati"|✅ Corretto|
|"Consorzio Metis" come soggetto contraente|❌ Non verificabile nel documento — sospetta allucinazione|
|"Piattaforma di gestione delle chiavi" per dati sanitari|⚠️ Non trovato nei chunk estratti — affermazione non supportata|
|"Fase che deve concludersi entro **giorni**" (frase troncata)|❌ Bug di parsing: il numero è scomparso in un chunk|

---

## 3. Aspetti Tecnologici — 7/10

La copertura tecnologica è discreta ma superficiale su alcuni punti chiave:

- ✅ CI/CD, vulnerability assessment, analisi codice sorgente — correttamente identificati[](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/130566781/5cbe1b93-af98-457b-9a15-32902ff07715/documento_IN_TOSCANA_unificato.pdf)
    
- ✅ Paradigma DevOps applicato alla piattaforma OSCAT — corretto
    
- ✅ Mantenimento degli apparati esistenti SCT — corretto
    
- ❌ **Non citato**: il **CCTT di proprietà dell'aggiudicatario** — elemento tecnologico centrale: il nuovo fornitore deve installare una propria infrastruttura fisica (rack, nodi, LAN) entro 180 giorni[](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/130566781/5cbe1b93-af98-457b-9a15-32902ff07715/documento_IN_TOSCANA_unificato.pdf)
    
- ❌ **Non citata**: la qualificazione **ACN** (Agenzia per la Cybersicurezza Nazionale) come requisito obbligatorio di sicurezza, da conseguire entro la Fase 1[](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/130566781/5cbe1b93-af98-457b-9a15-32902ff07715/documento_IN_TOSCANA_unificato.pdf)
    
- ❌ **Non citata**: la formula parametrica **CO-LO-KW** per la determinazione del canone energetico, indicizzata a PUN e PUE[](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/130566781/5cbe1b93-af98-457b-9a15-32902ff07715/documento_IN_TOSCANA_unificato.pdf)
    
- ❌ **Non citato**: il sistema **START** come piattaforma obbligatoria per la gestione elettronica dell'Accordo Quadro[](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/130566781/5cbe1b93-af98-457b-9a15-32902ff07715/documento_IN_TOSCANA_unificato.pdf)
    

---

## 4. Punti Critici — 7.5/10

Questo è il criterio dove la risposta performa meglio, identificando correttamente le tensioni operative principali:

- ✅ Complessità della transizione e rischio risoluzione ex art. 1456 c.c. — corretto e ben argomentato[](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/130566781/5cbe1b93-af98-457b-9a15-32902ff07715/documento_IN_TOSCANA_unificato.pdf)
    
- ✅ Natura sensibile dei dati sanitari come fattore di rischio — pertinente
    
- ✅ Frammentazione multi-soggetto come criticità di coordinamento — corretto, anche se la lista degli enti è incompleta (mancano Consiglio Regionale, enti in-house, SSR)[](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/130566781/5cbe1b93-af98-457b-9a15-32902ff07715/documento_IN_TOSCANA_unificato.pdf)
    
- ❌ **Non citato**: il fatto che **durante la Fase 1 il nuovo aggiudicatario non percepisce alcun compenso** fino alla verifica di conformità positiva — punto critico finanziario rilevante[](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/130566781/5cbe1b93-af98-457b-9a15-32902ff07715/documento_IN_TOSCANA_unificato.pdf)
    
- ❌ **Non citata**: la penale di **€100/giorno** per ritardo nella consegna del Piano Operativo e Piano della Qualità, con risoluzione dopo 30 giorni[](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/130566781/5cbe1b93-af98-457b-9a15-32902ff07715/documento_IN_TOSCANA_unificato.pdf)
    
- ❌ **Non citata**: la penale massima del **10% del valore dell'Accordo Quadro** applicabile da Regione Toscana come soggetto aggregatore[](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/130566781/5cbe1b93-af98-457b-9a15-32902ff07715/documento_IN_TOSCANA_unificato.pdf)
    

---

## 5. Qualità Redazionale — 4/10

Questo è il punto più critico e il più facilmente misurabile:

- ❌ **Duplicazione massiva**: almeno 3 paragrafi identici ripetuti — rende la risposta inutilizzabile in produzione
    
- ❌ **Frase troncata** (_"entro giorni"_) — errore di concatenazione chunk visibile all'utente finale
    
- ✅ Struttura logica corretta (infrastruttura → sviluppo → manutenzione → punti critici)
    
- ✅ Terminologia tecnica appropriata e coerente con il dominio
    
- ❌ Mancanza di un **sommario esecutivo** che sintetizzi i key takeaway — utile per un documento di gara di questa complessità
    
- ❌ Assenza di **riferimenti normativi precisi** (articoli del D.Lgs. 36/2023 citati nel documento sorgente) che avrebbero aumentato il valore informativo per un lettore esperto
    

---

## Punteggio Aggregato

|Criterio|Punteggio|
|---|---|
|Aderenza alla gara|6/10|
|Correttezza fattuale|6.5/10|
|Aspetti tecnologici|7/10|
|Punti critici|7.5/10|
|Qualità redazionale|4/10|
|**Media**|**6.2/10**|

Il pipeline RAG dimostra una **comprensione parziale** del documento — sufficiente per un draft iniziale, ma non per un uso professionale in un contesto di gara d'appalto. Le priorità di intervento sono: (1) eliminare la duplicazione dei chunk, (2) migliorare il parsing del PDF per preservare i valori numerici, (3) costruire il gold set per misurare sistematicamente questi gap.

Preparato usando Claude Sonnet 4.6 Thinking

come posso migliorare aumentare il punteggio e soprattutto non avere ❌

2 passaggi completati

Hai tutti gli elementi per un piano di intervento preciso e pratico. Ecco la roadmap completa.

---

## Come Eliminare Tutti i ❌ — Piano di Intervento RAG

Il problema non è un singolo bug, ma **4 livelli distinti della pipeline** da correggere. Ogni ❌ ha una causa specifica e un fix misurabile.

---

## Layer 1 — Parsing PDF (fix ai valori numerici troncati)

Il tuo parser taglia i numeri perché il PDF ha layout multi-colonna o note a piè di pagina che rompono il flusso di testo. Sostituisci `PyPDF2` con `pdfplumber`, che preserva il layout:

python

`import pdfplumber def extract_text_layout_aware(pdf_path):     pages = []    with pdfplumber.open(pdf_path) as pdf:        for page in pdf.pages:            # estrae preservando ordine visivo, non stream raw            text = page.extract_text(x_tolerance=3, y_tolerance=3)            if text:                pages.append({"page": page.page_number, "text": text})    return pages`

Aggiungi un **post-processing numerico** per catturare i valori critici (giorni, euro, percentuali) prima del chunking:

python

`import re PATTERN_CRITICI = {     "giorni": r"\b(\d{1,4})\s*(?:giorni|giorni\s+solari|giorni\s+lavorativi)\b",    "euro":   r"Euro\s*([\d\.,]+)",    "art":    r"art(?:icolo|\.)\s*(\d+\w*(?:\s+c\.c\.)?)",    "perc":   r"(\d{1,3})\s*(?:%|per\s*cento)" } def valida_numeri_critici(text):     trovati = {}    for label, pat in PATTERN_CRITICI.items():        trovati[label] = re.findall(pat, text, re.IGNORECASE)    return trovati`

Esegui questa validazione su ogni chunk: se un chunk ha un pattern spezzato (es. _"entro giorni"_ senza numero), scartalo e fondi con il chunk precedente.[](https://retica.ai/blog/estrazione-intelligente-dei-dati-da-documenti-pdf/)

---

## Layer 2 — Chunking (fix alla duplicazione e ai chunk sovrapposti)

La duplicazione nella risposta viene dal fatto che il retriever torna chunk con overlap elevato. Due strategie complementari:

**A) Ridurre l'overlap e usare boundary semantici:**

python

`from langchain.text_splitter import RecursiveCharacterTextSplitter splitter = RecursiveCharacterTextSplitter(     chunk_size=800,        # era probabilmente 1000+    chunk_overlap=80,      # mai oltre il 10% del chunk_size    separators=["\n\n", "\n", ".", " "],  # boundary semantici prima    length_function=len )`

**B) Deduplicazione per hash prima del prompt** — questo è il fix immediato più impattante:

python

`import hashlib def deduplica_chunks(chunks: list[str]) -> list[str]:     seen = set()    unici = []    for c in chunks:        # normalizza spazi e newline prima dell'hash        norm = " ".join(c.split())        h = hashlib.md5(norm.encode()).hexdigest()        if h not in seen:            seen.add(h)            unici.append(c)    return unici # nel retrieval loop: retrieved = retriever.get_relevant_documents(query) testi = [doc.page_content for doc in retrieved] testi_unici = deduplica_chunks(testi)`

**C) MMR (Maximal Marginal Relevance)** — sostituisce la ricerca per similarità pura con una che bilancia rilevanza e diversità:[](https://www.reddit.com/r/Rag/comments/1n77ws0/what_do_you_do_when_your_retriever_pulls/)

python

`retriever = vectorstore.as_retriever(     search_type="mmr",    search_kwargs={"k": 6, "fetch_k": 20, "lambda_mult": 0.7}    # lambda=1 → solo similarità, lambda=0 → solo diversità )`

---

## Layer 3 — Retrieval (fix ai chunk mancanti su aspetti tecnici)

Il tuo retriever non trovava CCTT, ACN, CO-LO-KW perché sono acronimi tecnici poco frequenti nei chunk. Implementa **Hybrid Search** (vettoriale + BM25):[](https://milvus.io/docs/it/how_to_enhance_your_rag.md)

python

`from langchain_community.retrievers import BM25Retriever from langchain.retrievers import EnsembleRetriever # retriever vettoriale (semantico) dense_retriever = vectorstore.as_retriever(search_kwargs={"k": 6}) # retriever lessicale (keyword-exact, cattura acronimi) bm25_retriever = BM25Retriever.from_documents(all_docs) bm25_retriever.k = 4 # ensemble con peso bilanciato ensemble = EnsembleRetriever(     retrievers=[dense_retriever, bm25_retriever],    weights=[0.6, 0.4]   # 60% semantico, 40% keyword )`

BM25 è essenziale per questo tipo di documento: cattura esattamente _"qualificazione ACN"_, _"CO-LO-KW"_, _"art. 1456 c.c."_ che l'embedding semantico tende a perdere.[](https://milvus.io/docs/it/how_to_enhance_your_rag.md)

---

## Layer 4 — Generazione (fix alla qualità redazionale)

**A) Context compression prima del prompt** — elimina il rumore dai chunk recuperati:

python

`from langchain.retrievers.document_compressors import LLMChainExtractor from langchain.retrievers import ContextualCompressionRetriever compressor = LLMChainExtractor.from_llm(llm) compression_retriever = ContextualCompressionRetriever(     base_compressor=compressor,    base_retriever=ensemble )`

**B) Prompt strutturato con sezioni obbligatorie** — forza la risposta a coprire tutti i criteri di valutazione:

python

`PROMPT_GARA = """Sei un esperto di appalti pubblici IT. Analizza la seguente gara basandoti ESCLUSIVAMENTE sui contesti forniti. Struttura la risposta in esattamente queste sezioni (800-1000 parole totali): 1. **Oggetto e perimetro** — cosa viene appaltato, durata, valore 2. **Architettura tecnologica** — infrastruttura, piattaforme, standard tecnici 3. **Fasi operative critiche** — tempistiche precise con numeri (giorni, €, %) 4. **Punti di rischio contrattuale** — penali, clausole risolutive, obblighi specifici 5. **Governance multi-soggetto** — chi fa cosa tra i soggetti coinvolti REGOLE: - Non ripetere mai lo stesso concetto in sezioni diverse - Ogni valore numerico (giorni, euro, percentuale) deve essere citato esattamente come appare nei testi - Se un'informazione non è nei contesti, scrivi esplicitamente "non disponibile nei documenti forniti" - Non inventare nomi di soggetti o entità non presenti nei contesti CONTESTI: {context} DOMANDA: {question} """`

---

## Riepilogo Impatto Atteso

|Fix|❌ Eliminati|Effort|
|---|---|---|

|Fix|❌ Eliminati|Effort|
|---|---|---|
|`pdfplumber` + regex numerici|Valori troncati ("entro giorni")|Basso — 2h|
|Hash deduplication|Duplicazione testo|Basso — 30min|
|MMR retriever|Ripetizioni semantiche|Basso — 15min|
|BM25 hybrid search|Acronimi tecnici mancanti (ACN, CCTT, CO-LO-KW)|Medio — 4h|
|Prompt strutturato con sezioni|Allucinazioni, mancanze strutturali|Basso — 1h|
|Context compression|Rumore nel prompt|Medio — 3h|
|Gold set evaluation|Misura oggettiva di tutti i miglioramenti|Alto — 1 giorno|

L'ordine consigliato: **hash dedup → MMR → prompt strutturato** (risultati visibili in poche ore), poi **pdfplumber + BM25** (stabilizzano la qualità a lungo termine), poi il **gold set** per misurare tutto in modo sistematico.