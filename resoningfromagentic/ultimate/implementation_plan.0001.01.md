# Proposta: Persistenza Status Ingestion in Dashboard

Il problema riscontrato (il tasto "Activate Tender" non compare dopo il refresh della pagina) è dovuto al fatto che lo stato dell'ingestion dei documenti è attualmente mantenuto solo nello stato volatile di React nel frontend.

## Modifiche Proposte

### Backend

#### [MODIFY] [tenders.py](file:///d:/tender/tenderwriter/backend/app/api/tenders.py)
- Aggiornare il modello `TenderResponse` per includere `ingestion_status: str | None = None`.
- Modificare `_tender_to_response` per calcolare lo stato di ingestion aggregato dai documenti del tender (se caricati).
- Aggiornare l'endpoint `list_tenders` per includere `selectinload(Tender.documents)` nelle opzioni della query, garantendo che i dati siano disponibili senza query aggiuntive per ogni riga.

### Frontend

#### [MODIFY] [client.ts](file:///d:/tender/tenderwriter/frontend/src/api/client.ts)
- Aggiungere `ingestion_status?: string` all'interfaccia `Tender`.

#### [MODIFY] [Dashboard.tsx](file:///d:/tender/tenderwriter/frontend/src/pages/Dashboard.tsx)
- Aggiornare il componente `TenderCard` per calcolare uno stato di ingestion "effettivo" che combini quello ricevuto dalla backend (persistente) con quello della sessione corrente (SSE).
- In questo modo, se un'ingestion è stata completata in precedenza, il tasto "Activate Tender" sarà visibile immediatamente al caricamento della pagina.

## Piano di Verifica

### Manuale
1. Caricare un documento per un nuovo Tender "test".
2. Attendere il completamento (pulsante Activate compare).
3. Ricaricare la pagina (F5).
4. Verificare che il pulsante "Activate Tender" sia ancora visibile sulla card.
5. Verificare che cliccando "Activate", il Tender passi correttamente nella colonna "Active".
