# TenderWriter

> Open-source Tender Proposal Writing Software powered by HybridRAG

TenderWriter aiuta i team a creare, gestire e inviare proposte di gara professionali più velocemente, sfruttando un **motore HybridRAG** (Dense + Sparse + Knowledge Graph retrieval) che gira interamente su infrastruttura locale e open-source.

---

## 🚀 Stato Attuale (AS-IS)

Il progetto è in fase attiva di sviluppo. Di seguito le funzionalità e i componenti attualmente implementati e funzionanti:

### 🔐 Authentication & Security
- **Login Tecnico**: Utente `admin@admin.com` con password `admin` pre-configurato.
- **Registrazione Utente**: Flusso completo di registrazione con verifica **2FA tramite OTP**.
- **Mail Testing**: Integrazione con **Mailpit** per catturare le email OTP in ambiente di sviluppo (disponibile a `http://localhost:8025`).
- **Session Management**: Sistema di autenticazione basato su JWT e React Context.

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
| **Infrastruttura AI** | Ollama |
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

### Configurazione Email (Mailpit)
Il sistema è configurato per inviare le email a un server SMTP locale (Mailpit). Non è necessaria alcuna configurazione SMTP reale per lo sviluppo. Per vedere i codici OTP:
1. Registrati nell'app (es. `test@example.com`).
2. Apri `http://localhost:8025` nel browser.
3. Copia il codice e inseriscilo nel frontend.

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

Email: admin@admin.com
Password: vN7pQ3wL9xR5tY2uA4bC6dE8fG1hJ0
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
*Progetto sviluppato con ❤️ per l'efficienza nelle gare d'appalto.*
```