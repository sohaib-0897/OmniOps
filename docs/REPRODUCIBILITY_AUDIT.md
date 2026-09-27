# Fresh-checkout reproducibility audit — 2026-09-27

This record describes local verification of commit `a3ba482` with the documentation and small fixes in the current working tree copied into an ignored local clone. It is not a hosted CI result or a deployment certification. No existing OmniOps database was used for the checks below.

## Isolation and setup

- Cloned the repository into an ignored temporary directory. Copied the pending README, documentation, and screenshots into that checkout; then applied the dependency and evaluation-runner fixes there for verification.
- Created `.env` from `.env.example` with fresh random database, signing, and runner secrets. Values were not printed or committed. Used the documented local HTTP settings and an existing reachable Ollama `qwen3:4b` service.
- Used a copy of `docker-compose.ubuntu.yml` with project name `omniops-audit`, Caddy on loopback port `18080`, and distinct `:audit` image tags to avoid the already running stack. For host integration tests, the isolated PostgreSQL container additionally joined a non-internal test network and published loopback port `55434`. The application itself used Compose's private database network.
- `docker compose ... config --quiet` passed for both the original Ubuntu file and the isolated copy. A single `up --build` failed because Compose tried to resolve the sandbox images' backend base image before that image existed locally. Building `backend frontend` first, then `sandbox-image sandbox-runner`, then running `up --no-build -d` succeeded. The README now uses this sequence.
- The first clean backend image installed SQLAlchemy without `greenlet`, so its Alembic job failed before creating the schema. Declaring `sqlalchemy[asyncio]` in `backend/requirements.txt` fixed the fresh image; rebuild and startup succeeded.

## Database and application

- Created a dedicated `omniops_audit_test` database inside the isolated pgvector PostgreSQL 16 container. Alembic upgraded from an empty schema to `20260912_final_audit_closure`, downgraded one revision, and upgraded to head again.
- The separate application database was migrated by the Compose migration job. Backend, worker, frontend, PostgreSQL, and sandbox runner became healthy. `GET http://localhost:18080/api/v1/readiness` returned `ready` for database, pgvector, migrations, runner, and the configured Ollama provider.
- Through the fresh stack's API, registered a throwaway test account, created a workspace, uploaded authored fictional text now saved as the [fictional operating review](demo/fictional-operating-review.txt), waited for source state `ready`, and created an investigation. The worker completed it with a saved report and five claims. A direct query to the isolated application database found one investigation and one non-null saved report. This checks one text-ingestion and investigation path; it does not measure answer correctness or multimodal accuracy.
- The README screenshots are from a separate completed local PDF investigation, as stated beside them. Both PNG files are 1440 × 900 and contain no embedded metadata.

## Checks

| Check | Result |
| --- | --- |
| Fresh Python 3.12 virtual environment; `pip install -r backend/requirements.txt`; `pip check` | Installed; no broken requirements after the asyncio extra fix |
| `python -m pip_audit -r backend/requirements.txt` | No known vulnerabilities reported; the audit emitted cache deserialization warnings before completing |
| Fresh `npm ci`; `npm audit --audit-level=high` | Installed; 0 reported vulnerabilities |
| Backend `python -m pytest tests -q --disable-warnings` in `backend/`, with `POSTGRES_TEST_DATABASE_URL` pointing only to the isolated test database | 245 passed, 0 failed, 0 skipped; 3 warnings |
| Frontend `node --test ../scripts/ui_frontend_tests.cjs`, `npx tsc --noEmit`, `npm run lint`, `npm run build` | 41 passed; typecheck, lint, and build passed |
| `python -m evals.runner` with the local Docker sandbox image | 15/15 authored deterministic scenarios passed. Factual precision, citation precision, and hallucination rate are `NOT_MEASURED`. |
| Same evaluation with the runner unavailable | 14/15 and exit code 1 after the evaluation-runner fix; a failed scenario now fails CI. |
| `python -m evals.retrieval_runner` with the isolated database but no embedding credential | `NOT_RUN (EMBEDDING_PROVIDER_UNAVAILABLE)`, exit code 1 |

The first attempts to run temporary-file tests inside the restricted Windows command sandbox produced permission errors. The test and evaluation runs above were repeated with access to the isolated checkout's temporary directory. No resulting test skip or failure was treated as a pass.

## CI, documentation, and hygiene

- CI now sets `POSTGRES_TEST_DATABASE_URL` for its full backend suite, so database tests are included once in the main result. It also runs the 41 frontend tests. The three workflow files parsed locally as YAML; no GitHub-hosted run was observed.
- Relative Markdown links in the tracked documentation and pending README were checked locally. The audit found no missing target after this document was added.
- Scanned 416 tracked files for common private-key, provider-key, GitHub-token, and AWS-key patterns: no matches. No `.env`, database, dump, cache, build output, or private key was tracked. The screenshot files were inspected visually and for metadata. This is a limited signature scan, not a full secret-history audit.
- There is no project license. Python requirements use lower bounds without a lockfile; future dependency resolution can change the installed set. The hosted-provider multimodal path, semantic retrieval quality, cloud TLS ingress, and an external rootless runner were not validated by this local audit.
