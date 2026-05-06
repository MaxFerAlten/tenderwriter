# Walkthrough: Extract Operational Workspace

La richiesta prevedeva di isolare l'enorme pannello dell'Operational Workspace ("Contributions", "Requests", "Open rework", "Gates and calls") rimuovendolo dal fondo della già densa scheda Amministrativa, portandolo in una pagina dedicata e accessibile per mezzo di un bottone.

L'operazione è stata completata con successo, ripulendo l'interfaccia principale e focalizzando lo spazio sulle Dashboard.

## Cosa è stato implementato:

1. **Routing dedicato:**
   - È stata aggiunta in [lazyRoutes.tsx](file:///D:/tender/tenderwriter/frontend/src/router/lazyRoutes.tsx) e in [App.tsx](file:///D:/tender/tenderwriter/frontend/src/App.tsx) la nuova rotta `/observability-kpi/:tenderId/operational-workspace`.
   - Il meccanismo di lazy-loading è stato configurato per pre-caricare adeguatamente la vista in memoria al bisogno.

2. **Nuova pagina "Shell":**
   - Ho creato [src/pages/OperationalWorkspacePage.tsx](file:///D:/tender/tenderwriter/frontend/src/pages/OperationalWorkspacePage.tsx), progettata esclusivamente attorno al [OperationalWorkspacePanel](file:///D:/tender/tenderwriter/frontend/src/components/observability/OperationalWorkspacePanel.tsx#120-661).
   - La pagina auto-referenzia e ricarica i dettagli del _Tender_ grazie all'ID proveniente dall'URL senza dipendere in modo bloccante dalla dashboard genitrice. 
   - Presenta una pulsantiera "Back to KPI Dashboard" per l'uscita veloce.

3. **Integrazione "Card" su Amministrativa:**
   - Ho cancellato il rendering "pesante" e diretto dell'[OperationalWorkspacePanel](file:///D:/tender/tenderwriter/frontend/src/components/observability/OperationalWorkspacePanel.tsx#120-661) nel file [AmministrativaView.tsx](file:///D:/tender/tenderwriter/frontend/src/features/observability/views/AmministrativaView.tsx).
   - Al suo posto ora, alla base della vista Amministrativa, viene mostrato un banner/card descrittivo che funge da "ponte" invitando l'utente al click sul bottone "Apri Operational Workspace".

L'architettura dell'applicazione compila senza errori ed i tipi TypeScript di React-Router rispondono in maniera fluida alle interazioni del link.
