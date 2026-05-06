# TenderWriter — Project Memory

## Architecture: Auth & Mattermost Integration

### Current State (2026-03-28)
- **Auth**: Dual-mode `legacy` (JWT+password) / `keycloak` (OIDC), controlled by feature flag
- **Mattermost**: Enterprise Edition (Entry mode, free) — migrated from Team Edition
- **Docker image**: `mattermost/mattermost-enterprise-edition:10.11.8`
- **Keycloak**: v26.1, realm `tenderwriter` with auto-import (`keycloak/tenderwriter-realm.json`)
- **Provisioning JIT**: `provision_mm_user_for_tw_user()` runs as `BackgroundTasks` after `login()` and `verify_otp()`
- **Full Chat**: `create_fullchat_session()` — ensures user + channel + membership + PAT (legacy path, rete di sicurezza)

### Key Decisions
1. **OIDC** (not SAML) is the target protocol for Keycloak integration
2. **Do NOT use GitLab hack** for Mattermost SSO — use OpenID Connect (Other) with Discovery Endpoint
3. **Mattermost Team Edition does NOT support SSO** — migrated to Enterprise Edition (Entry mode, free, no license needed)
4. **Never write directly to Mattermost DB** — only REST API v4
5. **Token exchange is NOT needed** for browser SSO — Keycloak SSO session + OIDC redirects suffice
6. **PAT-based auto-login is tactical/transitional** — target is Keycloak OIDC SSO for both TW and MM
7. **KC_HOSTNAME_BACKCHANNEL_DYNAMIC=true** — Keycloak serves browser-facing URLs for auth_endpoint, internal URLs for token_endpoint

### Fase 0 — Gate di fattibilita (COMPLETATA)
- `mattermost-enterprise-edition` senza licenza = Entry mode (gratis, OIDC nativo)

### Fase 1 — Keycloak Foundation (COMPLETATA)
- Container `keycloak` + `kc-postgres` (profile `keycloak`)
- Realm auto-import con 2 client OIDC (`tw-frontend`, `mattermost`)
- Mattermost OIDC env vars attive (default `MM_OIDC_ENABLE=false`)

### Fase 2 — TenderWriter OIDC (COMPLETATA)
**Feature flag**: `AUTH_PROVIDER=legacy|keycloak` (backend) + `VITE_AUTH_MODE=legacy|keycloak` (frontend)

**Frontend** (`frontend/src/`):
- `auth/keycloak.ts` — Keycloak JS wrapper: init, login, logout, token refresh, user info
- `public/silent-check-sso.html` — iframe per silent SSO check
- `contexts/AuthContext.tsx` — dual-mode: legacy (localStorage JWT) / keycloak (OIDC redirect + PKCE S256)
- `pages/Login.tsx` — bottone "Accedi con SSO" + form email/password sempre disponibile
- Dipendenza: `keycloak-js` installata

**Backend** (`backend/app/auth/`):
- `keycloak.py` — `KeycloakOIDCProvider`: JWKS validation (RS256), auto-provisioning, role mapping
- `provider.py` — registrato `keycloak` come provider valido
- `config.py` — settings: `keycloak_url`, `keycloak_realm`, `keycloak_client_id`

### Fase 3 — Mattermost OIDC Activation (COMPLETATA 2026-03-28)

**Problema risolto**: Docker split-horizon DNS (browser vs container access to Keycloak)
- **Soluzione**: `KC_HOSTNAME_BACKCHANNEL_DYNAMIC=true` (Keycloak 24+)
- Browser accede a Keycloak via `http://localhost:8180` (porta esposta)
- Mattermost accede a Keycloak via `http://keycloak:8080` (Docker internal)
- Discovery doc restituisce URL browser per `authorization_endpoint`, URL interno per `token_endpoint`

**Configurazione**:
- `KC_HOSTNAME=http://localhost:8180` (full URL richiesto con backchannel dynamic)
- `KC_HOSTNAME_BACKCHANNEL_DYNAMIC=true`
- `MM_OPENIDCONNECTSETTINGS_DISCOVERYENDPOINT=http://keycloak:8080/realms/tenderwriter/.well-known/openid-configuration`
- Client Mattermost redirect URI: `http://localhost:3000/mm/signup/openid/complete`
- Mattermost SiteURL: `http://localhost:3000/mm`

**Flusso SSO completo**:
1. Utente apre `http://localhost:3000/mm` (Mattermost via nginx proxy)
2. Clicca "Accedi con Keycloak"
3. Browser redirect a `http://localhost:8180/realms/tenderwriter/protocol/openid-connect/auth`
4. Utente si autentica su Keycloak (o sessione SSO gia attiva)
5. Keycloak redirect a `http://localhost:3000/mm/signup/openid/complete?code=...`
6. Mattermost scambia il code per token via `http://keycloak:8080/.../token` (interno)
7. Mattermost crea sessione e apre la dashboard

**SSO cross-app (TenderWriter -> Mattermost senza nuovo login)**:
1. Utente fa login su TenderWriter via Keycloak (Fase 2)
2. Keycloak crea sessione SSO nel browser
3. Utente clicca "Full Chat" -> redirect a Mattermost
4. Mattermost redirect a Keycloak per OIDC
5. Keycloak vede la sessione SSO gia attiva -> nessun prompt credenziali
6. Utente entra in Mattermost automaticamente

**Script di test**: `keycloak/test-sso-flow.sh` — verifica health, discovery, JWKS, clients, OIDC config

### How to activate full SSO stack
```bash
# 1. Start everything
docker compose --profile keycloak --profile videochat up -d

# 2. Set in .env
AUTH_PROVIDER=keycloak
KEYCLOAK_URL=http://keycloak:8080
MM_OIDC_ENABLE=true
VITE_AUTH_MODE=keycloak
VITE_KC_URL=http://localhost:8180

# 3. Rebuild frontend + restart backend
docker compose build frontend && docker compose up -d backend frontend

# 4. Run smoke test
bash keycloak/test-sso-flow.sh

# 5. Create test user in Keycloak
open http://localhost:8180  # admin console
```

### Keycloak Migration Plan
- ~~Fase 0: Verify Mattermost edition supports OIDC natively~~ DONE
- ~~Fase 1: Keycloak realm + clients~~ DONE
- ~~Fase 2: TenderWriter OIDC dual-mode~~ DONE
- ~~Fase 3: Mattermost OIDC activation~~ DONE
- ~~Fase 4: Seamless SSO (replace PAT auto-login with browser redirect only)~~ DONE
- ~~Fase 5: Hardening (federated logout, dismiss PAT/local passwords, audit, legacy user reconciliation)~~ DONE

### Fase 4 — Seamless SSO (COMPLETATA 2026-03-28)

**Dual-mode fullchat API**: backend auto-selects based on `AUTH_PROVIDER` setting
- `legacy`: `create_fullchat_session()` — user + channel + membership + PAT + cookie
- `keycloak`: `create_sso_chat_session()` — user + channel + membership only (no PAT)

**API response** includes `auth_mode: "legacy" | "sso"` so frontend knows how to handle:
- `legacy`: sets `MMAUTHTOKEN` cookie before opening MM
- `sso`: opens MM URL directly — Keycloak SSO handles authentication transparently

**Files modified**:
- `backend/app/services/mattermost.py` — new `create_sso_chat_session()` function
- `backend/app/api/mattermost.py` — dual-mode dispatch + `auth_mode` in response
- `frontend/src/api/client.ts` — updated fullchat response type
- `frontend/src/pages/Dashboard.tsx` — conditional cookie/redirect based on `auth_mode`

### Service Structure (mattermost.py)
Four levels:
1. `provision_mm_user_for_tw_user()` — user + team only (best-effort, called at login)
2. `create_sso_chat_session()` — user + channel + membership (SSO mode, no PAT)
3. `create_fullchat_session()` — full legacy path with PAT/token (legacy mode)
4. Individual helpers: `ensure_mm_user()`, `ensure_tender_channel()`, `add_user_to_channel()`

### Fase 5 — Hardening (COMPLETATA 2026-03-28)

**Logout federato**:
- Frontend: `logout()` chiama `POST /api/auth/logout` (audit) poi `keycloakLogout()` (redirect a KC end-session)
- Backend: `/auth/logout` logga evento e restituisce `redirect_url` per end-session Keycloak
- Keycloak invalida sessione SSO → logout propagato a tutti i client (TW + MM)

**Password Mattermost sicure**:
- Sostituita password predicibile `TWauto!{id}Secure2026` con `TW!{secrets.token_urlsafe(32)}`
- Password casuale a 32 byte, impossibile da indovinare
- In SSO mode la password MM non viene mai usata (auth via OIDC)

**Audit log** (eventi strutturati via structlog):
- `keycloak.audit.login_success` — ogni login riuscito con user_id, email, keycloak_sub, role
- `keycloak.audit.user_synced` — quando nome/ruolo vengono aggiornati dal token KC
- `keycloak.audit.legacy_user_verified` — quando utente legacy viene verificato via KC login
- `keycloak.user_auto_provisioned` — quando nuovo utente viene creato da KC
- `auth.logout` — ogni logout con user_id, auth_mode

**Riconciliazione utenti legacy**:
- `KeycloakOIDCProvider` matcha utenti per email → utente legacy esistente viene collegato a KC
- Se utente legacy non e verificato, KC login lo verifica automaticamente
- Nome e ruolo vengono sincronizzati dal token KC ad ogni accesso
- Password locale non viene toccata (utente puo ancora usare legacy mode se feature flag cambia)

**Endpoint /auth/config** (pubblico):
- Espone `auth_mode` e parametri KC al frontend
- Permette al frontend di auto-configurarsi senza env vars hardcoded

**Files modificati**:
- `backend/app/api/auth.py` — + `/auth/logout`, `/auth/config`
- `backend/app/auth/keycloak.py` — + audit logging, legacy user verification
- `backend/app/services/mattermost.py` — password casuale con `secrets.token_urlsafe(32)`
- `frontend/src/contexts/AuthContext.tsx` — logout chiama server prima di KC end-session

### Risks (residui)
- **Entry mode limit**: 10.000 messaggi visibili — ok per progetto attuale, valutare Professional se scale
- **iframe embedding**: CSP/X-Frame-Options issues — prefer redirect/new tab
- **Mattermost client secret**: placeholder `CHANGE_ME_mattermost_client_secret` — cambiare in produzione
- **KC backchannel-dynamic refresh bug**: Keycloak issue #27660 — monitorare
- **Existing MM users with old passwords**: utenti MM creati prima dell'hardening hanno ancora password predicibili. Valutare reset forzato se necessario.
