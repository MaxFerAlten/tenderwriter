# Refactory UI 001: Riorganizzazione /observability-kpi

**Data:** 21/03/2026  
**Task:** Riorganizzazione pagina Observability KPI monolitica  
**Stato:** Completato

---

## Problema

La pagina `/observability-kpi` era una **feature monolitica**:
- `ObservabilityKPI.tsx` conteneva ~1240 righe
- Convivano fetch portfolio, fetch detail, polling job, action handlers e JSX
- Utility UI duplicate tra `ObservabilityKPI.tsx`, `ComplianceDrilldownPanel.tsx` e `TransitionTimelinePanel.tsx`
- Nessuna navigazione a tab, scroll infinito
- Manutenzione difficile e alto carico cognitivo

---

## Soluzione Adottata

### 1. Architettura a 3 Modalità di Visualizzazione

| Modalità | Focus | Contenuto |
|----------|-------|-----------|
| **Manageriale** | Executive summary | Vista compatta con 6 tab navigabili |
| **Amministrativa** | Dettaglio completo | Tutti i pannelli espansi di default |
| **Operativa** | Workflow & Jobs | Focus su job queue e real-time status |

### 2. Modalità di Selezione

- **Al primo accesso:** Modal di selezione `ModeSelectorModal`
- **Salvataggio preferenza:** `localStorage` con key `kpi_view_mode`
- **Cambio modalità:** Toggle dropdown nell'header `ViewModeToggle`

---

## File Creati

### Hooks
```
src/features/observability/hooks/
└── useKpiViewMode.ts
    - Gestione stato modalità (manageriale/amministrativa/operativa)
    - Persistenza in localStorage
    - Rilevamento primo accesso
```

### Components
```
src/features/observability/components/
├── ModeSelectorModal.tsx
│   - Modal di selezione al primo accesso
│   - 3 card con icona, titolo e descrizione per ogni modalità
│   - Dismiss con salvataggio preferenza
│
└── ViewModeToggle.tsx
    - Dropdown toggle nell'header
    - Mostra modalità corrente con icona
    - Menu con tutte le opzioni
```

### Shared Utilities
```
src/features/observability/shared/
├── index.ts
└── formatters.ts
    - healthColors(): palette colori per health status
    - signalTone(): colori per signal type
    - semanticStatusTone(): colori per semantic status
    - analysisJobColors(): colori per job status
    - actionPriorityTone(): colori per priorità azioni
    - phaseLabel(): mapping codice fase → label leggibile
    - formatScoreValue(), formatGeneratedAt(), formatProbability()
    - chipStyle(): stile inline per chips/badge
    - mergeAnalysisMetadata(): fusione metadata da multiple source
    - isAnalysisJobActive(): check stato job attivo
```

### Views
```
src/features/observability/views/
├── index.ts                     # Esportazioni barrel
│
├── ManagerialeView.tsx
│   - Shell principale per modalità manageriale
│   - 6 tab: Overview, KPI Detail, Forecast, Compliance, Lifecycle, Operations
│   - Lazy mount-on-demand per tab non attivi
│   - Integrazione componenti reali nei tab
│
├── AmministrativaView.tsx
│   - Tutti i pannelli visibili senza tab
│   - Qualitative KPIs + Operational Scorecards
│   - LifecycleControlPanel, ComplianceDrilldownPanel, TransitionTimelinePanel
│   - OperationalWorkspacePanel
│
├── OperativaView.tsx
│   - 4 tab: Workspace, Transitions, Lifecycle, Diagnostics
│   - Job queue con stato e azioni (Recompute, Replay History, Refresh)
│   - Job details panel
│
├── OverviewTab.tsx
│   - Hero card con info tender
│   - 4 quadranti: Qualitative Score, Operational Score, Compliance, Forecast Signal
│   - Top KPI Cards (A1, A2, A3)
│   - Next Best Actions
│   - Diagnostics & Drivers panel
│
├── KpiDetailTab.tsx
│   - Qualitative KPIs cards complete
│   - Operational Scorecards grid
│   - Badge semantic, confidence, recommendations
│
└── ForecastTab.tsx
    - Forecast Summary con confidence
    - Markov Projected Path
    - Next Best Actions con priority
    - Scenarios grid
```

---

## File Modificati

### `src/pages/ObservabilityKPI.tsx`
- Rimane come **page shell**
- Gestisce fetch data (portfolio, tender detail, polling)
- Header con ViewModeToggle e azioni
- Portfolio summary cards
- Tender focus list sidebar
- Bottlenecks panel
- Portfolio intelligence panel
- Renderizza la view appropriata basata su `mode`

---

## Dipendenze Aggiunte

Nessuna nuova dipendenza - usa librerie già presenti:
- `framer-motion` per animazioni
- `lucide-react` per icone

---

## Navigazione

### Manageriale View - 6 Tab

```
[Overview] [KPI Detail] [Forecast] [Compliance] [Lifecycle] [Operations]
```

| Tab | Contenuto |
|-----|-----------|
| Overview | Hero + 4 quadranti + KPI cards + Drivers |
| KPI Detail | Qualitative KPIs + Operational Scorecards |
| Forecast | Summary + Projected Path + Next Actions + Scenarios |
| Compliance | ComplianceDrilldownPanel |
| Lifecycle | LifecycleControlPanel + TransitionTimelinePanel |
| Operations | OperationalWorkspacePanel |

### Operativa View - 4 Tab

```
[Workspace] [Transitions] [Lifecycle] [Diagnostics]
```

---

## Build & Type Check

```bash
npm run build  # ✅ tsc -b && vite build
```

- TypeScript: Nessun errore
- Build: ✅ 112.18 kB (gzip: 20.47 kB) per ObservabilityKPI bundle

---

## Prossimi Passi (Opzionali)

1. **Nested routes per deep-linking**
   - `/observability-kpi/:tenderId/compliance`
   - `/observability-kpi/:tenderId/lifecycle`

2. **Refactoring ObservabilityKPI.tsx**
   - Estrarre fetch logic in hook dedicati (`useObservabilityPortfolio`, `useObservabilityTenderDetail`)
   - Ulteriore split della sidebar

3. **Miglioramenti UI**
   - Animazioni tab transition più fluide
   - Loading states per tab mount-on-demand
   - Responsive layout per mobile

---

## Decisioni Architetturali

| Decisione | Razionale |
|-----------|-----------|
| 3 modalità invece di 2 | Operativa (job queue) è abbastanza diversa da giustificare una modalità dedicata |
| localStorage per preferenza | Semplice, no backend, persiste tra sessioni |
| Modal al primo accesso | Experience utente migliore, scelta consapevole |
| Tab mount-on-demand | Performance: non renderizzare pannelli pesanti se non necessario |
| Shared formatters | DRY, consistenza colori/labels in tutta l'app |

---

## Test

Per testare:
```bash
npm run dev
# Navigare su http://localhost:3000/observability-kpi
```

Al primo accesso apparirà il `ModeSelectorModal`. Dopo la selezione, la preferenza viene salvata e la modalità scelta viene applicata automaticamente alle visite successive.
