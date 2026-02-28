# Importazione PDF nel Frontend

Ho analizzato in dettaglio il codice sorgente del frontend (`d:\tender\tenderwriter\frontend\src`). 

## Situazione Attuale
Allo stato attuale, **non esiste nell'interfaccia utente (UI) un pulsante o una schermata per caricare un PDF legato a una gara**.
Il frontend permette di creare una Gara (Tender) dalla schermata "Dashboard", ma non offre l'opzione per allegare i documenti. L'endpoint backend `/api/tenders/{tender_id}/import` esiste ed è funzionante (come testato nello step precedente), ma il team frontend non ha ancora implementato il bottone e la chiamata API in [client.ts](file:///d:/tender/tenderwriter/frontend/src/api/client.ts) per utilizzarlo.

## Come fare per importare il PDF ora?

Dato che l'interfaccia non è ancora pronta, hai due opzioni per importare i tuoi PDF nelle gare:

### Opzione 1: Usare le API (Postman / cURL)
Se hai creato una gara dal frontend (es. ID 1), puoi caricare il documento direttamente chiamando l'API backend dal tuo terminale.

**Esempio cURL:**
```bash
curl -X POST "http://localhost:8000/api/tenders/1/import" \
  -H "Authorization: Bearer IL_TUO_TOKEN_JWT" \
  -F "file=@/percorso/al/tuo/documento.pdf"
```

### Opzione 2: Usare lo script di Test (Python)
Puoi usare o modificare lo script [test_pdf_upload.py](file:///d:/tender/tenderwriter/backend/test_pdf_upload.py) che ti ho creato prima. Quello script si occupa già di autenticarsi, creare la gara e fare l'upload del PDF automaticamente.

### Opzione 3: Implementare la UI nel Frontend (Consigliato)
Per aggiungere la funzionalità al frontend, bisognerebbe:
1. Aggiungere il metodo `uploadDocument` in [src/api/client.ts](file:///d:/tender/tenderwriter/frontend/src/api/client.ts).
2. Modificare il [Dashboard.tsx](file:///d:/tender/tenderwriter/frontend/src/pages/Dashboard.tsx) (o creare una pagina di dettaglio Gara) inserendo un bottone `<input type="file" />`.
3. Collegare l'invio del file per creare un oggetto `FormData` e mandarlo all'API.

*Se desideri che io implementi la UI nel frontend per avere il bottone di upload direttamente nella dashboard, chiedimelo pure!*


Il pulsante "Upload PDF" che ho aggiunto si trova all'interno della "Card" (scheda) di ogni singola gara, perché ogni documento PDF deve essere associato a un progetto specifico.

Per vedere il pulsante, ti basta fare così:

Clicca sul pulsante viola "+ New Tender" in alto a destra.
Inserisci un titolo a caso (es. "Gara di prova") e clicca su "Create Tender".
Apparirà un riquadro (una card) nella colonna "Draft" con il nome della tua gara.
Lì troverai il pulsante "Upload PDF" che potrai cliccare per caricare il tuo file!
Prova a creare una gara e vedrai che il pulsante apparirà immediatamente. Se incontri altri problemi, sono qui!