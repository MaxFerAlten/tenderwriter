# Implementazione Dashboard, Autenticazione e Funzionalità Avanzate

Ho completato lo sviluppo delle funzionalità richieste per TenderWriter. Ecco un riepilogo di quanto implementato e come testarlo.

## 1. Autenticazione e Sicurezza (2FA)

Ho implementato un sistema di autenticazione robusto basato su JWT con verifica OTP via email (simulata nei log del backend).

- **Registrazione**: Nuova pagina di registrazione con invio automatico di un codice OTP di 6 cifre.
- **Login**: Supporta l'utenza tecnica `admin/admin` e gli utenti registrati. Se l'utenza admin è abilitata (default), è possibile loggarsi immediatamente.
- **Verifica**: Flusso 2FA integrato. Al login o alla registrazione, viene richiesto il codice OTP inviato.
- **Persistent State**: Utilizzo di [AuthContext](file:///d:/tender/tenderwriter/frontend/src/contexts/AuthContext.tsx#4-10) per gestire lo stato dell'utente e proteggere le rotte.

## 2. System Monitor e Gestione Docker

Una nuova pagina "System Monitor" (accessibile agli admin) permette di monitorare l'intera infrastruttura TenderWriter.

- **Status Container**: Vista d'insieme di `Qdrant`, `Neo4j`, `Ollama`, `MinIO`, `Redis` e `Frontend`.
- **Statistiche Realtime**: Grafici e indicatori di utilizzo CPU e Memoria per ogni componente.
- **Streaming Log**: Possibilità di visualizzare i log in tempo reale di ogni container direttamente dal browser.
- **Docker Integration**: Il backend comunica direttamente col socket Docker (`/var/run/docker.sock`).

## 3. Configurazione Dinamica NGINX

All'interno della pagina Impostazioni, l'admin può modificare i timeout di proxy di Nginx senza riavviare i servizi.

- **Modifica "A Caldo"**: Update di `proxy_read_timeout`, `proxy_connect_timeout` e `proxy_send_timeout`.
- **Reload Automatico**: Il sistema aggiorna la configurazione dentro il container frontend ed esegue `nginx -s reload` istantaneamente.

## 4. Cronologia Ricerche AI

L'interfaccia di ricerca è stata arricchita con una barra laterale contenente la cronologia delle ricerche dell'utente.

- **Persistenza**: Ogni domanda posta a HybridRAG viene salvata nel database PostgreSQL legata all'utente.
- **Recupero**: Al caricamento della pagina di ricerca, viene mostrata la lista delle ultime interrogazioni effettuate.

## 5. Correzione Bug e Startup Backend

- **Risoluzione ValueError**: Risolto un problema critico di startup del backend legato alla libreria `bcrypt` in ambiente Alpine, passando all'algoritmo `pbkdf2_sha256` (ugualmente sicuro e più compatibile).
- **TypeScript Fix**: Rimossi import non utilizzati che bloccavano la build Docker del frontend.

---

### Come Verificare

1. **Dashboard di Sistema**: Accedi come admin e vai su `/monitor` per vedere lo stato dell'infrastruttura.
2. **Impostazioni**: Vai su `/settings` per cambiare i timeout Nginx o disabilitare l'account admin tecnico.
3. **Ricerca**: Effettua delle query e verifica che appaiano nella sidebar della cronologia.
4. **Registrazione**: Prova a creare un nuovo utente e verifica il codice OTP nei log del container `tw-backend`.
n autenticati vengono reindirizzati automaticamente al Login.

## 👨‍💻 Technical Admin `admin/admin`

È stata creata un'utenza tecnica di sistema predefinita:
- **Username**: [admin](file:///d:/tender/tenderwriter/backend/app/api/system.py#25-30)
- **Configurabilità**: Può essere abilitata o disabilitata tramite il file [backend/app/config.py](file:///d:/tender/tenderwriter/backend/app/config.py) o dinamicamente dalla pagina **Impostazioni**.
- **Ruolo**: Solo gli utenti con ruolo [admin](file:///d:/tender/tenderwriter/backend/app/api/system.py#25-30) hanno accesso al **System Monitor** e alle impostazioni delle infrastrutture.

## 🕰️ Cronologia Ricerche AI

La sezione **AI Search** è stata potenziata con una memoria persistente per ogni utente.
- **Salvataggio Automatico**: Ogni domanda posta al RAG e la relativa risposta dell'IA vengono salvate nel database.
- **Sidebar Retro**: Sulla sinistra della pagina di ricerca è ora presente un pannello con la cronologia delle ultime 50 ricerche.
- **Deep Recall**: Cliccando su un elemento della cronologia, è possibile visualizzare istantaneamente la query e la risposta generata in precedenza.

## 📊 Dashboard di Monitoraggio (Docker SDK)

È stata aggiunta una nuova pagina **System Monitor** (riservata agli admin) che si interfaccia direttamente con il socket Docker dell'host.
- **Stato Container**: Monitoraggio in tempo reale di Qdrant, Neo4j, Ollama, MinIO e Redis.
- **Metriche Real-time**: Visualizzazione dell'uso di **CPU** e **RAM** per ogni componente.
- **Log Explorer**: Possibilità di leggere gli ultimi 100 log di ogni container direttamente dalla UI.

## ⚙️ Configurazione Dinamica Nginx

Nelle **Impostazioni**, gli amministratori possono ora variare i timeout del proxy Nginx senza riavviare manualmente i container:
- `proxy_read_timeout`
- `proxy_connect_timeout`
- `proxy_send_timeout`
- **Hot Reload**: Al salvataggio, il backend esegue un comando `nginx -s reload` all'interno del container frontend tramite Docker SDK.

---

### Come Testare
1. **Login**: Usa [admin](file:///d:/tender/tenderwriter/backend/app/api/system.py#25-30) / [admin](file:///d:/tender/tenderwriter/backend/app/api/system.py#25-30) per accedere con pieni poteri.
2. **AI Search**: Fai qualche domanda e osserva la sidebar della cronologia che si popola.
3. **Monitor**: Accedi a "System Monitor" dalla barra laterale per vedere lo stato dell'infrastruttura.
4. **Proxy**: In "Impostazioni", prova a cambiare i timeout e clicca "Applica a Caldo".

Tutti i componenti backend e frontend sono stati integrati correttamente e sono pronti all'uso.
