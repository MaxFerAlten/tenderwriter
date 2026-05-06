# Mattermost FINAL

## Obiettivo

Documentare in un unico file tutto il lavoro svolto per integrare Mattermost dentro TenderWriter, prima con la soluzione Enterprise/Entry + OIDC nativo, poi con la soluzione Team/Community + plugin OIDC custom, mantenendo entrambe le modalità disponibili e commutabili via configurazione.

---

## Risultato finale

Alla fine del lavoro il progetto supporta **due modalità Mattermost**:

1. **Enterprise/Entry**
   - usa l'OIDC nativo di Mattermost
   - richiede `MM_EDITION=enterprise`

2. **Team/Community**
   - usa il plugin custom `com.tenderwriter.oidc`
   - richiede `MM_EDITION=team`

Le due modalità sono entrambe pronte e lo switch avviene via config, senza rimuovere nessuna delle due implementazioni.

Lo stato finale attuale del repository è:

- **default = Team/Community + plugin**
- **Enterprise/Entry resta disponibile**
- **login TenderWriter resta compatibile con `legacy`, `keycloak`, `hybrid`**

---

## Fase 1: integrazione Mattermost lato TenderWriter

### Provisioning JIT utenti Mattermost

È stato implementato il provisioning "just in time" dell'utente Mattermost quando l'utente TenderWriter effettua login o verifica OTP.

Modifiche principali:

- `backend/app/services/mattermost.py`
  - aggiunta `provision_mm_user_for_tw_user()`
  - hardening di `ensure_mm_user()`
- `backend/app/api/auth.py`
  - hook in `login()`
  - hook in `verify_otp()`
  - scheduling via `BackgroundTasks`

Obiettivo:

- evitare blocchi sul login
- garantire provisioning best-effort
- lasciare `create_fullchat_session()` come rete di sicurezza

---

## Fase 2: soluzione Enterprise/Entry + Keycloak

È stata implementata la prima soluzione completa basata su:

- Keycloak
- Mattermost Enterprise/Entry
- OIDC nativo

### Componenti introdotti

- container Keycloak con realm importato automaticamente
- client `tw-frontend`
- client `mattermost`
- integrazione frontend TenderWriter con `keycloak-js`
- validazione backend dei token Keycloak via JWKS
- dual mode TenderWriter: `legacy` / `keycloak` / `hybrid`

### File chiave

- `keycloak/tenderwriter-realm.json`
- `frontend/src/auth/keycloak.ts`
- `frontend/public/silent-check-sso.html`
- `frontend/src/contexts/AuthContext.tsx`
- `frontend/src/pages/Login.tsx`
- `backend/app/auth/keycloak.py`
- `backend/app/auth/provider.py`
- `backend/app/config.py`
- `docker-compose.yml`
- `.env.example`

### Risultato

TenderWriter poteva:

- fare login via Keycloak
- validare i token OIDC
- auto-provisionare utenti locali
- aprire Mattermost in modalità SSO

---

## Fase 3: full chat seamless SSO e hardening

È stato completato il flusso `TenderWriter -> Mattermost Full Chat`.

### Interventi principali

- eliminazione del PAT nel flusso SSO
- creazione di `create_sso_chat_session()`
- response backend dual-mode: `legacy` oppure `sso`
- frontend aggiornato per gestire:
  - cookie/sessione browser in legacy
  - redirect puro in SSO

### Hardening

- logout federato
- password Mattermost locali rese non predicibili
- audit logging auth
- riconciliazione utenti legacy/Keycloak per email

### File chiave

- `backend/app/services/mattermost.py`
- `backend/app/api/mattermost.py`
- `frontend/src/api/client.ts`
- `frontend/src/pages/Dashboard.tsx`
- `backend/app/api/auth.py`

---

## Fase 4: supporto login tradizionale + SSO insieme

In un secondo momento è stata corretta la convivenza dei due metodi di autenticazione.

### Problema risolto

Con `AUTH_PROVIDER=keycloak` il frontend permetteva ancora il login password legacy, ma poi il backend cercava di validare quel token come Keycloak token, generando errori come:

- `Could not validate Keycloak token`

### Soluzione introdotta

- `AUTH_PROVIDER=hybrid`
- `VITE_AUTH_MODE=hybrid`
- supporto simultaneo a:
  - login tradizionale
  - login SSO

### Effetto finale

Lo stesso utente di test può entrare in entrambi i modi:

- `e2e-admin@example.com`
- password: `E2E-Admin-2026!`

---

## Fase 5: analisi e implementazione Mattermost Team/Community + plugin

Successivamente è stata fatta l'analisi di fattibilità per usare Mattermost Community/Team con SSO, pur sapendo che non lo supporta nativamente.

### Conclusione architetturale

Non esiste un plugin OIDC nativo ufficiale da riusare. È stato quindi realizzato un plugin custom.

### Plugin creato

ID plugin:

- `com.tenderwriter.oidc`

Cartella:

- `mattermost-plugin-oidc/`

### Funzioni del plugin

- endpoint `/login`
- endpoint `/callback`
- health endpoint `/health`
- redirect a Keycloak
- callback OIDC
- validazione ID token
- auto-provisioning utente Mattermost
- creazione sessione Mattermost
- redirect finale al canale richiesto

### File plugin principali

- `mattermost-plugin-oidc/server/plugin.go`
- `mattermost-plugin-oidc/server/configuration.go`
- `mattermost-plugin-oidc/server/go.mod`
- `mattermost-plugin-oidc/plugin.json`
- `mattermost-plugin-oidc/Dockerfile`

---

## Fix tecnici fatti sul plugin

Il plugin non era inizialmente buildabile né pronto a funzionare in Docker con Keycloak.

### Fix 1: build Go

Problema:

- dipendenze Mattermost richiedevano Go >= 1.23

Fix:

- `go.mod` portato a `go 1.23`
- builder Docker aggiornato a `golang:1.23-alpine`

### Fix 2: split-horizon / split URL Keycloak

Problema:

- il discovery document di Keycloak pubblicava endpoint `localhost`
- da dentro i container `localhost` non è raggiungibile come host Keycloak

Fix:

- gestione separata tra:
  - URL pubblico browser
  - URL interno container
- nuove variabili:
  - `TW_OIDC_PUBLIC_BASE_URL`
  - `TW_OIDC_INTERNAL_BASE_URL`
- il plugin ora:
  - usa l'`authorization_endpoint` pubblico
  - riscrive `token_endpoint` e `jwks_uri` verso l'endpoint interno Docker

### Fix 3: hardening redirect

È stata sanificata la variabile `redirect_to` per evitare valori non validi o protocol-relative.

### Fix 4: lookup utente Mattermost

La creazione utente avviene solo su `404`; altri errori di lookup vengono trattati come errori reali.

---

## Fase 6: switch tra Enterprise e Team via configurazione

È stato introdotto il supporto nativo allo switch di edizione Mattermost nel compose.

### Variabile chiave

- `MM_EDITION=enterprise|team`

### Comportamento

- `enterprise`:
  - usa `mattermost-enterprise-edition`
  - usa OIDC nativo
- `team`:
  - usa `mattermost-team-edition`
  - usa plugin OIDC

### File coinvolti

- `docker-compose.yml`
- `.env`
- `.env.example`
- `README.md`

---

## Fase 7: routing backend consapevole del tipo di sessione auth

Poiché TenderWriter supporta `legacy`, `keycloak` e `hybrid`, il backend Mattermost è stato reso consapevole della sorgente auth della sessione corrente.

### Nuovo concetto introdotto

- `auth_source`

### Effetto

In modalità `hybrid`:

- se l'utente TenderWriter è entrato via Keycloak:
  - usa SSO Mattermost
- se l'utente TenderWriter è entrato via login tradizionale:
  - continua a usare il fallback legacy

### File coinvolti

- `backend/app/auth/base.py`
- `backend/app/auth/legacy.py`
- `backend/app/auth/keycloak.py`
- `backend/app/api/auth.py`
- `backend/app/services/mattermost.py`
- `backend/app/api/mattermost.py`

### Funzioni aggiunte/aggiornate

- `get_mm_sso_mode_for_auth_source()`
- `create_sso_chat_session(..., sso_mode=...)`

Supporta i tre esiti:

- `legacy`
- `native_oidc`
- `plugin_oidc`

---

## Fase 8: redirect opzionale di `/mm/login` al plugin

La Team Edition non permette di aggiungere un bottone login SSO nativo nella login page.

Per ottenere un comportamento vicino al "login nativo", è stato aggiunto un redirect opzionale a livello Nginx frontend:

- `MM_LOGIN_REDIRECT_MODE=plugin`

### Comportamento

- se `plugin`:
  - `/mm/login` redirige a `/mm/plugins/com.tenderwriter.oidc/login`
- se `off`:
  - `/mm/login` resta quello standard Mattermost

### File coinvolti

- `frontend/nginx/default.conf.template`
- `frontend/Dockerfile`
- `docker-compose.yml`

### Nota

È stato corretto anche un bug iniziale nel template Nginx dovuto a una condizione `if` non valida.

---

## Fase 9: attivazione reale del plugin in Mattermost

Il plugin inizialmente era copiato nei volumi ma non veniva attivato davvero da Mattermost.

### Problema

`PluginStates` era stato passato come chiave annidata non compatibile.

### Fix

In `docker-compose.yml` è stato passato `MM_PLUGINSETTINGS_PLUGINSTATES` come JSON completo.

Questo ha sbloccato l'attivazione vera del plugin.

### Evidenza runtime

Nei log Mattermost è comparso:

- `TW-OIDC initialized successfully`

---

## Fase 10: fix callback Keycloak del plugin

Durante il test browser reale, il login diretto a `/mm/login` falliva con:

- `Invalid parameter: redirect_uri`

### Causa

Il client `mattermost` in Keycloak consentiva solo:

- `http://localhost:3000/mm/signup/openid/complete`

ma non il callback del plugin:

- `http://localhost:3000/mm/plugins/com.tenderwriter.oidc/callback`

### Fix eseguito

Aggiornamento di:

- `keycloak/tenderwriter-realm.json`

e aggiornamento live del client `mattermost` in Keycloak admin.

### Stato finale callback

Il realm include ora entrambe:

- `http://localhost:3000/mm/signup/openid/complete`
- `http://localhost:3000/mm/plugins/com.tenderwriter.oidc/callback`

---

## Test eseguiti

### Test build/config

- build frontend: OK
- build plugin Mattermost: OK
- `docker compose config`: OK
- compilazione Python dei file backend toccati: OK

### Test HTTP/plugin

- `GET /mm/plugins/com.tenderwriter.oidc/health` -> `200`
- `GET /mm/login` -> redirect al plugin in modalità Team
- `GET /mm/plugins/com.tenderwriter.oidc/login?...` -> redirect a Keycloak

### Test browser reale con Playwright

Verificato:

1. login TenderWriter via SSO Keycloak: OK
2. apertura diretta di `http://localhost:3000/mm/login`: OK
3. redirect a Keycloak: OK
4. ritorno in Mattermost Team Edition: OK
5. atterraggio su canale Mattermost corretto: OK
6. click `Full Chat` dalla dashboard TenderWriter: OK
7. apertura del canale `tender-1-ops`: OK

### Verifica backend `fullchat`

Con sessione TenderWriter Keycloak:

- `POST /api/tenders/1/fullchat`

ha restituito:

- `auth_mode: "sso"`
- `mm_url: /mm/plugins/com.tenderwriter.oidc/login?...`

quindi il dispatch backend è corretto in modalità Team/plugin.

### Smoke test finale

Lo script:

- `keycloak/test-sso-flow.sh`

è stato aggiornato per capire sia:

- `enterprise/native OIDC`
- `team/plugin OIDC`

ed è risultato **verde** nella modalità Team/plugin di default.

---

## Default finali del progetto

### Default attuali nel repository

In questo momento il default è:

```env
MM_EDITION=team
MM_OIDC_ENABLE=false
TW_OIDC_ENABLE=true
MM_LOGIN_REDIRECT_MODE=plugin
AUTH_PROVIDER=hybrid
VITE_AUTH_MODE=hybrid
```

### Significato

- Mattermost di default parte come **Team Edition**
- il login diretto di Mattermost può usare il **plugin SSO**
- TenderWriter continua a supportare sia:
  - login tradizionale
  - login SSO

---

## Script di switch rapido aggiunto

È stato creato lo script:

- `utility/switch-mattermost-mode.ps1`

### Cosa fa

Aggiorna in `.env`:

- `MM_EDITION`
- `MM_OIDC_ENABLE`
- `TW_OIDC_ENABLE`
- `MM_LOGIN_REDIRECT_MODE`

crea backup:

- `.env.bak`

e opzionalmente ricrea i container:

- `backend`
- `frontend`
- `mattermost`
- `mm-plugin-oidc`

### Uso

```powershell
.\utility\switch-mattermost-mode.ps1 team
.\utility\switch-mattermost-mode.ps1 enterprise
.\utility\switch-mattermost-mode.ps1 team -NoRestart
```

---

## File principali toccati durante tutto il lavoro

### Backend

- `backend/app/services/mattermost.py`
- `backend/app/api/mattermost.py`
- `backend/app/api/auth.py`
- `backend/app/auth/base.py`
- `backend/app/auth/legacy.py`
- `backend/app/auth/keycloak.py`
- `backend/app/auth/provider.py`
- `backend/app/config.py`

### Frontend

- `frontend/src/auth/keycloak.ts`
- `frontend/src/contexts/AuthContext.tsx`
- `frontend/src/pages/Login.tsx`
- `frontend/src/pages/Dashboard.tsx`
- `frontend/src/api/client.ts`
- `frontend/public/silent-check-sso.html`
- `frontend/nginx/default.conf.template`
- `frontend/Dockerfile`

### Mattermost / Docker / IAM

- `docker-compose.yml`
- `.env`
- `.env.example`
- `keycloak/tenderwriter-realm.json`
- `keycloak/test-sso-flow.sh`
- `mattermost-plugin-oidc/server/plugin.go`
- `mattermost-plugin-oidc/server/configuration.go`
- `mattermost-plugin-oidc/server/go.mod`
- `mattermost-plugin-oidc/plugin.json`
- `mattermost-plugin-oidc/Dockerfile`
- `utility/switch-mattermost-mode.ps1`

### Documentazione

- `README.md`

---

## Stato finale sintetico

### Enterprise/Entry

- pronto
- non rimosso
- attivabile via config

### Team/Community + plugin

- pronto
- verificato end-to-end
- impostato come default

### Dual auth TenderWriter

- `legacy`: pronto
- `keycloak`: pronto
- `hybrid`: pronto

---

## Nota conclusiva

Il progetto è ora in una condizione migliore rispetto al punto di partenza:

- Mattermost non è più vincolato a una sola edizione
- il flusso SSO è disponibile anche in Team/Community tramite plugin
- Enterprise/Entry resta disponibile come fallback o scelta alternativa
- il passaggio tra le due modalità è standardizzato
- i test reali browser + HTTP hanno confermato il funzionamento

In breve: **la soluzione Enterprise è stata mantenuta, la soluzione Team/plugin è stata costruita e resa default, e lo switch tra le due è già pronto.**
