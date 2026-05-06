# Repository Guidelines

## Project Structure & Module Organization
`frontend/` contains the React + TypeScript UI (`src/`, `public/`, `nginx/`). `backend/app/` is the FastAPI product backend, `backend/migrations/` contains Alembic migrations, and `backend/tests/` contains backend tests. Supporting services live in `kpi-reason-engine/`, `ops-agent/`, and `gateway/`, each with their own `app/` and tests. `utility/` contains maintenance helpers, and `docker-compose.yml` is the main local orchestration entry point.

## Build, Test, and Development Commands
Use Docker first when you need the full stack:

- `docker compose up -d` starts the default local environment.
- `docker compose --profile keycloak up -d` adds the SSO profile.
- `cd frontend && npm run dev` starts Vite on port `3000`.
- `cd frontend && npm run build` creates the production bundle.
- `cd frontend && npm test` runs the Vitest suite.
- `cd backend && pytest -q` runs the main backend tests.
- `cd backend && ruff check .` applies the Python lint rules.
- `cd backend && pytest -q tests/test_main_route_registration.py` mirrors a CI smoke check.

## Coding Style & Naming Conventions
Python targets 3.11+ and follows Ruff with a 100-character line length. Use 4-space indentation, snake_case for modules/functions, and type hints on new public code. Frontend files use 4-space indentation, semicolons, single quotes, PascalCase for pages/components such as `Dashboard.tsx`, and `useX.ts` for hooks. Keep helper and test files adjacent to the feature when possible.

## Testing Guidelines
Pytest is the standard test runner for Python services; backend async tests use `pytest-asyncio`, and some suites use `unittest.TestCase` but still run under pytest. Frontend tests use Vitest with `*.test.ts` and `*.test.tsx` naming. No global coverage threshold is enforced in CI, so add or update focused tests for every behavior change, especially around API contracts, auth, and persistence.

## Commit & Pull Request Guidelines
Recent history favors short, lower-case, imperative subjects like `fix login sso` and `tuning ai search`. Keep commits focused and descriptive; avoid placeholders like `.`. PRs should include a concise summary, linked issue or context, the commands you ran, and screenshots for UI work. Call out `.env`, Docker, migration, or profile changes explicitly because they affect local setup.

## Security & Configuration Tips
Start from `.env.example` and keep real secrets only in local `.env`. Treat `docker-compose.yml` as the source of truth for ports, container names, and profiles; when those change, update the README in the same patch.
