# Keycloak & Mattermost — Ripristino e Configurazione

Data: 2026-03-29
Contesto: Dopo rebuild dei container backend/frontend, Keycloak e Mattermost risultavano non raggiungibili. La chat WebSocket era in fallback polling. Di seguito ogni singola azione eseguita per ripristinare il funzionamento.

---

## 1. Diagnosi iniziale

### 1.1 Stato dei container

Eseguendo `docker compose ps`, Keycloak e il suo PostgreSQL dedicato (`kc-postgres`) non comparivano nella lista dei container attivi. Mattermost (`tw-mattermost`) era anch'esso assente.

Il frontend (`tw-frontend`, porta 3000) e il backend (`tw-backend`, porta 8000) erano attivi e healthy.

### 1.2 Errori nel browser

- **Pagina vuota su `localhost:8180`** — Keycloak non raggiungibile, il login SSO falliva con `ERR_CONNECTION_REFUSED`.
- **Dashboard**: banner giallo `Mattermost integration error: [Errno -2] Name or service not known` — il backend non riusciva a risolvere il DNS interno `mattermost:8065`.
- **Tender Chat**: errore rosso `Realtime disconnected, fallback to polling active` — il WebSocket non si connetteva, la chat cadeva in polling HTTP ogni 10 secondi.
- **Console DevTools**: errori 502 Bad Gateway su `POST /api/tenders/{id}/fullchat` — il reverse proxy nginx non trovava il servizio Mattermost a monte.

---

## 2. Avvio di Keycloak

### 2.1 Configurazione nel docker-compose

Keycloak era definito nel `docker-compose.yml` con:

```yaml
keycloak:
    profiles: [ "keycloak" ]
    image: quay.io/keycloak/keycloak:26.1
    container_name: tw-keycloak
    depends_on:
      kc-postgres:
        condition: service_healthy
    environment:
      KC_BOOTSTRAP_ADMIN_USERNAME: admin
      KC_BOOTSTRAP_ADMIN_PASSWORD: DefaultKCAdmin2026Pass
      KC_HOSTNAME: http://localhost:8180
      KC_HTTP_ENABLED: "true"
    command: start-dev --import-realm
    ports:
      - "8180:8080"
    volumes:
      - ./keycloak/tenderwriter-realm.json:/opt/keycloak/data/import/tenderwriter-realm.json:ro
```

### 2.2 Comando eseguito

```bash
docker compose up -d keycloak kc-postgres
```

Questo ha:
- Creato il volume `tenderwriter_kc_postgres_data`
- Avviato `tw-kc-postgres` (PostgreSQL 16 Alpine dedicato a Keycloak)
- Atteso che `kc-postgres` diventasse healthy
- Avviato `tw-keycloak` con import del realm `tenderwriter`

### 2.3 Verifica health

Dopo circa 50 secondi, Keycloak risultava healthy:

```
tw-keycloak  quay.io/keycloak/keycloak:26.1  Up (healthy)  0.0.0.0:8180->8080/tcp
```

### 2.4 Stato del realm importato

Il file `keycloak/tenderwriter-realm.json` definiva:
- **Realm**: `tenderwriter` (display name: "TenderWriter")
- **Client `tw-frontend`**: pubblico, per il login SSO del frontend
- **Client `mattermost`**: confidenziale, per l'integrazione Mattermost
- **Ruoli realm**: `tw_admin`, `tw_editor`, `tw_viewer`
- **Utenti**: nessuno (array vuoto nel file di import)

---

## 3. Creazione utenti in Keycloak

### 3.1 Problema

Il realm `tenderwriter` aveva 0 utenti. Nessuno poteva fare login via SSO.

### 3.2 Ottenere il token admin

```bash
KC_TOKEN=$(curl -s -X POST \
  "http://localhost:8180/realms/master/protocol/openid-connect/token" \
  -d "grant_type=password&client_id=admin-cli&username=admin&password=DefaultKCAdmin2026Pass" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
```

### 3.3 Creazione utente admin

```bash
curl -s -X POST "http://localhost:8180/admin/realms/tenderwriter/users" \
  -H "Authorization: Bearer $KC_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin@admin.com",
    "email": "admin@admin.com",
    "firstName": "System",
    "lastName": "Admin",
    "enabled": true,
    "emailVerified": true,
    "credentials": [{"type": "password", "value": "TestPass123!", "temporary": false}]
  }'
```

Risposta: HTTP 201 Created.

### 3.4 Creazione utente principale

```bash
curl -s -X POST "http://localhost:8180/admin/realms/tenderwriter/users" \
  -H "Authorization: Bearer $KC_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "registrazioni.hyperknow@gmail.com",
    "email": "registrazioni.hyperknow@gmail.com",
    "firstName": "Massimo",
    "lastName": "Ferrara",
    "enabled": true,
    "emailVerified": true,
    "credentials": [{"type": "password", "value": "TestPass123!", "temporary": false}]
  }'
```

Risposta: HTTP 201 Created.

---

## 4. Assegnazione ruolo admin in Keycloak

### 4.1 Problema

Dopo la creazione, l'utente `admin@admin.com` aveva solo il ruolo `default-roles-tenderwriter`. Il ruolo `tw_admin` non era assegnato. Questo causava:
- Nel DB PostgreSQL dell'app, il ruolo veniva sincronizzato come `editor` (fallback) al login via Keycloak
- L'utente non aveva accesso alle funzionalità admin (es. endpoint `/api/auth/password-hash-stats`)

### 4.2 Mapping ruoli Keycloak -> TenderWriter

Il file `backend/app/auth/keycloak.py` (righe 130-135) mappa:

| Ruolo Keycloak | Ruolo TW |
|----------------|----------|
| `tw_admin` | `admin` |
| `tw_editor` (o nessun ruolo specifico) | `editor` |
| `tw_viewer` | `viewer` |

Il ruolo DB viene aggiornato automaticamente ad ogni login (righe 166-167).

### 4.3 Recupero ID del ruolo tw_admin

```bash
ADMIN_ROLE=$(curl -s \
  "http://localhost:8180/admin/realms/tenderwriter/roles/tw_admin" \
  -H "Authorization: Bearer $KC_TOKEN")
```

Risultato:
```json
{
  "id": "77a5935d-f9ad-4ebe-ae03-717edd40035b",
  "name": "tw_admin",
  "description": "TenderWriter administrator"
}
```

### 4.4 Assegnazione ruolo

```bash
USER_ID="98f1c911-2511-40ca-b2a1-7387bdfcb925"

curl -s -X POST \
  "http://localhost:8180/admin/realms/tenderwriter/users/$USER_ID/role-mappings/realm" \
  -H "Authorization: Bearer $KC_TOKEN" \
  -H "Content-Type: application/json" \
  -d "[$ADMIN_ROLE]"
```

Risposta: HTTP 204 No Content (successo).

### 4.5 Correzione diretta nel DB

Poiche l'utente aveva gia fatto login prima dell'assegnazione del ruolo, il DB aveva ancora `role = 'editor'`. Correzione manuale:

```bash
docker exec tw-backend python -c "
import asyncio
from app.db.database import engine
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
async def main():
    async with AsyncSession(engine) as db:
        await db.execute(text(\"UPDATE users SET role = 'admin' WHERE email = 'admin@admin.com'\"))
        await db.commit()
asyncio.run(main())
"
```

### 4.6 Verifica finale

```
Keycloak roles per admin@admin.com:
  - tw_admin
  - default-roles-tenderwriter

DB role: admin
```

Al prossimo login, il provider hybrid sincronizzera automaticamente il ruolo dal token Keycloak.

---

## 5. Avvio di Mattermost

### 5.1 Configurazione nel docker-compose

Mattermost era nel profilo `videochat`:

```yaml
mattermost:
    profiles: [ "videochat" ]
    image: mattermost/mattermost-team-edition:10.11.8
    container_name: tw-mattermost
    ports:
      - "8065:8065"
```

Il frontend nginx aveva gia la configurazione reverse proxy per `/mm/` verso `http://mattermost:8065`.

### 5.2 Comando eseguito

```bash
docker compose --profile videochat up -d mattermost
```

Questo ha:
- Creato 7 volumi: `mm_data`, `mm_config`, `mm_logs`, `mm_client_plugins`, `mm_bleve_indexes`, `mm_postgres_data`, `mm_plugins`
- Avviato `tw-mm-postgres` (PostgreSQL dedicato a Mattermost)
- Avviato `tw-mm-plugin-oidc` (plugin OIDC per SSO)
- Avviato `tw-mattermost`

### 5.3 Verifica health

Dopo circa 60 secondi:

```
tw-mattermost  mattermost/mattermost-team-edition:10.11.8  Up (healthy)  0.0.0.0:8065->8065/tcp
```

### 5.4 Problema: utente admin Mattermost inesistente

Essendo una prima installazione (nuovi volumi), Mattermost non aveva nessun utente. Il backend TenderWriter tenta di autenticarsi a Mattermost con le credenziali definite in `.env`:

```
MM_ADMIN_USER=tw-admin
MM_ADMIN_PASS=TW2026Secure!Pass
```

Ma l'utente `tw-admin` non esisteva in Mattermost, causando il `401 Unauthorized`.

### 5.5 Nota sulla subpath

Mattermost era configurato con subpath `/mm/`. L'API interna era raggiungibile su `http://localhost:8065/mm/api/v4/...`, non su `http://localhost:8065/api/v4/...`. Verificato con:

```bash
curl -s http://localhost:8065/mm/api/v4/system/ping
# {"status":"OK"}
```

### 5.6 Creazione utente admin via mmctl

Il container Mattermost non ha shell (`sh` non trovato), ma ha `mmctl` disponibile:

```bash
# Creazione utente admin
docker exec tw-mattermost mmctl user create \
  --email tw-admin@tenderwriter.local \
  --username tw-admin \
  --password "TW2026Secure!Pass" \
  --system-admin \
  --local

# Creazione team
docker exec tw-mattermost mmctl team create \
  --name tenderwriter \
  --display-name "TenderWriter" \
  --local

# Aggiunta admin al team
docker exec tw-mattermost mmctl team users add tenderwriter tw-admin --local
```

Ogni comando ha risposto con successo.

### 5.7 Verifica login Mattermost

```bash
curl -s -X POST http://localhost:8065/mm/api/v4/users/login \
  -H "Content-Type: application/json" \
  -d '{"login_id":"tw-admin","password":"TW2026Secure!Pass"}'
```

Risultato: HTTP 200, username `tw-admin` autenticato.

---

## 6. Fix WebSocket della Chat

### 6.1 Problema

La Tender Chat mostrava `Realtime disconnected, fallback to polling active`. Il polling HTTP funzionava (200 OK ogni 10 secondi), ma il WebSocket non si connetteva.

### 6.2 Diagnosi

Il frontend (`TenderChat.tsx`, riga 248-256) costruisce la URL WebSocket:

```typescript
const token = localStorage.getItem('token');
const ws = new WebSocket(buildWsUrl(tenderId, token));
```

Con `AUTH_PROVIDER=hybrid`, il token in localStorage e un token Keycloak (firmato RSA dal realm `tenderwriter`).

Il backend WebSocket handler (`chat.py`, funzione `_get_user_from_ws_token`, riga 165-178) decodava il token esclusivamente con:

```python
payload = jwt.decode(token, settings.app_secret_key, algorithms=[ALGORITHM])
```

Questo funziona solo per JWT locali (HS256 firmati con `app_secret_key`). I token Keycloak (RS256) venivano rifiutati con `JWTError`, e il WebSocket chiudeva con `WS_1008_POLICY_VIOLATION`.

### 6.3 Fix applicata

File: `backend/app/api/chat.py`, funzione `_get_user_from_ws_token`

Prima:
```python
async def _get_user_from_ws_token(token: str, db: AsyncSession) -> UserResponse | None:
    try:
        payload = jwt.decode(token, settings.app_secret_key, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            return None
    except JWTError:
        return None

    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()
    if user is None:
        return None
    return UserResponse.model_validate(user)
```

Dopo:
```python
async def _get_user_from_ws_token(token: str, db: AsyncSession) -> UserResponse | None:
    from app.auth.provider import _get_provider

    try:
        provider = _get_provider()
        return await provider.validate_token(token, db)
    except Exception:
        pass

    # Fallback: try legacy JWT decode for backward compatibility
    try:
        payload = jwt.decode(token, settings.app_secret_key, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            return None
    except JWTError:
        return None

    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()
    if user is None:
        return None
    return UserResponse.model_validate(user)
```

La logica ora:
1. Tenta la validazione tramite il provider attivo (hybrid: prova Keycloak, poi legacy)
2. Se fallisce, fallback al decode JWT locale per retrocompatibilita
3. Questo copre sia token Keycloak (RS256) che token locali (HS256)

### 6.4 Configurazione nginx (gia corretta)

Il reverse proxy nginx del frontend aveva gia la configurazione WebSocket corretta nel blocco `/api`:

```nginx
location /api {
    proxy_pass $backend;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_read_timeout 300;
}
```

Nessuna modifica necessaria lato nginx.

### 6.5 Rebuild e deploy

```bash
cd D:/tender/tenderwriter
docker compose build backend
docker compose up -d backend
```

---

## 7. Configurazione di riferimento (.env)

Valori rilevanti nel file `.env` per Keycloak e Mattermost:

```env
# Auth
AUTH_PROVIDER=hybrid
VITE_AUTH_MODE=hybrid

# Keycloak
KEYCLOAK_URL=http://localhost:8180
KEYCLOAK_INTERNAL_URL=http://keycloak:8080
KEYCLOAK_REALM=tenderwriter
KEYCLOAK_CLIENT_ID=tw-frontend

# Mattermost
MM_SITE_URL=http://localhost:8065
MM_ADMIN_USER=tw-admin
MM_ADMIN_PASS=TW2026Secure!Pass
```

---

## 8. Riepilogo servizi e porte

| Servizio | Container | Porta | Stato |
|----------|-----------|-------|-------|
| Keycloak | `tw-keycloak` | 8180 | Healthy |
| Keycloak DB | `tw-kc-postgres` | 5432 (interna) | Healthy |
| Mattermost | `tw-mattermost` | 8065 | Healthy |
| Mattermost DB | `tw-mm-postgres` | 5432 (interna) | Healthy |
| OIDC Plugin | `tw-mm-plugin-oidc` | - | Running |

---

## 9. Utenti creati

### Keycloak (realm tenderwriter)

| Username | Nome | Ruoli | Password |
|----------|------|-------|----------|
| `admin@admin.com` | System Admin | `tw_admin`, `default-roles-tenderwriter` | `TestPass123!` |
| `registrazioni.hyperknow@gmail.com` | Massimo Ferrara | `default-roles-tenderwriter` | `TestPass123!` |

### Mattermost

| Username | Email | Ruolo | Password |
|----------|-------|-------|----------|
| `tw-admin` | `tw-admin@tenderwriter.local` | System Admin | `TW2026Secure!Pass` |

### PostgreSQL (app)

| Email | Ruolo DB |
|-------|----------|
| `admin@admin.com` | `admin` |
| `registrazioni.hyperknow@gmail.com` | `editor` |

---

## 10. Comandi utili per manutenzione futura

```bash
# Avviare Keycloak (se spento)
docker compose up -d keycloak kc-postgres

# Avviare Mattermost (se spento)
docker compose --profile videochat up -d mattermost

# Creare un nuovo utente Keycloak via API
KC_TOKEN=$(curl -s -X POST \
  "http://localhost:8180/realms/master/protocol/openid-connect/token" \
  -d "grant_type=password&client_id=admin-cli&username=admin&password=DefaultKCAdmin2026Pass" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

curl -X POST "http://localhost:8180/admin/realms/tenderwriter/users" \
  -H "Authorization: Bearer $KC_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "nuovo@utente.com",
    "email": "nuovo@utente.com",
    "firstName": "Nome",
    "lastName": "Cognome",
    "enabled": true,
    "emailVerified": true,
    "credentials": [{"type": "password", "value": "Password123!", "temporary": false}]
  }'

# Creare un nuovo utente Mattermost
docker exec tw-mattermost mmctl user create \
  --email user@example.com \
  --username username \
  --password "Password123!" \
  --local

# Monitorare migrazione hash password
curl -s http://localhost:8000/api/auth/password-hash-stats \
  -H "Authorization: Bearer $TOKEN"

# Console admin Keycloak
# http://localhost:8180/admin (admin / DefaultKCAdmin2026Pass)
```
