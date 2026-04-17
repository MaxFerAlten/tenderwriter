# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the stack

Everything is containerized. The normal dev flow is Docker Compose, not local venv/uvicorn.

```bash
# Default stack (no SSO, no video): Postgres, Qdrant, Neo4j, Redis, MinIO,
# llama-tender, gpt4free, mailpit, backend (tw-backend), frontend (tw-frontend),
# celery-worker, celery-beat, gateway, onlyoffice, kpi-reason-engine, ops-agent.
docker compose up -d

# With Keycloak SSO profile (adds kc-postgres, keycloak, keycloak-bootstrap).
docker compose --profile keycloak up -d

# With video collab (Mattermost, Jitsi, Vosk, transcript-forwarder).
docker compose --profile videochat up -d

# Both profiles together — this is what build_and_start.sh runs.
./build_and_start.sh
```

Profiles are disjoint: the default `up -d` does NOT start Mattermost or Keycloak; `--profile keycloak` does NOT start Mattermost. Combine profiles explicitly to get everything.

Full reset (destroys all volumes, including DBs/users/realm):
```bash
docker compose down -v
docker compose --profile keycloak up -d
```

Rebuild after code changes:
```bash
docker compose build backend && docker compose up -d backend
docker compose build frontend && docker compose up -d frontend
```

## Tests & checks

**Backend** (`cd backend`, tests live in `backend/tests/`). Pytest is configured in `backend/pyproject.toml` with `asyncio_mode = "auto"`:

```bash
# Run in the running backend container (fastest — deps + DB already there)
docker exec tw-backend pytest -q
docker exec tw-backend pytest tests/test_rag_history.py -q
docker exec tw-backend pytest tests/test_rag_history.py::test_name -q

# Lint
docker exec tw-backend ruff check .
```

**Frontend** uses Vitest (`frontend/package.json`):
```bash
cd frontend && npm run test          # run once
cd frontend && npm run build         # tsc -b + vite build (also runs in CI)
cd frontend && npm run dev           # dev server on :3000 (proxies to backend)
```

**CI** (`.github/workflows/wave1-ci.yml`) runs Wave-1 smoke/reload scripts from `tools/` and `backend/tests/test_wave1_resume_minimal.py` — not the full pytest suite.

## Ops / debugging shortcuts

```bash
docker logs -f tw-backend                                    # backend logs
docker logs tw-keycloak-bootstrap                            # SSO user seeding
docker exec tw-backend sh -c "export PYTHONPATH=/app && python3 app/delete_user.py"
```

URLs: frontend `http://localhost:3000`, backend OpenAPI `http://localhost:8000/docs`, Mailpit (OTP inbox) `http://localhost:8025`, Keycloak admin `http://localhost:8180/admin`, Neo4j browser `http://localhost:7474`, Redis Insight `http://localhost:8001`.

## Architecture — two FastAPI apps in one repo

The `backend/` tree contains **two independent FastAPI applications** that share no state and must not be conflated:

1. **TenderWriter** — `backend/app/` — the production tender-proposal app. Entry point `app.main:app` (that's what the `tw-backend` Dockerfile CMD runs on :8000). Config in `backend/app/config.py` (no env prefix, validates unsafe defaults at startup).
2. **TenderClaw** — `backend/` top-level modules (`backend/main.py`, `backend/api/`, `backend/agents/`, `backend/orchestration/`, `backend/mcp/`, `backend/plugins/`, `backend/core/`, `backend/config.py`) — a separate multi-agent AI coding assistant. Entry point `backend.main:app` on port 7000, config prefix `TENDERCLAW_`. **It is NOT deployed by docker-compose.** It has its own tests (`test_tenderclaw_*.py`) and its own pyproject is at the repo root-adjacent. Almost all product work targets TenderWriter; touch TenderClaw only when explicitly asked.

When editing, always confirm which app you're in:
- `from app.xxx` / `backend/app/…` → TenderWriter
- `from backend.xxx` / `backend/{api,core,agents,orchestration,…}` → TenderClaw

### TenderWriter (`backend/app/`) internals

- **Lifespan** (`app/main.py`) runs Alembic migrations via `init_db()` → `app.db.migrations.run_migrations` (bootstrap mode set by `DB_SCHEMA_BOOTSTRAP_MODE`, default `alembic`, legacy `metadata_compat` delegates to Alembic anyway). Then seeds/toggles the admin user, lazy-inits `HybridRAGEngine` onto `app.state.rag_engine`, and registers built-in hooks.
- **Alembic** lives in `backend/migrations/` (NOT `backend/app/migrations/`) with config `backend/alembic.ini`. Versions are `YYYYMMDD_NNNN_*.py`; add a new revision when touching SQLAlchemy models. Do not hand-write DDL in model files.
- **Routers** are all wired in `app/main.py` under `/api/*`. Auth uses `slowapi` rate-limiting (login/register limits live in `app/api/auth.py`).
- **HybridRAG** (`app/rag/`): `engine.py` orchestrates `DenseRetriever` (Qdrant) + `SparseRetriever` (BM25) + `GraphRetriever` (Neo4j), fuses via `RankFusion` (RRF), re-ranks with a cross-encoder, and generates via `Generator` talking to the **llama-tender** container (`llama_server_url`, Qwen2.5-Coder-7B served by llama.cpp). `ollama_*` settings are deprecated — don't add new callers. Weights and top-k values are in `settings.rag_*`. `engine.py` also contains substantial prompt-leakage sanitization regex — edit carefully, the regex sets are load-bearing for output quality.
- **Async task queue**: `app/celery.py` defines `celery_app` (Redis broker), tasks in `app/tasks.py`. `celery-worker` + `celery-beat` containers run these; long-running jobs (ingestion, export) go through Celery, not request handlers. Beat schedules nightly cleanup tasks.
- **Ingestion** (`app/ingestion/pipeline.py`, `observability.py`) writes progress into `Document.metadata_json` via `update_ingestion_observability` — the `/api/ingestions` endpoints and the frontend `IngestionMonitor` page read that shape. Don't bypass these helpers when mutating stage/progress.
- **Privacy gateway**: optional `anonymizer` service (`app/privacy_policy.py`, `app/privacy_audit.py`, `app/api/rag.py::_resolve_runtime_privacy_policy`) can anonymize prompts before they leave for external LLMs. Controlled by `anonymizer_enabled` (env + runtime `AppSettings` override) and per-tender policies.
- **Auth modes**: `AUTH_PROVIDER` = `legacy` | `keycloak` | `hybrid`. In `hybrid` both JWT-local and Keycloak OIDC are active; Keycloak JWKS is validated against `keycloak_internal_url`, but issuer/logout use `keycloak_url`. Keep both URLs in sync when configuring.
- **Mattermost edition switch**: `MM_EDITION=team` uses the custom `com.tenderwriter.oidc` plugin (default); `MM_EDITION=enterprise` uses native OIDC. The realm import in `keycloak/` already registers both callback URLs. Use `utility/switch-mattermost-mode.ps1` to flip.

### Frontend (`frontend/`)

- React 18 + TS + Vite + SWC. Routes are lazy-loaded from `src/router/lazyRoutes.tsx` and warmed on hover (`App.tsx::warmRoute`, `preloadLikelyRoutes` by role). When adding a page: add the `.tsx` under `src/pages/`, export a lazy wrapper from `lazyRoutes.tsx`, add the `<Route>` in `App.tsx`, and (if sidebar-visible) add an entry to `navItems` with `adminOnly` if needed.
- Auth is React Context: `src/contexts/AuthContext.tsx`. Admin-only routes are gated twice: sidebar filter + `user.role === 'admin'` check per-route.
- Dev server proxies `/api` to the backend via `src/devProxyConfig.ts` (used in `vite.config.ts`). In production the frontend is built and served by Nginx (`frontend/nginx/`), and the backend is reached through the `gateway` container.
- Vitest tests sit beside their sources (e.g. `pages/Search.test.ts`, `pages/searchAnswerSanitizer.test.ts`). Keep that colocated style.

## Secrets & env

`app/config.py` **fails to start** if `app_secret_key`, `admin_password`, `database_url`, `neo4j_password`, `minio_secret_key`, or `onlyoffice_jwt_secret` are empty or contain any of `changeme`, `secret`, etc. When adding a new sensitive field, add it to `UNSAFE_DEFAULTS`/`sensitive_fields` — don't paper over it with a default.

`.env` is gitignored; `.env.example` is the canonical template.

## Known quirks

- `docker-compose.yml.backup` is kept alongside `docker-compose.yml` — ignore the backup, edit the real one.
- `backend/fix_*.py`, `frontend/fix_*.py`, and `test_demonstration.py` at the repo root are one-off migration/repair scripts, not part of the running system.
- The Neo4j graph starts empty; nodes are created by the ingestion pipeline when documents are processed. Empty `MATCH (n) RETURN n` is expected on a fresh volume.
- `ollama_data` volume and `ollama_*` settings are retained but deprecated; current LLM is llama-tender (llama.cpp + Qwen2.5-Coder-7B on :8080).
