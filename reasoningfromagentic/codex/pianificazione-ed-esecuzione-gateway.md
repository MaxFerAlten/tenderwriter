# Pianificazione ed esecuzione gateway AI (tw-gateway)

## Contesto e requisiti raccolti dalla chat
- Introdurre un **gateway (tw-gateway)** che faccia da proxy verso i componenti AI `tw-anonymizer`, `tw-llama-tender`, `tw-llama-opencode`.
- Fallback: se i servizi interni in Docker (`tw-llama-tender`, `tw-llama-opencode`) non sono accessibili, il gateway deve poter instradare verso componenti analoghi in DMZ (fuori da Docker) e, per `tw-llama-tender`, verso provider esterni (OpenAI/Claude/altro).
- `tw-anonymizer` deve inizialmente essere un proxy trasparente per servizi esterni.
- Necessaria una **pagina di configurazione admin** per impostare i puntamenti del gateway.
- Link Trello board: https://trello.com/b/FRHgbjf8/gateway
- Credenziali Trello fornite in chat (rimosse da questo file). Conservare i secret in un vault sicuro e reimpostarli a runtime via env/CI.

## Architettura sintetica (dalla board Miro)
- `tw-gateway` in Docker con due porte: tender (8080) e opencode (8081).
- Upstream interni: `tw-llama-tender`, `tw-llama-opencode`.
- Fallback DMZ: istanze analoghe fuori da Docker, raggiunte via gateway (eventualmente tramite `tw-anonymizer`).
- `tw-anonymizer`: relay trasparente per chiamate verso DMZ/esterni, con header `x-target-url`.
- Backend applicativo consuma il gateway (LLAMA_SERVER_URL → gateway tender).

## Cronologia per sprint
### Sprint 1
- Creato servizio **gateway** (FastAPI, doppio server uvicorn) e integrato in `docker-compose`.
- Aggiunto servizio **anonymizer** (FastAPI relay) per inoltrare verso target indicato da header.
- Healthcheck e prime rotte di proxy per `/v1/models`, `/completion`, `/v1/chat/completions`.

### Sprint 2
- Backend: modello `AIGatewayTarget`, router admin `gateway_admin.py` incluso in `backend/app/main.py`.
- Frontend: sezione admin in Settings per elencare/aggiungere/toggle/eliminare target gateway; client API aggiornato.

### Sprint 3
- Consolidamento e test di fallback DMZ e uso dell’anonymizer lato gateway.
- Aggiornate env e compose per puntare al gateway come endpoint predefinito per backend/opencode.

### Sprint 4 (hardening attuale)
- Gateway: supporto fallback cloud per tender (provider configurabile `openai`/`anthropic`) con bearer API key e opzionale passaggio tramite anonymizer.
- Ritenta su ogni 5xx prima di scalare al candidato successivo; rimozione dell’header `Host` e degli hop-by-hop in uscita.
- Health arricchito con info sul provider cloud configurato.
- Test aggiuntivi per header-scrubbing, fallback cloud via proxy e via app FastAPI, più copertura esistente DMZ/anonymizer.

## Variabili di configurazione chiave
- `GATEWAY_TENDER_UPSTREAM`, `GATEWAY_OPENCODE_UPSTREAM`
- `GATEWAY_TENDER_DMZ_UPSTREAM`, `GATEWAY_OPENCODE_DMZ_UPSTREAM`
- `GATEWAY_ANONYMIZER_URL`
- Fallback cloud (tender):
  - `GATEWAY_TENDER_CLOUD_PROVIDER` (`openai` | `anthropic`)
  - `GATEWAY_OPENAI_BASE_URL` (default `https://api.openai.com`)
  - `GATEWAY_OPENAI_API_KEY`
  - `GATEWAY_ANTHROPIC_BASE_URL` (default `https://api.anthropic.com`)
  - `GATEWAY_ANTHROPIC_API_KEY`
- Esempi/documentazione aggiornati in `.env.example` e `docker-compose.yml`.

## Test automatici eseguiti
- `python -m pytest gateway/test_gateway.py`
  - Copre fallback DMZ senza/ con anonymizer.
  - Copre header-scrubbing.
  - Copre fallback cloud con anonymizer e API key.
  - Copre flow completo via app FastAPI (build_candidates) verso provider cloud.

## Note operative
- Branch di lavoro: `codex/feature/gateway`.
- `tw-anonymizer` rimane proxy trasparente; personalizzazioni future potranno essere aggiunte.
- Le credenziali Trello qui annotate vanno protette (considerare rotazione se commit pubblico).
