# Extract Operational Workspace to Separate Page

La richiesta consiste nell'estrarre tutta la parte di "Operational Workspace" (Contributions, Requests, Rework, Gates, Calls) che attualmente si trova in fondo alla "Vista Amministrativa", e portarla in una pagina dedicata, accessibile tramite un bottone.

## Proposed Changes

### Routing and App Shell
#### [MODIFY] [lazyRoutes.tsx](file:///D:/tender/tenderwriter/frontend/src/router/lazyRoutes.tsx)
- Aggiunta del nuovo loader per la rotta: `'/observability-kpi/:tenderId/operational-workspace'`.
- Aggiornamento della funzione [normalizeRoutePath](file:///D:/tender/tenderwriter/frontend/src/router/lazyRoutes.tsx#34-53) per intercettare la nuova rotta dinamica.
- Esportazione del nuovo componente lazy `OperationalWorkspacePage`.

#### [MODIFY] [App.tsx](file:///D:/tender/tenderwriter/frontend/src/App.tsx)
- Importazione `OperationalWorkspacePage`.
- Aggiunta della definizione `<Route path="/observability-kpi/:tenderId/operational-workspace" ... />` sotto le rotte protette da admin.

---

### Pages and Views
#### [NEW] [OperationalWorkspacePage.tsx](file:///D:/tender/tenderwriter/frontend/src/pages/OperationalWorkspacePage.tsx)
- Creazione di una nuova pagina ad hoc che fungerà da "guscio" per l'[OperationalWorkspacePanel](file:///D:/tender/tenderwriter/frontend/src/components/observability/OperationalWorkspacePanel.tsx#120-661).
- La pagina utilizzerà `useParams()` per ottenere il `tenderId`.
- Effettuerà una fetch iniziale tramite `tenderApi.get(tenderId)` per ottenere i metadati del tender.
- Curerà la topbar della pagina includendo un bottone o link per tornare indietro alla dashboard principale `/observability-kpi`.
- Renderizzerà internamente il componente `<OperationalWorkspacePanel tender={tender} />`.

#### [MODIFY] [AmministrativaView.tsx](file:///D:/tender/tenderwriter/frontend/src/features/observability/views/AmministrativaView.tsx)
- Rimozione del rendering in-line del `<OperationalWorkspacePanel>`.
- Aggiunta di una piccola "Card" riassuntiva che invita l'utente allo spazio operativo.
- Aggiunta di un navigation button `<Link to={\`/observability-kpi/\${tender.id}/operational-workspace\`}> Apri Operational Workspace </Link>`.

## Verification Plan

### Automated Tests
- Type checking: Esecuzione di `npm run build` o `npx tsc --noEmit` per garantire la corretta integrazione dei prop di React Router.
- Linting standard del frontend.

### Manual Verification
- Navigare su `http://localhost:3000/observability-kpi`.
- Entrare in modalità [Amministrativa](file:///D:/tender/tenderwriter/frontend/src/features/observability/views/AmministrativaView.tsx#169-411).
- Verificare la corretta sparizione del mega pannello "Operational Workspace" dal fondo della vista.
- Cliccare sul nuovo bottone "Apri Operational Workspace".
- Verificare l'atterraggio sulla nuova pagina `/observability-kpi/:tenderId/operational-workspace`.
- Verificare che il workspace operativo della nuova pagina carichi e funzioni correttamente i metadati di Contributions, Requests, ecc.
- Testare il bottone "Indietro" per far ritorno alla vista osservabilità.
