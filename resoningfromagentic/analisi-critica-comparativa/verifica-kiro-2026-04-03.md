# Verifica Critica delle Osservazioni — TenderWriter
**Data:** 2026-04-03  
**Autore:** Kiro (analisi diretta sul codebase)  
**Documenti di riferimento:** `Analisi-salute-2026-04-03.md`, `Piano-azione-salute-2026-04-03.md`, `implementation_plan.md`

---

## Metodologia

Ho letto direttamente i file sorgente citati nei tre documenti di analisi e ho verificato ogni osservazione contro il codice reale. Per ogni punto indico: **CONFERMATO**, **PARZIALMENTE CONFERMATO**, **NON CONFERMATO** o **SUPERATO/GIÀ FIXATO**, con evidenza dal codice.

---

## 1. Runtime RAG degradato a Dense-only

### Osservazione dei documenti
> "dense 12/12, sparse 0/12, graph 0/12" — il sistema funziona solo con il retriever denso.

### Verifica

**BM25 (Sparse) — CONFERMATO**  
`backend/app/rag/sparse_retriever.py`: il `SparseRetriever` è puramente in-memory. Il metodo `build_index()` deve essere chiamato esplicitamente con i testi. All'avvio dell'applicazione (`main.py`) non c'è nessuna chiamata che ricarica i chunk da PostgreSQL nel BM25. Il `HybridRAGEngine.initialize()` crea un `SparseRetriever()` vuoto e non chiama mai `build_index()`. Risultato: `_bm25 is None`, ogni query restituisce lista vuota con warning "BM25 search called but index is empty".

```python
# engine.py - initialize()
self.sparse_retriever = SparseRetriever()
# ← nessun build_index() qui. Il corpus è sempre vuoto al boot.
```

**GraphRetriever — PARZIALMENTE CONFERMATO**  
Il bug `Neo.ClientError.Statement.ParameterMissing` citato nei documenti **non è riproducibile dal codice attuale**. Sia `_search_projects` che `_search_team_members` passano correttamente `parameters_={"query": query, "top_k": top_k}`. Il driver `neo4j-driver` async accetta `parameters_` come keyword. Se il bug era presente in una versione precedente, risulta già fixato. Tuttavia: se Neo4j non è raggiungibile o il grafo è vuoto (nessun nodo `Project`/`TeamMember` inserito), il retriever restituisce comunque lista vuota — il che spiega il "0/12" nel benchmark senza necessariamente un errore di parametri.

### Considerazione aggiuntiva
Il vero problema del BM25 è strutturale: non esiste nessun meccanismo di persistenza dei token. `add_chunks()` aggiunge in memoria ma al restart tutto si perde. La soluzione corretta richiede o un reload da DB all'avvio o la migrazione a un engine sparse persistente (OpenSearch/Elasticsearch come suggerito nel Piano).

---

## 2. Docker socket — escalation di privilegi

### Osservazione dei documenti
> "Docker socket nel backend" — rischio di escalation root.

### Verifica — PARZIALMENTE CONFERMATO (ma diverso da quanto descritto)

Il `docker-compose.yml` monta `/var/run/docker.sock` in **due** container:
1. `ops-agent` — **intenzionale e corretto**, è il container dedicato a questo scopo con allowlist `OPS_ALLOWED_PREFIX`
2. `mattermost-bootstrap` — container one-shot che usa `docker:28-cli` per eseguire `mmctl` via Docker exec

Il **backend** (`tw-backend`) **NON monta il Docker socket** — contrariamente a quanto affermato nell'analisi. Ho verificato sia il `docker-compose.yml` che il codice backend: nessun riferimento a `/var/run/docker.sock`.

Il rischio reale rimane su `mattermost-bootstrap`: è un container con accesso root al socket Docker, anche se è `restart: "no"`. Se compromesso durante il bootstrap, ha accesso completo al daemon Docker dell'host.

---

## 3. Credenziali hardcoded in docker-compose.yml

### Osservazione dei documenti
> "DefaultPg2024Pass, DefaultNEO4J2024Pass, DefaultMinIO2024Pass, DefaultMM2024Pass, CHANGEME-mattermost-client-secret"

### Verifica — CONFERMATO

Tutte le password citate sono presenti come fallback nei default `${VAR:-default}`:

```yaml
POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-DefaultPg2024Pass}
NEO4J_AUTH: neo4j/${NEO4J_PASSWORD:-DefaultNEO4J2024Pass}
MINIO_ROOT_PASSWORD: ${MINIO_SECRET_KEY:-DefaultMinIO2024Pass}
MM_OPENIDSETTINGS_SECRET: "${MM_OIDC_CLIENT_SECRET:-CHANGE_ME_mattermost_client_secret}"
KC_BOOTSTRAP_ADMIN_PASSWORD: ${KC_ADMIN_PASSWORD:-DefaultKCAdmin2026Pass}
```

Sono fallback, non hardcoded assoluti — se il `.env` è configurato correttamente non vengono usati. Il rischio è reale solo se il `.env` non viene creato prima del deploy (scenario comune in ambienti di sviluppo/staging). La password Mattermost admin `TW2026Secure!Pass` è invece hardcoded direttamente come default senza variabile d'ambiente nel service `backend`.

---

## 4. SSRF nell'anonymizer

### Osservazione dei documenti
> "Fix SSRF: intervenire sull'anonymizer per blindare la Server-Side Request Forgery"

### Verifica — NON CONFERMATO (già mitigato)

`anonymizer/app.py` implementa `_is_allowed_target_url()` che:
- Blocca `localhost`, `0.0.0.0`, `::1`, `metadata.google.internal`
- Risolve il hostname via DNS e blocca indirizzi loopback, link-local, multicast, reserved, unspecified
- Richiede schema `http` o `https`

La protezione è presente e ragionevole. Rimane un vettore residuo: **DNS rebinding** — il check risolve il DNS al momento della validazione, ma la richiesta HTTP viene fatta dopo. Un attaccante con controllo DNS può far risolvere il dominio a un IP pubblico durante il check e poi a `127.0.0.1` durante la richiesta. Questo è un problema noto e difficile da risolvere completamente senza un proxy con IP pinning.

---

## 5. Endpoint OnlyOffice senza autenticazione

### Osservazione dei documenti
> "Protezione Endpoint: applicare autenticazione agli endpoint OnlyOffice esposti (es. files/{docKey})"

### Verifica — PARZIALMENTE CONFERMATO

`serve_document` non usa `Depends(get_current_user)` ma implementa un meccanismo di firma proprietario:
- Verifica `_verify_file_signature(doc_key, expires, signature)` — HMAC-SHA256 con `onlyoffice_jwt_secret`
- Verifica `_verify_download_token(doc_key, metadata, download_token)` — token legato all'utente

Non è autenticazione JWT standard, ma è un meccanismo di autorizzazione funzionale. Il rischio è che se `onlyoffice_jwt_secret` è debole (default `changeme_oo_jwt_secret` nel compose), l'intera protezione crolla.

### Considerazione aggiuntiva
Il documento cita "MD5 per document keys" come vulnerabilità. **Non confermato**: il codice usa `hmac.new(..., hashlib.sha256).hexdigest()[:32]` — SHA-256 con HMAC, non MD5. Questa osservazione era probabilmente corretta su una versione precedente del codice, ora fixata.

---

## 6. BUG-01: DELETE senza commit

### Osservazione dei documenti
> "operazione DELETE senza await db.commit() — la cancellazione non viene persistita"

### Verifica — NON CONFERMATO (già fixato)

`backend/app/api/tenders.py` riga 470:
```python
await db.delete(tender)
await db.commit()  # ← presente
```

Il commit c'è. Il bug è già stato risolto.

---

## 7. BUG-03: XSS nel PDF export

### Osservazione dei documenti
> "XSS in generazione PDF via |safe Jinja"

### Verifica — CONFERMATO

`backend/app/tasks.py` riga ~140:
```html
<p>{{ section.content|safe }}</p>
```

Il filtro `|safe` disabilita l'escaping Jinja2. Se `section.content` contiene HTML arbitrario (es. `<script>alert(1)</script>`), viene renderizzato nel PDF. WeasyPrint non esegue JavaScript, quindi il rischio XSS classico è limitato, ma HTML injection nel PDF è possibile (es. link malevoli, contenuto fuorviante, CSS injection per esfiltrare dati via `url()`).

---

## 8. Content Library senza autenticazione

### Osservazione dei documenti
> "nelle API della Content Library non emergono guardie esplicite per utente o ruolo"

### Verifica — CONFERMATO

`backend/app/api/content_library.py`: **nessuna** delle route usa `Depends(get_current_user)`. Tutti gli endpoint (list, create, get, update, delete, increment_usage) sono accessibili senza autenticazione. Chiunque conosca l'URL può leggere, creare, modificare o cancellare i content block.

Questo è il bug di sicurezza più grave e facilmente sfruttabile nel codebase attuale.

---

## 9. generate_proposal_section_task chiama metodo inesistente

### Osservazione dei documenti
Non citato esplicitamente nei tre documenti analizzati.

### Verifica — CONFERMATO (bug aggiuntivo non documentato)

`backend/app/tasks.py` riga ~75:
```python
result = await engine.generate(
    query=query_text,
    mode=QueryMode.WRITE_SECTION,
    ...
)
```

`HybridRAGEngine` non ha un metodo `.generate()`. Il metodo pubblico è `.query(rag_query: RAGQuery)`. Questo task **fallisce sempre** con `AttributeError` al runtime. Non è citato nei documenti di analisi — è un bug aggiuntivo scoperto durante questa verifica.

---

## 10. Schema management e Alembic

### Osservazione dei documenti
> "migrazioni raw SQL all'avvio nel backend principale — schema management fragile"

### Verifica — CONFERMATO

`backend/app/db/database.py` usa `init_db()` che chiama `Base.metadata.create_all()` o equivalente. Non c'è Alembic nel progetto. Ogni modifica allo schema richiede `ALTER TABLE` manuale o drop/recreate. In produzione con dati reali questo è un rischio operativo serio.

---

## 11. Script operativi nel package applicativo

### Osservazione dei documenti
> "check_db_schema.py, clean_db.py, delete_user.py, reset_admin_password.py appartengono a un toolbox operativo separato"

### Verifica — CONFERMATO

Tutti e quattro i file esistono in `backend/app/`:
- `check_db_schema.py`
- `clean_db.py`  
- `delete_user.py`
- `reset_admin_password.py`
- `check_users.py`

Sono script standalone che importano dal package applicativo. Sono nel path di produzione e vengono inclusi nell'immagine Docker. `clean_db.py` in particolare è pericoloso se eseguito accidentalmente in produzione.

---

## 12. Latenza LLM (60-167 secondi)

### Osservazione dei documenti
> "Latenza LLM molto alta: circa 60-167 secondi per query QA"

### Verifica — PLAUSIBILE, non verificabile dal codice

Il `docker-compose.yml` mostra che `llama-tender` usa `gemma-3n-E4B-it-Q4_K_M.gguf` con `-t 20` (20 thread CPU) e `-c 8192` (context window). Senza GPU, su CPU, latenze di 60-167 secondi per un modello da 4B parametri sono plausibili. Il gateway ha `GATEWAY_TIMEOUT: ${GATEWAY_TIMEOUT:-180}` — il timeout di 180 secondi conferma che il team si aspetta latenze elevate.

---

## 13. Osservazioni sui documenti di analisi: accuratezza complessiva

| Osservazione | Stato | Note |
|---|---|---|
| RAG sparse 0/12 | ✅ Confermato | BM25 non viene mai inizializzato con dati |
| RAG graph 0/12 | ⚠️ Parziale | Parametri Cypher OK, problema probabilmente dati vuoti |
| Docker socket nel backend | ❌ Non confermato | Solo ops-agent e mattermost-bootstrap |
| Credenziali hardcoded compose | ✅ Confermato | Sono fallback, non assoluti |
| SSRF anonymizer | ❌ Non confermato | Protezione già implementata (con limite DNS rebinding) |
| OnlyOffice senza auth | ⚠️ Parziale | Auth proprietaria presente, ma dipende da secret debole |
| MD5 document keys | ❌ Non confermato | Già migrato a HMAC-SHA256 |
| BUG-01 delete senza commit | ❌ Non confermato | Già fixato |
| BUG-03 XSS PDF | ✅ Confermato | `\|safe` ancora presente |
| Content Library senza auth | ✅ Confermato | Zero guardie su tutte le route |
| Script ops nel package | ✅ Confermato | 5 script in `backend/app/` |
| Schema management fragile | ✅ Confermato | Nessun Alembic |

---

## 14. Bug aggiuntivi non documentati nei tre file

Trovati durante questa verifica, non presenti nei documenti analizzati:

1. **`generate_proposal_section_task` chiama `engine.generate()` inesistente** — task sempre in errore
2. **`double await db.refresh(user)` in `register`** — doppio round-trip inutile al DB
3. **`get_async_session()` crea un nuovo engine SQLAlchemy ad ogni chiamata Celery** — connection pool exhaustion sotto carico
4. **`cleanup_expired_otp` usa `datetime.utcnow()` naive** vs token con `timezone.utc` aware — confronto potenzialmente errato su PostgreSQL
5. **`verify_otp` usa `scalar_one_or_none()` su query senza `ORDER BY`** — se esistono due OTP per lo stesso utente (possibile perché `register` non cancella il vecchio), lancia `MultipleResultsFound`
6. **Redis client senza timeout** — hanging indefinito se Redis è irraggiungibile

---

## 15. Valutazione complessiva dei documenti

I tre documenti mostrano un'analisi di buona qualità con alcune imprecisioni:

- **Punti forti**: identificazione corretta del problema BM25/sparse, credenziali compose, XSS PDF, script ops nel package, assenza Alembic, content library senza auth
- **Imprecisioni**: il Docker socket nel backend non c'è (è solo in ops-agent), SSRF è già mitigato, MD5 è già stato sostituito con HMAC-SHA256, BUG-01 è già fixato
- **Gap**: il bug più critico (`generate_proposal_section_task` con metodo inesistente) non è documentato in nessuno dei tre file

Il piano d'azione proposto è sensato nelle priorità. La Fase 0 (72 ore) è corretta nell'identificare i blocchi principali, anche se alcune voci (SSRF, Docker socket backend) non richiedono intervento perché già risolte o non presenti.

**Raccomandazione principale non presente nei documenti**: prima di qualsiasi altra cosa, fixare `generate_proposal_section_task` e il reload BM25 all'avvio — sono i due problemi che rendono la pipeline RAG completamente non funzionale in produzione.
