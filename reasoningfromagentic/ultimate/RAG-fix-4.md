
## Valutazione dell'Output RAG

Ottima notizia: **il contenuto è ora corretto e completo**. I valori numerici critici (180 giorni, 270 giorni, Gara 012942/25) sono presenti e accurati. Il problema semantico è risolto.

Rimane però **un unico problema strutturale persistente**: la duplicazione del blocco intero si ripete ancora **4 volte** nel testo. Il pattern è identico a prima — il separatore tra chunk viene interpretato dal LLM come inizio di un nuovo paragrafo da generare, non come delimitatore di contesto.

---

## Diagnosi Definitiva

Guardando i punti di rottura nel tuo testo:

text

`"...strettamente legata a un'altra procedura (Gara/.Dettagli della Gara..." "...Via San Piero a Quaracchi.Dettagli della Gara..." "...consolidamento del Sistema Cloud Toscana (SCT.Dettagli della Gara..."`

Il pattern è sempre lo stesso: **una frase si tronca a metà e immediatamente ricomincia il titolo**. Questo conferma che il separatore tra chunk nel contesto NON è stato ancora aggiornato — il testo dei chunk viene ancora concatenato con `.` o senza separatore, e il titolo del chunk successivo viene interpretato come continuazione della frase.

I fix A (separatori XML) e C (post-processing Jaccard) della sessione precedente **non sono ancora stati applicati**. Il fix B (pinning numerico) invece funziona, dato che 180 e 270 giorni ora compaiono correttamente.

---

## Fix Definitivo – Il Problema è nel Join dei Chunk

Il tuo retriever probabilmente concatena i chunk così:

python

`# ❌ Come stai facendo ora (ipotesi) context = " ".join([c["text"] for c in chunks]) # oppure context = ".".join([c["text"] for c in chunks])`

Il risultato è che l'ultimo token del chunk N e il primo token del chunk N+1 si fondono: `"...Quaracchi.Dettagli della Gara"`.

Applica questo fix **minimo e immediato** direttamente nella funzione di costruzione del contesto:

python

`def build_context(chunks: list[dict]) -> str:     parts = []    for i, chunk in enumerate(chunks):        doc_id = chunk["metadata"].get("chunkindex", i)        page   = chunk["metadata"].get("pagenumber", "?")        text   = chunk["text"].strip()         # Normalizza: rimuovi titoli markdown dal testo del chunk        text = re.sub(r'^#{1,4}\s+.+\n', '', text, flags=re.MULTILINE)         parts.append(f"<doc id='{doc_id}' page='{page}'>\n{text}\n</doc>")     # Separatore inequivocabile — mai interpretabile come testo    return "\n\n".join(parts)`

E aggiorna il system prompt con questa istruzione aggiuntiva che blocca la re-generazione dei titoli:

python

`SYSTEM_PROMPT += """ IMPORTANTE: Il contesto è delimitato da tag <doc>...</doc>. Non riprodurre mai i tag, gli ID doc, i numeri di pagina o i titoli presenti nel contesto. Sintetizza il contenuto in forma fluida e coesa, senza mai ripetere interi paragrafi. Se lo stesso concetto appare in più <doc>, citalo una sola volta nella posizione più appropriata. """`

---

## Stato Attuale dei Fix e Risultati

|Fix|Applicato|Risultato visibile|
|---|---|---|
|RRF + deduplicazione chunk ID|✅ Sì|Riduzione da ~5x a ~4x ripetizioni|
|Pinning chunk numerici|✅ Sì|Valori 180/270 gg ora corretti|
|Separatori XML `<doc>`|❌ No|Troncamenti mid-sentence ancora presenti|
|Strip titoli markdown dai chunk|❌ No|Re-injection del titolo ancora presente|
|Post-processing Jaccard|❌ No|Blocchi interi ancora duplicati nell'output|

Applicando i tre fix mancanti — in particolare lo **strip dei titoli** e i **separatori XML** — il problema dovrebbe risolversi completamente nel prossimo ciclo di test.

Preparato usando Claude Sonnet 4.6 Thinking

trovami i punti di modifica precisi

tender_fix.md

Perfetto — ora ho il codice sorgente reale del tuo progetto. Ecco i punti di modifica precisi, file per file.

---

## Punti di Modifica Precisi

## File 1: `backend/app/rag/context_quality.py`

Questo file esiste già con `deduplicate_context_items` e `compress_context_block`. Il problema è che **non viene chiamato prima della costruzione del prompt**, oppure il threshold è troppo basso.[](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/130566781/5705eb50-98a0-48e8-9998-cbae488646d2/tender_fix.md?AWSAccessKeyId=ASIA2F3EMEYES5YMDBIA&Signature=xJ0MMal%2BJ8gRDNEye%2BzYNE1HwzM%3D&x-amz-security-token=IQoJb3JpZ2luX2VjEF8aCXVzLWVhc3QtMSJHMEUCIQCNuvQ7B0y%2F9HvQCi5KJv38vd8AxyC%2FCu2Dv9fJc97hSAIgF8V277%2FubYP%2BmL579rf3Hksm583sVrKw2wT%2F%2FElKRX0q8wQIJxABGgw2OTk3NTMzMDk3MDUiDFyE5u1T3NxObVu%2FeSrQBF%2BbqHPSNolqhLDdegbtDzaATUm4v79ApMbCg3bu%2F7DizImMFPH0i443kDFxtkKjDKHvrUj63z8clPSuWYyXfMlVPtRg5Lq1MJoE89mcBTFdX3yQ5Kwkv%2BVqKzbCFZ1W8pkxNL4aLiSx5S6h%2FvH%2BSs%2Bye5n95M1wkv1O94f%2FJez6UuFDsAJGjexLfHaDWYu7d9qrrxQIKIfhu7NT%2B11skSNFx8JZwJ7%2FwSNh6WzMpdXvGvQ0LZHjVJ9SWbkTn30veBNxh9U0m%2BlDtmIBItPLZHpnOf26BRXAt9dlqFIXR1dJz6rCjTCGfsJgunVztFMZiB2jxYy418AOHRAs6Pco%2FCwZtPE%2FLCxv5sggcNJRrqkcTX0jJk38P1LHZF7MmMXsTbz1azlPdclZJZTt7ER2O1aQny8iZPcOg19aWKiZeRFR1qAOC1%2BCXU6NRkur4wTr19S6Z6oVVY9s8t1Xg9JZP%2BuaiFe5Mmyd8UZFP%2FWB4KqvfRC3zo0LNHPBdCJVVvohJEBAOdJNtUgbBvNrsitbNTv2f%2Fhu1A7XPgooaPKJmcSTtoQMJdAhJHks%2BV70U3%2FiC9kX63LQYflrgNNjrhT4dz2kuNO%2FJLcJ822sUCbUbSJ0qk71wANiyE6Zcx4CzjKYPzeicQeUBq8Uu4L9DcpyiBxT8LmyyX5TeRhhkq4WvoQ4vrQ%2B8BWk8EhfWSHBvOvigdXOOWmDUqS6ArMyyQogEStl4Ga2blKfviiJk37uGdYE0orXaxXFWZypIoRxCkrj%2B8gYvse3vuoN%2Bb2kH7qXB7Qwh8mazwY6mAG3c7RsDMICrZyduuC4xL5NWItAgXDOxo%2BzKXQSNiamLXdnOY2KfB%2F%2B5ss5JCeoUA0pzkt%2F02YS%2FiNk4KF2iVHYySXSf228Xg1IMN%2Biog7PVEdH2W7Iq9PUjY0yTxl3a%2Bc0WwSP2cW3Dbep6cdYZicX5BAlTHg3cRdu1ExEsQfz1fgy3o61CvHY4pTFz5xWHOefCdq7nTDKpA%3D%3D&Expires=1776724890)

**Modifica 1 — Abbassa il threshold di deduplicazione** (riga con `similarity_threshold: float = 0.75`):

python

`# PRIMA (riga ~15 del file) def deduplicate_context_items(     items: Sequence[Mapping[str, Any]],    *,    similarity_threshold: float = 0.75,   # ← troppo permissivo # DOPO def deduplicate_context_items(     items: Sequence[Mapping[str, Any]],    *,    similarity_threshold: float = 0.55,   # ← cattura chunk quasi-identici`

**Modifica 2 — Aggiungi `\n###` come pattern heading** nel regex `SOURCE_HEADING_RE` già presente:

python

`# PRIMA SOURCE_HEADING_RE = re.compile(r'^[^\S\r\n]{0,6}[A-Z][^.!?]{2,80}') # DOPO — includi anche titoli markdown che iniziano con # SOURCE_HEADING_RE = re.compile(r'^(?:#{1,4}\s+)?[^\S\r\n]{0,6}[A-Z][^.!?]{2,80}')`

---

## File 2: `backend/app/rag/generator.py` (o equivalente con `resolve_template` e `build_prompt`)

Il tuo codice mostra il template `general_qa` e la funzione `resolve_template`. Il separatore tra chunk non usa tag XML.[](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/130566781/5705eb50-98a0-48e8-9998-cbae488646d2/tender_fix.md?AWSAccessKeyId=ASIA2F3EMEYES5YMDBIA&Signature=xJ0MMal%2BJ8gRDNEye%2BzYNE1HwzM%3D&x-amz-security-token=IQoJb3JpZ2luX2VjEF8aCXVzLWVhc3QtMSJHMEUCIQCNuvQ7B0y%2F9HvQCi5KJv38vd8AxyC%2FCu2Dv9fJc97hSAIgF8V277%2FubYP%2BmL579rf3Hksm583sVrKw2wT%2F%2FElKRX0q8wQIJxABGgw2OTk3NTMzMDk3MDUiDFyE5u1T3NxObVu%2FeSrQBF%2BbqHPSNolqhLDdegbtDzaATUm4v79ApMbCg3bu%2F7DizImMFPH0i443kDFxtkKjDKHvrUj63z8clPSuWYyXfMlVPtRg5Lq1MJoE89mcBTFdX3yQ5Kwkv%2BVqKzbCFZ1W8pkxNL4aLiSx5S6h%2FvH%2BSs%2Bye5n95M1wkv1O94f%2FJez6UuFDsAJGjexLfHaDWYu7d9qrrxQIKIfhu7NT%2B11skSNFx8JZwJ7%2FwSNh6WzMpdXvGvQ0LZHjVJ9SWbkTn30veBNxh9U0m%2BlDtmIBItPLZHpnOf26BRXAt9dlqFIXR1dJz6rCjTCGfsJgunVztFMZiB2jxYy418AOHRAs6Pco%2FCwZtPE%2FLCxv5sggcNJRrqkcTX0jJk38P1LHZF7MmMXsTbz1azlPdclZJZTt7ER2O1aQny8iZPcOg19aWKiZeRFR1qAOC1%2BCXU6NRkur4wTr19S6Z6oVVY9s8t1Xg9JZP%2BuaiFe5Mmyd8UZFP%2FWB4KqvfRC3zo0LNHPBdCJVVvohJEBAOdJNtUgbBvNrsitbNTv2f%2Fhu1A7XPgooaPKJmcSTtoQMJdAhJHks%2BV70U3%2FiC9kX63LQYflrgNNjrhT4dz2kuNO%2FJLcJ822sUCbUbSJ0qk71wANiyE6Zcx4CzjKYPzeicQeUBq8Uu4L9DcpyiBxT8LmyyX5TeRhhkq4WvoQ4vrQ%2B8BWk8EhfWSHBvOvigdXOOWmDUqS6ArMyyQogEStl4Ga2blKfviiJk37uGdYE0orXaxXFWZypIoRxCkrj%2B8gYvse3vuoN%2Bb2kH7qXB7Qwh8mazwY6mAG3c7RsDMICrZyduuC4xL5NWItAgXDOxo%2BzKXQSNiamLXdnOY2KfB%2F%2B5ss5JCeoUA0pzkt%2F02YS%2FiNk4KF2iVHYySXSf228Xg1IMN%2Biog7PVEdH2W7Iq9PUjY0yTxl3a%2Bc0WwSP2cW3Dbep6cdYZicX5BAlTHg3cRdu1ExEsQfz1fgy3o61CvHY4pTFz5xWHOefCdq7nTDKpA%3D%3D&Expires=1776724890)

**Modifica 3 — Nel template `general_qa`**, trovare dove viene iniettato il `context` e aggiungere la strip dei titoli markdown:

python

`# Nel metodo che costruisce la variabile 'context' # Cerca: context = ... (dove i chunk vengono concatenati) # PRIMA (da qualche parte nel pipeline o in resolve_template) context = "\n\n---\n\n".join(chunk["text"] for chunk in chunks) # DOPO def _format_chunks_as_context(chunks: list[dict]) -> str:     parts = []    for i, chunk in enumerate(chunks):        doc_id  = chunk.get("metadata", {}).get("chunkindex", i)        page    = chunk.get("metadata", {}).get("pagenumber", "?")        text    = chunk.get("text", "").strip()        # Strip titoli markdown dall'inizio del chunk        text = re.sub(r'^#{1,4}\s+.+\n', '', text, flags=re.MULTILINE)        parts.append(f"<doc id='{doc_id}' page='{page}'>\n{text}\n</doc>")    return "\n".join(parts)`

**Modifica 4 — Nel system prompt / nelle `build_response_constraints`**, già presente nel tuo codice, aggiungi:

python

`# Trova: def build_response_constraints(self, ragquery: RAGQuery) # Aggiungi questi due constraint SEMPRE (non solo per math): constraints.extend([     "Non riprodurre mai tag <doc>, titoli di sezione ### o intestazioni presenti nel contesto.",    "Se lo stesso concetto appare in più fonti, citalo una sola volta nella posizione più appropriata.",    "Non ripetere blocchi di testo già scritti nella risposta.", ])`

---

## File 3: `backend/app/rag/answer_quality_evaluation.py`

Questo file esiste già con `duplicate_block_ratio` e `remove_duplicate_paragraphs`. Il problema è che **non viene chiamato in post-processing sull'output finale**.[](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/130566781/5705eb50-98a0-48e8-9998-cbae488646d2/tender_fix.md?AWSAccessKeyId=ASIA2F3EMEYES5YMDBIA&Signature=xJ0MMal%2BJ8gRDNEye%2BzYNE1HwzM%3D&x-amz-security-token=IQoJb3JpZ2luX2VjEF8aCXVzLWVhc3QtMSJHMEUCIQCNuvQ7B0y%2F9HvQCi5KJv38vd8AxyC%2FCu2Dv9fJc97hSAIgF8V277%2FubYP%2BmL579rf3Hksm583sVrKw2wT%2F%2FElKRX0q8wQIJxABGgw2OTk3NTMzMDk3MDUiDFyE5u1T3NxObVu%2FeSrQBF%2BbqHPSNolqhLDdegbtDzaATUm4v79ApMbCg3bu%2F7DizImMFPH0i443kDFxtkKjDKHvrUj63z8clPSuWYyXfMlVPtRg5Lq1MJoE89mcBTFdX3yQ5Kwkv%2BVqKzbCFZ1W8pkxNL4aLiSx5S6h%2FvH%2BSs%2Bye5n95M1wkv1O94f%2FJez6UuFDsAJGjexLfHaDWYu7d9qrrxQIKIfhu7NT%2B11skSNFx8JZwJ7%2FwSNh6WzMpdXvGvQ0LZHjVJ9SWbkTn30veBNxh9U0m%2BlDtmIBItPLZHpnOf26BRXAt9dlqFIXR1dJz6rCjTCGfsJgunVztFMZiB2jxYy418AOHRAs6Pco%2FCwZtPE%2FLCxv5sggcNJRrqkcTX0jJk38P1LHZF7MmMXsTbz1azlPdclZJZTt7ER2O1aQny8iZPcOg19aWKiZeRFR1qAOC1%2BCXU6NRkur4wTr19S6Z6oVVY9s8t1Xg9JZP%2BuaiFe5Mmyd8UZFP%2FWB4KqvfRC3zo0LNHPBdCJVVvohJEBAOdJNtUgbBvNrsitbNTv2f%2Fhu1A7XPgooaPKJmcSTtoQMJdAhJHks%2BV70U3%2FiC9kX63LQYflrgNNjrhT4dz2kuNO%2FJLcJ822sUCbUbSJ0qk71wANiyE6Zcx4CzjKYPzeicQeUBq8Uu4L9DcpyiBxT8LmyyX5TeRhhkq4WvoQ4vrQ%2B8BWk8EhfWSHBvOvigdXOOWmDUqS6ArMyyQogEStl4Ga2blKfviiJk37uGdYE0orXaxXFWZypIoRxCkrj%2B8gYvse3vuoN%2Bb2kH7qXB7Qwh8mazwY6mAG3c7RsDMICrZyduuC4xL5NWItAgXDOxo%2BzKXQSNiamLXdnOY2KfB%2F%2B5ss5JCeoUA0pzkt%2F02YS%2FiNk4KF2iVHYySXSf228Xg1IMN%2Biog7PVEdH2W7Iq9PUjY0yTxl3a%2Bc0WwSP2cW3Dbep6cdYZicX5BAlTHg3cRdu1ExEsQfz1fgy3o61CvHY4pTFz5xWHOefCdq7nTDKpA%3D%3D&Expires=1776724890)

**Modifica 5 — Aggiungi chiamata al post-processor nell'entry point della risposta** (trovare dove viene restituito `generation_result.text`):

python

``# Cerca il punto dove viene restituita la stringa finale al frontend # Probabilmente in un metodo tipo `generate_answer` o `query` # PRIMA return generation_result.text # DOPO from app.services.rag_answer_quality_evaluation import duplicate_block_ratio raw_text = generation_result.text if duplicate_block_ratio(raw_text) > 0.08:   # threshold già nel tuo codice     raw_text = _remove_duplicate_paragraphs(raw_text) return raw_text # Helper locale (o importa da context_quality.py): def _remove_duplicate_paragraphs(text: str, threshold: float = 0.75) -> str:     from difflib import SequenceMatcher    blocks = [b.strip() for b in re.split(r'\n{2,}', text) if b.strip()]    unique = []    for block in blocks:        if not any(            SequenceMatcher(None, block.lower(), u.lower()).ratio() >= threshold            for u in unique        ):            unique.append(block)    return "\n\n".join(unique)``

---

## File 4: `backend/app/rag/chunker.py` (o dove viene chiamato `chunk_text`)

Il tuo metodo `chunk_and_embed` chiama `self.chunker.chunk_text(text, metadata)`.[](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/130566781/5705eb50-98a0-48e8-9998-cbae488646d2/tender_fix.md?AWSAccessKeyId=ASIA2F3EMEYES5YMDBIA&Signature=xJ0MMal%2BJ8gRDNEye%2BzYNE1HwzM%3D&x-amz-security-token=IQoJb3JpZ2luX2VjEF8aCXVzLWVhc3QtMSJHMEUCIQCNuvQ7B0y%2F9HvQCi5KJv38vd8AxyC%2FCu2Dv9fJc97hSAIgF8V277%2FubYP%2BmL579rf3Hksm583sVrKw2wT%2F%2FElKRX0q8wQIJxABGgw2OTk3NTMzMDk3MDUiDFyE5u1T3NxObVu%2FeSrQBF%2BbqHPSNolqhLDdegbtDzaATUm4v79ApMbCg3bu%2F7DizImMFPH0i443kDFxtkKjDKHvrUj63z8clPSuWYyXfMlVPtRg5Lq1MJoE89mcBTFdX3yQ5Kwkv%2BVqKzbCFZ1W8pkxNL4aLiSx5S6h%2FvH%2BSs%2Bye5n95M1wkv1O94f%2FJez6UuFDsAJGjexLfHaDWYu7d9qrrxQIKIfhu7NT%2B11skSNFx8JZwJ7%2FwSNh6WzMpdXvGvQ0LZHjVJ9SWbkTn30veBNxh9U0m%2BlDtmIBItPLZHpnOf26BRXAt9dlqFIXR1dJz6rCjTCGfsJgunVztFMZiB2jxYy418AOHRAs6Pco%2FCwZtPE%2FLCxv5sggcNJRrqkcTX0jJk38P1LHZF7MmMXsTbz1azlPdclZJZTt7ER2O1aQny8iZPcOg19aWKiZeRFR1qAOC1%2BCXU6NRkur4wTr19S6Z6oVVY9s8t1Xg9JZP%2BuaiFe5Mmyd8UZFP%2FWB4KqvfRC3zo0LNHPBdCJVVvohJEBAOdJNtUgbBvNrsitbNTv2f%2Fhu1A7XPgooaPKJmcSTtoQMJdAhJHks%2BV70U3%2FiC9kX63LQYflrgNNjrhT4dz2kuNO%2FJLcJ822sUCbUbSJ0qk71wANiyE6Zcx4CzjKYPzeicQeUBq8Uu4L9DcpyiBxT8LmyyX5TeRhhkq4WvoQ4vrQ%2B8BWk8EhfWSHBvOvigdXOOWmDUqS6ArMyyQogEStl4Ga2blKfviiJk37uGdYE0orXaxXFWZypIoRxCkrj%2B8gYvse3vuoN%2Bb2kH7qXB7Qwh8mazwY6mAG3c7RsDMICrZyduuC4xL5NWItAgXDOxo%2BzKXQSNiamLXdnOY2KfB%2F%2B5ss5JCeoUA0pzkt%2F02YS%2FiNk4KF2iVHYySXSf228Xg1IMN%2Biog7PVEdH2W7Iq9PUjY0yTxl3a%2Bc0WwSP2cW3Dbep6cdYZicX5BAlTHg3cRdu1ExEsQfz1fgy3o61CvHY4pTFz5xWHOefCdq7nTDKpA%3D%3D&Expires=1776724890)

**Modifica 6 — Aggiungi hash-dedup a livello di ingestion**, prima dell'upsert in `index_chunks`:

python

`# Trova: def index_chunks(self, chunks: list[TextChunk], collection: str = "documents") # PRIMA texts    = [c.text for c in chunks] metadatas = [c.metadata.dict() for c in chunks] # DOPO — dedup by content hash prima dell'indexing import hashlib seen_hashes: set[str] = set() unique_chunks = [] for c in chunks:     h = hashlib.sha256(c.text.encode()).hexdigest()[:20]    if h not in seen_hashes:        seen_hashes.add(h)        unique_chunks.append(c) texts     = [c.text for c in unique_chunks] metadatas = [c.metadata.dict() for c in unique_chunks]`

---

## Riepilogo dei Punti di Modifica

|File|Modifica|Effetto|
|---|---|---|
|`context_quality.py`|Threshold dedup `0.75 → 0.55` + regex heading|Cattura chunk quasi-identici|
|`generator.py`|Separatori `<doc>` XML + strip `###` dal testo chunk|Blocca re-injection del titolo|
|`generator.py`|Constraint anti-ripetizione nel system prompt|LLM non ricicla blocchi|
|`answer_quality_evaluation.py`|Chiamata post-processor su output finale|Fallback se LLM ignora constraint|
|`chunker.py` / `index_chunks`|Hash-dedup a ingestion|Previene duplicati alla fonte|

Preparato usando Claude Sonnet 4.6 Thinking