# TenderWriter

> Open-source Tender Proposal Writing Software powered by HybridRAG

TenderWriter helps teams create, manage, and submit professional tender proposals faster by leveraging a **HybridRAG engine** (Dense + Sparse + Knowledge Graph retrieval) that runs entirely on local and open-source infrastructure.

---

## 🚀 Current Status (AS-IS)

The project is under active development. Below are the currently implemented and working features and components:

### 🔐 Authentication & Security
- **Traditional Login (legacy/local)**: Technical user `admin@admin.com` with password configured in the `.env` file (default: `vN7pQ3wL9xR5tY2uA4bC6dE8fG1hJ0`).
- **SSO + Traditional Login**: The project supports three auth modes configurable via env:
  - `legacy`: email/password login only
  - `keycloak`: SSO login via Keycloak only
  - `hybrid`: dual mode, with both SSO button and traditional form active together
- **Keycloak → TenderWriter Users**: In the development setup, currently aligned with the `tenderwriter` realm, the following are used:
  - `admin@admin.com` / `TestPass123!` → Keycloak role `tw_admin` → TenderWriter role `admin`
  - `registrazioni.hyperknow@gmail.com` / `TestPass123!` → default Keycloak role → TenderWriter role `editor`
- **Keycloak Automatic Bootstrap**: With `docker compose --profile keycloak up -d`, the one-shot `tw-keycloak-bootstrap` service automatically creates/updates these users in the `tenderwriter` realm.
- **Keycloak Realm Note**: The import file of the `tenderwriter` realm does not create users by itself; user bootstrap is executed immediately after Keycloak starts.
- **User Registration**: Complete registration flow with **2FA via OTP** verification.
- **Mail Testing**: Integration with **Mailpit** to catch OTP emails in the development environment (available at `http://localhost:8025`).
- **Session Management**: Authentication system based on legacy JWT, Keycloak OIDC, and React Context with runtime bootstrap.

### 🧠 HybridRAG Engine
- **Dense Retrieval**: Semantic search via **Qdrant** (Vector Database).
- **Sparse Retrieval**: Built-in keyword search (BM25).
- **Knowledge Graph**: Integration with **Neo4j** to capture complex relationships between tenders and requirements.
- **Local LLM**: Generation and analysis via **Ollama** (Llama 3 by default).

### 🖥️ Frontend & Dashboard
- **Modern Interface**: Dark Mode design with premium aesthetics (Glassmorphism), fluid animations, and a centered layout for auth.
- **System Monitor**: Real-time visualization of Docker container status, CPU/RAM usage, and live logs of components (Qdrant, Redis, Ollama, etc.).
- **Hot Configuration**: Dynamic management of Nginx timeouts directly from the administration interface.
- **RAG Health**: Dashboard to monitor the health status of individual AI engine components.

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Python 3.11+, FastAPI, SQLAlchemy |
| **Frontend** | React 18, TypeScript, Vite, Framer Motion, Lucide Icons |
| **Relational Database** | PostgreSQL 16 |
| **Vector Database** | Qdrant |
| **Graph Database** | Neo4j Community |
| **Object Storage** | MinIO |
| **AI Infrastructure** | llama.cpp server (Qwen2.5-Coder-7B) |
| **Testing/Developer Tool** | Mailpit (Mock SMTP) |
| **Proxy & Static** | Nginx |

---

## 🚦 Quick Start

To start the entire stack locally:

```bash
# 1. Start all containers
docker compose up -d

# 2. Access the application
# Frontend: http://localhost:3000
# Mailpit (for OTP): http://localhost:8025
# Backend Docs (OpenAPI): http://localhost:8000/docs
```

To also start the SSO profile with Keycloak:

```bash
docker compose --profile keycloak up -d
```

Important:

- The `keycloak` profile starts Keycloak and SSO user bootstrap, but does not start Mattermost.
- Mattermost, `mm-postgres`, `mm-plugin-oidc`, Jitsi, Jigasi, Vosk, and `transcript-forwarder` are part of the `videochat` profile.
- To have TenderWriter + SSO + video stack together, you must use `docker compose --profile keycloak --profile videochat up -d`.

### Full Reset + Keycloak Bootstrap

If you want to start from scratch for the SSO profile as well and recreate the realm, Keycloak database, and bootstrap users:

```bash
# 1. Stop everything and also remove volumes
docker compose down -v

# 2. Bring the stack back up with the Keycloak profile
docker compose --profile keycloak up -d

# 3. Check user bootstrap
docker logs tw-keycloak-bootstrap
```

Expected result:

- Keycloak available at `http://localhost:8180`
- `tenderwriter` realm imported
- users `admin@admin.com` and `registrazioni.hyperknow@gmail.com` automatically created or updated
- `tw_admin` role assigned to `admin@admin.com`

Useful endpoints for SSO mode:

- Frontend: `http://localhost:3000`
- Keycloak: `http://localhost:8180`
- Mailpit: `http://localhost:8025`

### Authentication Modes

Login behavior depends on these variables:

```env
AUTH_PROVIDER=hybrid
VITE_AUTH_MODE=hybrid
KEYCLOAK_URL=http://localhost:8180
KEYCLOAK_INTERNAL_URL=http://keycloak:8080
MM_EDITION=team
MM_OIDC_ENABLE=false
TW_OIDC_ENABLE=true
MM_LOGIN_REDIRECT_MODE=plugin
```

Operational meaning:

- `AUTH_PROVIDER=legacy` and `VITE_AUTH_MODE=legacy`: traditional login only
- `AUTH_PROVIDER=keycloak` and `VITE_AUTH_MODE=keycloak`: SSO login only
- `AUTH_PROVIDER=hybrid` and `VITE_AUTH_MODE=hybrid`: traditional + SSO login together

With `hybrid`, the `/login` page shows:

- `Sign in with SSO` button
- classic email/password form

### Switching Mattermost: Enterprise vs Team/Community

The project supports two Mattermost modes, selectable only via configuration:

- `MM_EDITION=team`: uses Mattermost Team/Community with the `com.tenderwriter.oidc` plugin (this is the default)
- `MM_EDITION=enterprise`: uses Mattermost Enterprise/Entry with native OIDC

Default configuration for Team/Community:

```env
MM_EDITION=team
MM_OIDC_ENABLE=false
TW_OIDC_ENABLE=true
MM_LOGIN_REDIRECT_MODE=plugin
```

Alternative configuration for Enterprise/Entry:

```env
MM_EDITION=enterprise
MM_OIDC_ENABLE=true
TW_OIDC_ENABLE=false
MM_LOGIN_REDIRECT_MODE=off
```

Operational notes:

- the imported Keycloak realm already includes both Mattermost callbacks:
  - `http://localhost:3000/mm/signup/openid/complete`
  - `http://localhost:3000/mm/plugins/com.tenderwriter.oidc/callback`
- in `team` mode, direct access to `http://localhost:3000/mm/login` can be redirected to the plugin only if `MM_LOGIN_REDIRECT_MODE=plugin`
- in `hybrid` mode, only TenderWriter sessions authenticated via Keycloak use Mattermost SSO; traditional logins continue to use the legacy fallback

Quick terminal switch:

```powershell
# switch to Team/Community + plugin
.\utility\switch-mattermost-mode.ps1 team

# switch to Enterprise/Entry + native OIDC
.\utility\switch-mattermost-mode.ps1 enterprise

# update only .env without restarting containers
.\utility\switch-mattermost-mode.ps1 team -NoRestart
```

### Development Credentials

Legacy local account:

- Email: `admin@admin.com`
- Password: value present in `.env` or default `vN7pQ3wL9xR5tY2uA4bC6dE8fG1hJ0`

Keycloak users synchronized to TenderWriter:

- `admin@admin.com` / `TestPass123!`
  - Realm: `tenderwriter`
  - Keycloak Role: `tw_admin`
  - TenderWriter App Role: `admin`
- `registrazioni.hyperknow@gmail.com` / `TestPass123!`
  - Realm: `tenderwriter`
  - Keycloak Role: `default-roles-tenderwriter`
  - TenderWriter App Role: `editor`

Keycloak admin console:

- URL: `http://localhost:8180/admin`
- Username: `admin`
- Password: `DefaultKCAdmin2026Pass`

Mattermost system admin:

- Username: `tw-admin`
- Email: `tw-admin@tenderwriter.local`
- Password: `TW2026Secure!Pass`

Note:

- In `hybrid` mode, you can use both the traditional local login and the Keycloak users above.
- In pure `keycloak` mode, traditional login is intentionally disabled.
- If you recreate Keycloak volumes, realm users are automatically reseeded by the `tw-keycloak-bootstrap` service.
- If you recreate Mattermost volumes, the technical user `tw-admin` and the `tenderwriter` team are automatically reseeded by the `tw-mattermost-bootstrap` service.

### Email Configuration (Mailpit)
The system is configured to send emails to a local SMTP server (Mailpit). No real SMTP configuration is required for development. To view OTP codes:
1. Register in the app (e.g., `test@example.com`).
2. Open `http://localhost:8025` in your browser.
3. Copy the code and enter it in the frontend.

### Video Collaboration Stack (Optional)
Mattermost, Jitsi, Vosk, and the transcript forwarder are behind the `videochat` profile, so they do not start with the standard `docker compose up -d`.

Even `docker compose --profile keycloak up -d` does not start them: the `keycloak` profile remains separate from the `videochat` profile.

Automatic videochat bootstrap:

- the one-shot `tw-mattermost-bootstrap` service automatically creates or realigns the Mattermost technical user `tw-admin`
- it also creates the default `tenderwriter` team
- it adds `tw-admin` to the team, so the backend can correctly authenticate even after a volume reset
- this avoids the classic `401 Unauthorized` on `POST /mm/api/v4/users/login` when Mattermost starts empty

To also start video collaboration:
```bash
docker compose --profile videochat up -d \
  mm-postgres mattermost \
  jitsi-prosody jitsi-jicofo jitsi-jvb jitsi-web vosk jitsi-jigasi \
  transcript-forwarder
```

To simultaneously start Keycloak SSO and video collaboration:
```bash
docker compose --profile keycloak --profile videochat up -d
```

Operational notes:
- `transcript-forwarder` stays idle if `MM_TRANSCRIPT_WEBHOOK_URL` is not configured.
- The Mattermost button in the frontend uses the current host as fallback, so it works even if you access the dashboard from an IP/LAN and not from `localhost`.

---

## 🔧 Development & Debugging

### Backend Debug
The backend is configured with detailed logs. You can monitor them with:
```bash
docker logs -f tw-backend
```
### Delete Users 
```bash
docker exec tw-backend sh -c "export PYTHONPATH=/app && python3 app/delete_user.py"
docker compose build backend
```

### Frontend Build
Since the frontend is served by Nginx, after structural changes you need to rebuild the image:
```bash
docker compose build frontend
docker compose up -d frontend
```

### Backend Debug
The backend is now running with:

✅ Secret validation at startup
✅ Rate limiting (3/min register, 5/min login)
✅ MinIO storage for OnlyOffice
✅ Changed default values in docker-compose

Note: The default passwords are now DefaultPg2024Pass, DefaultNEO4J2024Pass, DefaultMinIO2024Pass. In production, you should use more secure ones and store them in a vault.

Temporary test credentials:

- Local legacy: `admin@admin.com` / value in `.env`
- Keycloak/TenderWriter admin: `admin@admin.com` / `TestPass123!`
- Keycloak/TenderWriter editor: `registrazioni.hyperknow@gmail.com` / `TestPass123!`
- Mattermost admin: `tw-admin` / `TW2026Secure!Pass`
---

## 🗺️ Roadmap Next Steps
- [ ] Full integration of AI search with user history.
- [ ] Professional export to PDF/Docx.
- [ ] Refinement of the Compliance Matrix for automatic tender mapping.


### Use repomix to get an md file to provide to external LLMs for architectural analysis, bug fixing, and robustness
You need to install repomix: 
```bash
curl -fsSL https://raw.githubusercontent.com/repomix/repomix/main/install.sh | bash
```
then: 
```bash
repomix --style markdown
```
if repomix does not work due to various conflicts with other tools, you can use: 
```bash
docker pull ghcr.io/yamadashy/repomix:latest
docker run --rm -v "d:/tender/tenderwriter:/app" ghcr.io/yamadashy/repomix .
📦 Repomix v1.11.0
No custom config found at repomix.config.ts, repomix.co
✔ Packing completed successfully!      
```
we recommend using repomix locally with nvm to avoid conflicts with other tools, update nvm to version 20.11.1 (64-bit) with nvm install 20.11. 

It is useful to have repomix md or xml files for architectural analysis, bug fixing, and robustness in pdf for certain llms so:

```bash
pip install markdown-pdf

# Create the environment
python -m venv venv

# Activate it
.\venv\Scripts\activate

# Install only what you need here
pip install markdown-pdf 

# to convert the md file to pdf
python convert-md-to-pdf.py
```

# NEO4J
1. All Tender nodes
```cypher
MATCH (t:Tender) RETURN t LIMIT 25
```
2. Nodes related to Tender with relationships
```cypher
MATCH (t:Tender)-[r]->(n) 
RETURN t.id as tender, type(r) as relationship, labels(n)[0] as node_type, n.name as name
```
3. Full graph visualization
```cypher
MATCH (n) RETURN n
```
4. Only Tender nodes with their requirements
```cypher
MATCH (t:Tender)-[:HAS_REQUIREMENT]->(r:Requirement)
RETURN t.id, t.title, r.id, r.description
```
5. Node statistics
```cypher
MATCH (n) 
RETURN labels(n)[0] as Type, count(*) as Quantity
ORDER BY Quantity DESC
```
Note: The Neo4j database appears empty. Nodes are created when you insert data into the system (e.g., tenders, proposals). To populate the graph, use TenderWriter's RAG functionality.

```text
Usage:
Celery Worker - executes background tasks
Redis - manages the message queue between backend and worker
When you start a task (Index/Generate/Export), the backend sends the message to Redis → Celery Worker picks it up and executes the task.
```

Go to `http://localhost:7474`
Enter:
Username: `neo4j`
Password: `DefaultNEO4J2024Pass`

Configuration:
Open `http://localhost:8001`
Connect to Redis:
Host: `redis` (from container) or `localhost` (from host)
Port: `6379`

---

## 🤖 OpenCode - AI Coding Agent

TenderWriter includes **OpenCode**, an AI coding agent running locally with a dedicated LLM.

### Architecture

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                    OpenCode + Codebase + LLM                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────────────┐   │
│  │  tw-opencode │────▶│ tw-codebase  │     │   tw-llama-server    │   │
│  │  (AI agent)  │     │ (source)     │     │  (Qwen2.5-Coder 7B)│   │
│  └──────────────┘     └──────────────┘     └──────────────────────┘   │
│         │                     │                      │                 │
│         │            /workspace/codebase           http://localhost:8080│
│         │                     │                      │                 │
│         └─────────────────────┴──────────────────────┘                 │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                     Supported Providers                           │  │
│  │  1. Local: llama.cpp (Qwen2.5-Coder 7B)                      │  │
│  │  2. Cloud: Anthropic (Claude) - requires API key               │  │
│  │  3. Cloud: OpenAI (GPT-4.1) - requires API key                 │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

### Services

| Service | Container | Description |
|----------|-----------|-------------|
| LLM Server | tw-llama-server | Qwen2.5-Coder:7B (port 8080) |
| OpenCode | tw-opencode | AI Agent |
| Codebase | tw-codebase | Mounted source code |

### How to Use

```bash
# 1. Enter the OpenCode container
docker compose exec opencode bash

# 2. Start OpenCode
opencode

# 3. The code is available in /workspace/codebase
cd /workspace/codebase
ls -la  # You will see backend/ and frontend/
```

### Changing Provider/Model

```bash
# View available models (local + cloud)
/models

# Use local model (default)
/use llama-cpp/qwen2.5-coder-7b

# Use Claude (requires ANTHROPIC_API_KEY)
/use anthropic/claude-sonnet-4-20250514

# Use GPT-4.1 (requires OPENAI_API_KEY)
/use openai/gpt-4.1
```

### Cloud API Configuration

To use cloud models, set the environment variables:

```bash
# In docker-compose or .env
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
```

Or pass the variables at startup:

```bash
docker compose exec -e ANTHROPIC_API_KEY=sk-ant-... opencode bash
```

### Useful Commands

```bash
# View available models
/models

# Change model
/use llama-cpp/qwen2.5-coder-7b

# Analyze current code
analyze the codebase

# Ask for help
/help
```

### Configuration

The `opencode.json` file supports:

| Provider | Model | Type |
|----------|---------|------|
| llama-cpp | qwen2.5-coder-7b | Local (default) |
| anthropic | claude-sonnet-4 | Cloud |
| openai | gpt-4.1 | Cloud |

### Troubleshooting

```bash
# Verify that the LLM server is active
curl http://localhost:8080/v1/models

# View llama-server logs
docker compose logs llama-server

# View OpenCode logs
docker compose logs opencode

# Verify that the codebase is mounted
docker compose exec opencode ls -la /workspace/codebase
```

---

*Project developed with ❤️ for efficiency in tender proposals.*
