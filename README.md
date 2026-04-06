# Novel Imagine — AI-Powered Novel Creation System

An automated novel creation system that expands outlines, plans chapters, writes prose in real-time via streaming, and extracts character relationships into a visual knowledge graph.

## Architecture

```
┌────────────┐   SSE Stream    ┌──────────────┐     ┌─────────┐
│  Next.js   │ <────────────── │   FastAPI     │ ──> │ SQLite  │
│  Frontend  │ ──────────────> │   Backend     │ ──> │ Neo4j   │
└────────────┘   REST API      └──────┬───────┘     └─────────┘
                                      │
                               ┌──────┴───────┐
                               │   LLM Layer  │
                               │ Ollama / Qwen│
                               └──────────────┘
```

## Prerequisites

- **Docker Desktop** (Windows/Mac) with Docker Compose
- **Neo4j** — running locally (Docker or native), accessible at `bolt://localhost:7687`
- **Ollama** (optional for local dev) — running locally with a model pulled, e.g. `ollama pull qwen2.5:7b`

## Quick Start

### 1. Configure Environment

Copy the example env file and fill in your credentials:

```bash
# The .env file is already created with defaults — edit it:
# - Set NEO4J_PASSWORD to your Neo4j password
# - Set LLM_PROVIDER to "ollama" or "qwen"
# - If using Qwen, set QWEN_API_KEY
```

### 2. Launch with Docker Compose

```bash
docker compose up --build
```

This starts:
- **Backend** at http://localhost:8001 (maps host 8001 -> container 8000)
- **Frontend** at http://localhost:3001 (maps host 3001 -> container 3000)

> Ports 8001/3001 are used to avoid conflicts with common local services. Edit `docker-compose.yml` to change.

### 3. Verify

- Open http://localhost:8001/api/health to check backend connectivity
- Open http://localhost:3001 to see the frontend UI

## Project Structure

```
novel_imagine/
├── docker-compose.yml          # Service orchestration
├── .env                        # Environment configuration
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py             # FastAPI entry, CORS, lifespan
│       ├── config.py           # Settings via pydantic-settings
│       ├── database/
│       │   ├── sqlite.py       # SQLAlchemy async ORM models
│       │   └── neo4j.py        # Neo4j async driver singleton
│       ├── models/
│       │   └── schemas.py      # Pydantic request/response models
│       ├── services/
│       │   └── llm.py          # Unified LLM client (Ollama + Qwen)
│       ├── agents/             # AI agents (Phase 2)
│       └── routers/
│           ├── health.py       # GET /api/health
│           └── generate.py     # POST /api/generate (Phase 2)
└── frontend/
    ├── Dockerfile
    ├── package.json
    └── src/
        ├── app/
        │   ├── layout.tsx
        │   ├── page.tsx        # Three-panel layout
        │   └── globals.css
        ├── components/         # UI components (Phase 3)
        └── lib/
            └── api.ts          # Backend API helpers
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `ollama` | `ollama` or `qwen` |
| `OLLAMA_BASE_URL` | `http://host.docker.internal:11434/v1` | Ollama API endpoint |
| `OLLAMA_MODEL` | `qwen2.5:7b` | Ollama model name |
| `QWEN_API_KEY` | `sk-xxx` | Alibaba Cloud DashScope API key |
| `QWEN_BASE_URL` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | Qwen API endpoint |
| `QWEN_MODEL` | `qwen-plus` | Qwen model name |
| `NEO4J_URI` | `bolt://host.docker.internal:7687` | Neo4j Bolt URI |
| `NEO4J_USER` | `neo4j` | Neo4j username |
| `NEO4J_PASSWORD` | `your_password` | Neo4j password |
| `SQLITE_URL` | `sqlite+aiosqlite:///./data/novel.db` | SQLite connection string |

## Development Phases

- [x] **Phase 1** — Scaffolding (backend, frontend, DB, Docker)
- [ ] **Phase 2** — Agent logic & streaming SSE endpoints
- [ ] **Phase 3** — Frontend interaction & graph visualization
- [ ] **Phase 4** — Integration, memory layer & GraphRAG
