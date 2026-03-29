# Walkthrough — Video Call Transcription Integration

## Obiettivo
Integrazione di Mattermost + Jitsi Meet + Jigasi + Vosk nella piattaforma TenderWriter per abilitare videochiamate con trascrizione automatica italiana, mantenendo la chat interna esistente.

## Modifiche Effettuate

### 1. Docker Compose — 8 nuovi servizi

```diff:docker-compose.yml
services:
  # --- PostgreSQL ---
  postgres:
    image: postgres:16-alpine
    container_name: tw-postgres
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-tenderwriter}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-DefaultPg2024Pass}
      POSTGRES_DB: ${POSTGRES_DB:-tenderwriter}
    ports:
      - "${POSTGRES_PORT:-5432}:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: [ "CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-tenderwriter}" ]
      interval: 10s
      timeout: 10s
      retries: 5

  # --- Qdrant (Vector Database) ---
  qdrant:
    image: qdrant/qdrant:v1.13.0
    container_name: tw-qdrant
    restart: unless-stopped
    ports:
      - "${QDRANT_PORT:-6333}:6333"
      - "6334:6334"
    volumes:
      - qdrant_data:/qdrant/storage
    healthcheck:
      test: [ "CMD-SHELL", "bash -c 'cat < /dev/null > /dev/tcp/127.0.0.1/6333'" ]
      interval: 10s
      timeout: 10s
      retries: 5

  # --- Neo4j Community (Knowledge Graph) ---
  neo4j:
    image: neo4j:5-community
    container_name: tw-neo4j
    restart: unless-stopped
    environment:
      NEO4J_AUTH: neo4j/${NEO4J_PASSWORD:-DefaultNEO4J2024Pass}
      NEO4J_PLUGINS: '["apoc"]'
    ports:
      - "7474:7474" # Browser UI
      - "7687:7687" # Bolt protocol
    volumes:
      - neo4j_data:/data
    healthcheck:
      test: [ "CMD-SHELL", "cypher-shell -u neo4j -p ${NEO4J_PASSWORD:-DefaultNEO4J2024Pass} 'RETURN 1'" ]
      interval: 20s
      timeout: 20s
      retries: 5

  # --- Ollama (Local LLM - DEPRECATED, use llama-server instead) ---
  # ollama:
  #   image: ollama/ollama:latest
  #   container_name: tw-ollama
  #   restart: unless-stopped
  #   ports:
  #     - "11434:11434"
  #   volumes:
  #     - ollama_data:/root/.ollama

  # --- llama.cpp Server for TenderWriter RAG ---
  llama-tender:
    image: ghcr.io/ggml-org/llama.cpp:server
    container_name: tw-llama-tender
    restart: unless-stopped
    ports:
      - "8080:8080"
    volumes:
      - ./models:/models
      - llama_tender_cache:/root/.cache/llama.cpp
    entrypoint: [ "/app/llama-server" ]
    command: [ "-m", "/models/qwen2.5-3b-instruct-q4_k_m.gguf", "--host", "0.0.0.0", "--port", "8080", "-c", "4096", "-t", "16", "--n-predict", "512", "-b", "512" ]
    networks:
      - default

  # --- llama.cpp Server for OpenCode (Agentic Coder) ---
  llama-opencode:
    image: ghcr.io/ggml-org/llama.cpp:server
    container_name: tw-llama-opencode
    restart: unless-stopped
    ports:
      - "8081:8080"
    volumes:
      - ./models:/models
      - llama_opencode_cache:/root/.cache/llama.cpp
    entrypoint: [ "/app/llama-server" ]
    command: [ "-m", "/models/Qwen2.5-Coder-3B-Instruct-Q8_0.gguf", "--host", "0.0.0.0", "--port", "8080", "-c", "8192", "-t", "16" ]
    networks:
      - default

  # --- OpenCode Web (AI Coding Agent) ---
  opencode:
    image: ghcr.io/anomalyco/opencode:latest
    container_name: tw-opencode
    restart: unless-stopped
    stdin_open: true
    tty: true
    ports:
      - "4096:4096"
    volumes:
      - ./backend:/workspace/backend:ro
      - ./frontend:/workspace/frontend:ro
      - opencode_config:/home/opencode/.config/opencode
      - opencode_data:/home/opencode/.local/share/opencode
    environment:
      - OPENCODE_BASE_URL=http://tw-gateway:8081/v1
      - OPENCODE_MODEL=llama-cpp/qwen2.5-32b-instruct
      - OPENCODE_SERVER_PORT=4096
      - OPENCODE_SERVER_HOST=0.0.0.0
      # Per usare modelli cloud (Anthropic/OpenAI), imposta:
      # - ANTHROPIC_API_KEY=your-key
      # - OPENAI_API_KEY=your-key
    command: [ "web", "--hostname", "0.0.0.0", "--port", "4096" ]
    depends_on:
      llama-opencode:
        condition: service_started
    networks:
      - default
    extra_hosts:
      - "host.docker.internal:host-gateway"

  # --- OpenCode CLI (Terminal Mode) ---
  opencode-cli:
    image: ghcr.io/anomalyco/opencode:latest
    container_name: tw-opencode-cli
    restart: unless-stopped
    stdin_open: true
    tty: true
    volumes:
      - ./backend:/workspace/backend:ro
      - ./frontend:/workspace/frontend:ro
      - opencode_config:/home/opencode/.config/opencode
      - opencode_data:/home/opencode/.local/share/opencode
    environment:
      - OPENCODE_BASE_URL=http://tw-gateway:8081/v1
      - OPENCODE_MODEL=llama-cpp/qwen2.5-32b-instruct
    depends_on:
      llama-opencode:
        condition: service_started
    networks:
      - default
    extra_hosts:
      - "host.docker.internal:host-gateway"

  # --- MinIO (Object Storage) ---
  minio:
    image: minio/minio:latest
    container_name: minio
    restart: unless-stopped
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: ${MINIO_ACCESS_KEY:-minioadmin}
      MINIO_ROOT_PASSWORD: ${MINIO_SECRET_KEY:-DefaultMinIO2024Pass}
    ports:
      - "9000:9000"
      - "9001:9001" # Console UI
    volumes:
      - minio_data:/data
    healthcheck:
      test: [ "CMD", "curl", "-f", "http://localhost:9000/minio/health/live" ]
      interval: 10s
      timeout: 10s
      retries: 5

  # --- Redis (Task Queue backend) ---
  redis:
    image: redis:7-alpine
    container_name: tw-redis
    restart: unless-stopped
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: [ "CMD", "redis-cli", "ping" ]
      interval: 10s
      timeout: 10s
      retries: 5

  # --- Redis Insight (Redis GUI) ---
  redis-insight:
    image: rediscommander/redis-commander:latest
    container_name: tw-redis-insight
    restart: unless-stopped
    ports:
      - "8001:8081"
    environment:
      - REDIS_HOSTS=local:redis:6379

  # --- Celery Worker ---
  celery-worker:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: tw-celery-worker
    restart: unless-stopped
    command: celery -A app.celery worker --loglevel=info --concurrency=2
    env_file:
      - .env
    depends_on:
      redis:
        condition: service_healthy
      postgres:
        condition: service_healthy
    volumes:
      - ./backend/app:/app/app

  # --- Celery Beat (Scheduler) ---
  celery-beat:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: tw-celery-beat
    restart: unless-stopped
    command: celery -A app.celery beat --loglevel=info
    env_file:
      - .env
    depends_on:
      redis:
        condition: service_healthy
    volumes:
      - ./backend/app:/app/app

  # --- Mailpit (SMTP Testing) ---
  mailpit:
    image: axllent/mailpit:latest
    container_name: tw-mailpit
    restart: unless-stopped
    ports:
      - "8025:8025" # Web UI
      - "1025:1025" # SMTP

  # --- Privileged Ops Agent ---
  ops-agent:
    build:
      context: ./ops-agent
      dockerfile: Dockerfile
    container_name: tw-ops-agent
    restart: unless-stopped
    environment:
      OPS_AGENT_TOKEN: ${OPS_AGENT_TOKEN}
      OPS_ALLOWED_PREFIX: ${OPS_ALLOWED_PREFIX:-tw-}
      OPS_FRONTEND_CONTAINER: ${OPS_FRONTEND_CONTAINER:-tw-frontend}
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    healthcheck:
      test: [ "CMD", "curl", "-f", "http://localhost:8070/health" ]
      interval: 10s
      timeout: 10s
      retries: 5

  # --- Backend (FastAPI) ---
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: tw-backend
    restart: unless-stopped
    env_file:
      - .env
    depends_on:
      postgres:
        condition: service_healthy
      qdrant:
        condition: service_healthy
      redis:
        condition: service_healthy
    environment:
      DATABASE_URL: ${DATABASE_URL}
      QDRANT_HOST: ${QDRANT_HOST}
      QDRANT_PORT: ${QDRANT_PORT}
      NEO4J_URI: ${NEO4J_URI}
      NEO4J_USER: ${NEO4J_USER}
      NEO4J_PASSWORD: ${NEO4J_PASSWORD}
      OLLAMA_BASE_URL: ${OLLAMA_BASE_URL}
      OLLAMA_MODEL: ${OLLAMA_MODEL}
      MINIO_ENDPOINT: ${MINIO_ENDPOINT}
      MINIO_ACCESS_KEY: ${MINIO_ACCESS_KEY}
      MINIO_SECRET_KEY: ${MINIO_SECRET_KEY}
      REDIS_URL: ${REDIS_URL}
      APP_SECRET_KEY: ${APP_SECRET_KEY}
      ONLYOFFICE_JWT_SECRET: ${ONLYOFFICE_JWT_SECRET}
      CORS_ORIGINS: ${CORS_ORIGINS}
      LLAMA_SERVER_URL: http://tw-gateway:8080/v1
      ADMIN_USERNAME: ${ADMIN_USERNAME}
      ADMIN_PASSWORD: ${ADMIN_PASSWORD}
      ADMIN_ENABLED: ${ADMIN_ENABLED}
      MINIO_BUCKET: ${MINIO_BUCKET}
      MINIO_CHAT_BUCKET: ${MINIO_CHAT_BUCKET:-tenderwriter-chat}
      MINIO_SECURE: ${MINIO_SECURE}
      ONLYOFFICE_INTERNAL_URL: ${ONLYOFFICE_INTERNAL_URL}
      BACKEND_PUBLIC_URL: ${BACKEND_PUBLIC_URL}
      SMTP_HOST: ${SMTP_HOST}
      SMTP_PORT: ${SMTP_PORT}
      SMTP_USER: ${SMTP_USER}
      SMTP_PASSWORD: ${SMTP_PASSWORD}
      SMTP_FROM: ${SMTP_FROM}
      SMTP_TLS: ${SMTP_TLS}
      KPI_REASON_ENGINE_BASE_URL: ${KPI_REASON_ENGINE_BASE_URL:-http://tw-kpi-reason-engine:8010}
      KPI_REASON_ENGINE_SERVICE_TOKEN: ${KPI_REASON_ENGINE_SERVICE_TOKEN:-changeme-kpi-service-token}
      OPS_AGENT_BASE_URL: ${OPS_AGENT_BASE_URL:-http://tw-ops-agent:8070}
      OPS_AGENT_TOKEN: ${OPS_AGENT_TOKEN}
      OPS_AGENT_TIMEOUT: ${OPS_AGENT_TIMEOUT:-5}
    ports:
      - "${APP_PORT:-8000}:8000"
    volumes:
      - ./backend/app:/app/app # Hot reload in development

  # --- OnlyOffice Document Server ---
  onlyoffice:
    image: onlyoffice/documentserver:latest
    container_name: tw-onlyoffice
    restart: unless-stopped
    environment:
      JWT_ENABLED: "true"
      JWT_SECRET: "${ONLYOFFICE_JWT_SECRET:-changeme_oo_jwt_secret}"
    ports:
      - "8443:80"
    volumes:
      - onlyoffice_data:/var/log/onlyoffice
      - onlyoffice_lib:/var/lib/onlyoffice

  # --- KPI Reason Engine ---
  kpi-reason-engine:
    build:
      context: ./kpi-reason-engine
      dockerfile: Dockerfile
    container_name: tw-kpi-reason-engine
    restart: unless-stopped
    env_file:
      - .env
    environment:
      KPI_REASON_ENGINE_APP_DEBUG: ${APP_DEBUG:-false}
      KPI_REASON_ENGINE_APP_HOST: 0.0.0.0
      KPI_REASON_ENGINE_APP_PORT: 8010
      KPI_REASON_ENGINE_LOG_LEVEL: info
      KPI_REASON_ENGINE_PUBLIC_BASE_URL: ${KPI_REASON_ENGINE_BASE_URL:-http://tw-kpi-reason-engine:8010}
      KPI_REASON_ENGINE_SERVICE_TOKEN: ${KPI_REASON_ENGINE_SERVICE_TOKEN:-changeme-kpi-service-token}
      KPI_REASON_ENGINE_DATABASE_PATH: ${KPI_REASON_ENGINE_DATABASE_PATH:-/app/data/kpi_reason_engine.db}
    ports:
      - "${KPI_REASON_ENGINE_PORT:-8010}:8010"
    volumes:
      - ./kpi-reason-engine/app:/app/app
      - ./kpi-reason-engine/docs:/app/docs
      - ./kpi-reason-engine/data:/app/data
    healthcheck:
      test: [ "CMD", "curl", "-f", "http://localhost:8010/health" ]
      interval: 10s
      timeout: 10s
      retries: 5

  # --- Frontend (React + Vite) ---
  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    container_name: tw-frontend
    restart: unless-stopped
    depends_on:
      - backend
    ports:
      - "3000:3000"
    volumes:
      - ./frontend/src:/app/src # Hot reload in development

  # --- Gateway (AI Router) ---
  gateway:
    build:
      context: ./gateway
      dockerfile: Dockerfile
    container_name: tw-gateway
    restart: unless-stopped
    environment:
      GATEWAY_TENDER_UPSTREAM: http://llama-tender:8080
      GATEWAY_OPENCODE_UPSTREAM: http://llama-opencode:8080
      GATEWAY_TIMEOUT: 30
      GATEWAY_TENDER_DMZ_UPSTREAM: http://llama-tender:8080
      GATEWAY_OPENCODE_DMZ_UPSTREAM: http://llama-opencode:8080
      GATEWAY_ANONYMIZER_URL: http://tw-anonymizer:8090
      GATEWAY_TENDER_CLOUD_PROVIDER: ${GATEWAY_TENDER_CLOUD_PROVIDER:-}
      GATEWAY_OPENAI_BASE_URL: ${GATEWAY_OPENAI_BASE_URL:-https://api.openai.com}
      GATEWAY_OPENAI_API_KEY: ${GATEWAY_OPENAI_API_KEY:-}
      GATEWAY_ANTHROPIC_BASE_URL: ${GATEWAY_ANTHROPIC_BASE_URL:-https://api.anthropic.com}
      GATEWAY_ANTHROPIC_API_KEY: ${GATEWAY_ANTHROPIC_API_KEY:-}
    depends_on:
      llama-tender:
        condition: service_started
      llama-opencode:
        condition: service_started
    ports:
      - "8085:8080"
      - "8086:8081"

  # --- Anonymizer (transparent relay for DMZ/externals) ---
  anonymizer:
    build:
      context: ./anonymizer
      dockerfile: Dockerfile
    container_name: tw-anonymizer
    restart: unless-stopped
    ports:
      - "8090:8090"

volumes:
  postgres_data:
  qdrant_data:
  neo4j_data:
  ollama_data: # Kept for potential future Ollama use
  minio_data:
  redis_data:
  onlyoffice_data:
  onlyoffice_lib:
  llama_tender_cache:
  llama_opencode_cache:
  opencode_config:
  opencode_data:





===
services:
  # --- PostgreSQL ---
  postgres:
    image: postgres:16-alpine
    container_name: tw-postgres
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-tenderwriter}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-DefaultPg2024Pass}
      POSTGRES_DB: ${POSTGRES_DB:-tenderwriter}
    ports:
      - "${POSTGRES_PORT:-5432}:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: [ "CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-tenderwriter}" ]
      interval: 10s
      timeout: 10s
      retries: 5

  # --- Qdrant (Vector Database) ---
  qdrant:
    image: qdrant/qdrant:v1.13.0
    container_name: tw-qdrant
    restart: unless-stopped
    ports:
      - "${QDRANT_PORT:-6333}:6333"
      - "6334:6334"
    volumes:
      - qdrant_data:/qdrant/storage
    healthcheck:
      test: [ "CMD-SHELL", "bash -c 'cat < /dev/null > /dev/tcp/127.0.0.1/6333'" ]
      interval: 10s
      timeout: 10s
      retries: 5

  # --- Neo4j Community (Knowledge Graph) ---
  neo4j:
    image: neo4j:5-community
    container_name: tw-neo4j
    restart: unless-stopped
    environment:
      NEO4J_AUTH: neo4j/${NEO4J_PASSWORD:-DefaultNEO4J2024Pass}
      NEO4J_PLUGINS: '["apoc"]'
    ports:
      - "7474:7474" # Browser UI
      - "7687:7687" # Bolt protocol
    volumes:
      - neo4j_data:/data
    healthcheck:
      test: [ "CMD-SHELL", "cypher-shell -u neo4j -p ${NEO4J_PASSWORD:-DefaultNEO4J2024Pass} 'RETURN 1'" ]
      interval: 20s
      timeout: 20s
      retries: 5

  # --- Ollama (Local LLM - DEPRECATED, use llama-server instead) ---
  # ollama:
  #   image: ollama/ollama:latest
  #   container_name: tw-ollama
  #   restart: unless-stopped
  #   ports:
  #     - "11434:11434"
  #   volumes:
  #     - ollama_data:/root/.ollama

  # --- llama.cpp Server for TenderWriter RAG ---
  llama-tender:
    image: ghcr.io/ggml-org/llama.cpp:server
    container_name: tw-llama-tender
    restart: unless-stopped
    ports:
      - "8080:8080"
    volumes:
      - ./models:/models
      - llama_tender_cache:/root/.cache/llama.cpp
    entrypoint: [ "/app/llama-server" ]
    command: [ "-m", "/models/qwen2.5-3b-instruct-q4_k_m.gguf", "--host", "0.0.0.0", "--port", "8080", "-c", "4096", "-t", "16", "--n-predict", "512", "-b", "512" ]
    networks:
      - default

  # --- llama.cpp Server for OpenCode (Agentic Coder) ---
  llama-opencode:
    image: ghcr.io/ggml-org/llama.cpp:server
    container_name: tw-llama-opencode
    restart: unless-stopped
    ports:
      - "8081:8080"
    volumes:
      - ./models:/models
      - llama_opencode_cache:/root/.cache/llama.cpp
    entrypoint: [ "/app/llama-server" ]
    command: [ "-m", "/models/Qwen2.5-Coder-3B-Instruct-Q8_0.gguf", "--host", "0.0.0.0", "--port", "8080", "-c", "8192", "-t", "16" ]
    networks:
      - default

  # --- OpenCode Web (AI Coding Agent) ---
  opencode:
    image: ghcr.io/anomalyco/opencode:latest
    container_name: tw-opencode
    restart: unless-stopped
    stdin_open: true
    tty: true
    ports:
      - "4096:4096"
    volumes:
      - ./backend:/workspace/backend:ro
      - ./frontend:/workspace/frontend:ro
      - opencode_config:/home/opencode/.config/opencode
      - opencode_data:/home/opencode/.local/share/opencode
    environment:
      - OPENCODE_BASE_URL=http://tw-gateway:8081/v1
      - OPENCODE_MODEL=llama-cpp/qwen2.5-32b-instruct
      - OPENCODE_SERVER_PORT=4096
      - OPENCODE_SERVER_HOST=0.0.0.0
      # Per usare modelli cloud (Anthropic/OpenAI), imposta:
      # - ANTHROPIC_API_KEY=your-key
      # - OPENAI_API_KEY=your-key
    command: [ "web", "--hostname", "0.0.0.0", "--port", "4096" ]
    depends_on:
      llama-opencode:
        condition: service_started
    networks:
      - default
    extra_hosts:
      - "host.docker.internal:host-gateway"

  # --- OpenCode CLI (Terminal Mode) ---
  opencode-cli:
    image: ghcr.io/anomalyco/opencode:latest
    container_name: tw-opencode-cli
    restart: unless-stopped
    stdin_open: true
    tty: true
    volumes:
      - ./backend:/workspace/backend:ro
      - ./frontend:/workspace/frontend:ro
      - opencode_config:/home/opencode/.config/opencode
      - opencode_data:/home/opencode/.local/share/opencode
    environment:
      - OPENCODE_BASE_URL=http://tw-gateway:8081/v1
      - OPENCODE_MODEL=llama-cpp/qwen2.5-32b-instruct
    depends_on:
      llama-opencode:
        condition: service_started
    networks:
      - default
    extra_hosts:
      - "host.docker.internal:host-gateway"

  # --- MinIO (Object Storage) ---
  minio:
    image: minio/minio:latest
    container_name: minio
    restart: unless-stopped
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: ${MINIO_ACCESS_KEY:-minioadmin}
      MINIO_ROOT_PASSWORD: ${MINIO_SECRET_KEY:-DefaultMinIO2024Pass}
    ports:
      - "9000:9000"
      - "9001:9001" # Console UI
    volumes:
      - minio_data:/data
    healthcheck:
      test: [ "CMD", "curl", "-f", "http://localhost:9000/minio/health/live" ]
      interval: 10s
      timeout: 10s
      retries: 5

  # --- Redis (Task Queue backend) ---
  redis:
    image: redis:7-alpine
    container_name: tw-redis
    restart: unless-stopped
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: [ "CMD", "redis-cli", "ping" ]
      interval: 10s
      timeout: 10s
      retries: 5

  # --- Redis Insight (Redis GUI) ---
  redis-insight:
    image: rediscommander/redis-commander:latest
    container_name: tw-redis-insight
    restart: unless-stopped
    ports:
      - "8001:8081"
    environment:
      - REDIS_HOSTS=local:redis:6379

  # --- Celery Worker ---
  celery-worker:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: tw-celery-worker
    restart: unless-stopped
    command: celery -A app.celery worker --loglevel=info --concurrency=2
    env_file:
      - .env
    depends_on:
      redis:
        condition: service_healthy
      postgres:
        condition: service_healthy
    volumes:
      - ./backend/app:/app/app

  # --- Celery Beat (Scheduler) ---
  celery-beat:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: tw-celery-beat
    restart: unless-stopped
    command: celery -A app.celery beat --loglevel=info
    env_file:
      - .env
    depends_on:
      redis:
        condition: service_healthy
    volumes:
      - ./backend/app:/app/app

  # --- Mailpit (SMTP Testing) ---
  mailpit:
    image: axllent/mailpit:latest
    container_name: tw-mailpit
    restart: unless-stopped
    ports:
      - "8025:8025" # Web UI
      - "1025:1025" # SMTP

  # --- Privileged Ops Agent ---
  ops-agent:
    build:
      context: ./ops-agent
      dockerfile: Dockerfile
    container_name: tw-ops-agent
    restart: unless-stopped
    environment:
      OPS_AGENT_TOKEN: ${OPS_AGENT_TOKEN}
      OPS_ALLOWED_PREFIX: ${OPS_ALLOWED_PREFIX:-tw-}
      OPS_FRONTEND_CONTAINER: ${OPS_FRONTEND_CONTAINER:-tw-frontend}
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    healthcheck:
      test: [ "CMD", "curl", "-f", "http://localhost:8070/health" ]
      interval: 10s
      timeout: 10s
      retries: 5

  # --- Backend (FastAPI) ---
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: tw-backend
    restart: unless-stopped
    env_file:
      - .env
    depends_on:
      postgres:
        condition: service_healthy
      qdrant:
        condition: service_healthy
      redis:
        condition: service_healthy
    environment:
      DATABASE_URL: ${DATABASE_URL}
      QDRANT_HOST: ${QDRANT_HOST}
      QDRANT_PORT: ${QDRANT_PORT}
      NEO4J_URI: ${NEO4J_URI}
      NEO4J_USER: ${NEO4J_USER}
      NEO4J_PASSWORD: ${NEO4J_PASSWORD}
      OLLAMA_BASE_URL: ${OLLAMA_BASE_URL}
      OLLAMA_MODEL: ${OLLAMA_MODEL}
      MINIO_ENDPOINT: ${MINIO_ENDPOINT}
      MINIO_ACCESS_KEY: ${MINIO_ACCESS_KEY}
      MINIO_SECRET_KEY: ${MINIO_SECRET_KEY}
      REDIS_URL: ${REDIS_URL}
      APP_SECRET_KEY: ${APP_SECRET_KEY}
      ONLYOFFICE_JWT_SECRET: ${ONLYOFFICE_JWT_SECRET}
      CORS_ORIGINS: ${CORS_ORIGINS}
      LLAMA_SERVER_URL: http://tw-gateway:8080/v1
      ADMIN_USERNAME: ${ADMIN_USERNAME}
      ADMIN_PASSWORD: ${ADMIN_PASSWORD}
      ADMIN_ENABLED: ${ADMIN_ENABLED}
      MINIO_BUCKET: ${MINIO_BUCKET}
      MINIO_CHAT_BUCKET: ${MINIO_CHAT_BUCKET:-tenderwriter-chat}
      MINIO_SECURE: ${MINIO_SECURE}
      ONLYOFFICE_INTERNAL_URL: ${ONLYOFFICE_INTERNAL_URL}
      BACKEND_PUBLIC_URL: ${BACKEND_PUBLIC_URL}
      SMTP_HOST: ${SMTP_HOST}
      SMTP_PORT: ${SMTP_PORT}
      SMTP_USER: ${SMTP_USER}
      SMTP_PASSWORD: ${SMTP_PASSWORD}
      SMTP_FROM: ${SMTP_FROM}
      SMTP_TLS: ${SMTP_TLS}
      KPI_REASON_ENGINE_BASE_URL: ${KPI_REASON_ENGINE_BASE_URL:-http://tw-kpi-reason-engine:8010}
      KPI_REASON_ENGINE_SERVICE_TOKEN: ${KPI_REASON_ENGINE_SERVICE_TOKEN:-changeme-kpi-service-token}
      OPS_AGENT_BASE_URL: ${OPS_AGENT_BASE_URL:-http://tw-ops-agent:8070}
      OPS_AGENT_TOKEN: ${OPS_AGENT_TOKEN}
      OPS_AGENT_TIMEOUT: ${OPS_AGENT_TIMEOUT:-5}
    ports:
      - "${APP_PORT:-8000}:8000"
    volumes:
      - ./backend/app:/app/app # Hot reload in development

  # --- OnlyOffice Document Server ---
  onlyoffice:
    image: onlyoffice/documentserver:latest
    container_name: tw-onlyoffice
    restart: unless-stopped
    environment:
      JWT_ENABLED: "true"
      JWT_SECRET: "${ONLYOFFICE_JWT_SECRET:-changeme_oo_jwt_secret}"
    ports:
      - "8443:80"
    volumes:
      - onlyoffice_data:/var/log/onlyoffice
      - onlyoffice_lib:/var/lib/onlyoffice

  # --- KPI Reason Engine ---
  kpi-reason-engine:
    build:
      context: ./kpi-reason-engine
      dockerfile: Dockerfile
    container_name: tw-kpi-reason-engine
    restart: unless-stopped
    env_file:
      - .env
    environment:
      KPI_REASON_ENGINE_APP_DEBUG: ${APP_DEBUG:-false}
      KPI_REASON_ENGINE_APP_HOST: 0.0.0.0
      KPI_REASON_ENGINE_APP_PORT: 8010
      KPI_REASON_ENGINE_LOG_LEVEL: info
      KPI_REASON_ENGINE_PUBLIC_BASE_URL: ${KPI_REASON_ENGINE_BASE_URL:-http://tw-kpi-reason-engine:8010}
      KPI_REASON_ENGINE_SERVICE_TOKEN: ${KPI_REASON_ENGINE_SERVICE_TOKEN:-changeme-kpi-service-token}
      KPI_REASON_ENGINE_DATABASE_PATH: ${KPI_REASON_ENGINE_DATABASE_PATH:-/app/data/kpi_reason_engine.db}
    ports:
      - "${KPI_REASON_ENGINE_PORT:-8010}:8010"
    volumes:
      - ./kpi-reason-engine/app:/app/app
      - ./kpi-reason-engine/docs:/app/docs
      - ./kpi-reason-engine/data:/app/data
    healthcheck:
      test: [ "CMD", "curl", "-f", "http://localhost:8010/health" ]
      interval: 10s
      timeout: 10s
      retries: 5

  # --- Frontend (React + Vite) ---
  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    container_name: tw-frontend
    restart: unless-stopped
    depends_on:
      - backend
    ports:
      - "3000:3000"
    volumes:
      - ./frontend/src:/app/src # Hot reload in development

  # --- Gateway (AI Router) ---
  gateway:
    build:
      context: ./gateway
      dockerfile: Dockerfile
    container_name: tw-gateway
    restart: unless-stopped
    environment:
      GATEWAY_TENDER_UPSTREAM: http://llama-tender:8080
      GATEWAY_OPENCODE_UPSTREAM: http://llama-opencode:8080
      GATEWAY_TIMEOUT: 30
      GATEWAY_TENDER_DMZ_UPSTREAM: http://llama-tender:8080
      GATEWAY_OPENCODE_DMZ_UPSTREAM: http://llama-opencode:8080
      GATEWAY_ANONYMIZER_URL: http://tw-anonymizer:8090
      GATEWAY_TENDER_CLOUD_PROVIDER: ${GATEWAY_TENDER_CLOUD_PROVIDER:-}
      GATEWAY_OPENAI_BASE_URL: ${GATEWAY_OPENAI_BASE_URL:-https://api.openai.com}
      GATEWAY_OPENAI_API_KEY: ${GATEWAY_OPENAI_API_KEY:-}
      GATEWAY_ANTHROPIC_BASE_URL: ${GATEWAY_ANTHROPIC_BASE_URL:-https://api.anthropic.com}
      GATEWAY_ANTHROPIC_API_KEY: ${GATEWAY_ANTHROPIC_API_KEY:-}
    depends_on:
      llama-tender:
        condition: service_started
      llama-opencode:
        condition: service_started
    ports:
      - "8085:8080"
      - "8086:8081"

  # --- Anonymizer (transparent relay for DMZ/externals) ---
  anonymizer:
    build:
      context: ./anonymizer
      dockerfile: Dockerfile
    container_name: tw-anonymizer
    restart: unless-stopped
    ports:
      - "8090:8090"

  # ===================================================================
  # VIDEO CALL TRANSCRIPTION STACK (Mattermost + Jitsi + Jigasi + Vosk)
  # ===================================================================

  # --- Mattermost PostgreSQL (dedicated, not shared with TenderWriter) ---
  mm-postgres:
    image: postgres:16-alpine
    container_name: tw-mm-postgres
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${MM_DBUSER:-mmuser}
      POSTGRES_PASSWORD: ${MM_DBPASS:-DefaultMM2024Pass}
      POSTGRES_DB: ${MM_DBNAME:-mattermost}
    volumes:
      - mm_postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${MM_DBUSER:-mmuser}"]
      interval: 10s
      timeout: 10s
      retries: 5

  # --- Mattermost Team Edition ---
  mattermost:
    image: mattermost/mattermost-team-edition:latest
    container_name: tw-mattermost
    restart: unless-stopped
    depends_on:
      mm-postgres:
        condition: service_healthy
    environment:
      MM_SQLSETTINGS_DRIVERNAME: postgres
      MM_SQLSETTINGS_DATASOURCE: "postgres://${MM_DBUSER:-mmuser}:${MM_DBPASS:-DefaultMM2024Pass}@mm-postgres:5432/${MM_DBNAME:-mattermost}?sslmode=disable&connect_timeout=10"
      MM_SERVICESETTINGS_SITEURL: ${MM_SITE_URL:-http://localhost:8065}
      MM_PLUGINSETTINGS_ENABLEUPLOADS: "true"
    ports:
      - "${MM_PORT:-8065}:8065"
    volumes:
      - mm_data:/mattermost/data
      - mm_config:/mattermost/config
      - mm_logs:/mattermost/logs
      - mm_plugins:/mattermost/plugins

  # --- Jitsi Prosody (XMPP Server) ---
  jitsi-prosody:
    image: jitsi/prosody:stable-9823
    container_name: tw-jitsi-prosody
    restart: unless-stopped
    environment:
      JICOFO_AUTH_PASSWORD: ${JITSI_JICOFO_AUTH_PASSWORD:-changeme-jicofo}
      JVB_AUTH_PASSWORD: ${JITSI_JVB_AUTH_PASSWORD:-changeme-jvb}
      JIGASI_XMPP_PASSWORD: ${JITSI_JIGASI_XMPP_PASSWORD:-changeme-jigasi}
      PUBLIC_URL: ${JITSI_PUBLIC_URL:-http://localhost:8880}
      TZ: ${TZ:-Europe/Rome}
    volumes:
      - jitsi_prosody_cfg:/config:Z

  # --- Jitsi Jicofo (Conference Focus) ---
  jitsi-jicofo:
    image: jitsi/jicofo:stable-9823
    container_name: tw-jitsi-jicofo
    restart: unless-stopped
    depends_on:
      - jitsi-prosody
    environment:
      JICOFO_AUTH_PASSWORD: ${JITSI_JICOFO_AUTH_PASSWORD:-changeme-jicofo}
      XMPP_SERVER: jitsi-prosody
      TZ: ${TZ:-Europe/Rome}
    volumes:
      - jitsi_jicofo_cfg:/config:Z

  # --- Jitsi JVB (Video Bridge) ---
  jitsi-jvb:
    image: jitsi/jvb:stable-9823
    container_name: tw-jitsi-jvb
    restart: unless-stopped
    depends_on:
      - jitsi-prosody
    environment:
      JVB_AUTH_PASSWORD: ${JITSI_JVB_AUTH_PASSWORD:-changeme-jvb}
      XMPP_SERVER: jitsi-prosody
      PUBLIC_URL: ${JITSI_PUBLIC_URL:-http://localhost:8880}
      TZ: ${TZ:-Europe/Rome}
    ports:
      - "10000:10000/udp"
    volumes:
      - jitsi_jvb_cfg:/config:Z

  # --- Jitsi Web (Frontend) ---
  jitsi-web:
    image: jitsi/web:stable-9823
    container_name: tw-jitsi-web
    restart: unless-stopped
    depends_on:
      - jitsi-prosody
    environment:
      XMPP_SERVER: jitsi-prosody
      PUBLIC_URL: ${JITSI_PUBLIC_URL:-http://localhost:8880}
      ENABLE_TRANSCRIPTIONS: 1
      TZ: ${TZ:-Europe/Rome}
    ports:
      - "${JITSI_WEB_PORT:-8880}:80"
      - "${JITSI_WEB_SSL_PORT:-8843}:443"
    volumes:
      - jitsi_web_cfg:/config:Z

  # --- Vosk Speech-to-Text Server (Italian Model) ---
  vosk:
    image: alphacep/kaldi-it:latest
    container_name: tw-vosk
    restart: unless-stopped

  # --- Jigasi (Jitsi Audio Bridge -> Vosk STT) ---
  jitsi-jigasi:
    image: jitsi/jigasi:stable-9823
    container_name: tw-jitsi-jigasi
    restart: unless-stopped
    depends_on:
      - vosk
      - jitsi-prosody
    environment:
      ENABLE_TRANSCRIPTIONS: 1
      JIGASI_TRANSCRIBER_ADVERTISE_URL: "true"
      XMPP_SERVER: jitsi-prosody
      JIGASI_XMPP_PASSWORD: ${JITSI_JIGASI_XMPP_PASSWORD:-changeme-jigasi}
      PUBLIC_URL: ${JITSI_PUBLIC_URL:-http://localhost:8880}
      TZ: ${TZ:-Europe/Rome}
    volumes:
      - jitsi_jigasi_cfg:/config:Z
      - jitsi_transcripts:/tmp/transcripts:Z

volumes:
  postgres_data:
  qdrant_data:
  neo4j_data:
  ollama_data: # Kept for potential future Ollama use
  minio_data:
  redis_data:
  onlyoffice_data:
  onlyoffice_lib:
  llama_tender_cache:
  llama_opencode_cache:
  opencode_config:
  opencode_data:
  # --- Mattermost volumes ---
  mm_postgres_data:
  mm_data:
  mm_config:
  mm_logs:
  mm_plugins:
  # --- Jitsi volumes ---
  jitsi_prosody_cfg:
  jitsi_jicofo_cfg:
  jitsi_jvb_cfg:
  jitsi_web_cfg:
  jitsi_jigasi_cfg:
  jitsi_transcripts:

```

| Servizio | Immagine | Scopo |
|---|---|---|
| `mm-postgres` | `postgres:16-alpine` | DB dedicato Mattermost |
| [mattermost](file:///d:/tender/tenderwriter/utility/transcript_forwarder.py#37-63) | `mattermost/mattermost-team-edition:latest` | Server chat/video |
| `jitsi-prosody` | `jitsi/prosody:stable-9823` | XMPP server |
| `jitsi-jicofo` | `jitsi/jicofo:stable-9823` | Conference focus |
| `jitsi-jvb` | `jitsi/jvb:stable-9823` | Video bridge |
| `jitsi-web` | `jitsi/web:stable-9823` | Web frontend |
| `vosk` | `alphacep/kaldi-it:latest` | STT italiano |
| `jitsi-jigasi` | `jitsi/jigasi:stable-9823` | Audio bridge → Vosk |

### 2. Environment Variables

```diff:.env
# TenderWriter - Environment Variables
# REQUIRED - All values must be changed from defaults

APP_SECRET_KEY=xK9mP2vL8qR4tY7wN3jH5bF6cA1dE0s
APP_DEBUG=false
CORS_ORIGINS=http://localhost:3000

ADMIN_USERNAME=admin@admin.com
ADMIN_PASSWORD=vN7pQ3wL9xR5tY2uA4bC6dE8fG1hJ0
ADMIN_ENABLED=true

DATABASE_URL=postgresql+asyncpg://tenderwriter:DefaultPg2024Pass@postgres:5432/tenderwriter

NEO4J_URI=bolt://neo4j:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=DefaultNEO4J2024Pass

MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=DefaultMinIO2024Pass
MINIO_BUCKET=tenderwriter
MINIO_SECURE=false

ONLYOFFICE_URL=http://localhost:8443
ONLYOFFICE_JWT_SECRET=OnlyOfficeJWT2026Key
ONLYOFFICE_INTERNAL_URL=http://onlyoffice
BACKEND_PUBLIC_URL=http://tw-backend:8000

QDRANT_HOST=qdrant
QDRANT_PORT=6333
QDRANT_API_KEY=

OLLAMA_BASE_URL=http://llama-server:8080/v1
OLLAMA_MODEL=qwen2.5-coder-7b
OLLAMA_TIMEOUT=120

OPENCODE_BASE_URL=http://llama-server:8080/v1

REDIS_URL=redis://redis:6379/0

SMTP_HOST=mailpit
SMTP_PORT=1025
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM=noreply@tenderwriter.ai
SMTP_TLS=false

GATEWAY_TENDER_UPSTREAM=http://127.0.0.1:1234
GATEWAY_TIMEOUT=10
# opzionale: GATEWAY_TENDER_DMZ_UPSTREAM=   (lascia vuoto)

OPS_AGENT_BASE_URL=http://tw-ops-agent:8070
OPS_AGENT_TOKEN=OpsAgentLocalToken2026Secure42
OPS_AGENT_TIMEOUT=5
===
# TenderWriter - Environment Variables
# REQUIRED - All values must be changed from defaults

APP_SECRET_KEY=xK9mP2vL8qR4tY7wN3jH5bF6cA1dE0s
APP_DEBUG=false
CORS_ORIGINS=http://localhost:3000

ADMIN_USERNAME=admin@admin.com
ADMIN_PASSWORD=vN7pQ3wL9xR5tY2uA4bC6dE8fG1hJ0
ADMIN_ENABLED=true

DATABASE_URL=postgresql+asyncpg://tenderwriter:DefaultPg2024Pass@postgres:5432/tenderwriter

NEO4J_URI=bolt://neo4j:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=DefaultNEO4J2024Pass

MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=DefaultMinIO2024Pass
MINIO_BUCKET=tenderwriter
MINIO_SECURE=false

ONLYOFFICE_URL=http://localhost:8443
ONLYOFFICE_JWT_SECRET=OnlyOfficeJWT2026Key
ONLYOFFICE_INTERNAL_URL=http://onlyoffice
BACKEND_PUBLIC_URL=http://tw-backend:8000

QDRANT_HOST=qdrant
QDRANT_PORT=6333
QDRANT_API_KEY=

OLLAMA_BASE_URL=http://llama-server:8080/v1
OLLAMA_MODEL=qwen2.5-coder-7b
OLLAMA_TIMEOUT=120

OPENCODE_BASE_URL=http://llama-server:8080/v1

REDIS_URL=redis://redis:6379/0

SMTP_HOST=mailpit
SMTP_PORT=1025
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM=noreply@tenderwriter.ai
SMTP_TLS=false

GATEWAY_TENDER_UPSTREAM=http://127.0.0.1:1234
GATEWAY_TIMEOUT=10
# opzionale: GATEWAY_TENDER_DMZ_UPSTREAM=   (lascia vuoto)

OPS_AGENT_BASE_URL=http://tw-ops-agent:8070
OPS_AGENT_TOKEN=OpsAgentLocalToken2026Secure42
OPS_AGENT_TIMEOUT=5

# --- Mattermost ---
MM_DBUSER=mmuser
MM_DBPASS=DefaultMM2024Pass
MM_DBNAME=mattermost
MM_PORT=8065
MM_SITE_URL=http://localhost:8065

# --- Jitsi Meet ---
JITSI_PUBLIC_URL=http://localhost:8880
JITSI_WEB_PORT=8880
JITSI_WEB_SSL_PORT=8843
JITSI_JICOFO_AUTH_PASSWORD=changeme-jicofo
JITSI_JVB_AUTH_PASSWORD=changeme-jvb
JITSI_JIGASI_XMPP_PASSWORD=changeme-jigasi
TZ=Europe/Rome
```

### 3. Transcript Forwarder Script

Nuovo file [transcript_forwarder.py](file:///d:/tender/tenderwriter/utility/transcript_forwarder.py) — script Python (zero dipendenze esterne) che monitora la cartella trascrizioni Jigasi e le inoltra a Mattermost tramite Incoming Webhook.

### 4. Frontend — Chat Mode Dropdown

```diff:Dashboard.tsx
import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
    Plus,
    Clock,
    TrendingUp,
    FileText,
    CheckCircle,
    AlertCircle,
    Loader2,
    Upload,
    Check,
    FileEdit,
    MessageSquare,
    X,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { prefetchTenderChatContext, prefetchTenderChatRetrospective, tenderApi, proposalApi, type Tender, type TenderCreate } from '../api/client';
import { preloadRoute } from '../router/lazyRoutes';

const PIPELINE_COLUMNS = [
    { key: 'draft', label: 'Draft', color: '#64748b' },
    { key: 'active', label: 'Active', color: '#3b82f6' },
    { key: 'in_progress', label: 'In Progress', color: '#f59e0b' },
    { key: 'submitted', label: 'Submitted', color: '#8b5cf6' },
    { key: 'won', label: 'Won', color: '#10b981' },
];

function getDaysUntil(dateStr: string | null): number | null {
    if (!dateStr) return null;
    const target = new Date(dateStr);
    const now = new Date();
    return Math.ceil((target.getTime() - now.getTime()) / (1000 * 60 * 60 * 24));
}

function TenderCard({ tender, index, onUpload, onCreateProposal, onEditProposal, onSubmit, onOpenChat, onWarmChat }: { tender: Tender; index: number; onUpload: (id: number, file: File) => Promise<void>; onCreateProposal: (tenderId: number | null) => void; onEditProposal: (proposalId: number) => void; onSubmit: (id: number) => Promise<void>; onOpenChat: (id: number) => void; onWarmChat: (id: number) => void }) {
    const days = getDaysUntil(tender.deadline);
    const isUrgent = days !== null && days <= 7 && days > 0;
    const isPast = days !== null && days < 0;

    const [uploading, setUploading] = useState(false);
    const [success, setSuccess] = useState(false);

    const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;

        try {
            setUploading(true);
            await onUpload(tender.id, file);
            setSuccess(true);
            setTimeout(() => setSuccess(false), 3000);
        } catch (err) {
            console.error(err);
        } finally {
            setUploading(false);
            // Reset input
            e.target.value = '';
        }
    };

    return (
        <motion.div
            className="tender-card"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            whileHover={{ y: -4, boxShadow: 'var(--shadow-lg)', borderColor: 'var(--accent-blue)' }}
            transition={{ delay: index * 0.05, duration: 0.2 }}
            style={{
                background: 'rgba(255, 255, 255, 0.02)',
                backdropFilter: 'blur(10px)',
                cursor: 'default'
            }}
        >
            <div className="tender-card-title">{tender.title}</div>
            <div className="tender-card-client">{tender.client || 'No client'}</div>

            <div style={{ marginTop: '0.75rem', marginBottom: '0.75rem', display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                {!['submitted', 'won', 'lost', 'cancelled'].includes(tender.status) && (
                    <label className="btn btn-secondary btn-sm" style={{ cursor: uploading ? 'not-allowed' : 'pointer', fontSize: '0.75rem', padding: '0.25rem 0.5rem' }}>
                        {uploading ? <Loader2 size={12} className="spin" /> : success ? <Check size={12} color="#10b981" /> : <Upload size={12} />}
                        {uploading ? 'Uploading...' : success ? 'Uploaded' : 'Upload PDF'}
                        <input
                            type="file"
                            accept=".pdf,.docx,.txt"
                            style={{ display: 'none' }}
                            onChange={handleFileChange}
                            disabled={uploading}
                        />
                    </label>
                )}

                {tender.status === 'active' && (
                    <button
                        className="btn btn-primary btn-sm"
                        style={{ fontSize: '0.75rem', padding: '0.25rem 0.5rem', gap: '0.25rem' }}
                        onClick={() => onCreateProposal(tender.id)}
                    >
                        <FileEdit size={12} />
                        Create Proposal
                    </button>
                )}

                {tender.status === 'in_progress' && (
                    <>
                        <button
                            className="btn btn-primary btn-sm"
                            style={{ fontSize: '0.75rem', padding: '0.25rem 0.5rem', gap: '0.25rem' }}
                            onClick={() => {
                                if (tender.proposal_id) {
                                    onEditProposal(tender.proposal_id);
                                } else {
                                    onCreateProposal(tender.id);
                                }
                            }}
                        >
                            <FileEdit size={12} />
                            Edit Proposal
                        </button>
                        <button
                            className="btn btn-secondary btn-sm"
                            style={{ fontSize: '0.75rem', padding: '0.25rem 0.6rem', gap: '0.25rem', background: 'var(--accent-purple)', color: 'white', border: 'none' }}
                            onClick={() => onSubmit(tender.id)}
                        >
                            <CheckCircle size={12} />
                            Submit
                        </button>
                    </>
                )}

                <button
                    className="btn btn-ghost btn-sm"
                    style={{ fontSize: '0.75rem', padding: '0.25rem 0.6rem', gap: '0.25rem' }}
                    onClick={() => onOpenChat(tender.id)}
                    onMouseEnter={() => onWarmChat(tender.id)}
                    onFocus={() => onWarmChat(tender.id)}
                    onTouchStart={() => onWarmChat(tender.id)}
                >
                    <MessageSquare size={12} />
                    Open Chat
                </button>
            </div>

            <div className="tender-card-footer">
                <span className={isUrgent ? 'deadline-urgent' : ''}>
                    <Clock size={12} style={{ marginRight: 4, verticalAlign: 'middle' }} />
                    {days === null
                        ? 'No deadline'
                        : isPast
                            ? 'Past due'
                            : isUrgent
                                ? `${days}d left!`
                                : `${days} days`}
                </span>
                <span className={`badge badge-${tender.status.replace('_', '-')}`}>
                    {tender.status.replace('_', ' ')}
                </span>
            </div>
        </motion.div>
    );
}

const EMPTY_FORM: TenderCreate = {
    title: '',
    client: '',
    description: '',
    deadline: '',
    category: '',
    tags: [],
    budget_estimate: undefined,
};

export default function Dashboard() {
    const [tenders, setTenders] = useState<Tender[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [showNewTender, setShowNewTender] = useState(false);
    const [form, setForm] = useState<TenderCreate>({ ...EMPTY_FORM });
    const [creating, setCreating] = useState(false);

    // Proposal creation state
    const [showNewProposal, setShowNewProposal] = useState<number | null>(null);
    const [proposalTitle, setProposalTitle] = useState('');
    const [creatingProposal, setCreatingProposal] = useState(false);

    const navigate = useNavigate();

    const loadTenders = useCallback(async () => {
        try {
            setLoading(true);
            setError(null);
            const data = await tenderApi.list({ limit: '100' });
            setTenders(data.items);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to load tenders');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        loadTenders();
    }, [loadTenders]);

    const handleCreate = async () => {
        if (!form.title.trim()) return;
        try {
            setCreating(true);
            const payload: TenderCreate = { title: form.title };
            if (form.client) payload.client = form.client;
            if (form.description) payload.description = form.description;
            if (form.deadline) payload.deadline = new Date(form.deadline).toISOString();
            if (form.category) payload.category = form.category;
            await tenderApi.create(payload);
            setForm({ ...EMPTY_FORM });
            setShowNewTender(false);
            await loadTenders();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to create tender');
        } finally {
            setCreating(false);
        }
    };

    const handleCreateProposal = async () => {
        if (!proposalTitle.trim() || showNewProposal === null) return;
        try {
            setCreatingProposal(true);
            const proposal = await proposalApi.create({
                tender_id: showNewProposal,
                title: proposalTitle,
            });
            setShowNewProposal(null);
            setProposalTitle('');
            // Navigate to proposals page and select the new proposal
            navigate('/proposals', { state: { proposalId: proposal.id } });
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to create proposal');
        } finally {
            setCreatingProposal(false);
        }
    };

    const handleUpload = async (id: number, file: File) => {
        try {
            setError(null);
            await tenderApi.uploadDocument(id, file);
            warmChatExperience(id);
            // Refresh to see status change from DRAFT -> ACTIVE
            await loadTenders();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to upload document');
            throw err;
        }
    };

    const handleEditProposal = (proposalId: number) => {
        navigate('/proposals', { state: { proposalId } });
    };

    const warmChatExperience = useCallback((id: number) => {
        void preloadRoute(`/tenders/${id}/chat`);
        void prefetchTenderChatContext(id);
        void prefetchTenderChatRetrospective(id);
    }, []);

    const handleWarmChat = (id: number) => {
        warmChatExperience(id);
    };

    const handleOpenChat = (id: number) => {
        warmChatExperience(id);
        navigate(`/tenders/${id}/chat`);
    };

    const handleSubmitTender = async (id: number) => {
        try {
            setLoading(true);
            await tenderApi.update(id, { status: 'submitted' });
            await loadTenders();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to submit tender');
        } finally {
            setLoading(false);
        }
    };

    // Compute real stats
    const activeTenders = tenders.filter(
        (t) => t.status === 'active' || t.status === 'in_progress' || t.status === 'submitted'
    ).length;
    const wonTenders = tenders.filter((t) => t.status === 'won').length;
    const totalDecided = tenders.filter(
        (t) => t.status === 'won' || t.status === 'lost'
    ).length;
    const winRate = totalDecided > 0 ? Math.round((wonTenders / totalDecided) * 100) : 0;
    const pendingDeadlines = tenders.filter((t) => {
        const days = getDaysUntil(t.deadline);
        // exclude won, lost, cancelled from pending deadlines
        const isPending = !['won', 'lost', 'cancelled'].includes(t.status);
        return isPending && days !== null && days > 0 && days <= 14;
    }).length;

    const stats = [
        { label: 'Active Tenders', value: String(activeTenders), icon: FileText },
        { label: 'Win Rate', value: totalDecided > 0 ? `${winRate}%` : 'N/A', icon: TrendingUp },
        { label: 'Pending Deadlines', value: String(pendingDeadlines), icon: Clock },
        { label: 'Proposals Won', value: String(wonTenders), icon: CheckCircle },
    ];

    return (
        <div className="animate-in">
            {/* Header */}
            <div className="page-header">
                <div>
                    <h1 className="page-title">Dashboard</h1>
                    <p className="page-subtitle">Manage your tender pipeline and track deadlines</p>
                </div>
                <button
                    className="btn btn-primary"
                    onClick={() => setShowNewTender(!showNewTender)}
                >
                    <Plus size={18} />
                    New Tender
                </button>
            </div>

            {/* Error */}
            {error && (
                <div className="card" style={{ borderColor: '#ef4444', marginBottom: '1.5rem', display: 'flex', alignItems: 'center', gap: '0.75rem', color: '#ef4444' }}>
                    <AlertCircle size={18} />
                    <span>{error}</span>
                    <button className="btn btn-ghost btn-sm" onClick={loadTenders} style={{ marginLeft: 'auto' }}>Retry</button>
                </div>
            )}

            {/* Stats */}
            <div className="stats-grid">
                {stats.map((stat, i) => (
                    <motion.div
                        key={stat.label}
                        className="stat-card"
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        whileHover={{ y: -4, boxShadow: 'var(--shadow-glow)', borderColor: 'var(--accent-blue)' }}
                        transition={{ delay: i * 0.08, duration: 0.2 }}
                        style={{
                            background: 'rgba(255, 255, 255, 0.03)',
                            backdropFilter: 'blur(10px)',
                            border: '1px solid var(--border-default)',
                        }}
                    >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                            <div>
                                <div className="stat-label">{stat.label}</div>
                                <div className="stat-value">
                                    {loading ? '—' : stat.value}
                                </div>
                            </div>
                            <stat.icon size={20} color="#64748b" />
                        </div>
                    </motion.div>
                ))}
            </div>

            {/* Tenders list logic remains below */}

            {/* Loading */}
            {loading && (
                <div className="loading-spinner" style={{ padding: '3rem 0' }}>
                    <div className="spinner" />
                    <p style={{ color: 'var(--text-muted)', marginTop: '0.75rem' }}>Loading tenders...</p>
                </div>
            )}

            {/* Pipeline Kanban */}
            {!loading && (
                <div className="pipeline">
                    {PIPELINE_COLUMNS.map((col) => {
                        const colTenders = tenders.filter((t) => t.status === col.key);
                        return (
                            <div className="pipeline-column" key={col.key}>
                                <div className="pipeline-header">
                                    <h3 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                        <span
                                            style={{
                                                width: 8,
                                                height: 8,
                                                borderRadius: '50%',
                                                background: col.color,
                                                display: 'inline-block',
                                            }}
                                        />
                                        {col.label}
                                    </h3>
                                    <span className="pipeline-count">{colTenders.length}</span>
                                </div>

                                {colTenders.length === 0 ? (
                                    <div className="empty-state" style={{ padding: '2rem 1rem' }}>
                                        <p style={{ fontSize: '0.8rem' }}>No tenders</p>
                                    </div>
                                ) : (
                                    colTenders.map((tender, i) => (
                                        <TenderCard key={tender.id} tender={tender} index={i} onUpload={handleUpload} onCreateProposal={setShowNewProposal} onEditProposal={handleEditProposal} onSubmit={handleSubmitTender} onOpenChat={handleOpenChat} onWarmChat={handleWarmChat} />
                                    ))
                                )}
                            </div>
                        );
                    })}
                </div>
            )}

            {/* New Proposal Modal */}
            <AnimatePresence>
                {showNewProposal !== null && (
                    <motion.div
                        className="modal-overlay"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                    >
                        <motion.div
                            className="modal-content"
                            initial={{ scale: 0.95, opacity: 0, y: 20 }}
                            animate={{ scale: 1, opacity: 1, y: 0 }}
                            exit={{ scale: 0.95, opacity: 0, y: 20 }}
                        >
                            <div className="modal-header">
                                <h3 style={{ margin: 0 }}>Create New Proposal</h3>
                                <button
                                    className="btn btn-icon btn-ghost"
                                    onClick={() => {
                                        setShowNewProposal(null);
                                        setProposalTitle('');
                                    }}
                                >
                                    <X size={20} />
                                </button>
                            </div>

                            <div className="modal-body">
                                <p className="page-subtitle" style={{ marginBottom: '1.5rem', marginTop: 0 }}>
                                    Define the title for your new technical proposal. You can change this later.
                                </p>
                                <div className="form-group">
                                    <label className="form-label">Proposal Title *</label>
                                    <input
                                        type="text"
                                        className="form-input"
                                        placeholder="e.g., Technical Proposal - Phase 1"
                                        value={proposalTitle}
                                        onChange={(e) => setProposalTitle(e.target.value)}
                                        autoFocus
                                    />
                                </div>
                            </div>

                            <div className="modal-footer">
                                <button
                                    className="btn btn-ghost"
                                    onClick={() => {
                                        setShowNewProposal(null);
                                        setProposalTitle('');
                                    }}
                                >
                                    Cancel
                                </button>
                                <button
                                    className="btn btn-primary"
                                    disabled={!proposalTitle.trim() || creatingProposal}
                                    onClick={handleCreateProposal}
                                >
                                    {creatingProposal ? (
                                        <>
                                            <Loader2 size={16} className="spin" />
                                            Creating...
                                        </>
                                    ) : (
                                        'Create Proposal'
                                    )}
                                </button>
                            </div>
                        </motion.div>
                    </motion.div>
                )}
                {showNewTender && (
                    <motion.div
                        className="modal-overlay"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                    >
                        <motion.div
                            className="modal-content"
                            style={{ maxWidth: '650px' }}
                            initial={{ scale: 0.95, opacity: 0, y: 20 }}
                            animate={{ scale: 1, opacity: 1, y: 0 }}
                            exit={{ scale: 0.95, opacity: 0, y: 20 }}
                        >
                            <div className="modal-header">
                                <h3 style={{ margin: 0 }}>Create New Tender</h3>
                                <button
                                    className="btn btn-icon btn-ghost"
                                    onClick={() => setShowNewTender(false)}
                                >
                                    <X size={20} />
                                </button>
                            </div>

                            <div className="modal-body">
                                <p className="page-subtitle" style={{ marginBottom: '1.5rem', marginTop: 0 }}>
                                    Add a new opportunity to the pipeline. You can import documents immediately after creation.
                                </p>
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.25rem' }}>
                                    <div className="form-group">
                                        <label className="form-label">Tender Title *</label>
                                        <input
                                            className="form-input"
                                            placeholder="e.g., Highway Bridge Rehabilitation"
                                            value={form.title}
                                            onChange={(e) => setForm({ ...form, title: e.target.value })}
                                            autoFocus
                                        />
                                    </div>
                                    <div className="form-group">
                                        <label className="form-label">Client</label>
                                        <input
                                            className="form-input"
                                            placeholder="e.g., State DOT"
                                            value={form.client || ''}
                                            onChange={(e) => setForm({ ...form, client: e.target.value })}
                                        />
                                    </div>
                                    <div className="form-group">
                                        <label className="form-label">Category</label>
                                        <select
                                            className="form-select"
                                            value={form.category || ''}
                                            onChange={(e) => setForm({ ...form, category: e.target.value })}
                                        >
                                            <option value="">Select category</option>
                                            <option>Infrastructure</option>
                                            <option>IT & Technology</option>
                                            <option>Water & Environment</option>
                                            <option>Energy</option>
                                            <option>Healthcare</option>
                                            <option>Education</option>
                                        </select>
                                    </div>
                                    <div className="form-group">
                                        <label className="form-label">Deadline</label>
                                        <input
                                            className="form-input"
                                            type="date"
                                            value={form.deadline || ''}
                                            onChange={(e) => setForm({ ...form, deadline: e.target.value })}
                                        />
                                    </div>
                                </div>
                                <div className="form-group" style={{ marginTop: '0.25rem' }}>
                                    <label className="form-label">Description (Optional)</label>
                                    <textarea
                                        className="form-textarea"
                                        placeholder="Briefly describe the tender requirements or context..."
                                        value={form.description || ''}
                                        onChange={(e) => setForm({ ...form, description: e.target.value })}
                                        rows={3}
                                    />
                                </div>
                            </div>

                            <div className="modal-footer">
                                <button className="btn btn-ghost" onClick={() => setShowNewTender(false)}>
                                    Cancel
                                </button>
                                <button
                                    className="btn btn-primary"
                                    onClick={handleCreate}
                                    disabled={creating || !form.title.trim()}
                                >
                                    {creating ? <Loader2 size={16} className="spin" /> : <Plus size={16} />}
                                    {creating ? 'Creating...' : 'Create Tender'}
                                </button>
                            </div>
                        </motion.div>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Empty state */}
            {!loading && tenders.length === 0 && !error && (
                <div className="empty-state" style={{ padding: '3rem 0' }}>
                    <FileText size={48} />
                    <h3>No tenders yet</h3>
                    <p>Create your first tender to get started</p>
                </div>
            )}
        </div>
    );
}
===
import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
    Plus,
    Clock,
    TrendingUp,
    FileText,
    CheckCircle,
    AlertCircle,
    Loader2,
    Upload,
    Check,
    FileEdit,
    MessageSquare,
    X,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { prefetchTenderChatContext, prefetchTenderChatRetrospective, tenderApi, proposalApi, type Tender, type TenderCreate } from '../api/client';
import { preloadRoute } from '../router/lazyRoutes';

const PIPELINE_COLUMNS = [
    { key: 'draft', label: 'Draft', color: '#64748b' },
    { key: 'active', label: 'Active', color: '#3b82f6' },
    { key: 'in_progress', label: 'In Progress', color: '#f59e0b' },
    { key: 'submitted', label: 'Submitted', color: '#8b5cf6' },
    { key: 'won', label: 'Won', color: '#10b981' },
];

function getDaysUntil(dateStr: string | null): number | null {
    if (!dateStr) return null;
    const target = new Date(dateStr);
    const now = new Date();
    return Math.ceil((target.getTime() - now.getTime()) / (1000 * 60 * 60 * 24));
}

function TenderCard({ tender, index, onUpload, onCreateProposal, onEditProposal, onSubmit, onOpenChat, onWarmChat, onOpenMattermost }: { tender: Tender; index: number; onUpload: (id: number, file: File) => Promise<void>; onCreateProposal: (tenderId: number | null) => void; onEditProposal: (proposalId: number) => void; onSubmit: (id: number) => Promise<void>; onOpenChat: (id: number) => void; onWarmChat: (id: number) => void; onOpenMattermost: () => void }) {
    const days = getDaysUntil(tender.deadline);
    const isUrgent = days !== null && days <= 7 && days > 0;
    const isPast = days !== null && days < 0;

    const [uploading, setUploading] = useState(false);
    const [success, setSuccess] = useState(false);
    const [chatMenuOpen, setChatMenuOpen] = useState(false);

    const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;

        try {
            setUploading(true);
            await onUpload(tender.id, file);
            setSuccess(true);
            setTimeout(() => setSuccess(false), 3000);
        } catch (err) {
            console.error(err);
        } finally {
            setUploading(false);
            // Reset input
            e.target.value = '';
        }
    };

    return (
        <motion.div
            className="tender-card"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            whileHover={{ y: -4, boxShadow: 'var(--shadow-lg)', borderColor: 'var(--accent-blue)' }}
            transition={{ delay: index * 0.05, duration: 0.2 }}
            style={{
                background: 'rgba(255, 255, 255, 0.02)',
                backdropFilter: 'blur(10px)',
                cursor: 'default'
            }}
        >
            <div className="tender-card-title">{tender.title}</div>
            <div className="tender-card-client">{tender.client || 'No client'}</div>

            <div style={{ marginTop: '0.75rem', marginBottom: '0.75rem', display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                {!['submitted', 'won', 'lost', 'cancelled'].includes(tender.status) && (
                    <label className="btn btn-secondary btn-sm" style={{ cursor: uploading ? 'not-allowed' : 'pointer', fontSize: '0.75rem', padding: '0.25rem 0.5rem' }}>
                        {uploading ? <Loader2 size={12} className="spin" /> : success ? <Check size={12} color="#10b981" /> : <Upload size={12} />}
                        {uploading ? 'Uploading...' : success ? 'Uploaded' : 'Upload PDF'}
                        <input
                            type="file"
                            accept=".pdf,.docx,.txt"
                            style={{ display: 'none' }}
                            onChange={handleFileChange}
                            disabled={uploading}
                        />
                    </label>
                )}

                {tender.status === 'active' && (
                    <button
                        className="btn btn-primary btn-sm"
                        style={{ fontSize: '0.75rem', padding: '0.25rem 0.5rem', gap: '0.25rem' }}
                        onClick={() => onCreateProposal(tender.id)}
                    >
                        <FileEdit size={12} />
                        Create Proposal
                    </button>
                )}

                {tender.status === 'in_progress' && (
                    <>
                        <button
                            className="btn btn-primary btn-sm"
                            style={{ fontSize: '0.75rem', padding: '0.25rem 0.5rem', gap: '0.25rem' }}
                            onClick={() => {
                                if (tender.proposal_id) {
                                    onEditProposal(tender.proposal_id);
                                } else {
                                    onCreateProposal(tender.id);
                                }
                            }}
                        >
                            <FileEdit size={12} />
                            Edit Proposal
                        </button>
                        <button
                            className="btn btn-secondary btn-sm"
                            style={{ fontSize: '0.75rem', padding: '0.25rem 0.6rem', gap: '0.25rem', background: 'var(--accent-purple)', color: 'white', border: 'none' }}
                            onClick={() => onSubmit(tender.id)}
                        >
                            <CheckCircle size={12} />
                            Submit
                        </button>
                    </>
                )}

                {/* Chat mode split-button: Internal Chat (default) + Mattermost dropdown */}
                <div style={{ position: 'relative', display: 'inline-flex' }}>
                    <button
                        className="btn btn-ghost btn-sm"
                        style={{ fontSize: '0.75rem', padding: '0.25rem 0.6rem', gap: '0.25rem', borderTopRightRadius: 0, borderBottomRightRadius: 0 }}
                        onClick={() => onOpenChat(tender.id)}
                        onMouseEnter={() => onWarmChat(tender.id)}
                        onFocus={() => onWarmChat(tender.id)}
                        onTouchStart={() => onWarmChat(tender.id)}
                    >
                        <MessageSquare size={12} />
                        Chat
                    </button>
                    <button
                        className="btn btn-ghost btn-sm"
                        style={{
                            fontSize: '0.65rem',
                            padding: '0.25rem 0.3rem',
                            borderTopLeftRadius: 0,
                            borderBottomLeftRadius: 0,
                            borderLeft: '1px solid var(--border-default)',
                            minWidth: 'unset',
                        }}
                        onClick={(e) => {
                            e.stopPropagation();
                            setChatMenuOpen(!chatMenuOpen);
                        }}
                        onBlur={() => setTimeout(() => setChatMenuOpen(false), 150)}
                        aria-label="Chat options"
                    >
                        ▼
                    </button>
                    {chatMenuOpen && (
                        <div style={{
                            position: 'absolute',
                            top: '100%',
                            right: 0,
                            marginTop: '0.25rem',
                            background: 'var(--bg-card, #1e293b)',
                            border: '1px solid var(--border-default)',
                            borderRadius: '8px',
                            boxShadow: 'var(--shadow-lg)',
                            zIndex: 50,
                            minWidth: '180px',
                            overflow: 'hidden',
                        }}>
                            <button
                                className="btn btn-ghost"
                                style={{ width: '100%', fontSize: '0.78rem', padding: '0.6rem 0.75rem', gap: '0.4rem', justifyContent: 'flex-start', borderRadius: 0 }}
                                onMouseDown={(e) => { e.preventDefault(); onOpenChat(tender.id); setChatMenuOpen(false); }}
                            >
                                💬 Chat Interna
                            </button>
                            <div style={{ borderTop: '1px solid var(--border-default)' }} />
                            <button
                                className="btn btn-ghost"
                                style={{ width: '100%', fontSize: '0.78rem', padding: '0.6rem 0.75rem', gap: '0.4rem', justifyContent: 'flex-start', borderRadius: 0 }}
                                onMouseDown={(e) => { e.preventDefault(); onOpenMattermost(); setChatMenuOpen(false); }}
                            >
                                📹 Mattermost + Video
                            </button>
                        </div>
                    )}
                </div>
            </div>

            <div className="tender-card-footer">
                <span className={isUrgent ? 'deadline-urgent' : ''}>
                    <Clock size={12} style={{ marginRight: 4, verticalAlign: 'middle' }} />
                    {days === null
                        ? 'No deadline'
                        : isPast
                            ? 'Past due'
                            : isUrgent
                                ? `${days}d left!`
                                : `${days} days`}
                </span>
                <span className={`badge badge-${tender.status.replace('_', '-')}`}>
                    {tender.status.replace('_', ' ')}
                </span>
            </div>
        </motion.div>
    );
}

const EMPTY_FORM: TenderCreate = {
    title: '',
    client: '',
    description: '',
    deadline: '',
    category: '',
    tags: [],
    budget_estimate: undefined,
};

export default function Dashboard() {
    const [tenders, setTenders] = useState<Tender[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [showNewTender, setShowNewTender] = useState(false);
    const [form, setForm] = useState<TenderCreate>({ ...EMPTY_FORM });
    const [creating, setCreating] = useState(false);

    // Proposal creation state
    const [showNewProposal, setShowNewProposal] = useState<number | null>(null);
    const [proposalTitle, setProposalTitle] = useState('');
    const [creatingProposal, setCreatingProposal] = useState(false);

    const navigate = useNavigate();

    const loadTenders = useCallback(async () => {
        try {
            setLoading(true);
            setError(null);
            const data = await tenderApi.list({ limit: '100' });
            setTenders(data.items);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to load tenders');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        loadTenders();
    }, [loadTenders]);

    const handleCreate = async () => {
        if (!form.title.trim()) return;
        try {
            setCreating(true);
            const payload: TenderCreate = { title: form.title };
            if (form.client) payload.client = form.client;
            if (form.description) payload.description = form.description;
            if (form.deadline) payload.deadline = new Date(form.deadline).toISOString();
            if (form.category) payload.category = form.category;
            await tenderApi.create(payload);
            setForm({ ...EMPTY_FORM });
            setShowNewTender(false);
            await loadTenders();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to create tender');
        } finally {
            setCreating(false);
        }
    };

    const handleCreateProposal = async () => {
        if (!proposalTitle.trim() || showNewProposal === null) return;
        try {
            setCreatingProposal(true);
            const proposal = await proposalApi.create({
                tender_id: showNewProposal,
                title: proposalTitle,
            });
            setShowNewProposal(null);
            setProposalTitle('');
            // Navigate to proposals page and select the new proposal
            navigate('/proposals', { state: { proposalId: proposal.id } });
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to create proposal');
        } finally {
            setCreatingProposal(false);
        }
    };

    const handleUpload = async (id: number, file: File) => {
        try {
            setError(null);
            await tenderApi.uploadDocument(id, file);
            warmChatExperience(id);
            // Refresh to see status change from DRAFT -> ACTIVE
            await loadTenders();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to upload document');
            throw err;
        }
    };

    const handleEditProposal = (proposalId: number) => {
        navigate('/proposals', { state: { proposalId } });
    };

    const warmChatExperience = useCallback((id: number) => {
        void preloadRoute(`/tenders/${id}/chat`);
        void prefetchTenderChatContext(id);
        void prefetchTenderChatRetrospective(id);
    }, []);

    const handleWarmChat = (id: number) => {
        warmChatExperience(id);
    };

    const handleOpenChat = (id: number) => {
        warmChatExperience(id);
        navigate(`/tenders/${id}/chat`);
    };

    const mattermostUrl = (import.meta as any).env?.VITE_MATTERMOST_URL || 'http://localhost:8065';
    const handleOpenMattermost = () => {
        window.open(mattermostUrl, '_blank', 'noopener,noreferrer');
    };

    const handleSubmitTender = async (id: number) => {
        try {
            setLoading(true);
            await tenderApi.update(id, { status: 'submitted' });
            await loadTenders();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to submit tender');
        } finally {
            setLoading(false);
        }
    };

    // Compute real stats
    const activeTenders = tenders.filter(
        (t) => t.status === 'active' || t.status === 'in_progress' || t.status === 'submitted'
    ).length;
    const wonTenders = tenders.filter((t) => t.status === 'won').length;
    const totalDecided = tenders.filter(
        (t) => t.status === 'won' || t.status === 'lost'
    ).length;
    const winRate = totalDecided > 0 ? Math.round((wonTenders / totalDecided) * 100) : 0;
    const pendingDeadlines = tenders.filter((t) => {
        const days = getDaysUntil(t.deadline);
        // exclude won, lost, cancelled from pending deadlines
        const isPending = !['won', 'lost', 'cancelled'].includes(t.status);
        return isPending && days !== null && days > 0 && days <= 14;
    }).length;

    const stats = [
        { label: 'Active Tenders', value: String(activeTenders), icon: FileText },
        { label: 'Win Rate', value: totalDecided > 0 ? `${winRate}%` : 'N/A', icon: TrendingUp },
        { label: 'Pending Deadlines', value: String(pendingDeadlines), icon: Clock },
        { label: 'Proposals Won', value: String(wonTenders), icon: CheckCircle },
    ];

    return (
        <div className="animate-in">
            {/* Header */}
            <div className="page-header">
                <div>
                    <h1 className="page-title">Dashboard</h1>
                    <p className="page-subtitle">Manage your tender pipeline and track deadlines</p>
                </div>
                <button
                    className="btn btn-primary"
                    onClick={() => setShowNewTender(!showNewTender)}
                >
                    <Plus size={18} />
                    New Tender
                </button>
            </div>

            {/* Error */}
            {error && (
                <div className="card" style={{ borderColor: '#ef4444', marginBottom: '1.5rem', display: 'flex', alignItems: 'center', gap: '0.75rem', color: '#ef4444' }}>
                    <AlertCircle size={18} />
                    <span>{error}</span>
                    <button className="btn btn-ghost btn-sm" onClick={loadTenders} style={{ marginLeft: 'auto' }}>Retry</button>
                </div>
            )}

            {/* Stats */}
            <div className="stats-grid">
                {stats.map((stat, i) => (
                    <motion.div
                        key={stat.label}
                        className="stat-card"
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        whileHover={{ y: -4, boxShadow: 'var(--shadow-glow)', borderColor: 'var(--accent-blue)' }}
                        transition={{ delay: i * 0.08, duration: 0.2 }}
                        style={{
                            background: 'rgba(255, 255, 255, 0.03)',
                            backdropFilter: 'blur(10px)',
                            border: '1px solid var(--border-default)',
                        }}
                    >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                            <div>
                                <div className="stat-label">{stat.label}</div>
                                <div className="stat-value">
                                    {loading ? '—' : stat.value}
                                </div>
                            </div>
                            <stat.icon size={20} color="#64748b" />
                        </div>
                    </motion.div>
                ))}
            </div>

            {/* Tenders list logic remains below */}

            {/* Loading */}
            {loading && (
                <div className="loading-spinner" style={{ padding: '3rem 0' }}>
                    <div className="spinner" />
                    <p style={{ color: 'var(--text-muted)', marginTop: '0.75rem' }}>Loading tenders...</p>
                </div>
            )}

            {/* Pipeline Kanban */}
            {!loading && (
                <div className="pipeline">
                    {PIPELINE_COLUMNS.map((col) => {
                        const colTenders = tenders.filter((t) => t.status === col.key);
                        return (
                            <div className="pipeline-column" key={col.key}>
                                <div className="pipeline-header">
                                    <h3 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                        <span
                                            style={{
                                                width: 8,
                                                height: 8,
                                                borderRadius: '50%',
                                                background: col.color,
                                                display: 'inline-block',
                                            }}
                                        />
                                        {col.label}
                                    </h3>
                                    <span className="pipeline-count">{colTenders.length}</span>
                                </div>

                                {colTenders.length === 0 ? (
                                    <div className="empty-state" style={{ padding: '2rem 1rem' }}>
                                        <p style={{ fontSize: '0.8rem' }}>No tenders</p>
                                    </div>
                                ) : (
                                    colTenders.map((tender, i) => (
                                        <TenderCard key={tender.id} tender={tender} index={i} onUpload={handleUpload} onCreateProposal={setShowNewProposal} onEditProposal={handleEditProposal} onSubmit={handleSubmitTender} onOpenChat={handleOpenChat} onWarmChat={handleWarmChat} onOpenMattermost={handleOpenMattermost} />
                                    ))
                                )}
                            </div>
                        );
                    })}
                </div>
            )}

            {/* New Proposal Modal */}
            <AnimatePresence>
                {showNewProposal !== null && (
                    <motion.div
                        className="modal-overlay"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                    >
                        <motion.div
                            className="modal-content"
                            initial={{ scale: 0.95, opacity: 0, y: 20 }}
                            animate={{ scale: 1, opacity: 1, y: 0 }}
                            exit={{ scale: 0.95, opacity: 0, y: 20 }}
                        >
                            <div className="modal-header">
                                <h3 style={{ margin: 0 }}>Create New Proposal</h3>
                                <button
                                    className="btn btn-icon btn-ghost"
                                    onClick={() => {
                                        setShowNewProposal(null);
                                        setProposalTitle('');
                                    }}
                                >
                                    <X size={20} />
                                </button>
                            </div>

                            <div className="modal-body">
                                <p className="page-subtitle" style={{ marginBottom: '1.5rem', marginTop: 0 }}>
                                    Define the title for your new technical proposal. You can change this later.
                                </p>
                                <div className="form-group">
                                    <label className="form-label">Proposal Title *</label>
                                    <input
                                        type="text"
                                        className="form-input"
                                        placeholder="e.g., Technical Proposal - Phase 1"
                                        value={proposalTitle}
                                        onChange={(e) => setProposalTitle(e.target.value)}
                                        autoFocus
                                    />
                                </div>
                            </div>

                            <div className="modal-footer">
                                <button
                                    className="btn btn-ghost"
                                    onClick={() => {
                                        setShowNewProposal(null);
                                        setProposalTitle('');
                                    }}
                                >
                                    Cancel
                                </button>
                                <button
                                    className="btn btn-primary"
                                    disabled={!proposalTitle.trim() || creatingProposal}
                                    onClick={handleCreateProposal}
                                >
                                    {creatingProposal ? (
                                        <>
                                            <Loader2 size={16} className="spin" />
                                            Creating...
                                        </>
                                    ) : (
                                        'Create Proposal'
                                    )}
                                </button>
                            </div>
                        </motion.div>
                    </motion.div>
                )}
                {showNewTender && (
                    <motion.div
                        className="modal-overlay"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                    >
                        <motion.div
                            className="modal-content"
                            style={{ maxWidth: '650px' }}
                            initial={{ scale: 0.95, opacity: 0, y: 20 }}
                            animate={{ scale: 1, opacity: 1, y: 0 }}
                            exit={{ scale: 0.95, opacity: 0, y: 20 }}
                        >
                            <div className="modal-header">
                                <h3 style={{ margin: 0 }}>Create New Tender</h3>
                                <button
                                    className="btn btn-icon btn-ghost"
                                    onClick={() => setShowNewTender(false)}
                                >
                                    <X size={20} />
                                </button>
                            </div>

                            <div className="modal-body">
                                <p className="page-subtitle" style={{ marginBottom: '1.5rem', marginTop: 0 }}>
                                    Add a new opportunity to the pipeline. You can import documents immediately after creation.
                                </p>
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.25rem' }}>
                                    <div className="form-group">
                                        <label className="form-label">Tender Title *</label>
                                        <input
                                            className="form-input"
                                            placeholder="e.g., Highway Bridge Rehabilitation"
                                            value={form.title}
                                            onChange={(e) => setForm({ ...form, title: e.target.value })}
                                            autoFocus
                                        />
                                    </div>
                                    <div className="form-group">
                                        <label className="form-label">Client</label>
                                        <input
                                            className="form-input"
                                            placeholder="e.g., State DOT"
                                            value={form.client || ''}
                                            onChange={(e) => setForm({ ...form, client: e.target.value })}
                                        />
                                    </div>
                                    <div className="form-group">
                                        <label className="form-label">Category</label>
                                        <select
                                            className="form-select"
                                            value={form.category || ''}
                                            onChange={(e) => setForm({ ...form, category: e.target.value })}
                                        >
                                            <option value="">Select category</option>
                                            <option>Infrastructure</option>
                                            <option>IT & Technology</option>
                                            <option>Water & Environment</option>
                                            <option>Energy</option>
                                            <option>Healthcare</option>
                                            <option>Education</option>
                                        </select>
                                    </div>
                                    <div className="form-group">
                                        <label className="form-label">Deadline</label>
                                        <input
                                            className="form-input"
                                            type="date"
                                            value={form.deadline || ''}
                                            onChange={(e) => setForm({ ...form, deadline: e.target.value })}
                                        />
                                    </div>
                                </div>
                                <div className="form-group" style={{ marginTop: '0.25rem' }}>
                                    <label className="form-label">Description (Optional)</label>
                                    <textarea
                                        className="form-textarea"
                                        placeholder="Briefly describe the tender requirements or context..."
                                        value={form.description || ''}
                                        onChange={(e) => setForm({ ...form, description: e.target.value })}
                                        rows={3}
                                    />
                                </div>
                            </div>

                            <div className="modal-footer">
                                <button className="btn btn-ghost" onClick={() => setShowNewTender(false)}>
                                    Cancel
                                </button>
                                <button
                                    className="btn btn-primary"
                                    onClick={handleCreate}
                                    disabled={creating || !form.title.trim()}
                                >
                                    {creating ? <Loader2 size={16} className="spin" /> : <Plus size={16} />}
                                    {creating ? 'Creating...' : 'Create Tender'}
                                </button>
                            </div>
                        </motion.div>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Empty state */}
            {!loading && tenders.length === 0 && !error && (
                <div className="empty-state" style={{ padding: '3rem 0' }}>
                    <FileText size={48} />
                    <h3>No tenders yet</h3>
                    <p>Create your first tender to get started</p>
                </div>
            )}
        </div>
    );
}
```

Il bottone "Open Chat" è ora un **split-button** con:
- **💬 Chat Interna** — comportamento originale (navigazione a `/tenders/:id/chat`)
- **📹 Mattermost + Video** — apre Mattermost in una nuova tab

## Validazione

| Test | Risultato |
|---|---|
| `docker compose config --quiet` | ✅ Nessun errore |

## Prossimi Passi (Manuali)

1. Avviare i nuovi servizi: `docker compose up -d mm-postgres mattermost`
2. Configurare Mattermost (primo setup admin) su `http://localhost:8065`
3. Installare il **Plugin Jitsi** nel Marketplace di Mattermost
4. Puntare il plugin a `http://jitsi-web:80` (URL interno Docker)
5. Avviare Jitsi + Vosk: `docker compose up -d jitsi-prosody jitsi-jicofo jitsi-jvb jitsi-web vosk jitsi-jigasi`
6. Configurare un **Incoming Webhook** su Mattermost e avviare il forwarder:
   ```bash
   python utility/transcript_forwarder.py --webhook-url https://... --watch-dir <path-to-transcripts-volume>
   ```


Analyzing Video Call Integration Architecture
Completed full codebase analysis. The current chat is launched from the Dashboard's 

TenderCard
 via the "Open Chat" button (line 131-141 in 

Dashboard.tsx
) which navigates to /tenders/:id/chat. The chat page (

TenderChat.tsx
) is an internal WebSocket/polling chat room with MinIO-backed message storage. No Mattermost, Jitsi, Jigasi, or Vosk infrastructure currently exists in the project. The 

docker-compose.yml
 has 17+ services on a shared Docker network. The user's pre-analysis proposes a fully self-hosted video-call transcription pipeline: Mattermost → Jitsi Meet → Jigasi → Vosk → transcript back to Mattermost.

Files Edited
Progress Updates
1
Reading pre-analysis document and exploring current codebase

2
Analyzing existing chat code in frontend and backend

3
Checking routing, Dashboard navigation and .env to understand full picture

4
Examining chat launch in Dashboard and writing the implementation plan

5
Writing implementation plan and task checklist

Ho completato l'analisi dell'intero codebase e validato la tua pre-analisi in VIDEO CALL.md.

Risultati chiave:

La pre-analisi è tecnicamente corretta ma necessita di adattamenti per integrarsi col docker-compose esistente (17+ servizi)
Ho identificato il punto di lancio chat: bottone "Open Chat" nel TenderCard (Dashboard, linee 131-141) → naviga a /tenders/:id/chat
Ho proposto di trasformare quel bottone in un dropdown a due scelte: Chat Interna (attuale) vs Mattermost + Video
Domande specifiche:

Vuoi un PostgreSQL dedicato separato per Mattermost (come proposto) o preferisci riutilizzare il PostgreSQL esistente di TenderWriter con un database diverso?
Per il transcript_forwarder.py, preferisci un container Docker dedicato o uno script eseguito come sidecar del container Jigasi?
Le porte proposte (Mattermost 8065, Jitsi 8880) vanno bene o hai conflitti noti?
Proceeded with
Manually proceeded.
