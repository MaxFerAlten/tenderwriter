# Log sintetico conversazione (gateway)

> Nota: contenuti sensibili (token, API key) citati in chat sono stati **rimossi/omessi** da questo log per evitare leak e blocchi push.

## Timeline dialogo
- Richiesta iniziale: introdurre `tw-gateway` come proxy per `tw-anonymizer`, `tw-llama-tender`, `tw-llama-opencode`, con fallback verso istanze DMZ ed esterni; pagina admin per configurazione puntamenti; `tw-anonymizer` come proxy trasparente.
- Condivisione board Miro e link Trello (più credenziali, poi rimosse da artefatti versionati).
- Sprint 1: creati servizi `gateway` (FastAPI dual-port tender/opencode) e `anonymizer` (relay con header `x-target-url`); integrazione in `docker-compose`; health endpoints.
- Sprint 2: backend router admin `/api/gateway/targets`, modello `AIGatewayTarget`; frontend Settings sezione “AI Gateway Targets” per CRUD dei target (solo admin).
- Sprint 3: fallback DMZ via anonymizer, env e compose aggiornati; gateway point di default per backend/opencode; test di fallback aggiunti.
- Sprint 4: fallback cloud per tender (provider openai/anthropic) con API key, opzionale anonymizer; hardening header (rimozione `Host` e hop-by-hop), retry su 5xx; health espone provider; test aggiuntivi per header e cloud flow.
- Documentazione: creato `pianificazione-ed-esecuzione-gateway.md` con cronologia e variabili (segreti omessi).
- Branching: creato branch `codex/feature/gateway`, tag `pre-gateway` su stato precedente, merge in `main`.
- Push: inizialmente bloccato da secret-scanning (credenziali Trello nel doc); file ripulito, commit riscritto, tag aggiornato, push completato (`main` + tag `pre-gateway`).

## Stato finale (10 marzo 2026)
- Branch: `main` aggiornato con gateway/anonymizer, admin UI e fallback cloud.
- Tag: `pre-gateway` punta allo stato pre-merge.
- Test eseguiti: `python -m pytest gateway/test_gateway.py` (tutti verdi).
- File chiave: `gateway/app.py`, `gateway/test_gateway.py`, `backend/app/api/gateway_admin.py`, `frontend/src/pages/Settings.tsx`, `.env.example`, `docker-compose.yml`, `resoningfromagentic/codex/pianificazione-ed-esecuzione-gateway.md`.
