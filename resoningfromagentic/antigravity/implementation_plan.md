# Integrazione Keycloak in TenderWriter

Sostituire il sistema di autenticazione custom (JWT + OTP) con **Keycloak** come Identity Provider centralizzato, usando il protocollo **OpenID Connect (OIDC)**.

## Stato Attuale

| Componente | Auth attuale |
|---|---|
| **Backend** ([auth.py](file:///d:/tender/tenderwriter/backend/app/api/auth.py)) | JWT custom (jose), password pbkdf2, OTP via SMTP, [get_current_user](file:///d:/tender/tenderwriter/backend/app/api/auth.py#296-321) usato in 12 router |
| **Frontend** ([AuthContext.tsx](file:///d:/tender/tenderwriter/frontend/src/contexts/AuthContext.tsx)) | Login form → POST `/api/auth/login` → localStorage token |
| **KPI Reason Engine** ([auth.py](file:///d:/tender/tenderwriter/backend/app/api/auth.py)) | Static service token via `X-Service-Token` header |
| **OnlyOffice** | JWT signing con `onlyoffice_jwt_secret` (separato, non tocchiamo) |

## User Review Required

> [!IMPORTANT]
> **Decisione: strategia di migrazione**
> Propongo un approccio **ibrido con feature flag** — il backend accetta **sia** JWT Keycloak **sia** JWT legacy durante la transizione. Questo permette di migrare gradualmente senza downtime. Alla fine della migrazione, il flag viene disabilitato e il JWT legacy rimosso.
>
> Alternativa: big-bang switch (più semplice ma richiede migrazione utenti simultanea).

> [!WARNING]
> **Utenti esistenti**: gli utenti nel DB PostgreSQL dovranno essere importati in Keycloak. Propongo di creare uno script di migrazione che li esporti nel formato Keycloak JSON. Le password NON sono migrabili (pbkdf2_sha256 → Keycloak bcrypt), quindi gli utenti dovranno fare **reset password** al primo login post-migrazione.

> [!IMPORTANT]
> **Scope della prima fase**: propongo di NON migrare il service-to-service auth (KPI engine ↔ backend) a Keycloak service accounts nella prima fase. Il token statico `X-Service-Token` è adeguato per comunicazione interna Docker. Possiamo farlo in una fase successiva.

---

## Proposed Changes

### Infrastruttura Docker

#### [NEW] `keycloak/realm-export.json`

Configurazione pre-configurata del realm `tenderwriter`:
- Client `tw-backend` (confidential, per il backend)
- Client `tw-frontend` (public, per il frontend SPA)
- Realm roles: `admin`, `editor`, `viewer`
- Default role mapping: nuovi utenti → `editor`

#### [MODIFY] [docker-compose.yml](file:///d:/tender/tenderwriter/docker-compose.yml)

Aggiungere il servizio Keycloak:
```yaml
keycloak:
  image: quay.io/keycloak/keycloak:26.0
  container_name: tw-keycloak
  restart: unless-stopped
  command: start-dev --import-realm
  environment:
    KC_DB: postgres
    KC_DB_URL: jdbc:postgresql://postgres:5432/${POSTGRES_DB:-tenderwriter}
    KC_DB_USERNAME: ${POSTGRES_USER:-tenderwriter}
    KC_DB_PASSWORD: ${POSTGRES_PASSWORD:-DefaultPg2024Pass}
    KC_DB_SCHEMA: keycloak
    KEYCLOAK_ADMIN: ${KEYCLOAK_ADMIN:-admin}
    KEYCLOAK_ADMIN_PASSWORD: ${KEYCLOAK_ADMIN_PASSWORD:-admin}
    KC_HOSTNAME_STRICT: "false"
    KC_PROXY_HEADERS: xforwarded
    KC_HTTP_ENABLED: "true"
  volumes:
    - ./keycloak/realm-export.json:/opt/keycloak/data/import/realm-export.json:ro
  ports:
    - "8180:8080"
  depends_on:
    postgres:
      condition: service_healthy
```

> Keycloak condivide PostgreSQL (schema separato `keycloak`), evitando un nuovo DB.

---

### Backend

#### [NEW] `backend/app/api/auth_keycloak.py`

Nuovo modulo di autenticazione OIDC:
- Fetch JWKS da `{KEYCLOAK_URL}/realms/tenderwriter/protocol/openid-connect/certs` (con cache in-memory)
- Validazione token: issuer, audience, expiration, signature
- Estrazione claims: [sub](file:///d:/tender/tenderwriter/backend/app/api/proposals.py#723-783), [email](file:///d:/tender/tenderwriter/backend/app/api/auth.py#99-109), `preferred_username`, `realm_access.roles`
- Funzione `get_current_user_keycloak()` che ritorna lo stesso [UserResponse](file:///d:/tender/tenderwriter/backend/app/api/auth.py#63-70) schema
- Auto-provisioning: se l'utente non esiste nel DB locale, lo crea automaticamente dal token Keycloak

```python
# Pseudocodice
async def get_current_user(token: str = Depends(oauth2_scheme), db = Depends(get_db)):
    if settings.auth_provider == "keycloak":
        return await _validate_keycloak_token(token, db)
    else:
        return await _validate_legacy_token(token, db)
```

#### [MODIFY] [auth.py](file:///d:/tender/tenderwriter/backend/app/api/auth.py)

- Rinominare [get_current_user](file:///d:/tender/tenderwriter/backend/app/api/auth.py#296-321) → `_validate_legacy_token` (funzione interna)
- Creare nuovo [get_current_user](file:///d:/tender/tenderwriter/backend/app/api/auth.py#296-321) che fa dispatch basato su `settings.auth_provider`
- Mantenere gli endpoint `/login`, `/register`, `/verify-otp` funzionanti (legacy mode)
- Aggiungere endpoint `/auth/keycloak/callback` per il backend-side token exchange (opzionale)

#### [MODIFY] [config.py](file:///d:/tender/tenderwriter/backend/app/config.py)

Nuove settings:
```python
# Keycloak
auth_provider: str = "legacy"  # "legacy" | "keycloak"
keycloak_url: str = "http://tw-keycloak:8080"
keycloak_realm: str = "tenderwriter"
keycloak_client_id: str = "tw-backend"
keycloak_client_secret: str = ""
```

#### [MODIFY] [models/__init__.py](file:///d:/tender/tenderwriter/backend/app/models/__init__.py)

Aggiungere al modello [User](file:///d:/tender/tenderwriter/backend/app/models/__init__.py#90-130):
```python
keycloak_sub = Column(String(255), unique=True, nullable=True, index=True)
```

Campo opzionale per collegare l'utente locale al subject ID di Keycloak.

#### [NEW] `backend/alembic/versions/xxx_add_keycloak_sub.py`

Migrazione Alembic per aggiungere la colonna `keycloak_sub`.

---

### Frontend

#### [MODIFY] [package.json](file:///d:/tender/tenderwriter/frontend/package.json)

Aggiungere dipendenza:
```json
"keycloak-js": "^26.0.0"
```

#### [NEW] `frontend/src/lib/keycloak.ts`

Inizializzazione del client Keycloak:
```typescript
import Keycloak from 'keycloak-js';

export const keycloak = new Keycloak({
  url: import.meta.env.VITE_KEYCLOAK_URL || 'http://localhost:8180',
  realm: 'tenderwriter',
  clientId: 'tw-frontend',
});
```

#### [MODIFY] [AuthContext.tsx](file:///d:/tender/tenderwriter/frontend/src/contexts/AuthContext.tsx)

Refactor basato su feature flag `VITE_AUTH_PROVIDER`:
- **`keycloak`**: usa `keycloak.init()` → redirect a Keycloak login → token in memoria (NOT localStorage) → auto-refresh via `keycloak.updateToken()`
- **`legacy`**: mantiene il flusso attuale (form login, localStorage)

```typescript
// Pseudocodice
if (import.meta.env.VITE_AUTH_PROVIDER === 'keycloak') {
  keycloak.init({ onLoad: 'login-required' }).then(authenticated => {
    if (authenticated) setUser(parseKeycloakToken(keycloak));
  });
} else {
  // legacy flow (esistente)
}
```

#### [MODIFY] [Login.tsx](file:///d:/tender/tenderwriter/frontend/src/pages/Login.tsx) e [Register.tsx](file:///d:/tender/tenderwriter/frontend/src/pages/Register.tsx)

- In modalità Keycloak: redirect automatico a Keycloak (queste pagine non vengono mostrate)
- In modalità legacy: comportamento invariato

#### [MODIFY] [App.tsx](file:///d:/tender/tenderwriter/frontend/src/App.tsx)

- Il logout chiama `keycloak.logout()` in modalità Keycloak
- Il token viene passato nell'header `Authorization: Bearer` come prima

---

### File di Configurazione

#### [MODIFY] [.env](file:///d:/tender/tenderwriter/.env)

Aggiungere:
```env
# Keycloak
AUTH_PROVIDER=legacy
KEYCLOAK_ADMIN=admin
KEYCLOAK_ADMIN_PASSWORD=admin
KEYCLOAK_URL=http://tw-keycloak:8080
KEYCLOAK_REALM=tenderwriter
KEYCLOAK_CLIENT_ID=tw-backend
KEYCLOAK_CLIENT_SECRET=<generato>
VITE_AUTH_PROVIDER=legacy
VITE_KEYCLOAK_URL=http://localhost:8180
```

#### [NEW] `scripts/migrate_users_to_keycloak.py`

Script standalone per esportare gli utenti dal DB PostgreSQL al formato Keycloak JSON import. Gli utenti migrarti dovranno fare reset password.

---

## Piano delle Fasi

```mermaid
graph LR
    A[Fase 1<br/>Infra] --> B[Fase 2<br/>Backend]
    B --> C[Fase 3<br/>Frontend]
    C --> D[Fase 4<br/>Migrazione utenti]
    D --> E[Fase 5<br/>Switch AUTH_PROVIDER]
    
    style A fill:#1e3a5f,stroke:#3b82f6
    style B fill:#1e3a5f,stroke:#3b82f6
    style C fill:#1e3a5f,stroke:#3b82f6
    style D fill:#3b1f2b,stroke:#ef4444
    style E fill:#1f3b2b,stroke:#10b981
```

| Fase | Scope | Rischio |
|---|---|---|
| 1 | Docker Compose + realm config | Basso — container indipendente |
| 2 | Backend OIDC validation + auto-provisioning | Medio — tocca [get_current_user](file:///d:/tender/tenderwriter/backend/app/api/auth.py#296-321) |
| 3 | Frontend keycloak-js | Medio — cambia il flusso di login |
| 4 | Script migrazione utenti | Alto — richiede reset password utenti |
| 5 | Switch `AUTH_PROVIDER=keycloak` | Alto — point of no return |

---

## Verification Plan

### Test Automatici Esistenti

Nella directory `backend/tests/` sono presenti 11 file di test. Tuttavia, nessuno copre direttamente l'autenticazione (sono test funzionali per compliance, KPI, tenders ecc.). Il testing della migrazione Keycloak sarà prevalentemente manuale e di integrazione.

### Test Manuali

**Fase 1 — Keycloak Container:**
1. `docker compose up keycloak -d`
2. Aprire `http://localhost:8180` → dovrebbe mostrare la console admin di Keycloak
3. Login con `admin`/`admin`
4. Verificare che il realm `tenderwriter` esista con i client `tw-backend` e `tw-frontend`

**Fase 2 — Backend OIDC:**
1. Impostare `.env`: `AUTH_PROVIDER=keycloak`
2. Ottenere un token da Keycloak:
   ```bash
   curl -X POST http://localhost:8180/realms/tenderwriter/protocol/openid-connect/token \
     -d "grant_type=password&client_id=tw-frontend&username=testuser&password=testpass"
   ```
3. Chiamare il backend con il token:
   ```bash
   curl -H "Authorization: Bearer <token>" http://localhost:8000/api/auth/me
   ```
4. Verificare che ritorna il profilo utente

**Fase 3 — Frontend OIDC:**
1. Impostare `.env`: `VITE_AUTH_PROVIDER=keycloak`
2. Aprire `http://localhost:3000`
3. Dovrebbe fare redirect a Keycloak login
4. Dopo login, redirect back a TenderWriter con sessione attiva
5. Verificare che tutte le pagine funzionino (Dashboard, Observability KPI, ecc.)
6. Verificare che Logout funzioni (redirect a Keycloak logout)

**Test di Regressione (legacy mode):**
1. Reimpostare `AUTH_PROVIDER=legacy` e `VITE_AUTH_PROVIDER=legacy`
2. Verificare che login/register/OTP funzionino come prima
3. Verificare che tutti gli endpoint API rispondano correttamente

> [!TIP]
> Propongo di scrivere un test di integrazione E2E con `pytest` + `httpx` che verifica entrambi i flussi (legacy e Keycloak) una volta completata la Fase 2. Vuoi che lo includa nel piano?



ok creami i test per dimostrare che quello che ha detto è vero punti 1,2,3,4,5




Writing Tests for Bug Fixes
Discovered the anonymizer container is not volume-mounted, so the test failed because it ran against the old app.py image. Syncing the updated app.py to the container and re-running pytest.

Files Edited
Progress Updates
1
Applying missed fix for BUG-04 and writing tests to verify points 1-5

2
Creating an automated test suite test_demonstration.py to execute the assertions for all 5 fixes

3
Creating permanent test files in the respective service directories (backend and anonymizer)

4
Running the newly created backend tests inside the backend container to prove they pass

5
Running backend tests via pytest and poetry if applicable

6
Executing python -m pytest in the backend and anonymizer containers and updating task documentation

7
Moving backend test to the mounted app directory and running tests

8
Debugging failed tests for BUG-01 and BUG-02 by checking pytest logs

9
Fixing mock types and assertions in test_bug_fixes.py based on pytest failure output

10
Running the fixed backend tests and then preparing to run the anonymizer SSRF test

11
Installing pytest in the anonymizer container and executing the SSRF fix tests

12
Viewing the anonymizer pytest failure logs to fix the test

13
Copying updated app.py into the anonymizer container and running the SSRF test

Ho appena creato ed eseguito con successo (100% passed) due set di test che dimostrano esattamente questi 5 punti:

backend/tests/test_bug_fixes.py:

test_bug_01_delete_tender_commits: Moka le chiamate e verifica formalmente che mock_db.commit.assert_awaited_once() venga invocato dopo un'eliminazione nel nuovo codice (il bug 1 era l'assenza di quest'ultimo chiamandolo db.delete(tender) senza fare commit).
test_bug_02_sql_injection_ilike_escaped: Simula un input malevolo come %admin_test\ e compila la query SQLAlchemy. Fa un assert stringente sull'estrazione dell'SQL, confermando che viene generata clausola ESCAPE '\' e i caratteri speciali sono sanati correttamente (\%admin\_test\\).
test_bug_16_inactive_or_unverified_jwt_rejected: Forgiato un JWT valido, moka un utente che ha appena completato la registrazione ma non ha fatto il check OTP (is_verified=False), e assicura che il provider lancia una HTTPException a status_code=403 "Account not verified".
test_auth_astratta_provider_resolution: Verifica che al variare della variabile in settings.auth_provider l'astrazione si disaccoppi dal protocollo caricando i Provider giusti dinamicamente.
anonymizer/test_ssrf_fix.py:

Moka socket.gethostbyname per catturare tentativi di DNS spoofing e accedere a nodi tramite i loro hostname interni (es. postgres), verificando che la funzione blocca formalmente alias malevoli facendoli cadere nei check su indirizzi IP riservati o di loopback. Ho notato che l'anonymizer non aveva il bind ai file locali da Compose, così ho allineato l'app.py e il test e li ho girati isolati al volo.