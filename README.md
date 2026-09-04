# OmniOps — Evidence-Grounded Business Intelligence Platform

OmniOps is an evidence-oriented business intelligence prototype for structured data and extracted document content. Unavailable semantic capabilities are reported explicitly.

---

## 🏛️ System Architecture Highlights

1. **Deterministic Bounded State Machine**: Pure Python + Pydantic v2 async state engine featuring dynamic sub-goal DAG planning, cycle & loop detection, strict step bounds (`max_steps=12`), and instant cancellation.
2. **DuckDB Vectorized Lakehouse**: Automatically converts uploaded Excel (`.xlsx`) and CSV (`.csv`) files into Parquet files, executing analytical SQL aggregations in microseconds with zero LLM token waste.
3. **PostgreSQL Hybrid Retrieval**: Production deployments use tenant-filtered pgvector cosine candidates and PostgreSQL full-text lexical candidates, fused in SQL with reciprocal rank fusion. SQLite uses a clearly labeled development-only fallback.
4. **Subprocess Python Analytics Sandbox**: Isolated Python runtime with stripped environment variables, timeout limits, and AST validation preventing introspection or unauthorized module imports.
5. **7-Stage Evidentiary Lineage**: Every claim is strictly backed by the 7-stage chain (`SOURCE` → `EXTRACTED CONTENT` → `EVIDENCE` → `CALCULATION` → `CLAIM` → `INFERENCE` → `RECOMMENDATION`) with exact source file coordinates (`page_number`, `cell_range`, `audio_timestamp`).
6. **Real-time Server-Sent Events (SSE)**: Streams sanitized user-facing step progress and discoveries without exposing vulnerable internal tokens or private chain-of-thought.

---

## 🚀 Quick Start

### 1. Prerequisites
* Python `3.12+`
* Node.js `20+` / `22+`
* Docker & Docker Compose (for containerized setup)

### 2. Running Locally (Development)

SQLite local development uses a clearly labeled retrieval fallback. Full hybrid retrieval requires PostgreSQL, pgvector, a migrated schema, and a configured genuine embedding provider.

#### Backend Setup:
```bash
cd backend
python -m venv venv
# On Windows: venv\Scripts\activate | On Unix: source venv/bin/activate
pip install -r requirements.txt
alembic -c alembic.ini upgrade head  # required when DATABASE_URL points to PostgreSQL
uvicorn app.main:app --reload --port 8000
```

#### Frontend Setup:
```bash
cd frontend
npm install
npm run dev
```
Open [http://localhost:3000](http://localhost:3000) in your browser.

---

### 3. Running with Docker Compose (Production)
```bash
docker-compose up --build
```
* **Frontend**: `http://localhost:3000`
* **FastAPI Backend & Swagger**: `http://localhost:8000/docs`
* **PostgreSQL + pgvector**: `localhost:5432` (Alembic creates the vector/FTS columns and HNSW/GIN indexes.)

---

## 🧪 Testing & Evaluation

### Run Test Suite (16/16 Unit & Integration Tests):
```bash
python -m pytest backend/tests -v
```

### Run Benchmark Evaluation Harness (10/10 Business Scenarios):
```bash
python -m evals.runner
```

---

## 🛡️ Security & Tenant Isolation
* **Tenant Isolation**: Mandatory `workspace_id` filtering on all SQL, vector, and FTS queries.
* **SSRF Defense**: Resolves destination host IPs and rejects loopback (`127.0.0.1`), private RFC 1918 ranges (`10.0.0.0/8`, `192.168.0.0/16`), and cloud metadata (`169.254.169.254`).
* **DuckDB Security**: Read-only in-memory Arrow table views with `enable_external_access=False`.
* **File Guard**: Validates magic bytes, enforces 50MB file size limits, and sanitizes filenames to prevent path traversal (`../../`).
