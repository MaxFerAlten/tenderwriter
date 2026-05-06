# Piano: Integrazione Mattermost + Jitsi + Jigasi + Vosk in TenderWriter

## Contesto
L'utente vuole aggiungere videochiamate con trascrizione automatica al progetto TenderWriter. Il flusso: Mattermost gestisce la chat di team, Jitsi Meet le videochiamate, Jigasi cattura l'audio e lo invia a Vosk (STT locale italiano), la trascrizione viene postata nel canale Mattermost. Il frontend deve offrire una scelta tra chat interno attuale e Mattermost.

---

## Allocazione Porte (senza conflitti)

| Servizio | Porta Host | Protocollo |
|---|---|---|
| Mattermost Server | **8065** | TCP |
| Mattermost PostgreSQL | **5433** | TCP |
| Jitsi Web | **8888** | TCP |
| JVB (media) | **10000** | UDP |
| Vosk Server | **2700** | TCP/WS |
| Prosody XMPP | solo interno | - |
| Jicofo | solo interno | - |
| Jigasi | solo interno | - |

---

## FASE 1: Docker Compose - Nuovi servizi

File: `D:\tender\claude\tenderwriter\docker-compose.yml`

### 1.1 Aggiungere 8 servizi (dopo `anonymizer`, prima di `volumes:`)

**Mattermost PostgreSQL** (`tw-mattermost-postgres`)
- Image: `postgres:16-alpine`, porta 5433:5432
- Volume: `mattermost_postgres_data`
- Env: `MM_POSTGRES_USER/PASSWORD/DB`

**Mattermost Server** (`tw-mattermost`)
- Image: `mattermost/mattermost-team-edition:latest`, porta 8065:8065
- Depends on: tw-mattermost-postgres (healthy)
- Env: datasource, site_url, webhooks enabled, bot creation enabled, plugin uploads enabled
- Volumes: config, data, logs, plugins

**Prosody** (`tw-jitsi-prosody`)
- Image: `jitsi/prosody:stable-9823`, solo porte interne
- Env condivise Jitsi: XMPP_DOMAIN, AUTH_DOMAIN, MUC_DOMAIN, passwords

**Jicofo** (`tw-jitsi-jicofo`)
- Image: `jitsi/jicofo:stable-9823`, nessuna porta host
- Depends on: prosody

**JVB** (`tw-jitsi-jvb`)
- Image: `jitsi/jvb:stable-9823`, porta 10000:10000/udp
- Depends on: prosody

**Jitsi Web** (`tw-jitsi-web`)
- Image: `jitsi/web:stable-9823`, porta 8888:80
- Depends on: prosody

**Vosk Server** (`tw-vosk`)
- Image: `alphacep/kaldi-grpc-it:latest` (modello italiano pre-incluso)
- Porta: 2700:2700
- ~1.5GB RAM

**Jigasi** (`tw-jitsi-jigasi`)
- Image: `jitsi/jigasi:stable-9823`, nessuna porta host
- Depends on: prosody, vosk
- Env: `JIGASI_TRANSCRIBER_ENABLED=true`, `JIGASI_TRANSCRIBER_VOSK_URL=ws://tw-vosk:2700`
- Volume condiviso `jitsi_transcripts` per i file di trascrizione

### 1.2 Nuovi volumi
```
mattermost_data, mattermost_config, mattermost_logs, mattermost_plugins
mattermost_postgres_data
jitsi_prosody_config, jitsi_prosody_plugins
jitsi_jicofo_data, jitsi_jvb_data, jitsi_jigasi_data
jitsi_web_config, jitsi_web_crontabs, jitsi_transcripts
```

---

## FASE 2: Variabili d'ambiente

File: `D:\tender\claude\tenderwriter\.env.example`

```
# --- Mattermost ---
MM_POSTGRES_USER=mattermost
MM_POSTGRES_PASSWORD=your-secure-mm-db-password
MM_POSTGRES_DB=mattermost
MM_SITE_URL=http://localhost:8065
MATTERMOST_BASE_URL=http://tw-mattermost:8065
MATTERMOST_BOT_TOKEN=
MATTERMOST_WEBHOOK_SECRET=your-secure-webhook-secret

# --- Jitsi Meet ---
JITSI_PUBLIC_URL=http://localhost:8888
XMPP_DOMAIN=meet.jitsi
XMPP_AUTH_DOMAIN=auth.meet.jitsi
XMPP_MUC_DOMAIN=muc.meet.jitsi
XMPP_INTERNAL_MUC_DOMAIN=internal-muc.meet.jitsi
XMPP_GUEST_DOMAIN=guest.meet.jitsi
JICOFO_AUTH_PASSWORD=changeme-jicofo
JVB_AUTH_PASSWORD=changeme-jvb
JIGASI_XMPP_PASSWORD=changeme-jigasi

# --- Vosk ---
VOSK_SERVER_URL=ws://tw-vosk:2700
```

File: `D:\tender\claude\tenderwriter\backend\app\config.py` - Aggiungere settings Mattermost (pattern KPI)

---

## FASE 3: Backend - Client Mattermost e webhook

### 3.1 Nuovo file: `backend/app/services/mattermost.py`
Pattern da: `backend/app/services/kpi_reason_engine.py`

- `MattermostClient` con httpx async
- Metodi: `post_message(channel_id, message)`, `create_channel(team_id, name)`, `get_channel_by_name()`
- Headers: `Authorization: Bearer {bot_token}`

### 3.2 Nuovo file: `backend/app/api/mattermost_webhook.py`
Router FastAPI:

- `POST /api/v1/mattermost/transcript` - riceve trascrizione da Jigasi/script, valida X-Webhook-Secret, posta in Mattermost
- `POST /api/v1/mattermost/channel-for-tender/{tender_id}` - crea/restituisce canale MM per un tender (naming: `tw-tender-{id}`)

### 3.3 Modello dati
Aggiungere colonna `mattermost_channel_id: str | None` a `ChatRoom` (opzionale, nullable)

### 3.4 Registrare router
In `backend/app/main.py` o dove sono registrati i router, aggiungere il nuovo router

---

## FASE 4: Frontend - Modale di scelta

### 4.1 Nuovo componente: `frontend/src/components/ChatChoiceModal.tsx`
Pattern da: `frontend/src/features/observability/components/ModeSelectorModal.tsx`

- 2 card in griglia: "Chat Interno" (MessageSquare icon) e "Mattermost" (Users icon)
- Animazioni framer-motion, classi CSS `.modal-overlay`, `.modal-content`

### 4.2 Modificare `Dashboard.tsx`
- Nuovo state: `chatChoiceTenderId: number | null`
- `handleOpenChat` apre il modale invece di navigare
- `handleSelectInternalChat` → `navigate(/tenders/${id}/chat)`
- `handleSelectMattermost` → `window.open(MM_URL/tw-tender-${id}, '_blank')`
- Env frontend: `VITE_MATTERMOST_URL=http://localhost:8065`

---

## FASE 5: Script consegna trascrizioni

Script shell montato in Jigasi: `config/jigasi/finalize-transcript.sh`
- Legge il file trascrizione completato da `/tmp/ogg/`
- POST a `http://tw-backend:8000/api/v1/mattermost/transcript` con il webhook secret
- ~15 righe di curl

---

## FASE 6: Configurazione post-deploy (manuale)

1. Aprire `http://localhost:8065`, creare account admin e team
2. Creare bot account "tw-transcriber-bot", copiare token in `.env`
3. Installare plugin Jitsi in Mattermost, configurare URL `http://localhost:8888`
4. Verificare Jitsi aprendo `http://localhost:8888`
5. Test end-to-end: chiamata da Mattermost → Jitsi → trascrizione → post in canale

---

## Ordine di implementazione

1. Docker Compose + env vars (infrastruttura)
2. Backend: config.py + MattermostClient + webhook endpoint
3. Frontend: ChatChoiceModal + Dashboard.tsx
4. Script Jigasi per consegna trascrizioni
5. Documentazione configurazione post-deploy

---

## Verifica

1. `docker compose up -d` → tutti i container sani
2. `http://localhost:8065` → Mattermost accessibile
3. `http://localhost:8888` → Jitsi Meet accessibile
4. Frontend: click "Open Chat" → modale con 2 scelte
5. Scelta "Chat Interno" → naviga alla chat esistente (invariata)
6. Scelta "Mattermost" → apre Mattermost in nuova tab
7. Avviare videocall da Mattermost → Jitsi si apre → Jigasi trascrive → testo postato nel canale

---

## File critici da modificare

| File | Azione |
|---|---|
| `docker-compose.yml` | +8 servizi, +14 volumi |
| `.env.example` | +18 variabili |
| `backend/app/config.py` | +4 settings Mattermost |
| `backend/app/services/mattermost.py` | NUOVO - client httpx |
| `backend/app/api/mattermost_webhook.py` | NUOVO - router webhook |
| `backend/app/models/__init__.py` | +1 colonna su ChatRoom |
| `backend/app/main.py` | Registrare nuovo router |
| `frontend/src/components/ChatChoiceModal.tsx` | NUOVO - modale scelta |
| `frontend/src/pages/Dashboard.tsx` | Modificare handleOpenChat |
| `config/jigasi/finalize-transcript.sh` | NUOVO - script consegna |
