# Cronologia Completa Progetto: TenderWriter

Questo documento ripercorre l'intera evoluzione della chat e dello sviluppo del progetto, dalle prime richieste di architettura fino allo stato attuale delle funzionalità.

---

## 📅 Fase 1: Visione e Architettura Iniziale
**Obiettivo**: Creare un software open-source per la scrittura di proposte di gara basato su **HybridRAG**.

*   **Setup Infrastrutturale**: Configurazione di uno stack complesso tramite Docker Compose:
    *   **Backend**: FastAPI (Python).
    *   **Frontend**: React + Vite + Tailwind (successivamente evoluto in Vanilla CSS premium).
    *   **Database**: PostgreSQL (Relazionale) + Qdrant (Vetoriale) + Neo4j (Grafo).
    *   **AI**: Ollama per LLM locali.
    *   **Storage**: MinIO per i documenti PDF.
*   **Pipeline RAG**: Analisi dei flussi di ingestione documenti, chunking e recupero ibrido (Dense + Sparse + Graph).

---

## 🔐 Fase 2: Sicurezza e Controllo Accessi
**Richiesta**: Implementare un sistema di autenticazione robusto con utenza tecnica e verifica 2FA.

*   **Auth System**: Implementazione di JWT sul backend e AuthContext sul frontend.
*   **Admin Power**: Creazione dell'utenza tecnica `admin/admin` (poi aggiornata a `admin@admin.com`) con bypass della 2FA per l'accesso rapido.
*   **Registrazione 2FA**: Sviluppo del flusso di registrazione con invio di codice OTP a 6 cifre via email.
*   **Integrazione Mailpit**: Aggiunta di un server SMTP mock per intercettare gli OTP in sviluppo senza server reali.

---

## 📊 Fase 3: Monitoraggio e "Configurazione a Caldo"
**Richiesta**: Visualizzare lo stato dei componenti e poter configurare i timeout senza riavvii.

*   **System Monitor**: Creazione di una dashboard dedicata per:
    *   Vedere i container Docker attivi/spenti.
    *   Monitorare in tempo reale CPU e RAM di ogni servizio.
    *   Leggere i log (Ollama, Neo4j, Qdrant, etc.) direttamente dal browser.
*   **Nginx Dynamic Config**: Implementazione di un sistema che scrive nel file di configurazione di Nginx all'interno del container e ricarica il servizio (`nginx -s reload`) tramite comando API, permettendo di regolare `proxy_read_timeout` istantaneamente.

---

## 🎨 Fase 4: Estetica e Raffinamento UI
**Richiesta**: Passare da uno stile "basico/anni 90" a un design premium e stiloso.

*   **Design System**: Creazione di un sistema CSS personalizzato basato sul **Glassmorphism**.
*   **Login & Register**: 
    *   Layout perfettamente centrato (addio allineamenti a sinistra).
    *   Modale "sopraelevata" con ombre profonde e bordi luminosi (glow).
    *   Effetti di blur sullo sfondo e testi con gradiente.
*   **OTP Branding**: Ottimizzazione dell'interfaccia di inserimento codice per massima usabilità.

---

## 🐞 Fase 5: Bug Fixing e Ottimizzazione Tecnica
*   **Timezone Fix**: Risoluzione dell'errore "400 Bad Request" causato dal confronto tra date offset-aware (database) e naive (Python) nei token OTP.
*   **Pydantic & Settings**: Correzione del caricamento delle variabili d'ambiente per il provider mail.
*   **Build Sync**: Chiarimento sulla necessità di ricostruire l'immagine Nginx per riflettere i cambiamenti CSS nel frontend di produzione.

---

## 🎯 Stato Attuale (AS-IS)
Il progetto dispone ora di:
1.  **Infrastruttura AI locale completa**.
2.  **Sistema di registrazione sicuro** con Mailpit.
3.  **Dashboard di monitoraggio** di livello enterprise.
4.  **UI Premium** pronta per la visualizzazione dei dati.

---
**Documento generato il:** 28/02/2026
