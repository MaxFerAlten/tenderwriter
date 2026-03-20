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
# x-target-url: http://169.254.169.254/latest/meta-data/  (AWS metadata)
# x-target-url: http://localhost:5432  (servizi interni)
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
tags = Column(ARRAY(String), default=[])        # ⚠️ Mutable default
metadata_json = Column(JSONB, default={})        # ⚠️ Mutable default
content = Column(JSONB, default={})              # ⚠️ Mutable default
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
    email: str      # ⚠️ Dovrebbe essere EmailStr
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
await db.refresh(user)  # ⚠️ Duplicato
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
if not proposal:  # ⚠️ Se proposal è None, la riga sopra ha già fatto NoneType access
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
        setattr(section, key, value)       # branch 1
    else:
        setattr(section, key, value)       # branch 2 — identico!
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
    is_active=True,   # ⚠️ Utente attivo immediatamente
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
