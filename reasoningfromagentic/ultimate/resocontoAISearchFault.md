# Resoconto: Analisi e Fix del Fault in AI Search (RAG)

Data: 2026-04-13

---

## Sintomo osservato

L'endpoint AI Search restituiva testo con degeneration loop:

```
...l'amministrazione owne owne owne owne owne owne owne owne owne owne owne own
```

Variante successiva (dopo primo tentativo di fix incompleto):

```
...mezzo attraverso cui l'amministrazione owne owne owne owne owne owne owne owne own
```

Il modello generava correttamente i primi paragrafi, poi collassava in ripetizione infinita di un frammento di token.

---

## Percorso diagnostico

### Step 1 — Esclusione crash container

```
Status: running | ExitCode: 0 | RestartCount: 0 | OOMKilled: false
```

Il container `tw-llama-tender` non crashava, non aveva OOM, non si riavviava. Il problema non era infrastrutturale.

### Step 2 — Analisi sampler chain nei log llama.cpp

```
slot launch_slot_: sampler chain:
  logits -> ?penalties -> ?dry -> ?top-n-sigma -> top-k -> ?typical -> top-p -> min-p -> ?xtc -> temp-ext -> dist
```

**Osservazione critica**: il prefisso `?` in llama.cpp indica un sampler presente nella chain ma **inattivo** perché i parametri corrispondenti hanno valore di default (disabilitato).

- `?penalties` → repetition penalty disattivato (default: 1.0 = nessuna penalità)
- `?dry` → DRY sampler disattivato (default: 0.0 = disabilitato)

Senza alcun meccanismo anti-ripetizione, il modello entrava in loop non appena la probabilità di un token diventava dominante in un ciclo di feedback.

### Step 3 — Analisi del payload inviato al server

Il codice in `backend/app/rag/generator.py` costruiva la richiesta verso `/completion` così:

```python
request_data = {
    "prompt": prompt,
    "n_predict": max_tokens,
    "temperature": temperature,
    "stop": stop_tokens,
}
```

Nessun parametro di penalizzazione. Il sampler riceveva solo temperatura e stop tokens — identico a non configurarlo affatto per la ripetizione.

### Step 4 — Identificazione del percorso di codice

La condizione di routing era:

```python
elif "/v1" in self.base_url:
    # Internal llama.cpp server - use /completion endpoint
```

La configurazione in `app/config.py`:

```python
llama_server_url: str = "http://llama-tender:8080/v1"
```

Il percorso veniva effettivamente colpito. Il problema era solo l'assenza dei parametri anti-repetition nel payload.

### Step 5 — Esclusione di cause alternative

| Ipotesi | Esito |
|---|---|
| Container usa GPU sbagliata | Esclusa — GFX1151 = RX 8060S, unica GPU nel sistema |
| Modello corrotto o sbagliato | Esclusa — Q6_K caricato correttamente, generazione iniziale coerente |
| Limite `--n-predict` nel server | Contribuisce ma non causa il loop — era già stato rimosso |
| Quantizzazione troppo aggressiva | Già sostituita da IQ2_XXS a Q6_K_L, non causa primaria |
| Context window insufficiente | Esclusa — 65536 token disponibili, prompt <3000 token |

---

## Causa radice

**Il payload della richiesta non includeva parametri di penalizzazione della ripetizione.**

llama.cpp con `repeat_penalty=1.0` (default) non penalizza alcun token già generato. Su sequenze lunghe o con contesti ripetitivi (documenti legali con terminologia ricorrente), il modello converge su un token o una sequenza breve e la replica indefinitamente.

Il DRY sampler (*Don't Repeat Yourself*), anch'esso assente, avrebbe bloccato la ripetizione di sequenze multi-token prima che si formasse il loop.

---

## Fix applicati

### Fix 1 — Parametri anti-repetition nel payload llama.cpp

**File**: `backend/app/rag/generator.py`  
**Righe**: chiamata principale (~L931) e chiamata retry (~L962)

**Prima:**
```python
request_data = {
    "prompt": prompt,
    "n_predict": max_tokens,
    "temperature": temperature,
    "stop": stop_tokens,
}
```

**Dopo:**
```python
request_data = {
    "prompt": prompt,
    "n_predict": max_tokens,
    "temperature": temperature,
    "stop": stop_tokens,
    "repeat_penalty": 1.1,
    "repeat_last_n": 256,
    "dry_multiplier": 0.8,
    "dry_base": 1.75,
    "dry_allowed_length": 2,
}
```

**Spiegazione parametri:**

| Parametro | Valore | Razionale |
|---|---|---|
| `repeat_penalty` | `1.1` | Moltiplica per 1/1.1 la probabilità di token già generati. Valore conservativo: penalizza senza distorcere la distribuzione. |
| `repeat_last_n` | `256` | Finestra di lookback: guarda gli ultimi 256 token. Il default (64) è troppo corto per documenti legali con terminologia ripetitiva strutturalmente necessaria. |
| `dry_multiplier` | `0.8` | Attiva il DRY sampler con intensità moderata. Blocca sequenze ripetute di qualsiasi lunghezza. |
| `dry_base` | `1.75` | Crescita esponenziale della penalità all'aumentare della lunghezza della sequenza ripetuta. Evita che sequenze lunghe si ripetano identiche. |
| `dry_allowed_length` | `2` | Sequenze di 1-2 token non vengono penalizzate: evita falsi positivi su articoli, preposizioni, congiunzioni italiane molto frequenti ("di", "in", "la", "il", ecc.). |

### Fix 2 — Rebuild immagine Docker backend

Il backend è costruito da `Dockerfile` (`build: context: ./backend`) senza volume mount del codice sorgente. Modificare i file locali non ha effetto sul container in esecuzione finché non si esegue:

```bash
docker compose build backend
docker compose up -d --force-recreate backend
```

Un semplice `restart` non è sufficiente — il codice è baked nell'immagine.

**Verifica fix applicato nel container:**
```bash
docker exec tw-backend grep -n 'repeat_penalty\|dry_multiplier' /app/app/rag/generator.py
# Output atteso:
# 936: "repeat_penalty": 1.1,
# 938: "dry_multiplier": 0.8,
# 973: "repeat_penalty": 1.1,
# 975: "dry_multiplier": 0.8,
```

---

## Fix correlati (contesto più ampio)

Identificati e applicati nella stessa sessione, concausa della qualità scadente generale:

### Fix 3 — Rimozione `--n-predict 1024` dal server llama.cpp

Il docker-compose aveva `--n-predict 1024` come argomento fisso al server: ogni risposta veniva troncata a ~750 parole indipendentemente dalla lunghezza richiesta. Rimosso e impostato a `-1` (illimitato, controllato dal client).

### Fix 4 — Sostituzione modello (da IQ2_XXS a Q6_K_L)

Il modello `gemma-3n-E4B-it-UD-IQ2_XXS.gguf` usava quantizzazione a 2 bit (~2.63 GB), la più aggressiva disponibile. Sostituito con `gemma-4-31b-it-q6_k_l.gguf` (Q6_K_L, ~27 GB): qualità quasi identica al BF16 originale, 256k token di contesto, supporto 140+ lingue.

### Fix 5 — Argomenti docker-compose corretti

Nel refactor dei parametri del server era stato introdotto un bug: `--flash-attn` senza valore esplicito consumava il parametro successivo (`--reasoning-format`) come suo valore, causando crash al boot:

```
error while handling argument "--flash-attn": error: unknown value for --flash-attn: '--reasoning-format'
```

Corretto in `-fa on` (valore esplicito) e rimosso `--reasoning-format none` (non supportato da questa versione dell'immagine).

---

## Stato post-fix

| Check | Stato |
|---|---|
| Container `tw-llama-tender` | Running, no restart |
| Modello caricato | `gemma-4-31b-it-q6_k_l.gguf` (Q6_K confermato) |
| GPU utilizzata | Vulkan0 RX 8060S (GFX1151) — corretto |
| Contesto server | 65536 token |
| Fix codice nel container | Confermato (`docker exec` grep) |
| Sampler chain post-fix | Da verificare sulla prossima richiesta — atteso `penalties` e `dry` senza `?` |

---

## Punto aperto

`llama_max_tokens: int = 256` in `app/config.py` limita l'output a 256 token per default (~190 parole). Per analisi di gare d'appalto questo è probabilmente insufficiente. Da valutare l'aumento a 2048-4096 in base ai casi d'uso reali.

---

*Analisi condotta da Claude Code (claude-sonnet-4-6) — 2026-04-13*
