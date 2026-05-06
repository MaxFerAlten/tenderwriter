## Valutazione dell'Output RAG – Progressione

Il contenuto è **quasi completamente corretto**, ma il sistema continua a ripetere il blocco introduttivo 3 volte. I fix applicati finora hanno ridotto le ripetizioni da 5x a 3x e hanno corretto i valori numerici (180 giorni ora presente), ma il problema strutturale del separatore tra chunk è ancora irrisolto.

---

## Diagnosi Precisa dei Problemi Residui

## Problema 1 – Il separatore XML `<doc>` non è ancora stato applicato

I punti di troncamento nel testo lo confermano inequivocabilmente:

text

`"(Gara/.Dettagli della Gara e Ambito Operativo" "(MAM.Dettagli della Gara e Ambito Operativo" "(Quaracchi.Dettagli della Gara e Ambito Operativo"`

Il separatore è ancora un carattere singolo (`.` o nessuno), non un tag XML. La **Modifica 3** del messaggio precedente non è ancora applicata.

## Problema 2 – Il CIG ha ancora un errore di fatto

Nel primo blocco compare `CIG BECF` (troncato), nel secondo e terzo compare `CIG B33988ECF1`. Il CIG corretto dal documento originale è **`B33988ECF2`** (cifra finale `2`, non `1`). Questo è un'**allucinazione residua** — il LLM corregge parzialmente il troncamento ma introduce un digit sbagliato perché non legge il valore dal chunk pinned.[](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/130566781/5705eb50-98a0-48e8-9998-cbae488646d2/tender_fix.md)

## Problema 3 – "270 giorni" ancora mancante

La frase recita _"entro il termine dell'affiancamento (fissato a giorni dalla stipula"_ — il valore 270 è assente. Il pinning del chunk numerico funziona per 180 ma non per 270, il che indica che i due valori si trovano in **chunk separati** e solo uno viene pinned.

---

## Fix Residui Mirati

## Fix immediato – Pattern di pinning esteso

Il regex di `pin_critical_chunks` deve catturare anche `270`:

python

`# In backend/app/rag/context_quality.py # Modifica la lista patterns in pin_critical_chunks patterns = [     r'\b1[0-9]{2,3}\s*giorni\b',    # "180 giorni", "270 giorni" — range 100-1999    r'\b[2-9][0-9]{2}\s*giorni\b',  # cattura anche "270 giorni" esplicitamente    r'CIG\s+[A-Z0-9]{6,}',          # CIG completo — almeno 6 caratteri    r'\beuro\s*\d',    r'\bSLA\b',    r'\bpenale\b',    r'\b[Qq]ualificazion[ei]\s+ACN\b', ]`

## Fix immediato – Verifica applicazione Modifica 3

Cerca nel tuo codice dove i chunk vengono concatenati. Il punto esatto è quasi certamente in uno di questi file:

bash

`# Cerca il join dei chunk nel codice grep -rn "join" backend/app/rag/ | grep -i "text\|chunk\|context" grep -rn '"\-\-\-"' backend/app/rag/ grep -rn "'\-\-\-'" backend/app/rag/ grep -rn "\\\\n\\\\n" backend/app/rag/ | grep -i "chunk\|context"`

Il risultato ti darà la riga esatta dove applicare il fix XML.

## Fix strutturale – Forza la posizione dei chunk pinned

Il CIG errato (`ECF1` invece di `ECF2`) indica che il chunk con il CIG corretto viene pinned ma il LLM usa quello con score più alto nel ranking RRF, che è il chunk troncato. Aggiungi questo controllo **dopo** il merge `pinned + diverse`:

python

`# In rag_pipeline(), dopo: final_chunks = pinned + diverse # Dedup finale: se un chunk pinned e uno MMR hanno lo stesso chunkindex, # tieni solo il pinned (che ha il testo completo con numero intero) seen_final = set() deduplicated_final = [] for chunk in final_chunks:     cid = chunk.get("metadata", {}).get("chunkindex")    if cid not in seen_final:        seen_final.add(cid)        deduplicated_final.append(chunk) final_chunks = deduplicated_final`

---

## Stato Complessivo dei Fix

|Fix|Stato|Evidenza nell'output|
|---|---|---|
|RRF + dedup chunk ID|✅ Applicato|Riduzione da 5x a 3x|
|Pinning 180 giorni|✅ Applicato|"180 giorni" ora presente|
|Separatori `<doc>` XML|❌ Non applicato|`.Dettagli della Gara` ancora visibile|
|Strip titoli `###` dal chunk|❌ Non applicato|Titolo si ripete identico|
|Pinning 270 giorni|❌ Parziale|"270 giorni" ancora mancante|
|Dedup post-merge pinned+MMR|❌ Non applicato|CIG errato (`ECF1` vs `ECF2`)|
|Post-processing Jaccard|❌ Non applicato|3 blocchi ancora identici nell'output|

Il collo di bottiglia principale rimane il **separatore tra chunk** — applicare la Modifica 3 risolverà in un colpo solo le ripetizioni residue e il troncamento mid-sentence.