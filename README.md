# Provenance Ledger

A continuous provenance-and-reproducibility auditing layer for LLM data science agents.

## Architecture

```
.
├── frontend/              # React + Tailwind SPA with Drag-and-Drop Ingestion & Audit Cards
│   └── index.html         # Live Single-Page Application served by FastAPI
├── src/
│   ├── api.py             # FastAPI service (/api/upload, /api/analyze, /api/reverify, /api/models)
│   ├── parser/            # Multi-format data parser (.csv, .xlsx, .pdf, .docx, .json, .parquet)
│   │   └── data_parser.py # DataIngestionEngine & immutable snapshot manager
│   ├── interceptor/       # Interceptor decorator, hashing & Gemini cloud agent
│   │   ├── hashing.py     # Canonical DataFrame (sha256) and environment fingerprinting
│   │   ├── capture.py     # Provenance capture wrapper & decorator
│   │   ├── gemini_client.py # Google Gemini Cloud API client
│   │   └── test_agent.py  # Data science agent powered by Gemini Cloud LLM
│   ├── store/             # Pure PostgreSQL schema & DAL
│   │   ├── models.py      # SQLAlchemy models with native UUID, JSONB, TIMESTAMPTZ
│   │   ├── database.py    # PostgreSQL connection and session management
│   │   └── repository.py  # ProvenanceStore DAL with JSON sanitization
│   ├── reexecutor/        # Re-execution logic (Mechanics §4)
│   ├── comparator/        # Result comparator engine (Mechanics §5)
│   ├── diagnoser/         # Drift diagnoser engine (Mechanics §6)
│   └── scheduler/         # Sampling & scheduling (Mechanics §7)
├── docker/
│   └── docker-compose.yml # PostgreSQL 16 Alpine
├── alembic/               # Database migrations for PostgreSQL
├── data_snapshots/        # Immutable dataset snapshots stored by sha256 hash
├── tests/                 # Full unit & integration test suite (29 tests)
├── Makefile
└── pyproject.toml
```

---

## Quickstart

### 1. Start PostgreSQL
```bash
make db-up
# or: docker compose -f docker/docker-compose.yml up -d
```

### 2. Run Database Migrations
```bash
make db-migrate
# or: alembic upgrade head
```

### 3. Launch Web Application
```bash
make web
# or: python -m uvicorn src.api:app --host 0.0.0.0 --port 8000 --reload
```
Open **[http://localhost:8000](http://localhost:8000)** in your browser.

### 4. Run Test Suite
```bash
pytest -v
```
