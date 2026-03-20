
Partendo dalle analisi seguenti:
# 🐛 TenderWriter — Analisi Bug Potenziali

  

Report generato dall'analisi statica dell'intera codebase. I bug sono classificati per **severità** e **categoria**.

  

---

  

## 🔴 Severità CRITICA

  

### BUG-01: Missing `db.commit()` in [delete_tender](file:///d:/tender/tenderwriter/backend/app/api/tenders.py#385-394) — il tender non viene cancellato

  

| | |

|---|---|

| **File** | [tenders.py](file:///d:/tender/tenderwriter/backend/app/api/tenders.py#L385-L393) |

| **Tipo** | Data Integrity |

  

```python

@router.delete("/{tender_id}", status_code=204)

async def delete_tender(...):

    tender = await check_tender_access(tender_id, current_user, db)

    await db.delete(tender)

    # ⚠️ MANCA: await db.commit() oppure await db.flush()

```

  

Anche se [get_db()](file:///d:/tender/tenderwriter/backend/app/db/database.py#25-34) fa auto-commit alla fine della sessione, il problema è che **nessun evento KPI viene pubblicato**, e se si verifica un'eccezione dopo `db.delete()` ma prima del commit implicito, la cancellazione rischia di essere persa silenziosamente. In più, i file su MinIO **non vengono cancellati** — si creano dati orfani nello storage.

  

---

  

### BUG-02: SQL Injection via `ilike` con f-string nel search dei tender

  

| | |

|---|---|

| **File** | [tenders.py](file:///d:/tender/tenderwriter/backend/app/api/tenders.py#L243) |

| **Tipo** | Security |

  

```python

if search:

    query = query.where(Tender.title.ilike(f"%{search}%"))

```

  

L'input utente `search` viene interpolato direttamente nel pattern `LIKE`. Un utente malintenzionato può iniettare caratteri speciali come `%` o `_` per alterare i risultati della query. Anche se non è SQL injection classica (il valore è parametrizzato da SQLAlchemy), **i metacaratteri LIKE non sono escapati**, permettendo ricerche wildcarded non intenzionali.

  

> [!WARNING]

> **Fix**: usare `func.escape()` o sostituire manualmente `%` e `_` nell'input prima dell'ilike.

  

---

  

### BUG-03: XSS (Cross-Site Scripting) nel PDF export via `|safe` Jinja

  

| | |

|---|---|

| **File** | [tasks.py](file:///d:/tender/tenderwriter/backend/app/tasks.py#L151) |

| **Tipo** | Security |

  

```html

<p>{{ section.content|safe }}</p>

```

  

Il filtro `|safe` disabilita l'auto-escaping di Jinja2. Se `section.content` contiene HTML/JS iniettato da un utente, il PDF generato eseguirà script nel contesto di WeasyPrint, e il contenuto HTML verrà renderizzato senza sanitizzazione.

  

---

  

### BUG-04: SSRF nell'Anonymizer — nessuna validazione dell'URL target

  

| | |

|---|---|

| **File** | [anonymizer/app.py](file:///d:/tender/tenderwriter/anonymizer/app.py#L12-L41) |

| **Tipo** | Security |

  

```python

target_url = request.headers.get("x-target-url")

# ⚠️ Nessuna validazione! Un attaccante può usare:

# x-target-url: http://169.254.169.254/latest/meta-data/  (AWS metadata)

# x-target-url: http://localhost:5432  (servizi interni)

```

  

L'anonymizer è un proxy aperto che inoltra richieste a **qualsiasi URL** specificato nell'header. Non c'è validazione dell'URL, il che permette attacchi **SSRF** verso servizi interni (DB, Redis, cloud metadata, ecc.).

  

---

  

### BUG-05: OnlyOffice [serve_document](file:///d:/tender/tenderwriter/backend/app/api/onlyoffice.py#534-556) endpoint non ha autenticazione

  

| | |

|---|---|

| **File** | [onlyoffice.py](file:///d:/tender/tenderwriter/backend/app/api/onlyoffice.py#L534-L555) |

| **Tipo** | Security |

  

```python

@router.get("/files/{doc_key}")

async def serve_document(doc_key: str):

    # ⚠️ Nessun Depends(get_current_user)!

```

  

Chiunque conosca un `doc_key` può scaricare il documento. I `doc_key` sono hash MD5 di 20 caratteri, ma derivati da dati prevedibili (`p{id}_s{id}_{timestamp}`), quindi potenzialmente brute-forcabili.

  

---

  

## 🟠 Severità ALTA

  

### BUG-06: OnlyOffice callback non ha autenticazione/validazione JWT

  

| | |

|---|---|

| **File** | [onlyoffice.py](file:///d:/tender/tenderwriter/backend/app/api/onlyoffice.py#L569-L742) |

| **Tipo** | Security |

  

Il callback riceve un campo [token](file:///d:/tender/tenderwriter/backend/app/api/auth.py#81-86) nel payload, ma **non viene mai verificato**. Un attaccante potrebbe inviare richieste POST false al callback per sovrascrivere il contenuto di sezioni o blocchi nel database.

  

---

  

### BUG-07: `asyncio.create_task()` senza gestione errori al startup

  

| | |

|---|---|

| **File** | [main.py](file:///d:/tender/tenderwriter/backend/app/main.py#L69) |

| **Tipo** | Reliability |

  

```python

asyncio.create_task(app.state.rag_engine.initialize())

```

  

Se `initialize()` fallisce, l'eccezione viene persa silenziosamente ("fire-and-forget"). L'app apparirebbe healthy ma il RAG engine non funzionerebbe, causando errori 500 in tutte le query RAG.

  

---

  

### BUG-08: Mutable default in SQLAlchemy Column definitions

  

| | |

|---|---|

| **File** | [models/__init__.py](file:///d:/tender/tenderwriter/backend/app/models/__init__.py#L172-L173) |

| **Tipo** | Data Integrity |

  

```python

tags = Column(ARRAY(String), default=[])        # ⚠️ Mutable default

metadata_json = Column(JSONB, default={})        # ⚠️ Mutable default

content = Column(JSONB, default={})              # ⚠️ Mutable default

```

  

Python condivide lo **stesso oggetto** tra tutte le istanze. Se si modifica `tender.tags.append(x)`, il default usato per le nuove istanze viene mutato. Usare `default=list` (callable) o `default_factory`.

  

---

  

### BUG-09: `datetime.utcnow()` deprecato — possibili errori di timezone

  

| | |

|---|---|

| **File** | Multipli |

| **Tipo** | Data Integrity |

  

`datetime.utcnow()` è usato ampiamente nel codice:

  

| Posizione | Riga |

|---|---|

| [tenders.py](file:///d:/tender/tenderwriter/backend/app/api/tenders.py#L363) | `recorded_at=datetime.utcnow()` |

| [tenders.py](file:///d:/tender/tenderwriter/backend/app/api/tenders.py#L604) | `return value or datetime.utcnow()` |

| [proposals.py](file:///d:/tender/tenderwriter/backend/app/api/proposals.py#L377) | `submitted_at=datetime.utcnow()` |

| [proposals.py](file:///d:/tender/tenderwriter/backend/app/api/proposals.py#L665) | `return value or datetime.utcnow()` |

| [tasks.py](file:///d:/tender/tenderwriter/backend/app/tasks.py#L207) | `OTPToken.expires_at < datetime.utcnow()` |

| [tasks.py](file:///d:/tender/tenderwriter/backend/app/tasks.py#L224) | `"timestamp": datetime.utcnow().isoformat()` |

| [onlyoffice.py](file:///d:/tender/tenderwriter/backend/app/api/onlyoffice.py#L122) | `cutoff_time = datetime.now()` |

  

`datetime.utcnow()` è deprecato da Python 3.12 e ritorna un datetime **naive** (senza timezone). Il modello [OTPToken](file:///d:/tender/tenderwriter/backend/app/models/__init__.py#132-145) usa `DateTime(timezone=True)`, creando un mismatch naive vs aware quando si compara `OTPToken.expires_at < datetime.utcnow()`.

  

---

  

### BUG-10: Cleanup [onlyoffice](file:///d:/tender/tenderwriter/backend/app/api/onlyoffice.py#569-743) usa `datetime.now()` senza timezone

  

| | |

|---|---|

| **File** | [onlyoffice.py](file:///d:/tender/tenderwriter/backend/app/api/onlyoffice.py#L122-L125) |

| **Tipo** | Data Integrity |

  

```python

cutoff_time = datetime.now() - timedelta(hours=max_age_hours)

# ...

if obj.last_modified and obj.last_modified.replace(tzinfo=None) < cutoff_time:

```

  

`last_modified` di MinIO è in UTC. `datetime.now()` usa l'ora locale. Se il server è in CET (+1), i documenti verrebbero cancellati **1 ora prima del dovuto**.

  

---

  

## 🟡 Severità MEDIA

  

### BUG-11: `UserRegister.email` non validato come email

  

| | |

|---|---|

| **File** | [auth.py](file:///d:/tender/tenderwriter/backend/app/api/auth.py#L48-L51) |

| **Tipo** | Validation |

  

```python

class UserRegister(BaseModel):

    email: str      # ⚠️ Dovrebbe essere EmailStr

    name: str

    password: str

```

  

Nessuna validazione del formato email. Un utente potrebbe registrare `email="malicious<script>alert(1)</script>"`. Lo schema [UserLogin](file:///d:/tender/tenderwriter/backend/app/api/auth.py#54-57) ha lo stesso problema.

  

---

  

### BUG-12: Doppia `db.refresh(user)` nella registrazione

  

| | |

|---|---|

| **File** | [auth.py](file:///d:/tender/tenderwriter/backend/app/api/auth.py#L191-L192) |

| **Tipo** | Code Quality |

  

```python

await db.refresh(user)

await db.refresh(user)  # ⚠️ Duplicato

```

  

Non è un bug critico, ma è una query non necessaria al database.

  

---

  

### BUG-13: [update_proposal](file:///d:/tender/tenderwriter/backend/app/api/proposals.py#333-406) accede a `proposal.status` prima del null check

  

| | |

|---|---|

| **File** | [proposals.py](file:///d:/tender/tenderwriter/backend/app/api/proposals.py#L343-L344) |

| **Tipo** | Logic Error |

  

```python

previous_status = proposal.status if proposal else None

if not proposal:  # ⚠️ Se proposal è None, la riga sopra ha già fatto NoneType access

    raise HTTPException(...)

```

  

Se [proposal](file:///d:/tender/tenderwriter/backend/app/api/proposals.py#290-331) è `None`, la riga 343 fa `None.status`, che solleva un `AttributeError` prima che si arrivi all'HTTPException. In pratica SQLAlchemy restituisce `None` per `scalar_one_or_none`, quindi il check sulla riga 344 non viene mai raggiunto in caso di errore.

  

---

  

### BUG-14: [update_section](file:///d:/tender/tenderwriter/backend/app/api/proposals.py#485-580) — logica if/else identica

  

| | |

|---|---|

| **File** | [proposals.py](file:///d:/tender/tenderwriter/backend/app/api/proposals.py#L514-L518) |

| **Tipo** | Logic Error |

  

```python

for key, value in data.model_dump(exclude_unset=True).items():

    if key == 'content' and isinstance(value, str):

        setattr(section, key, value)       # branch 1

    else:

        setattr(section, key, value)       # branch 2 — identico!

```

  

I due branch fanno esattamente la stessa cosa. Probabilmente manca una conversione/trasformazione del contenuto nel primo branch (es. [_text_to_tiptap_content(value)](file:///d:/tender/tenderwriter/backend/app/api/onlyoffice.py#291-304)).

  

---

  

### BUG-15: Gateway `_cache` — modulo-level mutable senza thread safety

  

| | |

|---|---|

| **File** | [gateway/app.py](file:///d:/tender/tenderwriter/gateway/app.py#L160-L161) |

| **Tipo** | Concurrency |

  

```python

_cache = {}

_CACHE_TTL = 5.0

```

  

`_cache` è un dizionario mutabile a livello di modulo senza lock. Con Uvicorn multiworker, ogni worker ha il suo dict (OK), ma in un singolo worker con asyncio, le scritture concurrent sono sicure perché Python ha il GIL. Tuttavia, se si passa a un deploy multi-thread, questo creerebbe race conditions.

  

---

  

### BUG-16: OTP non verificato — utente può fare login senza verificare

  

| | |

|---|---|

| **File** | [auth.py](file:///d:/tender/tenderwriter/backend/app/api/auth.py#L177-L179) |

| **Tipo** | Logic Issue |

  

```python

user = User(

    ...

    is_verified=False,

    is_active=True,   # ⚠️ Utente attivo immediatamente

)

```

  

L'utente viene creato con `is_active=True` ma `is_verified=False`. Il login controlla entrambi, ma ci sono altri endpoint che controllano solo `is_active` (o neanche quello), potenzialmente permettendo azioni prima della verifica OTP.

  

---

  

### BUG-17: Docker Compose — Docker socket montato nel backend

  

| | |

|---|---|

| **File** | [docker-compose.yml](file:///d:/tender/tenderwriter/docker-compose.yml#L291) |

| **Tipo** | Security |

  

```yaml

volumes:

  - /var/run/docker.sock:/var/run/docker.sock

```

  

Montare il Docker socket nel container backend dà **accesso root completo** all'host. Se il backend viene compromesso, l'attaccante può creare container privilegiati, leggere file dall'host, ecc.

  

---

  

### BUG-18: Hash MD5 usato per document keys — debole e prevedibile

  

| | |

|---|---|

| **File** | [onlyoffice.py](file:///d:/tender/tenderwriter/backend/app/api/onlyoffice.py#L220-L222) |

| **Tipo** | Security |

  

```python

raw = f"p{proposal_id}_s{section_id}_{ts}"

return hashlib.md5(raw.encode()).hexdigest()[:20]

```

  

MD5 è crittograficamente debole e l'input è facilmente prevedibile (IDs sequenziali + timestamp). Combinato con BUG-05 (nessuna autenticazione su `/files/{doc_key}`), questo rende facile enumerare e scaricare documenti.

  

---

  

## 📊 Riepilogo

  

| Severità | Count | Bug IDs |

|---|---|---|

| 🔴 Critica | 5 | BUG-01, BUG-02, BUG-03, BUG-04, BUG-05 |

| 🟠 Alta | 5 | BUG-06, BUG-07, BUG-08, BUG-09, BUG-10 |

| 🟡 Media | 8 | BUG-11 – BUG-18 |

  

### Priorità di fix raccomandata

  

1. **BUG-04** (SSRF anonymizer) + **BUG-05/06** (autenticazione OnlyOffice) — rischio di sicurezza immediato

2. **BUG-01** (delete senza commit) + **BUG-03** (XSS in PDF) — impatto funzionale e sicurezza

3. **BUG-17** (Docker socket) — escalation di privilegi

4. **BUG-09/10** (datetime) + **BUG-08** (mutable defaults) — bug latenti che emergono in produzione

5. **BUG-13/14** (logic errors) + **BUG-11/12** (validation/duplication) — code quality
CODEX:

ok from 0 to 10 give me a vote on codebase

6.5/10 overall.

It’s clearly above average in ambition and structure: there’s real product thinking here, multiple services, domain modeling, observability work, and a meaningful test suite instead of a toy app. The KPI engine in particular has solid depth.

What keeps it out of the 8-9 range is reliability and polish. I found workflow-state bugs in important lifecycle paths, there’s some environment/test friction, naming/organization is inconsistent in places, and the repo carries a fair amount of generated or noisy material that makes maintenance harder.

My rough split:

- Architecture: 7.5/10
- Product scope: 8/10
- Reliability: 5.5/10
- Developer experience: 5.5/10
- Test discipline: 6.5/10

If we keep tightening lifecycle correctness, trim repo noise, and smooth setup/test ergonomics, this can move to 8/10 without needing a rewrite.

for any dot please create table with "specific case", "motivation explain", "solution proposal"

|specific case|motivation explain|solution proposal|
|---|---|---|
|Overall 6.5/10|Strong product ambition, real multi-service architecture, useful domain modeling, and non-trivial tests. The main drag is operational reliability: important lifecycle/state paths were inconsistent, setup is a bit rough, and the repo has noise that increases maintenance cost.|Focus the next cycle on correctness and maintainability rather than new features: stabilize workflow transitions, clean repo hygiene, standardize testing/setup, and reduce incidental complexity.|
|Architecture 7.5/10|The split between backend, frontend, and kpi-reason-engine is meaningful, not arbitrary. There is a visible domain model and the KPI service has a clear responsibility. The weakness is that state is duplicated across boundaries, so drift bugs become likely.|Define a stricter contract for lifecycle/state transitions, centralize canonical workflow semantics, and add contract/regression tests around service boundaries.|
|Product scope 8/10|The codebase clearly aims at a real business workflow, not a demo. Tender lifecycle, proposal work, observability, and KPI reasoning all point to a credible product direction. The risk is that scope has grown faster than hardening.|Keep the scope, but gate new features behind a “stability budget”: every new lifecycle feature should land with regression tests, API contract notes, and operational fallback behavior.|
|Reliability 5.5/10|This is the biggest weakness. The bugs we just fixed were not cosmetic; they affected user-visible workflow state. That usually means there are still edge cases hiding in transition-heavy paths.|Build out lifecycle truth tables and test them end-to-end. Prioritize invariants such as “failed submission cannot remain submitted” and “closed clarification cannot remain active.”|
|Developer experience 5.5/10|The repo is workable, but not smooth. Test setup needed manual venv intervention, there is mixed repo noise, and naming/organization is uneven in places. That slows onboarding and raises the chance of accidental mistakes.|Add a single bootstrap path for local setup, pin test dependencies, document the happy path, and remove or isolate generated/debug artifacts from the main repo surface.|
|Test discipline 6.5/10|Better than many repos at this stage because tests already exist in the right areas. The gap is that some important lifecycle regressions were still missing, which let real logic bugs survive.|Keep expanding tests around workflow transitions, not just route existence. Favor regression tests that encode business behavior over broad but shallow coverage.|

If you want, I can turn this into a sharper 8/10 plan with prioritized actions for the next 2 sprints.


OPENCODE:

## Potential Bugs Found (23 total)

### High Severity

|Issue|Location|
|---|---|
|**Hardcoded localhost URLs**|`frontend/src/pages/ProposalEditor.tsx:61,148,220,232`, `TaskManager.tsx:69,93,131,151-152,164` - Will fail in production|

### Medium Severity

|Issue|Location|
|---|---|
|**Silent error swallowing**|`TaskManager.tsx:172` - Empty `catch (e) {}` hides bugs|
|**Silent DB migration failures**|`db/database.py:53` - Errors ignored with `pass`|
|**Resource leak**|`services/chat.py:181-182`, `api/onlyoffice.py:93-94` - MinIO response not properly closed|
|**Race condition**|`ObservabilityKPI.tsx:361-392` - `cancelled` flag checked too late|
|**Empty sequence crash**|`kpi-reason-engine/app/analytics.py:1197,1231` - `min()` on empty list|
|**Type safety bypass**|Multiple files - `(import.meta as any).env`|
|**No rate limiting on OTP**|`api/auth.py:166-197` - 5 attempts/minute on verification|

### Low Severity

|Issue|Location|
|---|---|
|**Duplicate `db.refresh()`**|`api/auth.py:192` - Wasted query|
|**Deprecated `get_event_loop()`**|`api/auth.py:139` - Python 3.10+ warning|
|**Global Redis client**|`db/redis.py:9` - No shutdown cleanup|
|**In-memory cache growth**|`api/client.ts:254-255` - Maps grow indefinitely|

Want me to fix any of these bugs?

KIRO:

Faccio un'analisi approfondita del codebase per trovare potenziali bug.


Invoked Context Gatherer
Using context-gatherer to do a thorough codebase analysis and identify all relevant files with potential bugs before diving into specifics.
Now let me provide the comprehensive analysis:

Ora leggo i file chiave per verificare i bug più critici con i miei occhi:

Analyzed code

backend/app/api/auth.py

backend/app/tasks.py

backend/app/rag/engine.py

backend/app/rag/engine.py

backend/app/api/auth.py

backend/app/api/auth.py

backend/app/rag/dense_retriever.py

backend/app/rag/engine.py

main.py

backend/app/rag/dense_retriever.py

frontend/src/api/client.ts

frontend/src/api/client.ts

backend/app/tasks.py
Ho ora una visione chiara e verificata dei bug reali. Ecco l'analisi completa con solo i bug confermati dal codice sorgente:

Bug confermati nel codebase
CRITICI
1. generate_proposal_section_task chiama un metodo inesistente 
tasks.py
 riga 75:

result = await engine.generate(...)  # ❌ HybridRAGEngine non ha metodo .generate()
Il metodo si chiama .query() e accetta un RAGQuery object, non keyword args. Questo task fallisce sempre al runtime.

2. double await db.refresh(user) in register 
auth.py
 riga 193-194:

await db.refresh(user)
await db.refresh(user)  # ❌ doppio refresh inutile, round-trip extra al DB
3. RAG engine inizializzato in background senza error handling 
main.py
 riga 63:

asyncio.create_task(app.state.rag_engine.initialize())
Se l'inizializzazione fallisce, l'errore viene silenziosamente inghiottito. L'app parte con _initialized = False e ogni query RAG lancia RuntimeError senza log chiaro.

4. _ensure_collection è async ma usa solo metodi sync di Qdrant 
dense_retriever.py
 righe 55-68:

async def _ensure_collection(self, name: str):
    collections = self.client.get_collections().collections  # sync
    self.client.create_collection(...)  # sync
Dichiarata async ma non fa nulla di asincrono — non è un crash ma è fuorviante e blocca l'event loop durante le chiamate I/O di rete.

ALTI
5. verify_otp non gestisce più OTP token per lo stesso utente 
auth.py
 riga 211:

result = await db.execute(select(OTPToken).where(OTPToken.user_id == user.id))
otp_record = result.scalar_one_or_none()  # ❌ se esistono 2 token → eccezione MultipleResultsFound
Se un utente richiede l'OTP due volte (senza che il primo scada), ci sono 2 record e scalar_one_or_none() lancia eccezione. Il vecchio token non viene mai cancellato in register.

6. export_proposal_pdf_task — XSS via Jinja2 |safe 
tasks.py
 riga 140:

<p>{{ section.content|safe }}</p>
Il contenuto delle sezioni viene renderizzato senza escaping nel PDF. Se il contenuto proviene da input utente, è un vettore XSS nel documento generato.

7. cleanup_expired_otp usa datetime.utcnow() naive vs timezone-aware 
tasks.py
 riga 196:

delete(OTPToken).where(OTPToken.expires_at < datetime.utcnow())
Se OTPToken.expires_at è timezone-aware (come in auth.py dove si usa datetime.now(timezone.utc)), il confronto con un datetime naive può fallire o dare risultati errati su PostgreSQL.

8. get_async_session() crea un nuovo engine ad ogni chiamata 
tasks.py
 riga 22-25:

def get_async_session():
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)  # ❌ nuovo engine ogni volta
Ogni task Celery crea un nuovo connection pool. Con molti task concorrenti si esauriscono le connessioni al DB.

MEDI
9. resolveTenderChatContext — race condition nella cache 
client.ts
 riga 284: la promise viene salvata in cache, ma se due chiamate arrivano quasi simultaneamente prima che la prima risolva, entrambe creano una nuova promise sovrascrivendo la precedente. Il .catch poi non trova cached?.promise === promise e non pulisce correttamente.

10. Redis client creato senza timeout 
redis.py
:

redis_client = redis.from_url(settings.redis_url, decode_responses=True)
# ❌ nessun socket_timeout, connection_timeout
Se Redis è irraggiungibile, le operazioni pendono indefinitamente.

11. send_otp_email è async ma chiama _send_sync_email in un thread executor non gestito 
auth.py
 riga 111: se _send_sync_email lancia eccezione SMTP, l'utente è già registrato nel DB ma non riceve l'OTP — account bloccato senza possibilità di recovery automatico.

SICUREZZA
12. User enumeration in verify_otp

if not user:
    raise HTTPException(status_code=400, detail="User not found")  # ❌ rivela se l'email esiste
Risposta diversa per email inesistente vs OTP errato permette di enumerare gli utenti registrati.

13. admin_password con default vuoto 
config.py
:

admin_password: str = ""
Se ADMIN_PASSWORD non è settata, l'admin viene creato con password vuota e hash_password("") è un hash valido.

I bug più urgenti da fixare sono nell'ordine: #1 (task che crashano sempre), #5 (MultipleResultsFound in produzione), #3 (RAG silenziosamente rotto), #8 (connection pool exhaustion), #13 (admin senza password).


NEMOTROM 3 SUPER:

# 

analizza in code base e cerca i potenziali bug

my-output.md

1 passaggio completato

Ho trovato diversi punti potenzialmente **fragili** o fonte di bug nella codebase che mi hai passato, soprattutto nell’area workflow operativo, KPI/eventi e integrazione OnlyOffice.​

## Possibili bug logici nel workflow operativo

- `derivecontributionstatus`: se `assignedto` è `None` e `sectionstatus` è `INPROGRESS`, il codice ritorna `OPEN` e non c’è nessun percorso che riporti a `REQUESTED` in assenza di assegnatario. Rischio: stato incoerente per contributi “in lavorazione” ma non assegnati.​
    
- `buildsectiontransitionplan`:
    
    - Quando da `INPROGRESS` si passa direttamente ad `APPROVED` viene forzata la creazione di una review completata con outcome `approved`, anche se non esiste nessun passo esplicito di review; questo potrebbe gonfiare gli eventi di review e confondere i KPI.​
        
    - `cancelopenrequests` viene chiamato solo se `assignmentchanged` e `previousassignedto is not None`; se un contributo nasce senza assegnatario e poi viene assegnato, le eventuali richieste pregresse non vengono mai chiuse.​
        

## Incongruenze/eventi duplicati o mancanti

- In `syncsectionoperationalworkflow` si costruisce un `plan` e poi si invocano in sequenza `ensurerequestforassignment`, `marklatestrequestreceived`, `ensureopenreview`, `completereview`, `ensureopenrework`, ecc.; la combinazione di flag può generare sequenze di eventi non intuitive (es. review creata e subito completata nello stesso tick, con emissione multipla di eventi per lo stesso stato).​
    
- In `completereview` si emettono sempre sia `contributionreviewcompleted` sia un evento `reviewapproved` o `reviewchangesrequested`, di fatto duplicando l’informazione outcome per i consumer.​
    
- In `resolveopenreworks` tutti i rework aperti vengono marcati come `RESOLVED` con note di default, anche se erano già parzialmente compilati; override silenzioso di informazioni distribuite.​
    

## Edge case su date e timezone

- Utility `asutc`, `datetimetoiso`, `durationhours`: se un datetime naïve arriva già in UTC ma con interpretazione diversa lato client, lo forzi a UTC senza conversione e i calcoli di durata possono risultare sballati (lateness/SLT, response time, ecc.).​
    
- In `buildcontributionreceivedeventpayload` e funzioni simili, se `requestedat` o `responsereceivedat` sono `None` ritorni `None` per `durationhours` ma continui a esporre altri campi di tempo; consumer che assumono `responseTimeHours` sempre presente potrebbero rompersi.​
    

## Potenziali bug su OnlyOffice e MinIO

- `servedocument`: se i metadati in Redis mancano o sono corrotti, fai fallback a `objectname = dockey` e se il file non esiste logghi un warning e ritorni `404 Document not found`; questo è ok, ma non c’è alcun backoff o tentativo di rebuild, e l’errore si manifesta come “file mancante” anziché “sessione scaduta/corrotta”, che rende il debugging lato client più difficile.​
    
- `onlyofficecallback`: gestisce sia GET che POST; nel caso POST senza `payload` ritorni comunque `error: 0` (successo) invece di segnalare errore, il che può nascondere chiamate malformate del Document Server.​
    

## Possibili bug di mapping / serializzazione

- `buildtendersyncpayload` ordina sezioni e requisiti per `order`/`id`, ma `selectprimaryproposal` sceglie il proposal usando `version`, `createdat` e `id`; se hai proposals con `createdat` `None` o versioni non coerenti, il “primary” può cambiare in modo non deterministico causando salti strani nello snapshot KPI.​
    
- `tendertoresponse`: `lifecyclemetadata` viene estratto da `tender.metadatajson.get("lifecycle")`; se `metadatajson` non è un dict ma una stringa JSON (per improvviso cambiamento di schema), la `.get` lancerà, rompendo l’endpoint per tutte le gare con metadati vecchi.​
    

## API e stati HTTP

- Nelle route di gestione chiarimenti (`drafttenderclarificationresponse`, `submittenderclarificationresponse`, `closetenderclarification`) il caso “clarification non trovata” usa `404` anche quando il tender esiste ma il record è stato cancellato o non appartiene a quel tender; logicamente sarebbe più vicino a `404 Clarification not found` su una subrisorsa, ma attento a non confondere col caso “tender non accessibile” che è anch’esso 404: lato client è impossibile distinguere permesso mancante da record assente.​
    

## Suggerimento per passo successivo

Per andare più in profondità, possiamo concentrarci su una macro-area e fare una revisione riga per riga (es. solo `operationalworkflow.py` + relativi test) proponendo patch concrete. Quale parte preferisci analizzare per prima?

Preparato usando Nemotron 3 Super

si vai in profondità

1 passaggio completato

Vado in profondità sull’**operational workflow** (business logic, stati, eventi KPI) usando il codice reale e il tuo bug report già generato.​

## derive_contribution_status: stati incoerenti

Funzione (rimappata dai nomi snake-case):​

python

`def derive_contribution_status(     *,    section_status: SectionStatus,    assigned_to: int | None,    has_open_rework: bool, ) -> ContributionUnitStatus:     if has_open_rework:        return ContributionUnitStatus.REWORK    if section_status == SectionStatus.APPROVED:        return ContributionUnitStatus.COMPLETED    if section_status == SectionStatus.IN_REVIEW:        return ContributionUnitStatus.IN_REVIEW    if assigned_to is not None and section_status == SectionStatus.IN_PROGRESS:        return ContributionUnitStatus.RECEIVED    if assigned_to is not None:        return ContributionUnitStatus.REQUESTED    return ContributionUnitStatus.OPEN`

Bug/edge case:​

- Sezione `IN_PROGRESS` ma `assigned_to is None` → ritorna `OPEN`. In UI vedrai “sezione in lavorazione” ma contribution “open”, rompendo metriche su “lavoro in corso”.​
    
- Nessun modo di distinguere “TO_DO ma già assegnato” (REQUESTED) da “TO_DO non assegnato” (OPEN) se qualcuno sbaglia a settare status/owner; la funzione è fortemente dipendente da combinazioni coerenti che il resto del codice **non** garantisce.​
    

Fix suggerito:

- Se `section_status == IN_PROGRESS` e non c’è assegnatario, forzare uno stato più esplicito (es. BLOCKED) o almeno loggare errore e mantenere `OPEN` ma con metrica separata.
    
- Valutare esplicitamente `SectionStatus.TODO` quando `assigned_to is not None` per togliere ambiguità:
    

python

`if section_status == SectionStatus.TODO:     return ContributionUnitStatus.REQUESTED if assigned_to is not None else ContributionUnitStatus.OPEN`

## build_section_transition_plan: “piano” troppo aggressivo

Struttura (estratta dai test e dal file):​

python

`@dataclass(slots=True) class SectionTransitionPlan:     cancel_open_requests: bool = False    ensure_request: bool = False    mark_request_received: bool = False    start_review: bool = False    complete_review: bool = False    review_outcome: str | None = None    open_rework: bool = False    resolve_rework: bool = False`

Logica chiave:​

python

`assignment_changed = previous_assigned_to != new_assigned_to if assignment_changed and previous_assigned_to is not None:     plan.cancel_open_requests = True if assignment_changed and new_assigned_to is not None and new_status in (TODO, IN_PROGRESS):     plan.ensure_request = True if new_status == IN_REVIEW and previous_status != IN_REVIEW:     plan.mark_request_received = True    plan.start_review = True    plan.resolve_rework = True if new_status == APPROVED and previous_status != APPROVED:     plan.mark_request_received = True    plan.resolve_rework = True    plan.complete_review = True    plan.review_outcome = "approved"    if previous_status != IN_REVIEW:        plan.start_review = True elif previous_status == IN_REVIEW and new_status in (TODO, IN_PROGRESS):     plan.complete_review = True    plan.review_outcome = "changes_requested"    plan.open_rework = True`

Problemi:​

1. **Cambio assegnatario da None → X non chiude richieste pregresse**
    
    - `cancel_open_requests` scatta solo se `previous_assigned_to is not None`. Se per qualunque motivo esistono `ContributionRequest` aperti su una section non ancora assegnata e poi la assegni, non vengono chiusi.​
        
    - In `ensure_request_for_assignment` poi ti ritrovi potenzialmente più richieste aperte per lo stesso `assigned_to` se lo stato gira più volte TO_DO/IN_PROGRESS.​
        
2. **APPROVED crea review “fantasma”**
    
    - Da `IN_PROGRESS -> APPROVED`: `start_review = True`, `complete_review = True`, `review_outcome = "approved"`, `mark_request_received = True`, `resolve_rework = True`.​
        
    - In `sync_section_operational_workflow` questo genera in coda: `ensure_open_review` (se necessario) + `complete_review` + `resolve_open_reworks`, di fatto creando un ciclo di review completo in un singolo tick, anche se nessuno ha mai messo la section in `IN_REVIEW`.​
        
    - Impatto KPI: sovrastima “review completate” e “tempo medio di review” (spesso zero).​
        
3. **Leaving review sempre “changes_requested”**
    
    - Da `IN_REVIEW` a `IN_PROGRESS`/`TODO` imposta sempre `review_outcome = "changes_requested"` e `open_rework = True`, anche se il caso d’uso potrebbe includere “review annullata” o “review fallback senza richiesta esplicita di rework”.​
        

Fix suggeriti:

- `cancel_open_requests` dovrebbe attivarsi su **ogni** cambio assegnatario, incluso `None → X`, e forse anche su cambio status bloccante.
    
- Limitare il caso “APPROVED fa partire review implicita” (es. permetterlo solo se c’è un feature flag o se non ci sono review storiche), altrimenti richiedere sempre `IN_REVIEW` prima di `APPROVED`.
    
- Aggiungere branch per distinguere “review chiusa senza rework” (p.es. `review_outcome = "cancelled"`) da “changes_requested`.
    

## sync_section_operational_workflow: combinatoria di eventi

Schema sintetico (ribattezzato dai nomi in snake-case):​

python

`async def sync_section_operational_workflow(     db: AsyncSession,    *,    tender_id: int,    section: ProposalSection,    actor_id: int | None,    previous_status: SectionStatus,    previous_assigned_to: int | None, ) -> list[tuple[str, dict]]:     contribution = await ensure_contribution_for_section(...)    plan = build_section_transition_plan(...)    occurred_at = now_utc()    events: list[tuple[str, dict]] = []     if plan.cancel_open_requests and section.assigned_to != previous_assigned_to:        await cancel_open_requests(db, contribution=contribution, keep_user_id=section.assigned_to)     if plan.ensure_request and section.assigned_to is not None:        events.extend(await ensure_request_for_assignment(...))     if plan.mark_request_received:        events.extend(await mark_latest_request_received(...))     if plan.resolve_rework:        events.extend(await resolve_open_reworks(...))     if plan.start_review:        review, created = await ensure_open_review(...)        if created:            events.append(("contribution_review_started", build_review_cycle_started_event_payload(...)))     if plan.complete_review and plan.review_outcome:        events.extend(await complete_review(..., outcome=plan.review_outcome))     if plan.open_rework:        events.extend(await ensure_open_rework(...))     contribution.status = derive_contribution_status(        section_status=section.status or SectionStatus.TODO,        assigned_to=section.assigned_to,        has_open_rework=bool(await load_open_reworks(db, contribution_id=contribution.id)),    )    await db.flush()    return events`

Problemi:​

1. **Sequenza “APPROVED” genera doppia emissione eventi review**
    
    - Caso IN_PROGRESS → APPROVED:
        
        - `ensure_open_review` (crea review aperta, emette `contribution_review_started` se `created=True`).
            
        - `complete_review` la chiude subito, emettendo a sua volta `contribution_review_completed` + `review_approved`.​
            
    - Questo rende la timeline review “start & complete nello stesso istante” per tutti i casi “approvazione diretta”, sporcando indicatori come `reviewDurationHours` e “lead time to approval”.
        
2. **resolve_open_reworks sempre prima di start_review**
    
    - In `plan.entering_review` hai `resolve_rework = True` + `start_review = True`, quindi qualsiasi rework aperto viene automaticamente marcato `RESOLVED` (con note di default) semplicemente entrando in `IN_REVIEW`, anche se nessuno ha effettivamente consegnato il rework.​
        
    - KPI di rework vengono falsati (tutti risolti all’ingresso in review, mai al vero completamento).
        
3. **Derivazione finale di status potenzialmente inconsistente con eventi appena emessi**
    
    - Dopo `complete_review` puoi aver portato `ContributionUnitStatus` a COMPLETED all’interno di `complete_review`, ma alla fine della funzione sovrascrivi comunque con il risultato di `derive_contribution_status`. Se lì la combinazione (status sezione / assigned_to / has_open_rework) non è coerente, puoi riportare lo stato indietro.​
        

Fix suggeriti:

- Spostare `resolve_open_reworks` **dopo** `complete_review` (o parametrizzare), o richiamarlo solo quando il review_outcome è `changes_requested` → `rework_resolved`, non quando entri in review.
    
- In `sync_section_operational_workflow`, usare una logica “non regressiva”:
    

python

`final_status = derive_contribution_status(...) if final_status != contribution.status:     contribution.status = final_status`

oppure fare in modo che `complete_review` non cambi lo status e lasci tutto alla derivazione finale.

## KPI Reason Engine: payload e durate

Dalla libreria eventi KPI:​

- Funzioni tipo `build_contribution_request_created_event_payload`, `build_contribution_assignment_confirmed_event_payload`, `build_contribution_review_completed_event_payload`, `build_rework_requested_event_payload`, ecc. costruiscono dict con campi come `requestedAt`, `dueAt`, `responseTimeHours`, `slaTargetHours`, `isLate`.​
    
- La funzione `_duration_hours` fa `if not start or not end: return None`, quindi molte metriche temporalmente incomplete diventano `null` ma gli eventi continuano a essere emessi.​
    

Problemi di business:​

- Con il pattern “review fantasma” e “rework auto-resolti” di cui sopra, i payload KPI conterranno tempi sempre cortissimi (a volte 0) per review e rework, rovinando medie/p95.
    
- In più, la logica di clean-up/aggiornamento (es. `mark_latest_request_received` che mette `response_received_at` se non presente) viene forzata ogni volta che il piano dice `mark_request_received`, anche se il tempo corretto sarebbe quello della prima vera risposta.​
    

Fix suggeriti:

- Introdurre nel payload un campo `isSyntheticLifecycleEvent` (o simile) quando i cambi di stato derivano da automazioni (es. `APPROVED` senza passare da `IN_REVIEW`), così il Reason Engine può escluderli da certi KPI.
    
- Rendere idempotente `mark_latest_request_received` con una policy chiara: se `response_received_at` esiste già, non toccare `response_summary`/status, per non sovrascrivere annotazioni manuali.
    

## Bug già mappati nel tuo bug_analysis.md

Nel file `resoningfromagentic/antigravity/bug_analysis.md` hai già una lista numerata di bug critici/medi (BUG-01 … BUG-18) che copre:​

- Security (SSRF anonymizer, OnlyOffice senza auth, MD5 doc_key).​
    
- Data integrity (mutable default in colonne SQLAlchemy, datetime naive vs aware, cleanup OnlyOffice con `datetime.now()` locale).​
    
- Logic errors in API (`update_proposal` che dereferenzia `proposal` prima del null-check, `update_section` con if/else identici).​
    

Quindi sul fronte “bug di business logic + KPI” l’area più scoperta rimane proprio l’**operational_workflow** che stiamo sezionando ora.

---

Se vuoi, nel prossimo passo posso proporti direttamente una patch concreta (diff) per `operational_workflow.py` che:

- ripulisce `build_section_transition_plan` e `sync_section_operational_workflow`,
    
- rende esplicite le transizioni valide,
    
- e riduce al minimo gli eventi “sintetici” per non inquinare la Reason Engine. Vuoi che ti proponga un refactor guidato da una tabella di stato (state machine esplicita) o preferisci solo fix mirati alle anomalie che ti ho evidenziato?
    

Preparato usando Nemotron 3 Super

in questa fase devi elencare tutti i problemi e possibili traccie di soluzioni non patch

1 passaggio completato

Elenco tutti i problemi che emergono dall’analisi (operational workflow + resto backend) e, per ciascuno, una possibile **traccia** di soluzione (senza patch dettagliate).​

---

## 1. derive_contribution_status: mapping troppo fragile

Problemi:​

- Sezione `IN_PROGRESS` con `assigned_to is None` → contribution `OPEN`, incoerenza semantica tra sezione “in lavorazione” e contribution “aperto generico”.
    
- Non distingue chiaramente `TODO` assegnata (`REQUESTED`) da casi limite (es. sezione `IN_REVIEW` ma senza assegnatario).
    
- Il mapping dipende da combinazioni “ideali” di `section_status` e `assigned_to` che il resto del sistema non sempre garantisce.
    

Tracce di soluzione (concettuali):

- Definire una matrice formale `(section_status, assigned_to, has_open_rework) → contribution_status` e validarla in test.​
    
- Introdurre uno stato esplicito per “IN_PROGRESS senza owner” (es. `BLOCKED`) o almeno loggare warning e tenerlo separato nei KPI.
    
- Gestire `TODO` in modo esplicito: se assegnata → `REQUESTED`, se non assegnata → `OPEN`.
    

---

## 2. build_section_transition_plan: logica di transizione troppo “magica”

Problemi:​

- `cancel_open_requests` scatta solo quando `previous_assigned_to` non è `None`; se esistono richieste aperte con `assigned_to=None` e poi assegni la sezione, non vengono chiuse.
    
- Transizione `IN_PROGRESS → APPROVED` forza un intero ciclo di review (start + complete) anche se la sezione non ha mai avuto `IN_REVIEW`, generando review “fantasma”.
    
- Uscita da `IN_REVIEW` verso `IN_PROGRESS`/`TODO` imposta sempre `review_outcome="changes_requested"` e `open_rework=True`, anche quando la review non ha realmente richiesto rework.
    
- La combinazione dei flag (start_review, complete_review, resolve_rework, open_rework) è poco leggibile e difficile da controllare in modo esaustivo.
    

Tracce di soluzione:

- Esplicitare una tabella di transizione `(previous_status, new_status)` che definisca: se ci deve essere review, se è richiesta rework, se le richieste vanno cancellate.​
    
- Separare i casi “APPROVED dopo IN_REVIEW” da “APPROVED diretto” e impedire che il secondo crei automaticamente review complete, oppure marcarle come “synthetic”.
    
- Introdurre un outcome aggiuntivo (“cancelled” / “no_changes”) per quando esci da review senza rework.
    
- Normalizzare la logica `assignment_changed`: ogni cambio owner può chiudere richieste non più valide, indipendentemente dal fatto che `previous_assigned_to` fosse `None` o meno.
    

---

## 3. sync_section_operational_workflow: ordine effetti/eventi e stato finale

Problemi:​

- Sequenza “APPROVED” con `start_review + complete_review` nel medesimo ciclo produce eventi `review_started` e `review_completed` a distanza temporale minima, falsando i KPI di durata review.
    
- `resolve_open_reworks` viene eseguito entrando in `IN_REVIEW`, quindi tutti i rework aperti risultano “risolti” anche se la sezione non è stata realmente lavorata.
    
- Alla fine, `contribution.status` viene sempre ricalcolato via `derive_contribution_status` anche se funzioni come `complete_review` hanno già cambiato lo stato; rischio di inconsistenza o regressione.
    
- L’ordine in cui vengono chiamate `cancel_open_requests`, `ensure_request_for_assignment`, `mark_latest_request_received`, `ensure_open_review`, `complete_review`, `ensure_open_rework`, `resolve_open_reworks` è complesso e poco auto‑esplicativo.
    

Tracce di soluzione:

- Definire una sequenza stabile: prima mutazioni (assignment, richieste, review, rework), poi **un solo punto** di derivazione finale dello stato contribution.​
    
- Non fare cambiare `ContributionUnitStatus` dentro `complete_review`/`ensure_open_rework`, ma lasciare che lo stato sia sempre derivato alla fine.
    
- Rinviare `resolve_open_reworks` al momento del completamento review (e solo con outcome “approved”), invece che all’ingresso in review.
    
- Introdurre flag per distinguere eventi “sintetici” (generate automaticamente per far quadrare lo schema) da eventi derivanti da azioni utente.
    

---

## 4. Eventi KPI: distorsione di metriche e incompletezza dati

Problemi:​

- Review virtuali e rework auto-risolti generano tempi artificialmente brevi (anche 0) per `reviewDurationHours`, `reworkDurationHours`, `timeToFirstResponse`.
    
- `_duration_hours` restituisce `None` se uno degli estremi manca; molti eventi così risultano “parziali” e possono rompere aggregazioni se consumer si aspettano sempre un valore numerico.
    
- Funzioni come `mark_latest_request_received` scrivono `response_received_at` e `responsesummary` con default generici (“Auto-received from proposal section workflow”), sovrascrivendo potenzialmente annotazioni manuali.
    

Tracce di soluzione:

- Definire uno schema di eventi con campi opzionali **chiaramente documentati** (quali possono essere null) e aggiornare il Reason Engine per gestire in sicurezza i `null`.
    
- Marcare negli eventi una proprietà tipo `is_automated` / `source="section-workflow"` per distinguere misurazioni “organiche” da quelle derivanti da automazioni.​
    
- Rendere idempotente `mark_latest_request_received`: se esiste già `response_received_at`, non sovrascrivere né tempo né summary, o farlo solo se provengono da un flusso “meno affidabile”.
    
- Introdurre test golden dataset che coprano casi borderline (approve diretto, rework multipli, reassignment) e verifichino che le metriche aggregate non risultino distorte.
    

---

## 5. OnlyOffice: superfici di rischio e incoerenze

Problemi:​

- Endpoint `/files/{doc_key}` senza autenticazione: chiunque conosca il `doc_key` può scaricare file, e i `doc_key` sono MD5 su input prevedibile.​
    
- Callback OnlyOffice non valida il JWT del payload, accettando update non autenticati.
    
- Cleanup documenti usa `datetime.now()` rispetto a `last_modified` (UTC) causando possibili cancellazioni anticipate o ritardate.
    
- Error handling del callback: in alcuni casi risponde `{"error": 0}` anche quando il payload è invalido o mancano campi essenziali.
    

Tracce di soluzione:

- Richiedere sempre `get_current_user` o almeno un token di servizio per `/files/{doc_key}`; opzionalmente verificare che l’utente abbia accesso a tender/proposal associati al documento.
    
- Verificare il token JWT nel callback con lo stesso secret usato per generarlo; rifiutare richieste con token mancante/invalid.
    
- Uniformare tutto a `datetime.now(timezone.utc)` e confronti tra aware datetime; spiegitarlo anche nei commenti e nella documentazione tecnica.​
    
- Restituire `error != 0` quando il payload è malformato, in modo che il Document Server possa reagire correttamente.
    

---

## 6. Sicurezza generale backend: bug_analysis esistenti

Dal tuo `bug_analysis.md` risultano già diversi problemi che vale la pena tracciare chiaramente:​

- Mancato commit esplicito in `delete_tender` → cancellazione “silenziosa” se qualcosa fallisce dopo `db.delete` ma prima del commit implicito; nessun evento KPI né cleanup storage MinIO.​
    
- Uso di `|safe` in template PDF senza sanitizzazione del contenuto sezione → rischio XSS lato generazione PDF.​
    
- Proxy anonymizer che forwarda a `X-Target-Url` senza whitelist/validazione → SSRF verso servizi interni o metadata cloud.​
    
- Uso di MD5 per doc_key e Docker socket montato nel backend → superfici di attacco per data leak ed escalation privilegi.​
    

Tracce di soluzione:

- Rendere sistematico l’uso di `db.commit()` e l’emissione di eventi (inclusi cleanup e KPI) sulle operazioni distruttive (delete tender, delete proposal, ecc.).
    
- Sanitizzare HTML di input o rimuovere `|safe` dove non strettamente indispensabile, usando librerie di sanitizzazione lato server.​
    
- Limitare anonymizer a domini/host configurati, oppure rimuoverlo da percorsi di produzione.
    
- Eliminare il mount del Docker socket o isolarlo in un servizio amministrativo non esposto.
    

---

## 7. API / DTO: coerenza dei contratti e validazioni

Problemi:​

- Modelli Pydantic per email (registrazione/login) usano `str` senza `EmailStr`, nessuna validazione del formato email.
    
- `update_proposal` accede a `proposal.status` prima di verificare che `proposal` non sia `None`; l’eccezione generata è un generico `AttributeError` invece di una HTTPException controllata.
    
- `update_section` ha un ramo `if key == "content"` ma esegue lo stesso identico `setattr` di `else`; probabile mancanza di conversione/normalizzazione contenuto.
    

Tracce di soluzione:

- Allineare la definizione di DTO a tipi Pydantic più specifici (EmailStr, constr, ecc.) per avere validazione server-side consistente.​
    
- In tutti i path “get X then muta X”, spostare il null-check subito dopo la query e prima di qualsiasi accesso ai campi, con test dedicati.
    
- Decidere una rappresentazione canonica del contenuto sezione (plain text vs JSON tiptap/OnlyOffice) e centralizzare la conversione in helper riusabili.
    

---

## 8. Modello dati: mutable default e timezone

Problemi:​

- Colonne `ARRAY` e `JSONB` con `default=[]` e `default={}` usano oggetti Python mutabili condivisi tra istanze, con rischio di side effects invisibili.
    
- Uso estensivo di `datetime.utcnow()` su campi `DateTime(timezone=True)` genera mismatch naive/aware e può creare warning o errori al confronto.
    

Tracce di soluzione:

- Sostituire i default mutabili con callables (`default=list`, `default=dict`) o usare `server_default` per casi semplici.​
    
- Uniformare tutti i timestamp di default/aggiornamento a `datetime.now(timezone.utc)` o, in alternativa, usare `func.now()` lato database per ridurre la divergenza.
    

---

Se per il prossimo passo vuoi, posso prendere una sola area (ad esempio solo `operational_workflow.py`) e costruire:

- una tabella completa delle transizioni `SectionStatus` e relativi effetti,
    
- seguita da uno “scheletro” di refactor a state machine (solo in pseudo‑codice), sempre senza ancora passare a patch concrete.


GEMINI 3.1 PRO:

Alziamo il livello dell'analisi. Lasciamo da parte per un momento i bug di sintassi (come le f-string o le validazioni mancanti) e guardiamo il sistema con le lenti dell'**architettura distribuita**, della **concorrenza** e della **consistenza di stato**, che sono le aree dove si nascondono i bug più letali in produzione.

Ecco un'analisi profonda dei colli di bottiglia architetturali e dei flaw logici nella codebase, con le relative tracce di mitigazione.

---

## 1. Dual-Write Problem e Perdita di Eventi KPI

**Il Problema Architetturale:**  
Nel backend, funzioni come `sync_section_operational_workflow` eseguono mutazioni sul database (Entity `ContributionUnit`, `ReviewCycle`, ecc.) e, contestualmente, accumulano in memoria una lista di tuple (es. `[("contribution_review_started", payload)]`).  
Se l'architettura corrente prevede di fare il `db.commit()` a fine richiesta HTTP e poi pubblicare questi eventi (su Redis/Kafka o via HTTP al KPI Reason Engine), siamo di fronte a un classico **Dual-Write Problem**:

- Se il commit DB fallisce, l'API va in 500. Gli eventi in memoria non partono. (OK)
    
- Se il commit DB ha successo, ma il pod backend crasha un millisecondo prima di fare il dispatch degli eventi, oppure la rete verso il Reason Engine va in timeout, **il database è aggiornato ma il Reason Engine perde per sempre l'evento**. I KPI si disallineano irreversibilmente dallo stato transazionale.
    

**Traccia di Soluzione (Pattern):**

- Implementare il **Transactional Outbox Pattern**: scrivere gli eventi in una tabella `outbox_events` all'interno della _stessa_ transazione SQL in cui si aggiornano le sezioni.
    
- Un worker asincrono (Celery o un loop interno) legge da `outbox_events`, pubblica al Reason Engine, e solo in caso di ACK positivo marca l'evento come `published`.
    

## 2. Assenza di Concurrency Control (Optimistic Locking)

**Il Problema Logico:**  
Il sistema permette l'editing collaborativo di `ProposalSection` e l'assegnazione tramite l'`operational_workflow`. Nel file `proposals.py` (API `update_section` e simili), il pattern è:

1. `SELECT` della section.
    
2. Modifica in memoria dei campi (es. status, content, assigned_to).
    
3. `UPDATE` implicito via flush/commit.  
    Non c'è alcun meccanismo di Lock (né ottimistico con `@version`, né pessimistico con `SELECT FOR UPDATE`).  
    Se il Manager A approva la sezione mentre il Manager B la riassegna o ne cambia lo stato un istante dopo (ma partendo dai dati non aggiornati), **l'ultimo che scrive vince**. L'evento di `complete_review` potrebbe partire per un utente che non è più l'assegnatario, sfociando in uno stato "ibrido" irrisolvibile.
    

**Traccia di Soluzione (Pattern):**

- Aggiungere una colonna `version (Integer)` nei modelli core (`ProposalSection`, `ContributionUnit`, `TenderRequirement`).
    
- Adottare **Optimistic Concurrency Control**: le API di update accettano la `version` in input. Se la versione sul DB nel frattempo è cambiata, il backend rifiuta con HTTP 409 (Conflict) obbligando il client a ricaricare i dati e ripetere l'azione.
    

## 3. Incoerenza tra Compliance Status e Mapping (Orphaned Requirements)

**Il Problema Logico:**  
Da `test_tender_requirement_response.py` e dai modelli si deduce che un `TenderRequirement` ha un legame verso `ProposalSection` via `proposal_section_id`.  
Cosa succede se una sezione viene cancellata o resettata?  
Nel modello, `proposal_section_id = Column(..., ondelete="SET NULL")`. Se elimino la sezione `Compliance Matrix`, il foreign key sul requisito diventa `NULL`.  
**Il bug latente:** Il campo `compliance_status` (es. `FULLY_ADDRESSED`) rimane inalterato! Avrai KPI che mostrano requisiti pienamente soddisfatti, ma che non sono mappati su nessuna sezione esistente del documento.

**Traccia di Soluzione:**

- Spostare la valutazione della "Compliance" in modo che sia computata _dinamicamente_ a partire dallo stato delle sezioni mappate, oppure:
    
- Aggiungere un Event Listener su SQLAlchemy (`after_delete` o `before_update` sulle sezioni) che forza il `compliance_status = NOT_ADDRESSED` per tutti i requisiti il cui `proposal_section_id` viene reciso.
    

## 4. RAG Pipeline: Timeout e Sezioni "Zombie" (Stuck States)

**Il Problema Architetturale:**  
Quando viene avviato un `generate_proposal_section_task` (file `tasks.py`), lo status della sezione passa verosimilmente a `IN_PROGRESS` o simili mentre Celery chiama l'LLM.  
Celery è configurato con `task_time_limit=3600` e `task_soft_time_limit=3000`.  
Se l'istanza di LLM (specialmente locale, es. LM Studio/Ollama visti nei tuoi log storici) va in crash o genera un OOM senza chiudere la connessione TCP, il task resta appeso fino al soft timeout (50 minuti). Peggio ancora, se il worker Celery muore bruscamente (es. pod eviction su Kubernetes o un kill -9), il task muore senza ripulire lo stato sul DB.  
Il risultato è una "Sezione Zombie": bloccata in generazione, senza che l'utente possa sbloccarla o riavviarla perché il sistema la crede ancora attivamente in esecuzione.

**Traccia di Soluzione:**

- Introdurre un pattern **Heartbeat / TTL** o una "Dead Letter Queue" procedurale:
    
    - La sezione salva un `generation_started_at`.
        
    - Un cron job (`celery beat`) cerca ciclicamente le sezioni in generazione da più di 10 minuti per cui non c'è più un task Celery attivo (usando le API di ispezione o verificando il fallimento) e le resetta a `FAILED` o `TODO`.
        

## 5. Security & Authorization: JWT Revocation Flow Assente

**Il Problema Logico:**  
Se un utente viene rimosso da un Tender (`deactivate_chat_member_for_tender` nel modulo chat e simili rimozioni lato RBAC), o se un Admin banna un utente in tempo reale, i token JWT che l'utente ha già nel suo browser **restano validi fino alla naturale scadenza**.  
Il backend, usando token stateless, estrarrà l'identità dell'utente ad ogni chiamata API. Se i check di accesso (`check_tender_access`) si basano su cache o sui claim del token senza ri-verificare sul database, l'utente continuerà a poter scaricare PDF dal sistema (in particolare quelli tramite OnlyOffice e `/files/` non protetti) per ore.

**Traccia di Soluzione:**

- Essendo impossibile invalidare un JWT stateless, è necessario introdurre un **Token Blacklist (DenyList)** su Redis. Quando i permessi di un utente cambiano criticamente, si inserisce il suo `user_id` o `jti` in Redis. I middleware di autenticazione fanno un check in-memory veloce su Redis (molto più rapido di una query Postgres) per respingere i token revocati.
    

## 6. OnlyOffice Document Synchronization Race

**Il Problema Logico:**  
Dal codice di `onlyoffice.py` emergono salvataggi asincroni attivati dal callback (quando l'utente chiude l'editor e il documento assume stato 2 - "Saved").  
Se l'utente chiude l'editor (innescando il trigger di OnlyOffice) ma **immediatamente** preme il pulsante "Genera PDF" o "Valuta Compliance" dall'interfaccia React di Lifecycle Control:

- Il Document Server di OnlyOffice può impiegare dai 2 ai 10 secondi per inviare il file al callback.
    
- L'utente genera l'output lavorando sui dati del database che **non contengono ancora l'ultima versione del testo**.  
    L'utente invierà una proposta mancante dell'ultimo paragrafo.
    

**Traccia di Soluzione:**

- Il backend, quando l'utente clicca "Genera" o avvia l'analisi, deve interrogare lo stato di _OnlyOffice Document Server_ (Force Save API) per accertarsi che non vi siano sessioni di editing "dirty" (pendenti) per quel `doc_key`.
    
- In alternativa, l'UI in React deve attendere un evento Server-Sent-Events (SSE) / WebSocket che notifichi `DOCUMENT_SAVED` dal backend prima di abilitare le azioni di downstream sulla sezione.
    

---

Se l'obiettivo è costruire un sistema Enterprise robusto (come immagino tu sia abituato a gestire con Spring Boot), questi sono i "buchi neri" in cui i dati perdono consistenza in produzione. Vuoi che ci concentriamo sulla risoluzione di uno di questi macro-temi (es. il refactoring verso un **Transactional Outbox** per i KPI) per blindare il passaggio dei dati al Reason Engine?

Preparato usando Gemini 3.1 Pro Thinking

voglio che me li elenchi tutti mi tracci una scenario di casistiche plausivili e traccie di soluzioni non risoluzioni completer

1 passaggio completato

Ecco la mappatura completa di tutte le vulnerabilità architetturali, logiche e di processo individuate nella codebase, strutturata in **Problema**, **Scenario Plausibile (Casistica)** e **Traccia di Soluzione** (design pattern o logica, senza implementazione).

---

## AREA 1: Architettura, Transazioni e Consistenza Dati

## 1. Il problema del "Dual-Write" (DB transazionale vs Eventi KPI)

- **Problema**: L'emissione degli eventi verso il _Reason Engine_ è disaccoppiata dal commit sul database Postgres.
    
- **Scenario Plausibile**: Un manager approva una sezione (HTTP request). Il backend scrive su Postgres, ma un istante prima di inviare l'evento HTTP/Kafka al Reason Engine, il container va in OOM (Out Of Memory) o la rete subisce un micro-distacco. Il DB registra l'approvazione, ma il Reason Engine perde per sempre l'evento. I KPI (es. _lead time to approval_) si corrompono irreversibilmente.
    
- **Traccia di Soluzione**: Adottare il **Transactional Outbox Pattern**. Scrivere il payload dell'evento in una tabella `outbox_events` all'interno della stessa transazione SQL dell'aggiornamento della sezione. Un worker asincrono leggerà poi l'outbox garantendo la consegna _at-least-once_.
    

## 2. Assenza di Concurrency Control (Race Conditions sulle Sezioni)

- **Problema**: L'aggiornamento delle `ProposalSection` avviene con un pattern di read-modify-write senza lock (né ottimistico né pessimistico).
    
- **Scenario Plausibile**: L'utente A (Tender Manager) apre la maschera per assegnare la sezione a Mario. Contemporaneamente l'utente B (Revisore) decide di marcare la sezione come "Approved". Entrambi partono dalla stessa versione dei dati. L'ultimo che preme "Salva" sovrascrive silenziosamente il lavoro dell'altro, portando il sistema in uno stato ibrido (es. approvata ma riassegnata come se fosse da fare).
    
- **Traccia di Soluzione**: Introdurre **Optimistic Locking**. Aggiungere una colonna `version` (interger) sul DB. Ogni operazione di update deve fallire (HTTP 409 Conflict) se la `version` fornita dal client non combacia con quella su DB, forzando un refresh dell'interfaccia.
    

## 3. Dati Orfani tra Requisiti (Compliance) e Sezioni

- **Problema**: `TenderRequirement` ha una foreign key su `ProposalSection` impostata a `ON DELETE SET NULL`, ma lo stato di compliance (es. `FULLY_ADDRESSED`) è salvato come stringa statica sul requisito.
    
- **Scenario Plausibile**: Un requisito tecnico viene marcato come `FULLY_ADDRESSED` mappandolo alla sezione "Matrice di Sicurezza". Un utente successivamente elimina l'intera sezione "Matrice di Sicurezza". Il legame scompare (diventa NULL), ma il requisito continua a figurare magicamente come "soddisfatto" nei report della gara.
    
- **Traccia di Soluzione**: Adottare eventi di dominio (SQLAlchemy listeners o logica applicativa) in fase di cancellazione sezione per scatenare in cascata il downgrade della compliance a `NOT_ADDRESSED`, oppure calcolare la compliance dinamicamente a runtime a partire dalle sezioni collegate.
    

## 4. Fallimento Silenzioso nelle Operazioni Distruttive

- **Problema**: In funzioni come `delete_tender`, manca un `db.commit()` esplicito ed eventuale rollback coordinato con i sistemi esterni (es. file su MinIO).
    
- **Scenario Plausibile**: Viene invocata l'eliminazione di una gara. I file associati vengono rimossi dallo storage object. Successivamente, prima che avvenga l'auto-commit di fine richiesta, un'eccezione interrompe il flusso. Risultato: il DB mantiene la gara, ma i suoi documenti sono spariti.
    
- **Traccia di Soluzione**: Implementare il pattern **Unit of Work** o un blocco `try/except` esplicito con rollback. Se si coordinano sistemi non transazionali (MinIO e DB), utilizzare meccanismi di soft-delete sul DB e cron job successivi per la rimozione asincrona dei file (Eventual Consistency).
    

---

## AREA 2: Integrazione OnlyOffice & Asincronicità

## 5. Race Condition di Salvataggio Documenti

- **Problema**: Il salvataggio del testo da OnlyOffice al DB avviene tramite un webhook/callback asincrono invocato dal Document Server circa 2-10 secondi dopo la chiusura del documento.
    
- **Scenario Plausibile**: Il Bid Manager finisce di scrivere l'ultimo paragrafo cruciale, chiude l'editor e _immediatamente_ clicca "Genera PDF Finale". Il backend legge il DB e crea il PDF mancando l'ultimo paragrafo, poiché il callback di OnlyOffice non è ancora arrivato a destinazione.
    
- **Traccia di Soluzione**: Introdurre un trigger di "Force Save" (API esposta da OnlyOffice) prima di qualsiasi operazione di esportazione/RAG, oppure notificare al client via WebSocket/SSE l'avvenuto update del DB, inibendo il pulsante "Genera PDF" finché il salvataggio non è completato.
    

## 6. Task Zombie e Timeout RAG

- **Problema**: I task Celery (es. generazione tramite LLM locale/Ollama) hanno limiti di tempo hard-coded lunghi (es. 50 minuti), e non ci sono meccanismi di recovery per task abortiti.
    
- **Scenario Plausibile**: Durante la generazione AI di una sezione complessa, il container dell'LLM crasha (OOM). Il task Celery si blocca, o il pod Celery stesso viene riavviato dal cluster. L'interfaccia utente rimarrà bloccata perennemente su "Generazione in corso", senza possibilità di sbloccare o ritentare l'azione.
    
- **Traccia di Soluzione**: Modello a stati espliciti con **Heartbeat** o timeout breve. Implementare un job di "reconciliation" (Sweep) che cerca transizioni bloccate da troppo tempo e le riporta a uno stato `FAILED` o `TODO`.
    

---

## AREA 3: Operational Workflow e Logica degli Stati

## 7. Generazione Automatica di Eventi Sintetici (Review Fantasma)

- **Problema**: La logica di transizione forza il passaggio attraverso la fase di "Review" anche se si salta direttamente ad "Approvato".
    
- **Scenario Plausibile**: Una sezione passa da `IN_PROGRESS` ad `APPROVED` con un singolo click del manager. Il codice genera istantaneamente una `review_started` e subito dopo una `review_completed`. I KPI del Reason Engine registreranno un tempo di revisione di 0.001 secondi, inquinando drasticamente le medie (SLT, LTA) della dashboard dirigenziale.
    
- **Traccia di Soluzione**: Separare i rami di business logic. Le approvazioni dirette devono generare un evento differenziato (es. `direct_approval_registered`), permettendo al Reason Engine di escluderle dalle metriche di durata "Review".
    

## 8. Fragilità della Derivazione di Stato (`derive_contribution_status`)

- **Problema**: Lo stato della "Contribution" (il contenitore concettuale del lavoro) è calcolato incrociando lo stato della sezione, la presenza di assegnatari e i rework aperti. Manca una gestione esplicita degli stati impossibili.
    
- **Scenario Plausibile**: Una sezione in `IN_PROGRESS` assegnata a "Giulia". Giulia viene rimossa dal team e l'assegnatario diventa `None`. Lo status della sezione resta `IN_PROGRESS`, ma la formula lo ricalcola silenziosamente a `OPEN`. Il task sparisce dai radar "in lavorazione" e non è tracciato come bloccato.
    
- **Traccia di Soluzione**: Costruire una **State Machine (FSM)** stretta. Non derivare ciecamente lo stato ad ogni giro, ma definire transizioni permesse (es. non si può togliere l'assegnatario se lo stato è `IN_PROGRESS`, si deve prima mettere in `TODO` o `BLOCKED`).
    

---

## AREA 4: Sicurezza, Permessi e Network (Vulnerabilità architetturali)

## 9. Impossibilità di Revocare i JWT Esistenti

- **Problema**: L'autenticazione tramite JWT è puramente stateless.
    
- **Scenario Plausibile**: Un consulente esterno lavora a un bando riservato. Alle 14:00 viene rimosso dai permessi di quel Tender. Tuttavia, il suo token JWT scade alle 18:00. Fino a quell'ora, può usare script o Postman per chiamare liberamente l'API `/files/` e scaricare documenti a cui non ha più diritto, bypassando i controlli dell'interfaccia.
    
- **Traccia di Soluzione**: Introdurre un meccanismo ibrido con **Redis DenyList**. Ad ogni cambio critico di permessi (o logout forzato), il JTI (ID univoco del token) o l'ID utente finisce in Redis. Il middleware API farà un check ultra-veloce contro Redis per invalidare la sessione in tempo reale.
    

## 10. SSRF (Server-Side Request Forgery) nel Gateway Anonymizer

- **Problema**: Il microservizio Anonymizer (visto nel file proxy) usa un header `x-target-url` fornito dal client per effettuare le chiamate HTTP interne senza validarlo.
    
- **Scenario Plausibile**: Un attaccante intercetta il traffico e invia una richiesta all'anonymizer chiedendo di reindirizzarla verso `http://169.254.169.254/latest/meta-data/` (se su AWS) o verso `http://localhost:5432`. Il proxy ubbidirà, recuperando variabili d'ambiente, credenziali cloud, o attaccando servizi interni non esposti al web.
    
- **Traccia di Soluzione**: Mantenere una rigida **AllowList (Whitelist)** di domini e porte verso cui il proxy è autorizzato a inoltrare (es. solo endpoint LLM noti o URL approvati a DB).
    

## 11. Endpoint Documenti Non Protetti ed Esiltrabili (ID Prevedibili)

- **Problema**: La risorsa che serve i documenti ad OnlyOffice e al frontend (`/files/{doc_key}`) non valida il JWT dell'utente, e genera le key con MD5 prevedibili (es. timestamp + ID).
    
- **Scenario Plausibile**: Conoscendo l'ID di un proposal, un attaccante scrive uno script Python che calcola gli MD5 per gli ultimi 10.000 timestamp al secondo, interrogando in massa l'endpoint aperto. Riesce così a scaricare file di gare sensibili senza alcuna autenticazione.
    
- **Traccia di Soluzione**: Rendere l'endpoint autenticato con JWT (passandolo tramite parametri o header configurati dal Document Server). Modificare la generazione della doc_key usando algoritmi sicuri (es. HMAC-SHA256 con un secret lato server, o UUID v4 associati al DB).


--------------------
Sto incrociando i due documenti di analisi con la codebase packata per separare i bug realmente confermati da quelli solo ipotizzati, poi li traduco in fix concreti e prioritizzati.

Ho isolato due cluster principali: bug “di sicurezza/affidabilità” davvero bloccanti e bug “di semantica workflow/KPI” che non rompono sempre l’app ma distorcono stato ed eventi.

Thought for 2m 1s

Ho incrociato i tre file e la mia conclusione è questa: la strategia migliore non è fare patch sparse, ma chiudere **tre refactor mirati**. Il primo deve eliminare i crash e i dead-end operativi; il secondo deve chiudere le superfici di attacco; il terzo deve rendere esplicita la state machine del workflow/KPI, che oggi è la parte più fragile dal punto di vista semantico.

La priorità assoluta è il blocco **task/RAG/OTP**. In `backend/app/tasks.py` il task `generate_proposal_section_task` chiama `engine.generate(...)`, mentre l’analisi retrospettiva segnala che `HybridRAGEngine` non espone quel metodo ma un flusso basato su `query`; nello stesso file ogni task crea anche un nuovo engine SQLAlchemy con `create_async_engine(...)`, quindi ogni esecuzione Celery apre un nuovo pool; in `main.py` l’inizializzazione del RAG parte con `asyncio.create_task(...)` senza gestione errori; in `auth.py` la registrazione fa un doppio `db.refresh(user)` e `verify_otp` usa `scalar_one_or_none()` su tutti gli OTP dell’utente, quindi con più token attivi rischia `MultipleResultsFound`. Inoltre l’invio mail OTP usa `get_event_loop().run_in_executor(...)` e logga l’errore senza ripristinare lo stato applicativo, lasciando possibile un utente registrato ma non realmente verificabile.

Qui la soluzione migliore è strutturale: introdurre un piccolo **service layer per i background task** invece di chiamare direttamente l’engine dal task. In pratica: `generate_proposal_section_task` deve delegare a un servizio che costruisce l’oggetto query corretto per il RAG; `get_async_session()` va eliminato e sostituito con `async_session_factory` condivisa dal modulo database; l’inizializzazione del RAG va o **awaitata a startup** con fail-fast, oppure lasciata in background ma con `done_callback`, stato `app.state.rag_ready`, healthcheck degradato e rifiuto esplicito delle query finché non è pronta; per OTP serve una regola chiara “**un solo token attivo per utente**”, quindi o si cancellano i precedenti prima di emettere il nuovo, o si impone un vincolo DB e si fa upsert; l’invio OTP non deve più fallire in silenzio, ma aprire due strade nette: `register` fallisce e rollbacka, oppure l’utente entra in uno stato “pending_verification” con endpoint `resend-otp`.

Il secondo refactor deve essere **security hardening**. L’anonymizer inoltra richieste verso qualunque `X-Target-Url`, quindi oggi è un proxy SSRF aperto; l’endpoint OnlyOffice `/files/{doc_key}` non richiede autenticazione; il callback OnlyOffice non valida il JWT del payload; i `doc_key` sono derivati da MD5 su input prevedibile; il template PDF usa `|safe`; e la retrospettiva richiama anche il mount del Docker socket come superficie critica. Sul search tender, il problema non è SQL injection classica ma il fatto che `%` e `_` non vengono escapati nell’`ilike`, quindi la ricerca è troppo permissiva rispetto all’intenzione.

Anche qui eviterei micro-fix isolati. Farei un **security boundary unico** per tutto ciò che tocca OnlyOffice e documenti temporanei: `doc_key` random con `secrets.token_urlsafe()` o UUID signed, tabella server-side per mappare il token a proposal/section, scadenza breve, verifica dei permessi utente sul tender/proposal associato, callback firmato con lo stesso secret JWT configurato tra backend e OnlyOffice, e risposta `error != 0` quando payload o token sono invalidi. L’anonymizer o viene rimosso dai path di produzione, o passa a allowlist stretta di host/scheme/port con blocco esplicito di loopback, RFC1918 e metadata endpoints. Per il PDF la scelta migliore è **sanitizzare lato server** con una whitelist HTML molto ridotta oppure serializzare plain text; togliere `|safe` senza una strategia di rendering spesso rompe l’output, quindi conviene definire un formato consentito. Per la ricerca tender basta un helper che escape `%` e `_` prima dell’`ilike`. Sul Docker socket, meglio spostare le operazioni amministrative in un servizio separato non esposto al traffico utente.

Il terzo refactor, a mio avviso, è quello che migliora di più la qualità del prodotto: **state machine esplicita per workflow operativo e KPI**. In `operational_workflow.py`, `derive_contribution_status()` restituisce `OPEN` quando una section è `IN_PROGRESS` ma non assegnata; `build_section_transition_plan()` attiva `cancel_open_requests` solo quando `previous_assigned_to is not None`; il passaggio diretto verso `APPROVED` può innescare review sintetiche; entrando in `IN_REVIEW` vengono anche risolti rework aperti; e in `sync_section_operational_workflow` la derivazione finale dello stato può sovrascrivere lo stato appena prodotto dagli step precedenti. La retrospettiva nota anche che review virtuali e rework auto-risolti falsano metriche come `reviewDurationHours`, `reworkDurationHours` e `timeToFirstResponse`, mentre `mark_latest_request_received` può sovrascrivere annotazioni manuali con summary generici.

La soluzione migliore qui non è una sequenza di `if` aggiuntivi, ma una **tabella di transizione dichiarativa**. Devi rendere esplicite le sole transizioni valide tra `TODO`, `IN_PROGRESS`, `IN_REVIEW`, `APPROVED`, con effetti secondari separati: richiesta contributo, review, rework, KPI. Io la imposterei così: `build_section_transition_plan()` diventa puro e senza side effect; `sync_section_operational_workflow()` applica il piano in modo idempotente; il passaggio diretto `IN_PROGRESS -> APPROVED` o viene vietato, o viene marcato come “auto-approval” senza aprire/chiudere una review fittizia; `resolve_open_reworks()` non parte entrando in review ma solo quando c’è un evento reale di consegna/chiusura; `mark_latest_request_received()` non deve più sovrascrivere `response_received_at` se già presente; tutti gli eventi sintetici devono portare `source="section-workflow"` o `is_automated=true` così il Reason Engine può filtrarli o pesarli diversamente.

Ci sono poi fix trasversali che farei nello stesso sprint, ma dopo i tre blocchi sopra. I default mutabili nei modelli (`default=[]`, `default={}`) vanno sostituiti con callable; il codice va uniformato a datetime timezone-aware (`datetime.now(timezone.utc)`) perché oggi convivono `datetime.utcnow()` e confronti locali/UTC; `AppSettings` e `LLMSettings` usano ancora `datetime.utcnow`; il cleanup OnlyOffice usa `datetime.now()` confrontandolo con `last_modified` UTC; il client Redis non ha timeout configurati; e `_ensure_collection()` del dense retriever è dichiarata async ma fa I/O sincrono verso Qdrant, quindi blocca l’event loop.

Su alcuni punti secondari farei però una nota di metodo. Il bug su `delete_tender` è reale come **fragilità transazionale**, ma non lo descriverei come “la delete non avviene mai”, perché `get_db()` effettua commit a fine request: il vero problema è che delete, cleanup storage e KPI non sono gestiti come un’unità atomica. Allo stesso modo la “race condition” in `resolveTenderChatContext()` la metterei in seconda fascia: il codice usa una promise cache già abbastanza vicina a un single-flight; la miglior motivazione per toccarlo non è tanto una race sicura, quanto il fatto che le mappe crescono senza eviction reale e che il comportamento dipende da `preferCached`.

Se dovessi tradurre tutto in ordine operativo, farei così. **Sprint 1**: task/RAG/OTP, OnlyOffice auth/callback/doc_key, anonymizer allowlist o rimozione, `|safe` nel PDF, timezones. **Sprint 2**: refactor della state machine workflow/KPI, idempotenza eventi, marcatura eventi automatici, test golden/regression sulle transizioni. **Sprint 3**: pulizia contratti e qualità: `EmailStr`, rimozione doppi refresh, null-check corretti in `update_proposal`, sistemazione `update_section`, timeout Redis, Qdrant async/thread offload, hardening del deploy. Questa sequenza è coerente con la priorità emersa sia dal report bug sia dalla retrospettiva.

La cosa più importante, infine, è che i test cambino natura. La retrospettiva dice esplicitamente che mancano regression test sui lifecycle path; io aggiungerei pochi test ma molto “carichi”: doppia emissione OTP, `verify_otp` con due token attivi, task di generation che deve andare in `SUCCESS`, accesso non autenticato a `/files/{doc_key}` che deve dare 401/403, callback OnlyOffice con token invalido che deve fallire, `IN_PROGRESS -> APPROVED` che non deve creare review fantasma, e reassignment che non deve lasciare richieste aperte incoerenti. Questi test difendono le invarianti vere della codebase, non solo le route.

Se vuoi, nel passo successivo posso trasformare questa analisi in una **checklist di refactor file-per-file** con ordine di modifica preciso.

si

Adesso lo trasformo in un piano operativo file-per-file, con patch order, obiettivo del fix e test di regressione minimo per ciascun blocco.

Sto consolidando il piano su file reali del repo, non solo sui bug titles, così l’ordine di intervento resta eseguibile e non teorico.

Thought for 1m 6s

Perfetto. Ti lascio una **checklist di refactor file-per-file**, ordinata per impatto e dipendenze. Considero `my-output.md` come pack Repomix della repo: quindi i fix vanno applicati ai file originali indicati nei blocchi `## File: ...`, non al markdown aggregato.

## Ordine corretto di intervento

**Wave 1 — bloccare crash e vulnerabilità esposte**

1. `backend/app/tasks.py`
    
2. `backend/app/main.py`
    
3. `backend/app/api/auth.py`
    
4. `backend/app/api/onlyoffice.py`
    
5. `anonymizer/app.py`
    
6. `docker-compose.yml`
    

**Wave 2 — rimettere in asse semantica workflow/KPI**  
7. `backend/app/services/operational_workflow.py`  
8. `backend/tests/test_operational_workflow.py`  
9. `kpi-reason-engine` consumer/tests correlati

**Wave 3 — hardening e qualità strutturale**  
10. `backend/app/models/__init__.py`  
11. `backend/app/models/app_settings.py`  
12. `backend/app/models/llm_settings.py`  
13. `backend/app/api/tenders.py`  
14. `backend/app/api/proposals.py`  
15. `backend/app/rag/dense_retriever.py`  
16. `backend/app/db/database.py`  
17. `backend/app/db/redis.py`  
18. frontend (`ProposalEditor.tsx`, `TaskManager.tsx`, `ObservabilityKPI.tsx`, `api/client.ts`)

---

## 1) `backend/app/tasks.py`

Qui farei il primo intervento. Il task di generation usa `engine.generate(...)`, mentre l’analisi conferma che il contratto reale dell’engine è diverso; inoltre il modulo crea un nuovo `create_async_engine(...)` per i task e usa `datetime.utcnow()` nel cleanup OTP. Questo è il punto con più probabilità di failure runtime immediato.

**Fix da fare**

- Eliminare `get_async_session()` locale e riusare la session factory condivisa del layer DB.
    
- Sostituire il contratto `engine.generate(...)` con un servizio applicativo compatibile con l’API reale del RAG.
    
- Togliere dal task la responsabilità di bootstrap/shutdown dell’engine, o incapsularla in un adapter.
    
- Uniformare i datetime a timezone-aware.
    

**Done criteria**

- `generate_proposal_section_task` completa davvero con `SUCCESS`.
    
- Nessun engine DB creato ad hoc per invocazione.
    
- Cleanup OTP non confronta naive vs aware datetime.
    

**Test minimi**

- test task generation happy path
    
- test proposal/section non trovata
    
- test cleanup OTP con record scaduti e timezone UTC
    

---

## 2) `backend/app/main.py`

Lo startup inizializza il RAG con `asyncio.create_task(...)` fire-and-forget. Se l’inizializzazione fallisce, l’app parte ma resta in stato rotto. È un classico bug di affidabilità “sembra healthy ma non lo è”.

**Fix da fare**

- O fai startup fail-fast: `await initialize()`.
    
- Oppure tieni il bootstrap lazy, ma con stato esplicito `rag_ready / rag_error`.
    
- Aggiungi log strutturato e health endpoint che rifletta davvero lo stato del RAG.
    

**Done criteria**

- errore di init visibile nei log
    
- stato applicativo interrogabile
    
- nessuna query RAG accettata quando l’engine non è pronto
    

**Test minimi**

- startup con init ok
    
- startup con init fallita
    
- health/readiness degradati
    

---

## 3) `backend/app/api/auth.py`

Qui il cluster OTP è da sistemare subito: doppio `db.refresh(user)`, `get_event_loop()` deprecato, rischio `MultipleResultsFound` in `verify_otp` se esistono più token per utente, e modello utente attivo prima della verifica. Nel retro è anche segnalata una superficie OTP non sufficientemente hardenizzata.

**Fix da fare**

- `UserRegister.email` deve diventare `EmailStr`.
    
- Rimuovere il doppio `refresh`.
    
- Stabilire policy OTP unica: un solo token attivo per utente.
    
- `verify_otp` deve selezionare l’OTP valido più recente, non fare `scalar_one_or_none()` sull’intero set.
    
- Sostituire `get_event_loop()` con `get_running_loop()` o wrapper asincrono moderno.
    
- Decidere in modo netto lo stato utente: `is_active=False` fino a verifica, oppure guardie sistematiche su `is_verified`.
    

**Done criteria**

- doppia emissione OTP non rompe `verify_otp`
    
- email formalmente validata
    
- registrazione e verifica hanno stati utente coerenti
    
- errori invio OTP non restano silenziosi lato flusso utente
    

**Test minimi**

- due OTP consecutivi per stesso utente
    
- OTP scaduto
    
- OTP valido più recente
    
- login negato prima della verifica, consentito dopo verifica
    

---

## 4) `backend/app/api/onlyoffice.py`

Questo è il pezzo più delicato lato security: `doc_key` MD5 prevedibile, endpoint `/files/{doc_key}` senza auth, callback OnlyOffice senza vera validazione JWT, cleanup basato su `datetime.now()` locale. È uno dei blocchi più chiaramente prioritizzati nel bug analysis.

**Fix da fare**

- Sostituire MD5 con token random non prevedibile e persistence server-side.
    
- Proteggere `/files/{doc_key}` con auth + authorization sul documento.
    
- Validare davvero il JWT del callback OnlyOffice.
    
- Rendere il cleanup interamente UTC-aware.
    
- Chiudere bene eventuali response stream/risorse MinIO.
    

**Done criteria**

- documento non scaricabile senza sessione o permesso
    
- callback falsa respinta
    
- doc_key non enumerabile
    
- cleanup TTL coerente in UTC
    

**Test minimi**

- GET file senza auth
    
- GET file con auth ma senza permesso
    
- callback con token invalido
    
- callback valida aggiorna il contenuto corretto
    

---

## 5) `anonymizer/app.py`

L’anonymizer oggi è un forwarder aperto basato su `X-Target-Url`. Questo è SSRF quasi textbook verso servizi interni e metadata endpoints.

**Fix da fare**

- Se non è indispensabile, toglierlo dal perimetro production.
    
- Se serve, imporre allowlist stretta di host/scheme/port.
    
- Bloccare loopback, RFC1918, link-local, metadata IP.
    
- Sanitizzare e ricostruire gli header inoltrati.
    

**Done criteria**

- impossibile forwardare verso host arbitrari
    
- richieste solo verso upstream esplicitamente ammessi
    

**Test minimi**

- target URL mancante
    
- target URL non in allowlist
    
- target localhost / 169.254.x.x negato
    
- target ammesso inoltrato correttamente
    

---

## 6) `docker-compose.yml`

Il mount `/var/run/docker.sock` nel backend va trattato come rischio di privilege escalation host-level. Non è un bug applicativo, ma è una scelta di deployment pericolosa.

**Fix da fare**

- Rimuovere il mount dal backend.
    
- Se qualche feature lo richiede, spostarla in un sidecar/servizio admin separato e isolato.
    

**Done criteria**

- backend non ha più accesso al socket Docker host
    

---

## 7) `backend/app/services/operational_workflow.py`

Questo è il refactor più importante lato dominio. Il retro segnala chiaramente che la sequenza delle mutazioni è opaca, `resolve_open_reworks` parte troppo presto, e lo stato finale viene ricalcolato in modo che può sovrascrivere mutazioni precedenti. Nel codice, `build_section_transition_plan()` e `derive_contribution_status()` oggi codificano una semantica troppo fragile per casi come reassignment, passaggio diretto ad `APPROVED`, review sintetiche e rework multipli.

**Fix da fare**

- Introdurre una state machine esplicita per le sole transizioni ammesse.
    
- Separare “decisione transizione” da “side effects”.
    
- Fare un solo punto finale di derivazione `ContributionUnitStatus`.
    
- Non risolvere rework entrando in `IN_REVIEW`; farlo solo all’esito corretto.
    
- Marcare gli eventi automatici con `is_automated` o campo equivalente.
    

**Done criteria**

- niente review fantasma su approve diretto
    
- niente rework risolti automaticamente troppo presto
    
- reassignment non lascia richieste incoerenti
    
- stato contribution coerente con sezione e rework aperti
    

**Test minimi**

- TODO -> IN_PROGRESS con assignment
    
- IN_PROGRESS -> IN_REVIEW
    
- IN_REVIEW -> IN_PROGRESS con changes requested
    
- IN_PROGRESS -> APPROVED diretto
    
- reassignment con richiesta aperta
    
- rework multipli / idempotenza eventi
    

---

## 8) `backend/tests/test_operational_workflow.py`

Questo file esiste già ed è il posto giusto per trasformare i bug di dominio in regression tests stabili. La retrospettiva insiste proprio sulla mancanza di test sui lifecycle path reali.

**Fix da fare**

- Ampliare i test da “plan booleans” a “effetti osservabili”.
    
- Aggiungere golden path e anti-regression path.
    
- Verificare sia stato finale sia eventi emessi.
    

**Done criteria**

- ogni bug semantico già emerso ha almeno un test che fallirebbe senza fix
    

---

## 9) `kpi-reason-engine`

Il retro evidenzia che review virtuali, rework auto-risolti e campi opzionali non gestiti bene distorcono KPI come `reviewDurationHours`, `reworkDurationHours`, `timeToFirstResponse`. Quindi il refactor workflow va accompagnato da adattamento consumer/contract test nel Reason Engine.

**Fix da fare**

- Accettare e distinguere eventi sintetici/automatici.
    
- Gestire `null` in modo robusto nelle aggregazioni.
    
- Introdurre golden datasets sui casi borderline.
    

**Done criteria**

- KPI non collassano o si drogano su eventi sintetici
    
- dataset golden stabile dopo il refactor workflow
    

---

## 10) `backend/app/models/__init__.py`

Qui il problema è classico ma serio: mutable defaults (`default=[]`, `default={}`) su colonne SQLAlchemy. Inoltre il dominio osservability è abbastanza ricco da soffrire molto la condivisione involontaria di default mutabili.

**Fix da fare**

- Sostituire con callable (`default=list`, `default=dict`) dove applicabile.
    
- Rivedere anche eventuali JSON/ARRAY simili in altri model file.
    

**Done criteria**

- nessun model usa più default mutabili condivisi
    

---

## 11) `backend/app/models/app_settings.py` e `backend/app/models/llm_settings.py`

Entrambi usano `datetime.utcnow` come default/onupdate. È coerente con il bug di timezone già rilevato, e va uniformato al resto del backend.

**Fix da fare**

- passare a datetime timezone-aware o server-side timestamps coerenti
    
- evitare mix naive/aware
    

---

## 12) `backend/app/api/tenders.py`

Qui hai due punti: ricerca con `ilike(f"%{search}%")` senza escape dei metacaratteri LIKE, e delete tender con semantica transazionale debole rispetto a KPI/storage cleanup. Il bug analysis lo classifica fra i punti da sistemare, ma io lo metterei dopo security/runtime/workflow.

**Fix da fare**

- helper per escapare `%` e `_` prima dell’`ilike`
    
- su delete tender: orchestrare delete DB + cleanup storage + publish KPI come unità logica, non come effetto incidentale
    

**Done criteria**

- ricerca non espandibile con wildcard arbitrarie
    
- delete tender non lascia orfani né eventi mancanti
    

---

## 13) `backend/app/api/proposals.py`

Nel bug analysis ci sono due punti netti: accesso a `proposal.status` prima del null-check e `update_section` con branch `if/else` identici, segno che manca una trasformazione reale del contenuto.

**Fix da fare**

- anticipare il null-check prima di qualsiasi dereferenziazione
    
- chiarire se `content` richiede conversione verso formato editoriale strutturato
    
- ridurre rami morti o duplicati
    

**Done criteria**

- nessun `AttributeError` al posto di HTTP 404/400
    
- `update_section` ha semantica chiara sul campo `content`
    

---

## 14) `backend/app/rag/dense_retriever.py`

La retro-analisi conferma che `_ensure_collection` è dichiarata async ma usa I/O sincrono Qdrant, quindi blocca l’event loop e inganna chi legge il contratto.

**Fix da fare**

- o renderla davvero async
    
- oppure dichiararla sync e invocarla fuori dal loop / via executor dove serve
    

**Done criteria**

- niente pseudo-async che fa I/O bloccante
    

---

## 15) `backend/app/db/database.py`

Qui non farei un refactor enorme, ma due fix secchi: non silenziare le “migration error” con `pass`, e consolidare il contratto di session management per far sì che i task non creino engine propri. Il retro segnala esplicitamente “silent DB migration failures”.

**Fix da fare**

- loggare e classificare gli errori di migration bootstrap
    
- riusare un’unica session factory condivisa
    
- evitare swallow di eccezioni non attese
    

---

## 16) `backend/app/db/redis.py`

Il client globale senza cleanup è secondario ma reale. Lo sposterei in coda rispetto ai bug di dominio e sicurezza.

**Fix da fare**

- lifecycle esplicito open/close
    
- timeout configurati
    
- integrazione con shutdown app
    

---

## 17) Frontend

`ProposalEditor.tsx` e `TaskManager.tsx` hanno URL hardcoded `http://localhost:8000`; `TaskManager.tsx` ha anche empty catch; `ObservabilityKPI.tsx` ha logica `cancelled` fragile; `client.ts` è il posto giusto per centralizzare base URL e policy fetch. Sono problemi veri, ma stanno dietro ai fix backend.

**Fix da fare**

- eliminare localhost hardcoded e usare `API_BASE`
    
- vietare `catch {}` vuoti
    
- migliorare cancellazione/polling cleanup
    
- ridurre cache growth dove già segnalato nel retro
    

**Done criteria**

- frontend deployabile fuori localhost
    
- niente errori silenziati
    
- polling e cleanup prevedibili
    

---

## Backlog finale sintetico

Se vuoi massimizzare rapporto impatto/sforzo, io farei questo taglio:

**Sprint A**

- `tasks.py`
    
- `main.py`
    
- `auth.py`
    
- `onlyoffice.py`
    
- `anonymizer/app.py`
    
- `docker-compose.yml`
    

**Sprint B**

- `operational_workflow.py`
    
- test workflow
    
- adaptation KPI engine
    

**Sprint C**

- models defaults/timezone
    
- `tenders.py`
    
- `proposals.py`
    
- `dense_retriever.py`
    
- DB/Redis
    
- frontend hardening
    

Il prossimo passo utile è questo: ti posso produrre una **matrice esecutiva “file / bug / fix strategy / rischio regressione / priorità / test”** già pronta da usare come piano di lavorazione.

si

Estraggo dai tre allegati i riferimenti file-level e li trasformo in una matrice esecutiva pronta da usare come backlog tecnico.

Thought for 27s

Ecco la **matrice esecutiva** pronta da usare come backlog tecnico. Ho privilegiato i fix che massimizzano insieme **stabilità runtime, sicurezza e coerenza di dominio**; dove il bug è “direttamente confermato” nel codice packed l’ho trattato come prioritario, dove emerge soprattutto da `bug_analysis.md`/`Retrospective.md` l’ho mantenuto ma con priorità un gradino sotto.

|File|Caso specifico|Motivazione|Proposta di soluzione|Rischio regressione|Priorità|Test minimo|
|---|---|---|---|---|---|---|
|`backend/app/tasks.py`|`generate_proposal_section_task` chiama `engine.generate(...)`; task DB session crea un nuovo engine ad ogni invocazione; cleanup OTP usa `datetime.utcnow()`|È il cluster più pericoloso lato runtime: task che può fallire sempre, pool DB che cresce male sotto concorrenza, confronto naive/aware sugli OTP.|Introdurre un service adapter per il RAG, riusare la session factory centralizzata, uniformare tutti i timestamp a UTC aware. Separare “task orchestration” da “RAG invocation contract”.|Medio|P0|task generation happy path; task fail path; cleanup OTP con record scaduti UTC|
|`backend/app/main.py`|`asyncio.create_task(app.state.rag_engine.initialize())` fire-and-forget|Se init fallisce, l’app può sembrare up ma il RAG resta rotto e l’errore si perde.|O startup fail-fast con `await`, oppure init lazy con stato esplicito `rag_ready/rag_error`, callback di errore e readiness endpoint reale.|Medio|P0|startup con init ok / init fail; readiness degradato|
|`backend/app/api/auth.py`|doppio `db.refresh(user)`, `verify_otp` fragile con più token, `get_event_loop()` deprecato, failure invio OTP lascia account in stato ambiguo|È un flusso utente critico: registrazione/OTP può rompersi in produzione e bloccare account. La retro segnala esplicitamente `MultipleResultsFound` e invio OTP non robusto.|Politica “un solo OTP attivo per utente”, selezione del token valido più recente, stato utente coerente (`pending_verification` o simile), rimozione del doppio refresh, modernizzazione loop async.|Medio|P0|due OTP consecutivi; OTP scaduto; login prima/dopo verifica|
|`backend/app/api/onlyoffice.py`|`/files/{doc_key}` senza auth; callback senza validazione JWT; `doc_key` MD5 prevedibile; cleanup con `datetime.now()` locale|È la superficie security più esposta dopo SSRF: data exfiltration, callback falsi, cancellazioni anticipate/ritardate.|Rendere autenticato l’endpoint file, validare il callback con secret condiviso, sostituire MD5 con token random/HMAC, portare tutto a UTC-aware e restituire errori coerenti al Document Server.|Medio-Alto|P0|GET file senza auth; callback con token invalido; cleanup TTL corretto|
|`anonymizer/app.py`|proxy aperto basato su `X-Target-Url`|SSRF classico verso loopback, metadata cloud e servizi interni. È un rischio immediato.|Allowlist stretta di host/scheme/port oppure rimozione dal perimetro production. Bloccare RFC1918, loopback, link-local e ricostruire gli header forwardati.|Basso-Medio|P0|target non ammesso; target localhost; target ammesso|
|`docker-compose.yml`|mount di `/var/run/docker.sock` nel backend|Se il backend viene compromesso, l’attaccante ottiene quasi root sull’host.|Eliminare il socket dal backend; se serve, spostare in un servizio admin isolato.|Basso|P0|smoke deploy senza dipendenza dal socket|
|`backend/app/services/operational_workflow.py`|mapping stato fragile (`derive_contribution_status`), piano transizioni troppo implicito, rischio review/rework sintetici che inquinano KPI|È il principale debito di business logic: stati incoerenti e KPI alterati da eventi automatici. La retro lo individua come area più scoperta.|Passare a state machine dichiarativa; separare decisione transizione da side effect; marcare eventi sintetici (`isSyntheticLifecycleEvent` o equivalente); rendere idempotenti i punti sensibili come `mark_latest_request_received`.|Alto|P1|TODO→IN_PROGRESS; IN_PROGRESS→IN_REVIEW; IN_PROGRESS→APPROVED diretto; reassignment; rework multipli|
|`backend/tests/test_operational_workflow.py`|coverage insufficiente sui lifecycle path veri|I bug di workflow sono sopravvissuti perché i test non codificano abbastanza bene le invarianti di dominio.|Aggiungere regression test per ogni transizione critica e verificare sia stato finale sia eventi emessi.|Basso|P1|suite golden sui path principali|
|`kpi-reason-engine` consumer / analytics / contract tests|KPI distorti da review virtuali, rework auto-risolti, eventi sintetici e casi edge|Anche con workflow corretto, il Reason Engine può continuare a misurare male se non distingue eventi automatici.|Estendere il contratto eventi con marker di sinteticità, gestire `null`/edge cases, aggiungere golden dataset e contract tests cross-service.|Medio|P1|dataset con eventi sintetici vs reali|
|`backend/app/models/__init__.py`|mutable defaults (`default=[]`, `default={}`)|Rischio latente di condivisione stato tra istanze.|Sostituire con callable (`default=list`, `default=dict`) o equivalente lato ORM.|Basso|P1|creazione di due istanze indipendenti|
|`backend/app/models/app_settings.py` + `llm_settings.py` + punti multipli backend|uso diffuso di `datetime.utcnow()`/`datetime.now()` naive|Il mix naive/aware è già emerso in OTP e OnlyOffice; è un problema trasversale di integrità temporale.|Standard unico UTC-aware (`datetime.now(timezone.utc)` o timestamp server-side), helper condiviso e refactor graduale dei callsite.|Medio|P1|confronti datetime su DB e cleanup|
|`backend/app/api/tenders.py`|`ilike(f"%{search}%")` senza escape metacaratteri; delete tender non orchestra bene DB/KPI/storage|Non è SQL injection classica, ma ricerca troppo permissiva; delete tender ha semantica transazionale debole.|Escapare `%` e `_`; per delete introdurre orchestrazione esplicita: delete DB, cleanup storage, emissione eventi/KPI in sequenza controllata.|Medio|P1|ricerca con `%` e `_`; delete con cleanup e rollback|
|`backend/app/api/proposals.py`|null-check/logic issues già mappati nel report; `update_section` con rami identici|Sono bug meno esplosivi ma sintomo di contratti API poco chiari.|Ripulire null-check prima delle dereferenziazioni; chiarire la trasformazione del contenuto e rimuovere branch morti.|Basso-Medio|P2|404/400 corretti; update section coerente|
|`backend/app/rag/dense_retriever.py`|`_ensure_collection` dichiarata async ma con I/O sync|Non è il bug più urgente, ma blocca l’event loop e inganna il contratto del metodo.|O renderla davvero async oppure dichiararla sync e isolarla fuori dal loop.|Basso|P2|init retriever senza blocchi evidenti|
|`backend/app/db/database.py` + `db/redis.py`|silent migration failures; client Redis globale senza timeout/shutdown chiaro|Debito operativo: errori nascosti e risorse che possono restare appese.|Loggare/propagare gli errori di migration bootstrap, introdurre lifecycle esplicito e timeout su Redis.|Basso-Medio|P2|startup con migration fail; Redis down|
|Frontend (`ProposalEditor.tsx`, `TaskManager.tsx`, `ObservabilityKPI.tsx`, `api/client.ts`)|URL localhost hardcoded, empty catch, cache growth / cancellazione fragile|Non blocca il core backend, ma rovina deploy e diagnosi in produzione.|Centralizzare `API_BASE`, vietare `catch {}`, migliorare eviction cache e cleanup polling/cancel.|Basso|P2|deploy non-localhost; error surfacing; cleanup polling|

## Lettura operativa della matrice

La sequenza che consiglierei è questa.

**Sprint A**

- `tasks.py`
    
- `main.py`
    
- `auth.py`
    
- `onlyoffice.py`
    
- `anonymizer/app.py`
    
- `docker-compose.yml`
    

Qui chiudi il 70% del rischio reale: crash certi, superfici di attacco e failure invisibili.

**Sprint B**

- `operational_workflow.py`
    
- `test_operational_workflow.py`
    
- adattamento `kpi-reason-engine`
    

Qui chiudi il problema più importante di dominio: stati e KPI.

**Sprint C**

- models/defaults/timezones
    
- `tenders.py`
    
- `proposals.py`
    
- `dense_retriever.py`
    
- `database.py`
    
- `redis.py`
    
- frontend hardening
    

Qui fai consolidamento e riduci il debito tecnico residuo.

## Nota importante su due punti

Su `delete_tender`, non lo leggerei come “il tender non viene mai cancellato” in senso assoluto: il report stesso riconosce che `get_db()` fa auto-commit a fine sessione. Il problema vero è che la cancellazione non è trattata come operazione orchestrata con cleanup storage ed emissione KPI, quindi il comportamento resta fragile se qualcosa fallisce nel mezzo.

Sui bug di workflow/KPI, invece, la priorità è alta anche se meno “appariscente” di SSRF/OnlyOffice: è lì che il prodotto rischia di mentire su stato reale e metriche, che per questa codebase è un problema molto serio.

Nel prossimo passo posso convertire questa matrice in un **piano Jira-ready** con colonne: `Epic`, `Story`, `Task`, `Acceptance Criteria`, `Definition of Done`.

si

Sto trasformando il backlog tecnico in una struttura Jira utilizzabile subito, con epic, story, task e acceptance criteria ancorati ai problemi emersi nei tre allegati.

Thought for 18s

Perfetto. Ti propongo un **piano Jira-ready** già strutturato in **Epic → Story → Task**, con **Acceptance Criteria** e **Definition of Done**, costruito sui problemi emersi nei tre allegati e sui file reali della codebase packata. I driver principali sono: crash runtime nel task RAG, startup non affidabile, flusso OTP fragile, superfici security OnlyOffice/anonymizer, e incoerenze nella state machine del workflow/KPI.

## EPIC 1 — Stabilizzare runtime, autenticazione e superfici esposte

Questa epic raccoglie i fix che oggi hanno impatto immediato su disponibilità e sicurezza: `generate_proposal_section_task` che invoca un metodo non compatibile con `HybridRAGEngine`, startup RAG fire-and-forget senza gestione errori, OTP con più token potenzialmente concorrenti e OnlyOffice/anonymizer esposti in modo non sicuro.

### Story 1.1 — Correggere il contratto di esecuzione dei Celery task RAG

**Obiettivo**: rendere `backend/app/tasks.py` eseguibile e stabile in produzione.  
Il report retrospettivo conferma che `generate_proposal_section_task` chiama `engine.generate(...)` mentre il contratto reale atteso dall’engine è diverso; inoltre lo stesso file crea una session factory DB propria con `create_async_engine(...)`, e usa anche confronti temporali basati su `datetime.utcnow()`.

**Task**

- Sostituire l’invocazione diretta `engine.generate(...)` con un adapter/service compatibile con il contratto reale del RAG.
    
- Eliminare `get_async_session()` locale e riusare la session factory centralizzata del layer DB.
    
- Uniformare i timestamp usati dai task a UTC-aware.
    
- Riesaminare il template PDF che usa `|safe` e introdurre sanitizzazione o rendering sicuro.
    

**Acceptance Criteria**

- `generate_proposal_section_task` termina in `SUCCESS` in happy path.
    
- Nessuna nuova async engine viene creata per singola invocazione task.
    
- I confronti temporali non usano più datetime naive.
    
- L’export PDF non renderizza HTML arbitrario non sanitizzato.
    

**Definition of Done**

- Test automatici verdi per generation happy path, error path e cleanup OTP.
    
- Nessun riferimento residuo a `engine.generate(...)`.
    
- Nessun `datetime.utcnow()` nei punti toccati dallo story.
    

---

### Story 1.2 — Rendere affidabile l’inizializzazione del RAG a startup

**Obiettivo**: impedire che l’app risulti “up” mentre il RAG è in stato rotto.  
Nel materiale allegato è esplicitamente segnalato `asyncio.create_task(app.state.rag_engine.initialize())` come fire-and-forget senza gestione errori.

**Task**

- Decidere una strategia unica: fail-fast su startup oppure lazy-init con stato esplicito.
    
- Introdurre `rag_ready` / `rag_error` nello state applicativo.
    
- Aggiornare readiness/health per riflettere lo stato reale dell’engine.
    
- Loggare e propagare correttamente i failure di inizializzazione.
    

**Acceptance Criteria**

- Se l’init fallisce, l’errore è visibile nei log.
    
- Le route che dipendono dal RAG non procedono quando l’engine non è pronto.
    
- Health/readiness distinguono chiaramente stato healthy e degraded.
    

**Definition of Done**

- Test startup con init OK e init KO.
    
- Nessun `create_task(...)` non osservato per l’inizializzazione del RAG.
    

---

### Story 1.3 — Mettere in sicurezza il flusso di registrazione e verifica OTP

**Obiettivo**: eliminare errori di business e inconsistenze nel flusso auth.  
La retrospettiva e il bug analysis evidenziano doppio `db.refresh(user)`, uso di `get_event_loop()`, `verify_otp` fragile in presenza di più token per utente, e utente attivo anche con `is_verified=False`.

**Task**

- Introdurre policy “un solo OTP attivo per utente”.
    
- Correggere `verify_otp` per selezionare il token valido corretto senza `scalar_one_or_none()` sull’intero set.
    
- Rimuovere il doppio `db.refresh(user)`.
    
- Sostituire `get_event_loop()` con un approccio asincrono compatibile.
    
- Portare i DTO `UserRegister` / `UserLogin` a validazione email forte (`EmailStr` o equivalente).
    
- Allineare stato utente: non attivo fino a verifica, oppure guardia esplicita su `is_verified`.
    

**Acceptance Criteria**

- Due OTP consecutivi per lo stesso utente non causano eccezioni.
    
- Login prima della verifica bloccato secondo la policy scelta.
    
- La registrazione non esegue round-trip DB inutili.
    
- Email non valida respinta dallo schema.
    

**Definition of Done**

- Test su doppio OTP, OTP scaduto, OTP valido più recente, login pre/post verifica.
    
- Nessun doppio `refresh` residuo.
    
- Nessun `get_event_loop()` residuo nei punti toccati.
    

---

### Story 1.4 — Proteggere OnlyOffice document serving e callback

**Obiettivo**: chiudere le superfici di data leak e aggiornamento non autenticato.  
I file allegati segnalano che `/files/{doc_key}` non richiede autenticazione, che i `doc_key` sono MD5 prevedibili, che il callback OnlyOffice non valida il JWT e che il cleanup usa `datetime.now()` locale rispetto a timestamp UTC.

**Task**

- Proteggere `/files/{doc_key}` con autenticazione e autorizzazione.
    
- Sostituire `doc_key` prevedibile con token random/HMAC server-side.
    
- Validare il JWT del callback con secret condiviso.
    
- Restituire `error != 0` quando payload o token sono invalidi.
    
- Uniformare il cleanup a `datetime.now(timezone.utc)` con confronti aware.
    

**Acceptance Criteria**

- Documento non scaricabile senza credenziali valide.
    
- Callback falsa o incompleta respinta.
    
- I token documento non sono enumerabili.
    
- Il cleanup non dipende dal timezone locale del server.
    

**Definition of Done**

- Test su GET file anonimo, GET senza permesso, callback con token invalido, callback valido.
    
- Nessun MD5 residuo usato per `doc_key`.
    
- Nessun `datetime.now()` naive nel cleanup OnlyOffice.
    

---

### Story 1.5 — Bloccare SSRF e ridurre il rischio infrastrutturale del backend

**Obiettivo**: impedire forward arbitrari e ridurre escalation host-level.  
L’anonymizer inoltra richieste verso il valore di `x-target-url` senza validazione, e il materiale allegato richiama anche il mount del Docker socket come superficie critica.

**Task**

- Introdurre allowlist stretta per host/scheme/port nell’anonymizer oppure escluderlo dal perimetro production.
    
- Bloccare loopback, RFC1918, link-local e metadata endpoints.
    
- Sanificare gli header forwardati.
    
- Rimuovere il mount del Docker socket dal backend o isolarlo in un servizio amministrativo separato.
    

**Acceptance Criteria**

- Richieste verso target arbitrari vengono respinte.
    
- Non è possibile forwardare verso `localhost` o metadata endpoints.
    
- Il backend non richiede più accesso diretto al Docker socket.
    

**Definition of Done**

- Test SSRF su target non ammesso, localhost e target consentito.
    
- Compose/deploy aggiornato e verificato.
    

---

## EPIC 2 — Formalizzare workflow operativo e KPI

Questa epic nasce dalla parte più “di dominio” della retrospettiva: `operational_workflow.py` ha una logica di transizione troppo implicita, produce review o rework sintetici, e rischia di falsare i KPI di durata o di risposta.

### Story 2.1 — Esplicitare la state machine delle sezioni e dei contribution unit

**Obiettivo**: sostituire la logica “magica” delle transizioni con una matrice formale e testabile.  
La retrospettiva descrive problemi su `derive_contribution_status`, `build_section_transition_plan` e `sync_section_operational_workflow`, in particolare nei casi `IN_PROGRESS → APPROVED`, uscita da review e gestione reassignment/rework.

**Task**

- Definire formalmente la matrice `(section_status, assigned_to, has_open_rework) -> contribution_status`.
    
- Esplicitare la tabella `(previous_status, new_status) -> side effects`.
    
- Separare decisione di transizione da esecuzione degli effetti.
    
- Normalizzare la logica di assignment change e cancellazione richieste aperte.
    
- Gestire in modo distinto `APPROVED` diretto vs `APPROVED` dopo `IN_REVIEW`.
    

**Acceptance Criteria**

- Nessuna review “fantasma” su passaggio diretto ad `APPROVED`, salvo marcatura esplicita sintetica.
    
- Nessun rework viene risolto automaticamente entrando in review.
    
- Lo stato finale del contribution unit è coerente e non viene sovrascritto in modo regressivo.
    

**Definition of Done**

- State table documentata nel codice.
    
- Copertura test su tutti i path principali e sui casi edge noti.
    

---

### Story 2.2 — Ripulire il tracciamento KPI dagli eventi sintetici

**Obiettivo**: evitare che automazioni di lifecycle falsino le metriche.  
La retrospettiva segnala che eventi come review avviata/completata nello stesso ciclo o rework auto-risolti portano durate artificialmente basse e KPI distorti; propone esplicitamente un flag come `isSyntheticLifecycleEvent`.

**Task**

- Introdurre un marcatore esplicito per eventi sintetici/automatici.
    
- Rendere `mark_latest_request_received` idempotente e non distruttivo.
    
- Aggiornare il Reason Engine per distinguere eventi reali da sintetici.
    
- Preparare dataset golden per verificare le metriche.
    

**Acceptance Criteria**

- Review/rework sintetici non alterano medie e p95 dei KPI principali.
    
- La prima vera risposta non viene sovrascritta da una risposta “ricostruita”.
    
- Il Reason Engine gestisce correttamente campi temporali null o incompleti.
    

**Definition of Done**

- Contract test tra backend workflow e KPI reason engine.
    
- Dataset golden approvato e stabile su almeno i casi edge mappati.
    

---

### Story 2.3 — Portare i workflow test da “boolean plan” a regression suite di dominio

**Obiettivo**: fare in modo che i bug già emersi non rientrino.  
La retrospettiva identifica la mancanza di regression test sui lifecycle path come una causa diretta della fragilità attuale.

**Task**

- Aggiungere test su TODO → IN_PROGRESS.
    
- Aggiungere test su IN_PROGRESS → IN_REVIEW.
    
- Aggiungere test su IN_PROGRESS → APPROVED diretto.
    
- Aggiungere test su uscita da review con/ senza rework.
    
- Aggiungere test su reassignment e richieste aperte residue.
    

**Acceptance Criteria**

- Ogni bug di business logic già emerso è coperto da almeno un test di regressione.
    
- I test verificano sia stato finale sia eventi emessi.
    

**Definition of Done**

- Suite workflow verde in CI.
    
- Test nominati per scenario di business e non per dettaglio implementativo.
    

---

## EPIC 3 — Hardening dati, contratti API e debito tecnico trasversale

Questa epic consolida i fix strutturali: default mutabili nei model, datetime naive vs aware, ricerca tender con wildcard non escapate, bug logici in `proposals.py`, pseudo-async nel dense retriever, gestione DB/Redis e alcuni debiti frontend.

### Story 3.1 — Eliminare i mutable defaults e standardizzare il tempo applicativo

**Obiettivo**: chiudere i problemi di integrità dati ricorrenti.  
Il bug analysis evidenzia `default=[]`, `default={}` nei model e uso diffuso di `datetime.utcnow()` / `datetime.now()` naive in più file.

**Task**

- Sostituire i mutable defaults con callable.
    
- Definire una policy unica UTC-aware.
    
- Ripulire i callsite più critici: OTP, OnlyOffice, settings, tender/proposal timestamps.
    

**Acceptance Criteria**

- Nessun model usa più default mutabili condivisi.
    
- Nessun confronto naive/aware nei moduli toccati.
    
- Timestamp coerenti lato DB e lato codice.
    

**Definition of Done**

- Static grep / test che escludano i pattern proibiti.
    
- Aggiornamento note tecniche/documentazione interna.
    

---

### Story 3.2 — Correggere ricerca tender e operazioni distruttive

**Obiettivo**: rendere robuste ricerca e delete.  
Il bug analysis nota che `Tender.title.ilike(f"%{search}%")` non escape `%` e `_`, e che `delete_tender` ha una semantica fragile rispetto a commit, cleanup storage e KPI.

**Task**

- Escapare i metacaratteri LIKE nella ricerca tender.
    
- Rifattorizzare `delete_tender` come operazione orchestrata con cleanup ed emissione eventi.
    
- Aggiungere test su rollback/failure intermedi.
    

**Acceptance Criteria**

- La ricerca non interpreta wildcard utente non intenzionali.
    
- La delete non lascia dati orfani senza tracciamento.
    
- In caso di errore intermedio, il comportamento è esplicito e osservabile.
    

**Definition of Done**

- Test con input `%` e `_`.
    
- Test delete con storage/event emission.
    

---

### Story 3.3 — Ripulire i contratti API di proposals e DTO auth

**Obiettivo**: eliminare errori logici e ambiguità nei DTO.  
Il bug analysis segnala `update_proposal` che dereferenzia `proposal` prima del null-check, `update_section` con due branch identici, e DTO auth con validazioni deboli.

**Task**

- Correggere l’ordine del null-check in `update_proposal`.
    
- Dare semantica reale al branch `content` in `update_section` oppure rimuoverlo.
    
- Consolidare le validazioni dei DTO auth.
    

**Acceptance Criteria**

- `update_proposal` restituisce 404/errore coerente senza `AttributeError`.
    
- `update_section` ha branch distinti o codice semplificato.
    
- I DTO respingono input non coerenti col contratto.
    

**Definition of Done**

- Test su proposal mancante e update section content.
    
- Code review senza dead branch residui.
    

---

### Story 3.4 — Allineare dense retriever, DB bootstrap, Redis e frontend

**Obiettivo**: chiudere il debito tecnico che oggi rende il sistema meno osservabile e meno deployabile.  
La retrospettiva segnala `_ensure_collection` async ma con I/O sync, Redis globale senza cleanup e growth indefinita di cache lato frontend.

**Task**

- Rendere coerente `_ensure_collection` con la sua vera natura sync/async.
    
- Rendere espliciti lifecycle e timeout Redis.
    
- Esporre meglio gli errori di bootstrap DB/migration.
    
- Rimuovere localhost hardcoded e catch vuoti dal frontend; introdurre gestione base URL centralizzata.
    

**Acceptance Criteria**

- Nessun pseudo-async bloccante nel dense retriever.
    
- Redis viene chiuso correttamente a shutdown.
    
- Il frontend è deployabile fuori localhost senza patch manuali.
    
- Gli errori non vengono silenziati.
    

**Definition of Done**

- Smoke test startup/shutdown.
    
- Smoke test frontend con base URL configurato via env.
    

---

## Ordine consigliato in Jira

Io lo schedulerei così:

**Sprint 1**

- Epic 1 completa
    

**Sprint 2**

- Story 2.1
    
- Story 2.3
    

**Sprint 3**

- Story 2.2
    
- Story 3.1
    
- Story 3.2
    

**Sprint 4**

- Story 3.3
    
- Story 3.4
    

Questo ordine segue bene il rapporto rischio/impatto emerso dagli allegati: prima crash e superfici esposte, poi correttezza del dominio, poi hardening e consolidamento.

