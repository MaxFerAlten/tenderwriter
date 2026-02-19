# TenderWriter

> Open-source Tender Proposal Writing Software powered by HybridRAG

TenderWriter helps teams create, manage, and submit professional tender proposals faster by leveraging a **HybridRAG engine** (Dense + Sparse + Knowledge Graph retrieval) running entirely on local, open-source infrastructure.

## Features

- **HybridRAG Engine** — Combines vector search, BM25 keyword search, and knowledge graph queries for high-quality retrieval
- **Proposal Builder** — Rich text editor with AI-assisted writing
- **Content Library** — Reusable content blocks with tagging and search
- **Tender Dashboard** — Pipeline view with deadline tracking
- **Compliance Matrix** — Auto-map RFP requirements to proposal sections
- **PDF Export** — Branded, professional proposal documents
- **100% Local** — All AI runs on your infrastructure via Ollama. No data leaves your network.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python, FastAPI |
| Frontend | React, TypeScript, Vite, TipTap |
| Vector DB | Qdrant |
| Graph DB | Neo4j Community |
| Relational DB | PostgreSQL + pgvector |
| LLM | Ollama (Llama 3, Mistral, Qwen) |
| Embeddings | sentence-transformers (BGE) |
| Document Parsing | unstructured |
| Object Storage | MinIO |
| Task Queue | Celery + Redis |

## Quick Start

```bash
# Clone the repository
git clone https://github.com/your-org/tenderwriter.git
cd tenderwriter

# Start all services
docker compose up -d

# The app will be available at http://localhost:3000
# API docs at http://localhost:8000/docs
```

## Development

### Backend

```bash
cd backend
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## Architecture

See [docs/architecture.md](docs/architecture.md) for the full system architecture and HybridRAG pipeline design.

## License

MIT License — see [LICENSE](LICENSE) for details.
