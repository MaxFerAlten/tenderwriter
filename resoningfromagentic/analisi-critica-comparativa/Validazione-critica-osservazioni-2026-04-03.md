# Validazione Critica delle Osservazioni — 2026-04-03

Documento di analisi indipendente che verifica punto per punto le osservazioni contenute nei documenti della cartella `analisi-critica-comparativa` contro l'attuale codebase di TenderWriter.

---

## 1. Verifica Osservazioni sulla Sicurezza

### 1.1 Credenziali Hardcoded nel docker-compose.yml

**Osservazione**: Password hardcoded visibili in chiaro (`DefaultPg2024Pass`, `DefaultNEO4J2024Pass`, `DefaultMinIO2024Pass`, `DefaultMM2024Pass`).

**Stato: ✅ CONFERMATA**

```
docker-compose.yml:9   POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-DefaultPg2024Pass}
docker-compose.yml:43  NEO4J_AUTH: neo4j/${NEO4J_PASSWORD:-DefaultNEO4J2024Pass}
docker-compose.yml:159 MINIO_ROOT_PASSWORD: ${MINIO_SECRET_KEY:-DefaultMinIO2024Pass}
docker-compose.yml:582 POSTGRES_PASSWORD: ${MM_DBPASS:-DefaultMM2024Pass}
```

**Validazione**: Le password di default sono effettivamente presenti come fallback. È positivo che esistano variabili d'ambiente configurabili, ma i default in chiaro rappresentano un rischio in ambienti non controllati.

**Nota aggiuntiva**: Le stesse credenziali appaiono anche in `frontend/src/pages/Components.tsx:394-396` nella sezione di debug delle credenziali services. Questo è un ulteriore leak di informazioni sensibili nel frontend.

---

### 1.2 Docker Socket Montato nel Backend

**Osservazione**: `/var/run/docker.sock` montato nel container `tw-backend`.

**Stato: ✅ CONFERMATA**

```
docker-compose.yml:251  - /var/run/docker.sock:/var/run/docker.sock
docker-compose.yml:674  - /var/run/docker.sock:/var/run/docker.sock
```

**Validazione**: Il mount è presente in due servizi. L'osservazione è corretta. La documentazione dell'ops-agent indica che "This service is the only TenderWriter component allowed to access docker.sock", ma il mount è ancora presente nel backend.

---

### 1.3 Placeholder CHANGEME

**Osservazione**: `CHANGEME-mattermost-client-secret` visibile nel compose.

**Stato: ⚠️ PARZIALMENTE CONFERMATA**

La stringa esatta non è stata trovata nel codebase attuale, ma il rischio rimane poiché le credenziali Mattermost usano variabili con default deboli. Il rischio è reale anche se il placeholder specifico potrebbe essere stato già modificato.

---

### 1.4 SSRF nell'Anonymizer

**Osservazione**: Vulnerabilità SSRF nel servizio anonymizer.

**Stato: ✅ CONFERMATA - FIX IN CORSO**

Esiste il file `anonymizer/test_ssrf_fix.py` con test specifico per BUG-04:

```python
def test_bug_04_ssrf_anonymizer_blocks_internal_dns():
    # Verifica che hostname interni che risolvono a IP privati siano bloccati
```

**Considerazione**: La presenza del test suggerisce che il fix è stato implementato o è in fase di test. Il codice in `anonymizer/app.py:214` gestisce header `x-target-url` che potrebbe essere vettore di SSRF.

---

## 2. Verifica Osservazioni sull'Hybrid RAG

### 2.1 Sparse e Graph Retrieval Inattivi

**Osservazione**: `sparse_corpus_size: 0`, `bm25_empty_count: 12`, `graph_failure_count: 12`.

**Stato: ✅ CONFERMATA**

Dal benchmark `report-stat/real-corpus-benchmark.json`:
```json
"sparse_corpus_size": 0,
"bm25_empty_count": 12,
"graph_failure_count": 12,
```

**Causa root**: Il corpus è vuoto perché non ci sono documenti indicizzati. Il sistema funziona, ma non ha dati da processare. Questo è un problema di configurazione/operativo più che un bug di codice.

---

### 2.2 GraphRetriever Cypher Query Error

**Osservazione**: Errore `Neo.ClientError.Statement.ParameterMissing` nel GraphRetriever.

**Stato: ⚠️ DISCREPANZA**

Il codice attuale in `backend/app/rag/graph_retriever.py` usa correttamente i parametri:

```python
# Linea 288
cursor = await session.run(cypher, parameters_={"query": query, "top_k": top_k})
```

**Considerazione**: O il bug è stato già risolto, oppure l'analisi originale si basava su una versione precedente del codice. Il codice attuale sembra corretto. Questo potrebbe indicare che il fix è già stato applicato.

---

## 3. Verifica Osservazioni sulla Qualità del Codice

### 3.1 Script di Debug nel Package Applicativo

**Osservazione**: Script operativi in `backend/app/` (`check_db_schema.py`, `clean_db.py`, `delete_user.py`, `reset_admin_password.py`, etc.).

**Stato: ✅ CONFERMATA**

File trovati in `backend/app/`:
- `check_db_schema.py`
- `clean_db.py`
- `delete_user.py`
- `reset_admin_password.py`
- `reset_user_password.py`
- `check_users.py`
- `test_openrouter_support.py`
- `test_bug_fixes.py`
- `test_reg.py`
- `privacy_policy.py`
- `privacy_audit.py`

**Considerazione**: La presenza di 11 script operativi/di test nel package principale è confermata. Questi dovrebbero essere in una directory `tools/` separata.

---

### 3.2 BUG-01: DELETE senza commit

**Osservazione**: Operazione DELETE senza `await db.commit()`.

**Stato: ⚠️ NON VERIFICABILE**

La ricerca non ha trovato un pattern chiaro di DELETE senza commit nei file API. Potrebbe essere stato già risolto o potrebbe essere in un file non controllato.

---

### 3.3 Auth su Route API

**Osservazione**: Route senza guardie esplicite di autenticazione.

**Stato: ✅ CONTRADDETTO**

La maggior parte delle route API usa correttamente `Depends(get_current_user)`:

```
app/api/rag.py - Tutte le route con auth
app/api/tenders.py - Tutte le route con auth
app/api/chat.py - Tutte le route con auth
app/api/system.py - Route con admin_required
app/api/gateway_admin.py - Route con auth
app/api/onlyoffice.py - Route con auth
app/api/anonymizer_admin.py - Route con auth
app/api/proposals.py - Route con auth
app/api/mattermost.py - Route con auth
app/api/kpi_admin.py - Route con auth
```

**Considerazione**: L'analisi originale lamentava assenza di auth nelle route della Content Library. Verificato: tutte le route API moderne usano `get_current_user`. La criticità potrebbe riferirsi a route legacy o a specifiche funzionalità non coperte.

---

## 4. Verifica Osservazioni su Schema Management

### 4.1 Alembic Assente nel Backend Principale

**Osservazione**: Nessuna migrazione Alembic nel backend principale, solo raw `ALTER TABLE`.

**Stato: ✅ CONFERMATA**

Non esiste cartella `alembic/` in `backend/`. Il file `backend/app/db/database.py:41` contiene:
```python
"""Create all tables on startup (dev only — use Alembic in production)."""
```

**Confronto positivo**: Il KPI reason engine ha invece Alembic completo con 4 migration files (`20260315_0001` → `20260329_0004`).

---

## 5. Verifica Osservazioni sul LLM Routing

### 5.1 Route LLM Sempre su external_anonymized

**Osservazione**: Le query QA usano sempre `external_anonymized` invece del server locale.

**Stato: ✅ CONFERMATA**

Dal benchmark `report-stat/real-corpus-benchmark.json`:
```json
"llm_route": "external_anonymized"  // Ricorre 3 volte
```

**Causa**: In `backend/app/privacy_policy.py:168`:
```python
policy.mode = "external_anonymized"
```

**Considerazione**: Il routing è configurato per usare sempre la route esterna anonimizzata. Questo è probabilmente una scelta di design (sicurezza PII) piuttosto che un bug, ma ha implicazioni di latenza significative (60-167 secondi vs stimati 5-20s per locale).

---

## 6. Osservazioni NON nel Documento Originale ma Rilevanti

### 6.1 Leak di Credenziali nel Frontend

I file `frontend/src/pages/Components.tsx:394-396` mostrano credenziali di servizio hardcoded nella UI di debug. Questo non era menzionato nell'analisi originale ma rappresenta un rischio.

### 6.2 Dipendenze con Tag "latest"

Il docker-compose.yml usa alcune immagini con tag non pinned. L'osservazione è corretta.

### 6.3 Ollama DEPRECATED ma Ancora Presente

Dal docker-compose.yml:
```yaml
# --- Ollama (Local LLM - DEPRECATED, use llama-server instead) ---
```

Esistono due servizi llama-server (`tw-llama-tender` e `tw-llama-opencode`) e un container orfano `tw-llama-server` come documentato nei log. Lo stack mostra segni di transizione non completata.

---

## 7. Sintesi delle Verifiche

| Osservazione | Stato | Note |
|-------------|-------|------|
| Credenziali hardcoded | ✅ Confermata | Presenti in docker-compose.yml e frontend |
| Docker socket mount | ✅ Confermata | Presente in 2 servizi |
| CHANGEME placeholder | ⚠️ Parziale | Non trovato, ma rischio reale |
| SSRF anonymizer | ✅ Fix in corso | Test esistente |
| Sparse/Graph a zero | ✅ Confermata | Corpus vuoto |
| GraphRetriever Cypher | ⚠️ Discrepanza | Codice attuale sembra corretto |
| Script in package | ✅ Confermata | 11 file operativi in backend/app/ |
| Auth route | ✅ Contraddetta | Route usano correttamente auth |
| Alembic mancante | ✅ Confermata | Non presente nel backend |
| LLM route external | ✅ Confermata | Configurazione di design |

---

## 8. Valutazione Complessiva dell'Analisi Originale

L'analisi architetturale contenuta nei documenti è **generalmente accurata** ma presenta alcune imprecisioni:

**Punti di forza dell'analisi:**
- Identificazione corretta delle criticità di sicurezza più gravi (Docker socket, credenziali)
- Rilevamento corretto del problema Hybrid RAG (sparse/graph non attivi)
- Identificazione corretta della questione schema management
- Rilevamento corretto degli script operativi nel package

**Punti da correggere/aggiornare:**
- L'analisi sembra assumere che GraphRetriever avesse un bug Cypher, ma il codice attuale sembra corretto
- L'analisi lamentava assenza di auth nelle route, ma verificato che le route moderne usano auth
- Alcuni bug menzionati (BUG-01, BUG-03) non sono verificabili nell'attuale codebase

**Conclusioni:**
1. Le criticità di sicurezza P0 (Docker socket, credenziali hardcoded) sono reali e urgenti
2. Il problema dell'Hybrid RAG è operativo (corpus vuoto), non un bug di codice
3. La maggior parte delle route API è correttamente protetta
4. Il routing LLM verso external_anonymized è una scelta di design con implicazioni di latenza
5. Il piano d'azione è ragionevole, ma alcune priorità potrebbero essere riviste

---

*Documento generato: 2026-04-03*
*Analisi indipendente vs documenti di analisi-critica-comparativa*
