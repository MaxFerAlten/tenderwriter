# Il Thread Chat in Questione

## Obiettivo della thread

Portare a funzionamento reale l'integrazione tra TenderWriter, Keycloak e Mattermost, verificare il flusso end-to-end, correggere i bug emersi durante i test e arrivare a una modalita finale in cui TenderWriter supporta sia autenticazione tradizionale sia SSO.

## Contesto iniziale

Durante questa thread era gia stato impostato un lavoro ampio su:

- provisioning JIT utenti Mattermost
- Keycloak come identity provider
- dual mode tra autenticazione legacy e Keycloak
- predisposizione OIDC per Mattermost
- apertura del Full Chat da TenderWriter

Il passaggio richiesto in questa fase e stato soprattutto di verifica reale, correzione bug e chiusura operativa del flusso.

## Attivita svolte in questa thread

### 1. Verifica iniziale E2E e test tecnici di base

Sono state eseguite verifiche su:

- compilazione frontend TypeScript
- validita di `docker-compose.yml`
- stato dei container Docker
- disponibilita di backend, frontend, Mattermost e Keycloak

Da queste verifiche e emerso che:

- Docker era operativo
- frontend compilava
- il backend era raggiungibile
- Keycloak andava avviato e riallineato alla configurazione finale

## 2. Correzione del problema reale su Keycloak token validation

Durante il test end-to-end e emerso un problema importante:

- il frontend poteva apparire autenticato
- ma il backend rispondeva con `Could not validate Keycloak token`

La causa principale era una combinazione di:

- configurazione auth letta male o troppo rigidamente lato frontend
- differenza tra URL pubblico di Keycloak e URL interno Docker
- mismatch tra token usato dal browser e aspettative del backend

### Correzioni applicate

Sono state corrette le seguenti aree:

- caricamento runtime della configurazione auth da `/api/auth/config`
- separazione tra URL pubblico Keycloak e URL interno per il backend
- allineamento tra issuer atteso e issuer reale dei token
- miglior gestione del bootstrap auth lato frontend

## 3. Correzione del Full Chat verso Mattermost

Durante le verifiche e emerso che il flusso Full Chat non era robusto in tutti i casi.

In particolare:

- il fallback legacy non doveva usare un semplice PAT come se fosse una sessione browser reale
- il browser Mattermost richiede cookie/sessione validi

### Soluzione implementata

E stata corretta la logica in modo che, nel fallback legacy:

- il backend ottenga una vera sessione browser Mattermost
- il frontend imposti i cookie/session fields necessari
- l'utente atterri direttamente nel canale corretto

Sono stati sistemati in particolare:

- `backend/app/services/mattermost.py`
- `backend/app/api/mattermost.py`
- `frontend/src/api/client.ts`
- `frontend/src/pages/Dashboard.tsx`

### Comportamento finale verificato

Quando il native OIDC di Mattermost non risulta ancora pronto lato client:

- TenderWriter esegue provisioning utente/canale
- il backend usa un fallback legacy verificato
- il browser apre Mattermost gia autenticato

## 4. Test E2E reale completato

E stato eseguito un test end-to-end reale con browser.

### Verifiche riuscite

- login SSO TenderWriter via Keycloak riuscito
- dashboard caricata correttamente
- apertura del Full Chat dal tender corretta
- arrivo diretto nel canale Mattermost corretto
- invio messaggio nel canale riuscito

Messaggio di test inviato:

`E2E after legacy-session fix from TenderWriter dashboard`

### Stato tecnico emerso dal test

Il flusso utente finale funzionava, ma con questo caveat:

- Mattermost OIDC nativo non risultava ancora effettivamente esposto al client
- quindi il backend entrava nel fallback legacy verificato

Questo era tracciato anche nei log con un evento simile a:

`mattermost.fullchat_fallback_legacy reason=mattermost_oidc_not_ready`

## 5. Bug emerso con login tradizionale in modalita solo Keycloak

Successivamente e emerso un bug reale mostrato anche da screenshot:

- entrando con email/password mentre il sistema era in modalita `keycloak`
- l'app faceva entrare apparentemente l'utente
- poi il backend provava a validare quel token come token Keycloak
- risultato: dashboard con errore `Could not validate Keycloak token`

### Causa

Il sistema stava mescolando due modelli incompatibili:

- JWT locale legacy
- validazione forzata come token Keycloak

### Correzioni applicate

Sono state introdotte protezioni precise:

- in modalita `keycloak`, `/api/auth/login` rifiuta il login password con errore esplicito
- la pagina login mostra solo `Accedi con SSO`
- vengono rimossi eventuali token legacy rimasti in `localStorage`

Le modifiche principali sono state fatte in:

- `backend/app/api/auth.py`
- `frontend/src/contexts/AuthContext.tsx`
- `frontend/src/pages/Login.tsx`

## 6. Nuova richiesta utente: doppio sistema di login

Dopo la correzione del bug, e stata richiesta una modalita finale diversa:

- mantenere il login tradizionale
- mantenere anche SSO
- far convivere entrambi in modo corretto

### Decisione applicata

E stata implementata una vera modalita `hybrid`.

## 7. Implementazione della modalita Hybrid

### Backend

E stato aggiunto un provider dedicato:

- `backend/app/auth/hybrid.py`

E stato poi registrato e integrato il supporto a:

- `AUTH_PROVIDER=hybrid`

con aggiornamenti in:

- `backend/app/auth/provider.py`
- `backend/app/config.py`
- `backend/app/api/auth.py`

### Frontend

E stato aggiornato il runtime auth per supportare:

- `legacy`
- `keycloak`
- `hybrid`

File toccati:

- `frontend/src/config/runtime.ts`
- `frontend/src/auth/keycloak.ts`
- `frontend/src/contexts/AuthContext.tsx`
- `frontend/src/pages/Login.tsx`

### Comportamento finale della modalita hybrid

In modalita `hybrid` il bootstrap auth fa questo:

1. prova prima il silent check SSO con Keycloak
2. se esiste una sessione SSO valida, usa quella
3. se non esiste sessione SSO, prova il token locale legacy
4. sulla pagina login mostra sia il bottone SSO sia il form email/password

### Gestione logout

Il logout e stato corretto in modo che:

- se la sessione attiva e `keycloak`, esegua logout federato
- se la sessione attiva e `legacy`, faccia logout locale senza forzare quello SSO

## 8. Hardening login password per utenti SSO-managed

E stata anche migliorata la parte login locale per gli utenti gestiti SSO:

- la verifica password ora intercetta hash non validi senza far fallire male la richiesta
- se un account e marcato come gestito da Keycloak e non ha password locale, il backend risponde con un errore chiaro

Comportamento introdotto:

- login locale negato con messaggio esplicito se l'account non ha ancora password locale

## 9. Configurazione persistente dell'ambiente

Per rendere stabile il comportamento del progetto in questa macchina, e stato aggiornato il file:

- `D:\tender\tenderwriter\.env`

con questi valori:

```env
AUTH_PROVIDER=hybrid
VITE_AUTH_MODE=hybrid
MM_OIDC_ENABLE=true
KEYCLOAK_URL=http://localhost:8180
KEYCLOAK_INTERNAL_URL=http://keycloak:8080
```

## 10. Abilitazione dell'utente di test per entrambi i metodi

Per rispettare la richiesta di usare davvero lo stesso account sia via SSO sia via login tradizionale, e stato aggiornato l'utente di test:

- `e2e-admin@example.com`

E stata impostata una password locale valida, mantenendo anche l'accesso SSO sullo stesso utente.

### Credenziali usate in questa macchina di sviluppo

- email: `e2e-admin@example.com`
- password: `E2E-Admin-2026!`

Queste credenziali sono state usate per:

- login tradizionale su TenderWriter
- login SSO via Keycloak

## 11. Verifica finale della modalita ibrida

Sono state eseguite verifiche browser reali dopo l'introduzione della modalita hybrid.

### Esito verificato

- pagina `/login` mostrava sia `Accedi con SSO` sia il form tradizionale
- login tradizionale con `e2e-admin@example.com / E2E-Admin-2026!` riuscito
- logout riuscito
- nuovo login SSO con lo stesso account riuscito
- arrivo in dashboard corretto in entrambi i casi

## File principali creati o modificati durante questa thread

### Nuovi file

- `D:\tender\tenderwriter\backend\app\auth\hybrid.py`

### File modificati principali

- `D:\tender\tenderwriter\backend\app\api\auth.py`
- `D:\tender\tenderwriter\backend\app\auth\provider.py`
- `D:\tender\tenderwriter\backend\app\config.py`
- `D:\tender\tenderwriter\backend\app\services\mattermost.py`
- `D:\tender\tenderwriter\backend\app\api\mattermost.py`
- `D:\tender\tenderwriter\frontend\src\config\runtime.ts`
- `D:\tender\tenderwriter\frontend\src\auth\keycloak.ts`
- `D:\tender\tenderwriter\frontend\src\contexts\AuthContext.tsx`
- `D:\tender\tenderwriter\frontend\src\pages\Login.tsx`
- `D:\tender\tenderwriter\frontend\src\pages\Dashboard.tsx`
- `D:\tender\tenderwriter\frontend\src\api\client.ts`
- `D:\tender\tenderwriter\.env`

## Stato finale raggiunto

Alla fine di questa thread il sistema risulta in questo stato:

- TenderWriter supporta login tradizionale
- TenderWriter supporta login SSO via Keycloak
- gli stessi utenti possono essere usati in entrambi i flussi se hanno anche password locale
- il Full Chat da TenderWriter a Mattermost funziona
- l'E2E reale e stato eseguito con successo

## Caveat residuo importante

Il punto ancora non completamente chiuso e questo:

- Mattermost OIDC nativo non risulta ancora esposto/attivato lato client nel modo atteso
- quindi il flusso finale verso Mattermost oggi funziona tramite fallback legacy verificato, non ancora tramite native OIDC end-to-end lato Mattermost

Questo significa che:

- dal punto di vista utente il flusso funziona
- dal punto di vista architetturale c'e ancora un ultimo step possibile di rifinitura se si vuole eliminare del tutto il fallback

## Conclusione

Questa thread ha portato il sistema da una situazione con problemi reali di compatibilita auth e SSO a una configurazione stabile, testata e utilizzabile, con:

- doppio metodo di autenticazione operativo
- flusso Full Chat funzionante
- test E2E reale completato
- configurazione persistente pronta per ulteriori raffinamenti
