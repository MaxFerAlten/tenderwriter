# TenderWriter - Stato debug registrazione

Data: 2026-03-27

## Obiettivo

Capire perche la registrazione fallisce e velocizzare il ciclo di build/startup del backend.

## Stato attuale

- Il problema di lentezza della build Docker del backend e stato ridotto in modo netto.
- La registrazione non funziona ancora, ma il blocco attuale non e piu la build Docker.
- Il backend `tw-backend` resta bloccato prima di aprire la porta `8000`, quindi `/health` e `/api/auth/register` falliscono per connessione rifiutata o chiusa.

## Miglioramenti gia applicati

### 1. Build Docker backend molto piu veloce

File toccato:

- `backend/.dockerignore`

Causa trovata:

- `backend/.venv` veniva incluso nel contesto Docker.
- Solo `backend/.venv` pesava circa `647M`.

Esito misurato:

- Prima il contesto Docker backend arrivava a oltre `500MB`.
- Dopo la modifica, `docker compose build backend` trasferisce pochi KB:
  esempio osservato `3.71kB`.

### 2. Backend senza reloader quando `APP_DEBUG=false`

File toccato:

- `backend/Dockerfile`

Modifica:

- `uvicorn --reload` ora parte solo se `APP_DEBUG=true`.
- Con `.env` attuale (`APP_DEBUG=false`) il backend usa un solo processo `uvicorn`.

### 3. Inizializzazione RAG resa non bloccante lato codice

File toccati:

- `backend/app/main.py`
- `backend/app/rag/engine.py`
- `backend/app/api/tenders.py`
- `backend/app/api/onlyoffice.py`
- `backend/tests/test_main_route_registration.py`

Idea applicata:

- Il motore RAG non dovrebbe piu bloccare il flusso auth all'avvio.
- Gli endpoint che ne hanno bisogno chiamano `ensure_initialized()`.

## Verifiche gia fatte

### Build backend

- `docker compose build backend`
- Dopo il fix del `.dockerignore`, la build e tornata rapida e quasi tutta in cache.

### Stato runtime backend

Verifiche effettuate:

- `curl http://localhost:8000/health`
- `curl -X POST http://localhost:8000/api/auth/register ...`
- test connessione a `127.0.0.1:8000` dall'interno del container

Esito:

- la porta `8000` non risulta in ascolto dentro `tw-backend`
- connessione interna fallita con `ConnectionRefusedError(111, 'Connection refused')`
- il container e `Up`, ma Uvicorn non ha ancora aperto la socket

### Misure mirate

- import layer database: circa `0.49s`
- `init_db()`: circa `4.54s`
- import singoli router: in genere rapido, circa `0.01s` - `1.4s`

Conclusione provvisoria:

- il freeze del backend non sembra dovuto al solo `init_db()`
- il backend resta bloccato durante il bootstrap complessivo, prima del bind della porta
- serve isolare con precisione cosa impedisce a Uvicorn/FastAPI di completare startup e bind

## Ultimo sintomo confermato

Comando interno al container:

- tentativo di connessione a `127.0.0.1:8000`

Risultato:

- `connect-fail ConnectionRefusedError(111, 'Connection refused')`

## File modificati in questa sessione

- `backend/.dockerignore`
- `backend/Dockerfile`
- `backend/app/main.py`
- `backend/app/rag/engine.py`
- `backend/app/api/tenders.py`
- `backend/app/api/onlyoffice.py`
- `backend/tests/test_main_route_registration.py`

Nota:

- `backend/Dockerfile` era gia modificato anche prima in questa sessione per il preinstall di torch CPU.
- Non sono state revertite modifiche utente.

## Prossimo passo consigliato

1. Isolare il punto esatto del blocco di startup del backend.
2. Strumentare `lifespan` con log ancora piu granulari immediatamente prima e dopo ogni step.
3. Verificare se il blocco avviene:
   - dentro startup FastAPI
   - durante l'avvio di Uvicorn
   - o in una side effect non visibile nei log correnti
4. Solo dopo, ritestare:
   - `GET /health`
   - `POST /api/auth/register`

## Comando utile da ripetere domani

Per verificare se il backend apre davvero la porta dall'interno del container:

```bash
docker exec tw-backend sh -lc 'python - <<\"PY\"
import socket
s=socket.socket(); s.settimeout(3)
try:
    s.connect((\"127.0.0.1\",8000)); print(\"connect-ok\")
except Exception as e:
    print(\"connect-fail\", repr(e))
finally:
    s.close()
PY'
```
