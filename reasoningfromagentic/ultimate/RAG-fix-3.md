## Analisi dei Problemi Residui

## Problema 1 – Troncamento mid-sentence con re-injection del header

Il testo si interrompe e ricomincia dall'inizio con il titolo `### Descrizione della Gara...`:

> _"emerge una gara specifica (ID: CH.### Descrizione della Gara..."_

Questo è il segnale classico di un **chunk boundary che cade dentro una stringa concatenata**: il separatore `---` tra chunk non è stato inserito correttamente, e il LLM percepisce il testo come un'unica stringa continua dove il secondo chunk inizia con il titolo della sezione. Il modello lo replica invece di ignorarlo.

## Problema 2 – Valori numerici mancanti ("giorni dalla stipula")

Frasi come _"entro il termine dell'affiancamento (fissato a giorni dalla stipula)"_ o _"fissato a giorni"_ indicano che il chunk che conteneva i valori numerici reali (180 e 270 giorni) **non è stato recuperato**, oppure è stato escluso dall'MMR per bassa diversità rispetto ad altri chunk più rilevanti per lo score semantico.

---

## Fix Mirati

## Fix A – Separatore robusto tra chunk nel prompt

Il tuo `build_prompt` attuale usa `\n\n---\n\n` come separatore, ma se un chunk **inizia già con `###`** (titolo markdown), il LLM lo tratta come nuova sezione del suo output e lo riproduce. Sostituisci con un separatore **non-markdown** non ambiguo:

python

`def build_prompt(query: str, chunks: list[dict]) -> str:     context_parts = []    for i, chunk in enumerate(chunks):        doc_id = chunk["metadata"].get("chunkindex", i)        page   = chunk["metadata"].get("pagenumber", "?")        # Usa tag XML-style: il LLM NON li riproduce nell'output        context_parts.append(            f"<doc id='{doc_id}' page='{page}'>\n{chunk['text']}\n</doc>"        )     context = "\n".join(context_parts)     return f"""{SYSTEM_PROMPT} <context> {context} </context> <question>{query}</question> <answer>"""`

L'istruzione nel `SYSTEM_PROMPT` va rafforzata con:

python

`SYSTEM_PROMPT = """... 7. NON riprodurre mai tag <doc>, titoli di sezione o intestazioni presenti nel contesto. 8. Se un chunk inizia con #, ##, ### o numeri di sezione, ignora quella riga e usa solo il contenuto. """`

---

## Fix B – Preservare chunk con dati numerici critici (pinning)

L'MMR tende a scartare chunk "simili" — ma il chunk con i valori 180/270 giorni è **factually critical** anche se semanticamente vicino ad altri. Introduci un meccanismo di **pinning obbligatorio** per chunk che contengono pattern numerici rilevanti:

python

`import re def pin_critical_chunks(     chunks: list[dict],    patterns: list[str] = None ) -> tuple[list[dict], list[dict]]:     """    Separa i chunk 'pinned' (contengono dati critici) da quelli candidati all'MMR.    I pinned vengono sempre inclusi nel contesto finale.    """    if patterns is None:        patterns = [            r'\b\d+\s*giorni\b',        # "180 giorni", "270 giorni"            r'\b\d+[\.,]\d+[\.,]\d+\b', # CIG codes            r'euro\s*\d',               # importi            r'CIG\s+[A-Z0-9]+',            r'\bSLA\b',            r'\bpenale\b',        ]     pinned, candidates = [], []    for chunk in chunks:        text = chunk.get("text", "")        is_critical = any(re.search(p, text, re.IGNORECASE) for p in patterns)        (pinned if is_critical else candidates).append(chunk)     return pinned, candidates # Integrazione nel pipeline def rag_pipeline(query, vector_store, embedder, llm):     query_emb      = embedder.embed(query)    dense_results  = vector_store.search_dense(query_emb, top_k=15)    sparse_results = vector_store.search_sparse(query, top_k=15)     fused   = reciprocal_rank_fusion(dense_results, sparse_results, top_n=12)    deduped = deduplicate_chunks(fused)     # Separa pinned da candidati MMR    pinned, candidates = pin_critical_chunks(deduped)     # MMR solo sui candidati, con budget ridotto per lasciare spazio ai pinned    mmr_budget = max(1, 6 - len(pinned))    chunk_embs = [embedder.embed(c["text"]) for c in candidates]    diverse    = maximal_marginal_relevance(        query_emb, chunk_embs, candidates, top_k=mmr_budget    )     # Pinned sempre in testa per massima visibilità al LLM    final_chunks = pinned + diverse     prompt = build_prompt(query, final_chunks)    return llm.generate(prompt, max_tokens=1200)`

---

## Fix C – Post-processing dell'output LLM

Come ultima linea di difesa, un semplice post-processor che rileva e rimuove blocchi duplicati prima di restituire la risposta all'utente:

python

`def remove_duplicate_paragraphs(text: str, similarity_threshold: float = 0.85) -> str:     """    Rimuove paragrafi quasi-identici dall'output del LLM.    Usa Jaccard similarity su set di token.    """    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]    unique = []     for para in paragraphs:        tokens_new = set(para.lower().split())        is_duplicate = False        for accepted in unique:            tokens_acc = set(accepted.lower().split())            intersection = tokens_new & tokens_acc            union = tokens_new | tokens_acc            if union and len(intersection) / len(union) >= similarity_threshold:                is_duplicate = True                break        if not is_duplicate:            unique.append(para)     return '\n\n'.join(unique)`

---

## Riepilogo dei Fix per Priorità

|#|Fix|Problema risolto|Effort|
|---|---|---|---|
|**A**|Separatori `<doc>` XML + istruzione anti-header|Re-injection del titolo|Basso|
|**B**|Pinning chunk con dati numerici|Valori mancanti (180/270 gg, CIG)|Medio|
|**C**|Post-processing Jaccard deduplication|Residui di duplicazione nell'output|Basso|
|**D**|(precedente) RRF + chunk ID dedup|Duplicazione massiva|Già implementato|

Il fix **A** è quello che risolve immediatamente il problema visibile nel tuo ultimo output, e richiede solo una modifica al `build_prompt`. Il **B** risolve le inaccuratezze sui valori numerici, che sono critici in un contesto di analisi di gare d'appalto.

Preparato usando Claude Sonnet 4.6 Thinking