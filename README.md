# TenderWriter

> Open-source Tender Proposal Writing Software powered by HybridRAG

TenderWriter aiuta i team a creare, gestire e inviare proposte di gara professionali più velocemente, sfruttando un **motore HybridRAG** (Dense + Sparse + Knowledge Graph retrieval) che gira interamente su infrastruttura locale e open-source.

---

## 🚀 Stato Attuale (AS-IS)

Il progetto è in fase attiva di sviluppo. Di seguito le funzionalità e i componenti attualmente implementati e funzionanti:

### 🔐 Authentication & Security
- **Login Tradizionale (legacy/local)**: Utente tecnico `admin@admin.com` con password configurata nel file `.env` (default: `vN7pQ3wL9xR5tY2uA4bC6dE8fG1hJ0`).
- **Login SSO + Tradizionale**: il progetto supporta tre modalità auth configurabili via env:
  - `legacy`: solo login email/password
  - `keycloak`: solo login SSO via Keycloak
  - `hybrid`: doppia modalità, con bottone SSO e form tradizionale attivi insieme
- **Utenti Keycloak → TenderWriter**: nel setup di sviluppo attualmente allineato al realm `tenderwriter` sono usati:
  - `admin@admin.com` / `TestPass123!` → ruolo Keycloak `tw_admin` → ruolo TenderWriter `admin`
  - `registrazioni.hyperknow@gmail.com` / `TestPass123!` → ruolo Keycloak di default → ruolo TenderWriter `editor`
- **Nota Realm Keycloak**: il file di import del realm `tenderwriter` non crea utenti automaticamente; le utenze sopra vanno presenti/create come da procedura di bootstrap.
- **Registrazione Utente**: Flusso completo di registrazione con verifica **2FA tramite OTP**.
- **Mail Testing**: Integrazione con **Mailpit** per catturare le email OTP in ambiente di sviluppo (disponibile a `http://localhost:8025`).
- **Session Management**: Sistema di autenticazione basato su JWT legacy, OIDC Keycloak e React Context con bootstrap runtime.

### 🧠 Motore HybridRAG
- **Dense Retrieval**: Ricerca semantica tramite **Qdrant** (Vector Database).
- **Sparse Retrieval**: Ricerca per parole chiave (BM25) integrata.
- **Knowledge Graph**: Integrazione con **Neo4j** per catturare relazioni complesse tra gare e requisiti.
- **Local LLM**: Generazione e analisi tramite **Ollama** (Llama 3 di default).

### 🖥️ Frontend & Dashboard
- **Interfaccia Moderna**: Design in Dark Mode con estetica premium (Glassmorphism), animazioni fluide e layout centrato per l'auth.
- **System Monitor**: Visualizzazione in tempo reale dello stato dei container Docker, utilizzo CPU/RAM e log live dei componenti (Qdrant, Redis, Ollama, ecc.).
- **Configurazione a Caldo**: Gestione dinamica dei timeout di Nginx direttamente dall'interfaccia di amministrazione.
- **RAG Health**: Dashboard per monitorare lo stato di salute dei singoli componenti del motore AI.

---

## 🛠️ Tech Stack

| Strato | Tecnologia |
|-------|-----------|
| **Backend** | Python 3.11+, FastAPI, SQLAlchemy |
| **Frontend** | React 18, TypeScript, Vite, Framer Motion, Lucide Icons |
| **Database Relazionale** | PostgreSQL 16 |
| **Vector Database** | Qdrant |
| **Graph Database** | Neo4j Community |
| **Object Storage** | MinIO |
| **Infrastruttura AI** | llama.cpp server (Qwen2.5-Coder-7B) |
| **Testing/Developer Tool** | Mailpit (Mock SMTP) |
| **Proxy & Static** | Nginx |

---

## 🚦 Quick Start

Per avviare l'intero stack in locale:

```bash
# 1. Avvia tutti i container
docker compose up -d

# 2. Accedi all'applicazione
# Frontend: http://localhost:3000
# Mailpit (per OTP): http://localhost:8025
# Backend Docs (OpenAPI): http://localhost:8000/docs
```

Per avviare anche il profilo SSO con Keycloak:

```bash
docker compose --profile keycloak up -d
```

Endpoint utili per la modalità SSO:

- Frontend: `http://localhost:3000`
- Keycloak: `http://localhost:8180`
- Mailpit: `http://localhost:8025`

### Modalità di autenticazione

Il comportamento del login dipende da queste variabili:

```env
AUTH_PROVIDER=hybrid
VITE_AUTH_MODE=hybrid
KEYCLOAK_URL=http://localhost:8180
KEYCLOAK_INTERNAL_URL=http://keycloak:8080
MM_EDITION=team
MM_OIDC_ENABLE=false
TW_OIDC_ENABLE=true
MM_LOGIN_REDIRECT_MODE=plugin
```

Significato operativo:

- `AUTH_PROVIDER=legacy` e `VITE_AUTH_MODE=legacy`: solo login tradizionale
- `AUTH_PROVIDER=keycloak` e `VITE_AUTH_MODE=keycloak`: solo login SSO
- `AUTH_PROVIDER=hybrid` e `VITE_AUTH_MODE=hybrid`: login tradizionale + SSO insieme

Con `hybrid`, la pagina `/login` mostra:

- bottone `Accedi con SSO`
- form email/password classico

### Switching Mattermost: Enterprise vs Team/Community

Il progetto supporta due modalità Mattermost, selezionabili solo via configurazione:

- `MM_EDITION=team`: usa Mattermost Team/Community con plugin `com.tenderwriter.oidc` ed è il default
- `MM_EDITION=enterprise`: usa Mattermost Enterprise/Entry con OIDC nativo

Configurazione di default per Team/Community:

```env
MM_EDITION=team
MM_OIDC_ENABLE=false
TW_OIDC_ENABLE=true
MM_LOGIN_REDIRECT_MODE=plugin
```

Configurazione alternativa per Enterprise/Entry:

```env
MM_EDITION=enterprise
MM_OIDC_ENABLE=true
TW_OIDC_ENABLE=false
MM_LOGIN_REDIRECT_MODE=off
```

Note operative:

- il realm Keycloak importato include già entrambe le callback Mattermost:
  - `http://localhost:3000/mm/signup/openid/complete`
  - `http://localhost:3000/mm/plugins/com.tenderwriter.oidc/callback`
- in modalità `team`, l’accesso diretto a `http://localhost:3000/mm/login` può essere reindirizzato al plugin solo se `MM_LOGIN_REDIRECT_MODE=plugin`
- in modalità `hybrid`, solo le sessioni TenderWriter autenticate via Keycloak usano l’SSO Mattermost; i login tradizionali continuano a usare il fallback legacy

Switch rapido da terminale:

```powershell
# passa a Team/Community + plugin
.\utility\switch-mattermost-mode.ps1 team

# passa a Enterprise/Entry + OIDC nativo
.\utility\switch-mattermost-mode.ps1 enterprise

# aggiorna solo .env senza riavviare i container
.\utility\switch-mattermost-mode.ps1 team -NoRestart
```

### Credenziali di sviluppo

Account locale legacy:

- Email: `admin@admin.com`
- Password: valore presente in `.env` oppure default `vN7pQ3wL9xR5tY2uA4bC6dE8fG1hJ0`

Utenti Keycloak sincronizzati su TenderWriter:

- `admin@admin.com` / `TestPass123!`
  - Realm: `tenderwriter`
  - Ruolo Keycloak: `tw_admin`
  - Ruolo applicativo TenderWriter: `admin`
- `registrazioni.hyperknow@gmail.com` / `TestPass123!`
  - Realm: `tenderwriter`
  - Ruolo Keycloak: `default-roles-tenderwriter`
  - Ruolo applicativo TenderWriter: `editor`

Admin console Keycloak:

- URL: `http://localhost:8180/admin`
- Username: `admin`
- Password: `DefaultKCAdmin2026Pass`

Mattermost system admin:

- Username: `tw-admin`
- Email: `tw-admin@tenderwriter.local`
- Password: `TW2026Secure!Pass`

Nota:

- In modalità `hybrid`, puoi usare sia il login tradizionale locale sia gli utenti Keycloak sopra.
- In modalità `keycloak` pura, il login tradizionale viene disabilitato volutamente.
- Il realm `tenderwriter` importato da file non include utenti di default: se ricrei i volumi Keycloak devi ricreare anche queste utenze.

### Configurazione Email (Mailpit)
Il sistema è configurato per inviare le email a un server SMTP locale (Mailpit). Non è necessaria alcuna configurazione SMTP reale per lo sviluppo. Per vedere i codici OTP:
1. Registrati nell'app (es. `test@example.com`).
2. Apri `http://localhost:8025` nel browser.
3. Copia il codice e inseriscilo nel frontend.

### Stack Video Collaboration (Opzionale)
Mattermost, Jitsi, Vosk e il forwarder delle trascrizioni sono dietro al profilo `videochat`, quindi non partono con il normale `docker compose up -d`.

Per avviare anche la collaborazione video:
```bash
docker compose --profile videochat up -d \
  mm-postgres mattermost \
  jitsi-prosody jitsi-jicofo jitsi-jvb jitsi-web vosk jitsi-jigasi \
  transcript-forwarder
```

Note operative:
- `transcript-forwarder` resta in idle se `MM_TRANSCRIPT_WEBHOOK_URL` non è configurata.
- Il pulsante Mattermost nel frontend usa l'host corrente come fallback, quindi funziona anche se accedi alla dashboard da un IP/LAN e non da `localhost`.

---

## 🔧 Sviluppo & Debug

### Backend Debug
Il backend è configurato con log dettagliati. Puoi monitorarli con:
```bash
docker logs -f tw-backend
```
### cancellare gli user 
```bash
docker exec tw-backend sh -c "export PYTHONPATH=/app && python3 app/delete_user.py"
docker compose build backend
```

### Frontend Build
Poiché il frontend viene servito da Nginx, dopo modifiche strutturali è necessario ricostruire l'immagine:
```bash
docker compose build frontend
docker compose up -d frontend
```

### Backend Debug
Il backend è ora in funzione con:

✅ Validazione secret al startup
✅ Rate limiting (3/min register, 5/min login)
✅ Storage MinIO per OnlyOffice
✅ Valori di default cambiati nel docker-compose

Nota: Le password di default sono ora DefaultPg2024Pass, DefaultNEO4J2024Pass, DefaultMinIO2024Pass. In produzione dovresti usarne di più sicure e memorizzarle in un vault.

Credenziali temporanee per test:

- Legacy locale: `admin@admin.com` / valore in `.env`
- Keycloak/TenderWriter admin: `admin@admin.com` / `TestPass123!`
- Keycloak/TenderWriter editor: `registrazioni.hyperknow@gmail.com` / `TestPass123!`
- Mattermost admin: `tw-admin` / `TW2026Secure!Pass`
---

## 🗺️ Roadmap Prossimi Passi
- [ ] Integrazione completa della ricerca AI con cronologia utente.
- [ ] Export professionale in PDF/Docx.
- [ ] Raffinamento del Compliance Matrix per la mappatura automatica dei bandi.


### usare repomix per ottenere un md file da dare a LLM esternmi per analisi architetturali e bug fix e robustezza
Occorre installare repomix: 
```
curl -fsSL https://raw.githubusercontent.com/repomix/repomix/main/install.sh | bash
```
poi: 
```
repomix --style markdown
```
se non funziona repomix per vari motivi di conflitti con altri tool si può usare: 
```
docker pull ghcr.io/yamadashy/repomix:latest
docker run --rm -v "d:/tender/tenderwriter:/app" ghcr.io/yamadashy/repomix .
📦 Repomix v1.11.0
No custom config found at repomix.config.ts, repomix.co
✔ Packing completed successfully!      
```
consigliamo di usare repomix in locale con nvm per evitare conflitti con altri tool aggiornare nvm alla versione 20.11.1 (64-bit) con nvm install 20.11. 

E' utile avere repomix file md o xml per analisi architetturali e bug fix e robustezza in pdf per certi llm quindi:

pip install markdown-pdf

bash
# Crea l'ambiente
python -m venv venv

# Attivalo
.\venv\Scripts\activate

# Installa solo quello che ti serve qui
pip install markdown-pdf 

# per convertire il file md in pdf
python convert-md-to-pdf.py


# NEO4J
Tutti i nodi Tender
MATCH (t:Tender) RETURN t LIMIT 25
2. Nodi correlati a Tender con relazioni
MATCH (t:Tender)-[r]->(n) 
RETURN t.id as tender, type(r) as relazione, labels(n)[0] as tipo_nodo, n.name as nome
3. Visualizzazione completa grafo
MATCH (n) RETURN n
4. Solo nodi Tender con loro requisiti
MATCH (t:Tender)-[:HAS_REQUIREMENT]->(r:Requirement)
RETURN t.id, t.title, r.id, r.description
5. Statistiche nodi
MATCH (n) 
RETURN labels(n)[0] as Tipo, count(*) as Quantita
ORDER BY Quantita DESC
Nota: Il database Neo4j sembra vuoto. I nodi vengono creati quando inserisci dati nel sistema (es. tenders, proposals). Per popolare il grafo, usa la funzionalità RAG di TenderWriter.



```
Utilizzo:
Celery Worker - esegue i task in background
Redis - gestisce la coda dei messaggi tra backend e worker
Quando avvii un task (Index/Generate/Export), il backend invia il messaggio a Redis → Celery Worker lo preleva ed esegue il task.


Vai su http://localhost:7474
Inserisci:
Username: neo4j
Password: DefaultNEO4J2024Pass

Configurazione:
Apri http://localhost:8001
Connettiti a Redis:
Host: redis (dal container) o localhost (dal host)
Port: 6379
---

## 🤖 OpenCode - AI Coding Agent

TenderWriter include **OpenCode**, un agente AI per coding che gira localmente con un LLM dedicato.

### Architettura

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    OpenCode + Codebase + LLM                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────────────┐   │
│  │  tw-opencode │────▶│ tw-codebase  │     │   tw-llama-server    │   │
│  │  (agente AI) │     │ (sorgente)   │     │  (Qwen2.5-Coder 7B)│   │
│  └──────────────┘     └──────────────┘     └──────────────────────┘   │
│         │                     │                      │                 │
│         │            /workspace/codebase           http://localhost:8080│
│         │                     │                      │                 │
│         └─────────────────────┴──────────────────────┘                 │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                     Provider Supportati                           │  │
│  │  1. Locale: llama.cpp (Qwen2.5-Coder 7B)                      │  │
│  │  2. Cloud: Anthropic (Claude) - richiede API key               │  │
│  │  3. Cloud: OpenAI (GPT-4.1) - richiede API key                 │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

### Servizi

| Servizio | Container | Descrizione |
|----------|-----------|-------------|
| LLM Server | tw-llama-server | Qwen2.5-Coder:7B (porta 8080) |
| OpenCode | tw-opencode | Agente AI |
| Codebase | tw-codebase | Codice sorgente montato |

### Come Usare

```bash
# 1. Entrare nel container OpenCode
docker compose exec opencode bash

# 2. Avviare OpenCode
opencode

# 3. Il codice è disponibile in /workspace/codebase
cd /workspace/codebase
ls -la  # Vedrai backend/ e frontend/
```

### Cambiare Provider/Modello

```bash
# Vedere modelli disponibili (locale + cloud)
/models

# Usare modello locale (default)
/use llama-cpp/qwen2.5-coder-7b

# Usare Claude (richiede ANTHROPIC_API_KEY)
/use anthropic/claude-sonnet-4-20250514

# Usare GPT-4.1 (richiede OPENAI_API_KEY)
/use openai/gpt-4.1
```

### Configurazione API Cloud

Per usare modelli cloud, imposta le variabili d'ambiente:

```bash
# Nel docker-compose o .env
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
```

Oppure passa le variabili all'avvio:

```bash
docker compose exec -e ANTHROPIC_API_KEY=sk-ant-... opencode bash
```

### Comandi Utili

```bash
# Vedere i modelli disponibili
/models

# Cambiare modello
/use llama-cpp/qwen2.5-coder-7b

# Analizzare il codice corrente
analyze the codebase

# Chiedere aiuto
/help
```

### Configurazione

Il file `opencode.json` supporta:

| Provider | Modello | Tipo |
|----------|---------|------|
| llama-cpp | qwen2.5-coder-7b | Locale (default) |
| anthropic | claude-sonnet-4 | Cloud |
| openai | gpt-4.1 | Cloud |

### Risoluzione Problemi

```bash
# Verificare che il server LLM sia attivo
curl http://localhost:8080/v1/models

# Vedere i log di llama-server
docker compose logs llama-server

# Vedere i log di OpenCode
docker compose logs opencode

# Verificare che il codebase sia montato
docker compose exec opencode ls -la /workspace/codebase
```

---

*Progetto sviluppato con ❤️ per l'efficienza nelle gare d'appalto.*
```
