# TenderWriter — Checklist minima di avvio locale

Questa checklist serve per avviare **frontend + backend + dipendenze** in locale ed evitare errori comuni (es. DB non raggiungibile).

## 1) Prerequisiti

- Docker + Docker Compose installati
- Node.js 18+ e npm
- Python 3.11+

## 2) Configurazione ambiente

1. Copia il file di esempio delle variabili:
   ```bash
   cp .env.example .env
   ```
2. Verifica che le variabili nel `.env` siano coerenti con i servizi Docker (porte/host).

## 3) Avvio stack dipendenze (consigliato)

Dalla root del repository:

```bash
docker compose up -d
```

Servizi attesi:
- PostgreSQL
- Redis
- Qdrant
- Neo4j
- MinIO
- (eventuali altri servizi definiti in `docker-compose.yml`)

## 4) Avvio backend

```bash
cd backend
pip install -e ".[dev]"
python3 verify_imports.py
uvicorn app.main:app --reload --port 8000
```

Controlli rapidi:
- API docs: <http://localhost:8000/docs>
- Se ricevi `ConnectionRefusedError`, quasi sempre il database/servizi non sono ancora pronti.

## 5) Avvio frontend

In un altro terminale:

```bash
cd frontend
npm install
npm run dev
```

Controllo rapido:
- UI: <http://localhost:3000>

## 6) Test rapidi

Frontend:
```bash
cd frontend
npm test -- --run
```

Backend (check import essenziali):
```bash
cd backend
python3 verify_imports.py
```

## 7) Troubleshooting veloce

- **`docker: command not found`**: installa Docker Desktop / Docker Engine.
- **Backend non parte con errore DB**: esegui `docker compose ps`, verifica che PostgreSQL sia `healthy` o in stato `running`.
- **Frontend parte ma backend no**: verifica variabili DB nel `.env` e la porta usata dal backend (`8000`).

## 8) Spegnimento

```bash
docker compose down
```
