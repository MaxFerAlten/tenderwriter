# 🔍 TW-Anonymizer — Analisi Comparativa delle 3 Proposte

> **Data**: 21 Marzo 2026
> **Contesto**: Analisi delle proposte ChatGPT, Gemini e Claude per l'evoluzione del componente `tw-anonymizer` nel progetto TenderWriter.
> **Obiettivo**: Convergere verso una specifica unica, coerente e implementabile.

---

## 1. Panoramica: Cosa Propone Ciascun Modello

| Aspetto | ChatGPT | Gemini | Claude |
|---|---|---|---|
| **Approccio generale** | Iterativo, bottom-up, molto discorsivo | Sintetico, pragmatico, timeline settimanali | Strutturato, architetturale, sprint-based |
| **NER Engine** | Presidio + spaCy | Presidio + spaCy (+ menzione pii-rahna) | Presidio + **pii-rahna** (primario) + spaCy (fallback) |
| **Placeholder** | `<<PERSON_1>>` | `[PERSONA]` generico | `[PERSONA_1]` / Faking con dati sintetici |
| **Reverse mapping** | In-memory (MVP) → Redis (opzionale) | Redis con TTL | Redis con TTL (confermato) |
| **Fallback** | Non chiaro / graceful degradation | Fallback su LLM interno | **Security-first**: fallback obbligatorio su `tw-llama-tender` |
| **Faking strategy** | Non menzionata | Faker (cenno) | ✅ Implementata con pool italiano |
| **Admin UI** | Non menzionata | Pagina nelle impostazioni (cenno) | ✅ Dettagliata con wireframe testuale |
| **Compliance GDPR/AI Act** | Cenno generico | Non trattata | ✅ Sezione dedicata |
| **CIG (codice gara)** | Non menzionato | ✅ Menzionato come recognizer custom | ✅ Previsto come custom recognizer |
| **Profondità codice** | Snippet frammentari, molto ripetitivo | Schematico, pochi snippet | Codice completo per ogni componente |

---

## 2. Punti di Convergenza (Tutti e 3 d'accordo ✅)

Questi punti sono confermati da tutti e 3 i modelli e possiamo considerarli **validati**:

1. **Il servizio `anonymizer/` attuale è solo un proxy SSRF** — va evoluto, non sostituito
2. **Microsoft Presidio** è il framework orchestratore giusto (maturo, estendibile, open-source)
3. **Il punto di inserimento** è tra reranker e generator nel pipeline RAG: `Rerank → Anonymize → LLM`
4. **Endpoint principale**: `POST /anonymize` con input lista di chunk e output chunk anonimizzati + mapping
5. **Endpoint secondario**: `POST /deanonymize` per ripristino (opzionale ma utile)
6. **Redis con TTL** per il reverse mapping (vault ephemeral)
7. **Recognizer custom** necessari per entità italiane strutturate (CF, PIVA, IBAN)
8. **Microservizio separato** (non modulo inline nel backend) — coerente con l'architettura a microservizi esistente
9. **Feature flag** `ANONYMIZER_ENABLED` nella configurazione del backend

---

## 3. Punti di Divergenza e Mia Valutazione

### 3.1 NER Engine: spaCy vs pii-rahna

| | spaCy `it_core_news_lg` | pii-rahna (278M params) |
|---|---|---|
| **Precision su IT** | Buona (~85-90%) | >98% (benchmark pubblicati) |
| **Categorie PII** | ~4 (PER, ORG, LOC, MISC) | 17 categorie specializzate |
| **Dimensione** | ~500MB | ~560MB |
| **GPU richiesta** | No | No (CPU sufficiente) |
| **Maturità** | Alta (anni) | Recente ma validato |
| **Licenza** | MIT | Apache 2.0 |

> [!IMPORTANT]
> **Mia raccomandazione**: Seguo l'approccio di Claude con un **NER backend pluggabile**. Si usa pii-rahna come primario perché è più preciso sull'italiano, ma si mantiene spaCy come fallback. Presidio resta l'orchestratore in entrambi i casi.
>
> ⚠️ **VERIFICA NECESSARIA**: controllare che `pii-rahna` sia effettivamente disponibile su HuggingFace con licenza Apache 2.0 compatibile con uso commerciale. Se no, si parte con spaCy e si aggiunge pii-rahna dopo.

### 3.2 Strategia di Sostituzione: Placeholder vs Faking

- **ChatGPT**: solo placeholder (`<<PERSON_1>>`)
- **Gemini**: placeholder + cenno a Faker
- **Claude**: entrambe le strategie, configurabili dall'admin

> [!TIP]
> **Mia raccomandazione**: servono **entrambe le strategie**, configurabili. Il **REDACTION** (`[PERSONA_1]`) è più sicuro ma l'LLM perde contesto. Il **FAKING** (dati sintetici plausibili) preserva meglio il contesto semantico per l'LLM esterno. La scelta deve essere dell'admin, con REDACTION come default.

### 3.3 Fallback: Graceful Degradation vs Security-First

Questa è la **divergenza più importante**:

- **ChatGPT**: se anonymizer è down → procedi comunque senza anonimizzazione (graceful degradation)
- **Gemini**: fallback su LLM interno (menzionato)
- **Claude**: **security-first obbligatorio** — se anonymizer è down e `anonymizer_enabled=true`, si commuta AUTOMATICAMENTE su `tw-llama-tender` interno. I dati NON escono MAI.

> [!CAUTION]
> **Mia raccomandazione FORTE**: l'approccio security-first di Claude è l'unico corretto. Se l'admin ha ATTIVATO l'anonimizzazione, significa che ha deciso che i dati NON devono uscire in chiaro. Procedere comunque senza anonimizzazione (come suggerisce ChatGPT) sarebbe un **data leak silenzioso** — inaccettabile per GDPR e AI Act. Il fallback su LLM interno è obbligatorio.

### 3.4 Formato Placeholder

- **ChatGPT**: `<<PERSON_1>>` — angle brackets doppi
- **Claude (Perplexity harmonized)**: `[PERSONA_1]` — square brackets

> [!NOTE]
> **Mia raccomandazione**: usare `[PERSONA_1]`, `[ORG_1]`, etc. con label **italiani** (coerente con il dominio). I square brackets sono sufficientemente robusti e meno problematici dei double angle brackets che in alcuni contesti HTML/XML potrebbero creare conflitti. Il formato è già quello usato da Presidio di default.

### 3.5 CIG (Codice Identificativo Gara)

Solo Gemini e Claude menzionano il CIG, che è un identificatore **cruciale** nel dominio gare d'appalto.

> [!IMPORTANT]
> Il CIG (10 caratteri alfanumerici, pattern ANAC) va **assolutamente** incluso come custom recognizer. È un dato specifico del dominio che nessun NER generico rileverà. Tuttavia, come nota Claude: il CIG è già **pubblico** su ANAC — va discusso se ha senso oscurarlo o se è OK lasciarlo visibile.

---

## 4. Problemi Non Affrontati o Affrontati Male

### 4.1 ⚠️ ChatGPT: Troppo Superficiale sulla Sicurezza
Il file ChatGPT è molto lungo e ripetitivo (1854 righe per contenuto che si poteva esprimere in 300), con molteplici "ricapitolami", "dimmi tu", "vuoi il codice?". L'analisi è corretta a livello alto ma:
- Non propone un design di fallback sicuro
- Non considera il CIG
- Non propone la strategia FAKING
- La roadmap è generica ("Fase 1: MVP 1-2 giorni") senza deliverable concreti

### 4.2 ⚠️ Gemini: Troppo Generico sulla Roadmap
Gemini è sintetico e corretto, ma:
- La roadmap è per settimane (Settimana 1-4), troppo vaga
- Non produce codice concreto
- Non approfondisce il fallback di sicurezza
- Non tratta la compliance GDPR/AI Act

### 4.3 ✅ Claude (+ Perplexity): La Proposta Più Completa
Il documento Claude è il più strutturato e completo:
- Codice concreto per ogni componente
- Matrice comportamentale chiara
- Domande aperte esplicite (Sezione 4)
- Roadmap per sprint con deliverable checkbox
- Compliance AI Act/GDPR
- Security-first fallback obbligatorio

**Tuttavia**, anche Claude ha alcune debolezze:
- Il codice dell'engine.py usa un pattern `custom lambda operator` per Presidio che potrebbe non funzionare come previsto (da verificare con i test)
- La stima degli sprint (3-4 giorni per Sprint 1) potrebbe essere ottimistica se si considera il setup di pii-rahna + test

---

## 5. Domande Aperte Prima dell'Implementazione

Queste domande emergono dall'analisi incrociata e vanno chiarite:

### Q1: Modalità Operativa
L'anonimizzazione è sempre attiva quando `ANONYMIZER_ENABLED=true`, o deve essere configurabile per-progetto/per-query?
- **Mia proposta**: globale (`enabled/disabled`), non per-query. Semplifica enormemente l'implementazione.

### Q2: Strategia di Default
Il default è REDACTION (placeholder) o FAKING (dati sintetici)?
- **Mia proposta**: REDACTION come default (più sicuro). FAKING come opzione avanzata.

### Q3: Reverse Mapping — Serve la De-anonimizzazione?
Serve mostrare all'admin il testo originale dato un session_token?
- **Mia proposta**: Sì, ma solo per admin e solo per testing/audit. Non esposto nel flusso utente.

### Q4: CIG — Oscurare o No?
Il CIG è già pubblico su ANAC. Ha senso oscurarlo?
- **Mia proposta**: Rendere il CIG configurabile (ON/OFF) nella sezione entità, con default OFF siccome è informazione pubblica.

### Q5: Dove Fare l'Integrazione — engine.py o generator.py?
- ChatGPT dice `generator.py`
- Claude dice [engine.py](file:///media/marco/DATA2/progettiAi/tenderwriter/backend/app/rag/engine.py) (nel metodo [query()](file:///media/marco/DATA2/progettiAi/tenderwriter/backend/app/rag/engine.py#140-286))
- **Mia raccomandazione**: [engine.py](file:///media/marco/DATA2/progettiAi/tenderwriter/backend/app/rag/engine.py) è il punto corretto — è l'orchestratore. Il Generator deve ricevere chunk già pronti (anonimizzati o meno). L'engine decide il routing.

### Q6: Il Gateway come si integra?
Il [gateway/app.py](file:///media/marco/DATA2/progettiAi/tenderwriter/gateway/app.py) ha già `GATEWAY_ANONYMIZER_URL` configurato e punta a `http://tw-anonymizer:8090`. Attualmente il gateway fa routing verso LLM interni/esterni. Come si coordina con il nuovo flusso anonymizer?
- **Mia proposta**: L'anonymizer è chiamato DIRETTAMENTE dal backend (engine.py), NON dal gateway. Il gateway continua a fare il suo lavoro di proxy LLM. L'anonymizer opera prima che i dati raggiungano il gateway/LLM. Il forward proxy attuale dell'anonymizer viene mantenuto per retrocompatibilità ma non è il flusso principale.

---

## 6. Stato Attuale del Codice (Verificato)

Per completezza, ecco cosa esiste già nel progetto:

| Componente | Stato | File |
|---|---|---|
| [anonymizer/app.py](file:///media/marco/DATA2/progettiAi/tenderwriter/anonymizer/app.py) | ✅ Esiste — proxy SSRF-protected | [app.py](file:///media/marco/DATA2/progettiAi/tenderwriter/anonymizer/app.py) |
| [anonymizer/Dockerfile](file:///media/marco/DATA2/progettiAi/tenderwriter/anonymizer/Dockerfile) | ✅ Esiste — minimale | [Dockerfile](file:///media/marco/DATA2/progettiAi/tenderwriter/anonymizer/Dockerfile) |
| [anonymizer/requirements.txt](file:///media/marco/DATA2/progettiAi/tenderwriter/anonymizer/requirements.txt) | ✅ Esiste — solo fastapi+httpx | [requirements.txt](file:///media/marco/DATA2/progettiAi/tenderwriter/anonymizer/requirements.txt) |
| [docker-compose.yml](file:///media/marco/DATA2/progettiAi/tenderwriter/docker-compose.yml) | ✅ Servizio `anonymizer` già presente su porta 8090 | [docker-compose.yml](file:///media/marco/DATA2/progettiAi/tenderwriter/docker-compose.yml#L399-L407) |
| [backend/app/config.py](file:///media/marco/DATA2/progettiAi/tenderwriter/backend/app/config.py) | ✅ Manca: `ANONYMIZER_URL`, `ANONYMIZER_ENABLED`, `EXTERNAL_LLM_*` | [config.py](file:///media/marco/DATA2/progettiAi/tenderwriter/backend/app/config.py) |
| [backend/app/rag/engine.py](file:///media/marco/DATA2/progettiAi/tenderwriter/backend/app/rag/engine.py) | ✅ Pipeline RAG completa, manca punto anonimizzazione | [engine.py](file:///media/marco/DATA2/progettiAi/tenderwriter/backend/app/rag/engine.py) |
| Redis (`tw-redis`) | ✅ Già nello stack Docker su porta 6379 | docker-compose.yml L170-183 |
| [gateway/app.py](file:///media/marco/DATA2/progettiAi/tenderwriter/gateway/app.py) | ✅ Già configura `GATEWAY_ANONYMIZER_URL` → future-proof | [gateway app.py](file:///media/marco/DATA2/progettiAi/tenderwriter/gateway/app.py) |
| Analisi Perplexity | ✅ Già presente — molto dettagliata | [Tw-anonimizzatore.md](file:///media/marco/DATA2/progettiAi/tenderwriter/resoningfromagentic/perplexity/Tw-anonimizzatore.md) |

---

## 7. Prossimo Step: Specifica Definitiva

Una volta che rispondi alle domande della Sezione 5, produrrò la **specifica tecnica definitiva** con:
- Struttura file completa
- API contract (OpenAPI-style)
- Codice di riferimento per ogni componente
- docker-compose aggiornato
- Task Trello pronti per lo sviluppo

La specifica sarà basata primariamente sulla proposta Claude (la più completa e architetturalmente corretta), integrata con:
- Il NER backend pluggabile (pii-rahna + spaCy)
- La strategia FAKING dal documento Perplexity
- Il CIG recognizer da Gemini/Claude
- Il security-first fallback (unanime Claude/Gemini)
