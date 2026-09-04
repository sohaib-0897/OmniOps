# OmniOps Phase 2 Remediation

## Summary

Phase 2 replaces the production in-memory retrieval path with a PostgreSQL-native implementation: genuine OpenAI embeddings stored in `vector(1536)`, pgvector cosine candidate retrieval, PostgreSQL full-text lexical retrieval, and database-side reciprocal rank fusion (RRF). Both candidate branches apply workspace and optional source/modality predicates before ranking.

SQLite remains available only as an explicitly labeled development/test fallback. It is not reported as pgvector or PostgreSQL FTS. A PostgreSQL server and Docker were unavailable in this environment, so the migration and SQL were compiled and PostgreSQL tests were added, but live PostgreSQL execution is honestly reported as not run.

## Previous Retrieval Architecture

- Embeddings were persisted as JSON.
- A deterministic hash projection could silently stand in for a semantic provider.
- Retrieval loaded workspace chunks into Python and calculated cosine and token-overlap scores in memory.
- Lexical matching was not PostgreSQL full-text search.
- There were no pgvector, HNSW, `tsvector`, or GIN schema objects.

## New Retrieval Architecture

Upload/extraction creates source-linked chunks, requests a real embedding, validates its model-specific dimension, and persists indexing provenance and readiness. Investigation retrieval calls a single PostgreSQL hybrid query containing independent semantic and lexical candidate CTEs, bounded candidate sets, SQL predicates for authorization/restriction, and deterministic RRF. Results are returned as API-safe structured values and then become evidence candidates under the Phase 1 evidence contract.

## Database Schema Changes

`document_chunks` now has:

- `embedding vector(1536)` in PostgreSQL
- embedding provider, model, dimension, and generation timestamp
- semantic and lexical indexing states
- a stored generated `search_vector` based on chunk content
- a dimension check constraint

The SQLAlchemy type uses pgvector on PostgreSQL. JSON storage exists only to support the explicitly identified SQLite development fallback.

## Alembic Migrations

- `20260830_baseline_schema.py` creates the pre-Phase-1 schema explicitly so a clean database has a valid migration path.
- Phase 1 now follows that baseline.
- `20260903_phase2_postgres_hybrid_retrieval.py` enables the vector extension, replaces JSON embedding storage, adds provenance/readiness fields and generated `tsvector`, and creates HNSW, GIN, and tenant/source indexes.
- PostgreSQL URLs are converted from asyncpg to psycopg for synchronous Alembic execution.
- Offline PostgreSQL upgrade and Phase 2 downgrade SQL compilation succeeded.
- Live upgrade/downgrade was not run because neither PostgreSQL, `psql`, nor Docker is installed/available here.

## Embedding Strategy

Production semantic indexing uses the configured OpenAI embedding model. The configured model, expected dimension, schema dimension, and every returned vector are validated. Provider absence/failure and dimension mismatch produce explicit states; they do not generate semantic vectors. The deterministic hash provider is isolated to development/test fallback use and is labeled `DEVELOPMENT_FALLBACK`.

## Semantic Retrieval

The PostgreSQL branch uses pgvector cosine distance (`<=>`) with an index-compatible ordered, bounded query. `workspace_id`, source IDs, and modality restrictions are SQL predicates inside the candidate query. If semantic embedding generation is unavailable, retrieval returns an explicit lexical-only/degraded state instead of pretending semantic search occurred.

## Lexical Retrieval

The lexical branch uses a stored `tsvector`, `websearch_to_tsquery('english', ...)`, and `ts_rank_cd`. It is accurately described as PostgreSQL full-text lexical ranking, not BM25.

## Reciprocal Rank Fusion

Semantic and lexical ranks are fused in SQL using `sum(1 / (rrf_k + rank))`, with `rrf_k` configurable and defaulting to 60. Raw vector and FTS scores are not mixed. Stable tie-breaking uses fused score followed by the chunk ID.

## Tenant Isolation

Every semantic and lexical candidate query filters `workspace_id` before ranking or return. Optional source and modality restrictions are also SQL predicates. The final join reasserts workspace membership. Tests cover a foreign tenant, manipulated/foreign source IDs, malformed IDs, empty queries, oversized queries, and invalid `top_k` values.

## PostgreSQL Integration Tests

Real PostgreSQL tests were added for:

- clean Alembic upgrade and vector column inspection
- vector persistence and semantic ranking
- PostgreSQL FTS and deterministic RRF
- tenant and source isolation
- HNSW and GIN catalog/index definitions
- representative `EXPLAIN` plans with index scans enabled

They require `POSTGRES_TEST_DATABASE_URL` pointing to a database whose name contains `test`; the fixture recreates only that database's `public` schema. In this environment they were collected and skipped because no PostgreSQL test URL/server was available: **5 skipped**.

## Retrieval Evaluation

`evals/retrieval_dataset.json` contains labeled exact phrase, semantic synonym, mixed, multi-document, misleading-keyword, and tenant-isolation scenarios. The runner seeds real provider embeddings into a migrated PostgreSQL transaction, performs the production hybrid search, and calculates Precision@K, Recall@K, MRR, and nDCG from returned rankings. It reports `NOT_RUN` when PostgreSQL or genuine embeddings are unavailable; it never fabricates scores.

Observed here: `Retrieval evaluation: NOT_RUN (RETRIEVAL_EVAL_DATABASE_URL is not configured)`.

## Query Plan Verification

The integration suite contains `EXPLAIN` assertions for the HNSW and GIN-backed representative queries and verifies the tenant predicate in the plans. These assertions were not executed because PostgreSQL was unavailable. Architecture-level SQL inspection and offline migration compilation succeeded, but this is not a substitute for a live query-plan result.

## Exact Verification Commands

From `backend/` unless noted:

```text
python -m pytest tests -v
python -m pytest tests/test_postgres_hybrid_retrieval.py -v
python -m evals.runner                         # repository root
python -m evals.retrieval_runner               # repository root
alembic history
alembic upgrade head --sql
alembic downgrade 20260903_phase2:20260902_phase1 --sql
python -m compileall -q app tests ..\evals
npx tsc --noEmit                               # frontend/
npm run lint                                   # frontend/
npm run build                                  # frontend/
```

Environment capability checks also confirmed `docker` and `psql` are unavailable and no service is listening on local PostgreSQL port 5432.

## Exact Test Results

- Backend suite: **48 passed, 5 skipped in 30.49s**. The five skips are the PostgreSQL-only integration module.
- PostgreSQL integration module separately: **5 skipped in 0.03s**, with the explicit reason that `POSTGRES_TEST_DATABASE_URL` is required.
- Phase 1 evaluation suite: **15/15 scenarios passed**; unmeasurable quality metrics remained `NOT_MEASURED`; observed mean latency was 90.4 ms.
- Retrieval evaluation: **NOT_RUN** because `RETRIEVAL_EVAL_DATABASE_URL` was not configured.
- Alembic history: baseline -> Phase 1 -> Phase 2 head.
- Offline PostgreSQL upgrade SQL: **compiled successfully**.
- Offline Phase 2 downgrade SQL: **compiled successfully**.
- Python compileall: **passed**.
- Frontend TypeScript (`npx tsc --noEmit`): **passed**.
- Frontend lint: **passed with no warnings or errors**.
- Frontend production build: **passed**; all five static pages generated and the dynamic workspace route built.
- Live PostgreSQL migration/query plans: **NOT RUN** (PostgreSQL unavailable).
- Docker build: **NOT RUN** (`docker` command unavailable).

## Remaining Risks

- Phase 2 is implemented but cannot be declared fully environment-verified until the PostgreSQL suite, live clean upgrade, index catalog checks, and query-plan assertions run against pgvector-enabled PostgreSQL.
- The vector schema is intentionally single-model/single-dimension. Changing to a different dimension requires a schema migration or separate versioned embedding storage.
- Existing documents need an explicit backfill/reindex operation before they become semantically searchable under the new model.
- PostgreSQL FTS configuration is currently fixed to English; multilingual retrieval will need per-document configuration or a deliberate neutral strategy.
- HNSW effectiveness and candidate limits need tuning with realistic production corpus sizes after live plan/latency measurement.

## Phase 3 Recommendations

1. Run the PostgreSQL suite and retrieval evaluation in CI using a pinned pgvector PostgreSQL service; make both required release checks.
2. Add a resumable embedding backfill/reindex job with model/version migration support and operational progress reporting.
3. Benchmark HNSW parameters, RRF candidate limits, and FTS configuration on a representative tenant-scaled corpus.
4. Add database row-level security as defense in depth while retaining mandatory query predicates.
5. Add embedding batching, provider rate-limit handling, and durable indexing jobs without reintroducing semantic fallback behavior.

# Live Environment Verification

Phase 2.5 classification: **BLOCKED**.

The verification host has no Docker or Podman command, no PostgreSQL server/client tooling (`postgres`, `psql`, `pg_isready`, `initdb`, and `createdb` are absent), no listener on ports 5432 or 5433, and no `POSTGRES_TEST_DATABASE_URL` or `RETRIEVAL_EVAL_DATABASE_URL`. Consequently, no live pgvector-enabled PostgreSQL environment could be established. SQLite was not used as a substitute, and no Phase 1 or Phase 2 production behavior was changed.

| Verification | Result | Evidence |
| --- | --- | --- |
| Live PostgreSQL connection | BLOCKED | No PostgreSQL tooling, configured URL, or listener on 5432/5433. |
| pgvector extension | BLOCKED | No live PostgreSQL connection on which to query `pg_extension`. |
| Alembic clean upgrade | BLOCKED | Cannot execute migrations without a live PostgreSQL database. Previous offline SQL compilation is not counted. |
| Alembic downgrade/re-upgrade | BLOCKED | No isolated live test database exists. |
| vector(1536) persistence | BLOCKED | Cannot inspect or round-trip the live PostgreSQL column. |
| semantic ranking | BLOCKED | No live pgvector database; genuine embedding-provider credentials were also not established for this run. |
| PostgreSQL FTS | BLOCKED | No live PostgreSQL database. |
| HNSW exists | BLOCKED | PostgreSQL catalogs are unavailable. |
| HNSW observed in plan | NOT_OBSERVED | No live `EXPLAIN` could be run. |
| GIN exists | BLOCKED | PostgreSQL catalogs are unavailable. |
| GIN observed in plan | NOT_OBSERVED | No live `EXPLAIN` could be run. |
| RRF correctness | BLOCKED | PostgreSQL integration test could not execute. |
| tenant isolation | BLOCKED | Database-side semantic, lexical, and hybrid paths could not execute. |
| source filtering | BLOCKED | PostgreSQL integration test could not execute. |
| PostgreSQL tests | BLOCKED | `POSTGRES_TEST_DATABASE_URL` is not configured and no server is available; the tests were not rerun as skipped tests cannot certify this phase. |
| retrieval evaluation | BLOCKED | `RETRIEVAL_EVAL_DATABASE_URL` is not configured; no fake or SQLite metrics were produced. |
| Docker build | NOT_RUN | `docker` and `podman` commands are unavailable. |

Exact environmental requirement remaining: provide either Docker Desktop/Engine capable of running the repository's `pgvector/pgvector:pg16` Compose service, or a reachable PostgreSQL 16 server with pgvector installation privileges. Create an isolated database whose name contains `test`, then configure `POSTGRES_TEST_DATABASE_URL` and `RETRIEVAL_EVAL_DATABASE_URL` with async PostgreSQL URLs. Genuine semantic ranking and hybrid evaluation additionally require valid credentials for the configured OpenAI embedding model (`text-embedding-3-small`, 1536 dimensions).

## Phase 2.5 Resume Attempt

On the requested resume attempt, `docker --version` and `docker compose version` both failed because `docker` was not recognized. No executable was present at the standard Docker Desktop paths (`C:\\Program Files\\Docker\\Docker\\resources\\bin\\docker.exe` or `com.docker.cli.exe`), and no PostgreSQL tooling or listener was available. The mandated Docker availability gate therefore remains blocked; no live database commands were run.

## Live Environment Verification (2026-09-02)

Phase 2.5 classification: **PARTIALLY VERIFIED**. The live PostgreSQL retrieval path executed successfully, but genuine semantic-provider evaluation and the full Docker stack could not be completed.

| Verification | Result | Evidence |
| --- | --- | --- |
| Docker available | PASS | `docker --version` = 29.7.2; Compose = v5.5.0; `docker info` reached the Docker Desktop engine after host permission approval. |
| PostgreSQL 16 live | PASS | `docker compose ps`; `pg_isready`; PostgreSQL 16.15 response. |
| pgvector enabled | PASS | `SELECT extname, extversion` returned `vector | 0.8.6`. |
| Clean Alembic migration | PASS | `alembic upgrade head` against `omniops_phase2_test`, exit 0. |
| Alembic downgrade/re-upgrade | PASS | `alembic downgrade -1` and `alembic upgrade head`, both exit 0. |
| vector(1536) verified | PASS | Live catalog returned `embedding | vector(1536)` and dimension check constraint; integration persistence test passed. |
| HNSW exists | PASS | Catalog returned `ix_document_chunks_embedding_hnsw ... USING hnsw (embedding vector_cosine_ops) WHERE (embedding IS NOT NULL)`. |
| HNSW observed | NOT_OBSERVED | Tiny fixture planner selected `ix_document_chunks_workspace_source`; no forced index conclusion was made. |
| GIN exists | PASS | Catalog returned `ix_document_chunks_search_vector_gin ... USING gin (search_vector)`. |
| GIN observed | NOT_OBSERVED | Tiny fixture planner selected the tenant/source index; index existence and planner observation remain separate. |
| Semantic retrieval | PASS | Live integration test round-tripped `vector(1536)` and pgvector `<=>` ranking with a labeled controlled test embedding; no SQLite fallback. |
| Lexical retrieval | PASS | Live FTS/RRF integration test passed using `tsvector` and `websearch_to_tsquery`. |
| RRF | PASS | Live integration test verified deterministic repeated ordering and rank-based fused scores. |
| Tenant isolation | PASS | Live integration test returned no foreign-workspace chunk; workspace predicates are present in both candidate CTEs and final joins. |
| Source restriction | PASS | Live integration test restricted results to the selected source. |
| PostgreSQL test suite | PASS | `python -m pytest tests/test_postgres_hybrid_retrieval.py -q`: **5 passed in 26.59s**; no skips. Full suite with live tests: **53 passed in 31.71s**. |
| Retrieval evaluation | BLOCKED | After adding migration bootstrap, runner reached genuine embedding generation and returned `NOT_RUN (EMBEDDING_PROVIDER_UNAVAILABLE)`; no metrics were fabricated. |
| Agent integration | PARTIALLY VERIFIED | Agent code is wired to `HybridRetriever`; live retrieval path is proven by integration tests, but a full provider-backed investigation was not run without embedding credentials. |
| Docker build | NOT_RUN/INCOMPLETE | `docker compose build` started successfully, but was stopped after ~531 seconds while transferring a ~423 MB frontend context; no success is claimed. |
| Full stack smoke test | NOT_RUN | PostgreSQL service was healthy; backend/frontend images were not completed, so full Compose startup was not claimed. |

### Direct live schema evidence

The isolated test database reported PostgreSQL 16.15, pgvector 0.8.6, `embedding vector(1536)`, `search_vector tsvector`, the embedding provenance columns, the dimension check constraint, HNSW cosine index, GIN index, and `(workspace_id, source_id)` B-tree index.

### Live query-plan evidence

The integration `EXPLAIN` checks confirmed tenant predicates were applied. For the small controlled fixture, PostgreSQL chose `ix_document_chunks_workspace_source` for both representative plans rather than HNSW/GIN. This is recorded as `INDEX EXISTS` with `INDEX OBSERVED IN PLAN = NOT_OBSERVED`, consistent with PostgreSQL's cost-based planner behavior on tiny tables.

### Additional live verification notes

The first live test run exposed and fixed a module-scoped async engine/event-loop fixture defect; the final five-test run passed. The first evaluation run exposed and fixed missing Alembic bootstrap in `evals/retrieval_runner.py`; the subsequent run correctly stopped at unavailable genuine embeddings. The benchmark suite completed with **12/15** scenarios and three existing scenario failures; factual/citation/hallucination metrics remained `NOT_MEASURED`.

### Resumed live verification (latest run)

`docker --version` returned 29.7.2 and `docker compose version` returned v5.5.0. The Docker daemon was initially stopped; `docker desktop start` started it successfully, after which `docker info` reported the Docker Desktop server. `docker compose up -d postgres` reported the existing `pgvector/pgvector:pg16` container healthy, and `pg_isready` returned `accepting connections`. Direct PostgreSQL checks again returned PostgreSQL 16.15 and `vector` 0.8.6. The complete live integration suite was rerun: **5 passed in 7.96s**, with no skips.

The resumed `docker compose build` again began successfully and used cached backend layers, but the frontend context transfer reached approximately 409 MB and was stopped after it stalled. Therefore Docker image build and full-stack smoke verification remain **NOT_VERIFIED**. No semantic evaluation metrics were produced because the configured genuine embedding provider remains unavailable.
