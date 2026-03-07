# Cronologia Interazioni — 28 Febbraio 2026

Questo documento riassume tutte le attività, i suggerimenti e le modifiche apportate durante la sessione di sviluppo odierna sul progetto **TenderWriter**.

---

## 🛠️ Attività Svolte

### 1. Debugging e Correzione Registrazione
- **Problema**: Errore "400 Bad Request" generico durante la registrazione e "Unknown error" durante la verifica OTP.
- **Causa**: Conflitto di timezone tra Python (offset-naive) e PostgreSQL (offset-aware) durante il confronto della data di scadenza dell'OTP.
- **Soluzione**:
    - Abilitazione dei log di debug nel backend.
    - Modifica di `auth.py` per utilizzare `datetime.now(timezone.utc)` garantendo coerenza in tutto il flusso.
    - Risolto errore di validazione Pydantic aggiungendo i type hints ai campi SMTP in `config.py`.

### 2. Implementazione Email & 2FA (Test Lab)
- **Componente**: Inserito **Mailpit** nello stack `docker-compose`.
- **Configurazione**:
    - SMTP Host: `mailpit` (porta 1025).
    - Web UI: Disponibile a `http://localhost:8025`.
- **Flusso**: Ora le email OTP vengono catturate istantaneamente da Mailpit, permettendo di testare il login sicuro senza configurare un provider reale.

### 3. Restyling Grafico "Premium"
- **Obiettivo**: Superare lo stile "anni 90" per un'estetica moderna e pulita.
- **Interventi**:
    - **Layout**: Centrato e minimalista per le pagine di login e registrazione.
    - **Estetica**: Implementato il **Glassmorphism** (effetto satinato, blur, bordi luminosi).
    - **Elevazione**: Card con ombre profonde e riflesso superiore (glow) per un effetto "modal sopraelevata".
    - **Pulizia**: Rimosse le linee di stile inline in favore di classi CSS riutilizzabili in `index.css`.

### 4. Monitoraggio e Configurazione "A Caldo"
- **System Monitor**: Creata pagina FE per vedere lo stato dei container Docker, utilizzo CPU/RAM e log in tempo reale.
- **Nginx Dynamic Config**: Implementata API per cambiare i timeout di Nginx (`proxy_read_timeout`, etc.) direttamente dal frontend senza riavviare manualmente i servizi.

---

## 💡 Suggerimenti per la Gestione Docker

Durante lo sviluppo del frontend, abbiamo chiarito che:
- **Build di Produzione**: Il `Dockerfile` attuale esegue `npm run build`. Ogni modifica alla grafica (CSS/TSX) richiede una ricostruzione dell'immagine:
  ```powershell
  docker compose build frontend
  docker compose up -d frontend
  ```
- **Hot Reload (Dev)**: Se desideri vedere i cambiamenti istantaneamente senza ricostruire ogni volta, è consigliabile implementare un `Dockerfile.dev` che esegua `npm run dev` mappando i volumi.

---

## 📂 Strumenti di Test Creati
Sono stati creati degli script di utilità all'interno del container backend (`/app/app/`):
- `test_reg.py`: Per simulare una registrazione via script.
- `delete_user.py`: Per cancellare velocemente un utente specifico e riprovare il flusso.
- `clean_db.py`: Per ripulire il database dagli utenti di test e mantenere solo l'admin.

---

## 📄 Documentazione Aggiornata
- Il file `README.md` è stato riscritto per descrivere lo stato **AS-IS** attuale, includendo il nuovo tech stack e le istruzioni per Mailpit.

---
**Ultimo aggiornamento:** 28/02/2026 - Ore 18:05
