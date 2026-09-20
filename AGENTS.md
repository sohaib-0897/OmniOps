# OmniOps Codex Handoff

Read this file before changing code. It records the repository state for a fresh Codex chat.

## Repository

- Backend: FastAPI, async SQLAlchemy, PostgreSQL/pgvector, and Alembic.
- Frontend: Next.js App Router, TypeScript, and Tailwind.
- Local services: PostgreSQL, backend, frontend, and a dedicated sandbox runner.
- `audit.md` is historical and must remain untouched.
- The working tree contains extensive user and Phase 4-6 changes. Preserve all unrelated changes and never use broad reset/checkout cleanup.

## Verified foundation

- Phase 1: VERIFIED, 15/15; quality metrics remain `NOT_MEASURED`.
- Phase 2: PostgreSQL retrieval is verified 5/5. The separate semantic embedding evaluation remains `BLOCKED` because a compatible configured embedding credential is unavailable.
- Phase 3: VERIFIED. Durable runtime, persisted events, leases, fencing, recovery, cancellation, retry idempotency, and PostgreSQL concurrency behavior are preserved.
- Phase 4: VERIFIED. Production backend has no Docker socket; execution uses the authenticated remote sandbox runner and fails closed. SSRF and untrusted-source controls are preserved.
- Phase 5: VERIFIED. Tesseract OCR, genuine Gemini vision/transcription/timestamps/diarization, provenance, retrieval, and evidence lineage are preserved.
- Frontend overhaul: complete and desktop-verified. Do not redesign it.

## Phase 6 closure: VERIFIED; next task is Phase 7 adversarial audit

Phase 6 final closure is VERIFIED after fresh regression, production-mode multi-worker/restart/backpressure, live auth/rate-limit, migration, performance, and final-image scan evidence. See `PHASE_6_REMEDIATION.md` under Final Closure Verification and the `phase6-*-evidence.json` / SARIF artifacts. Do not add more Phase 6 architecture. The next requested phase is Phase 7 adversarial audit; no Phase 7 findings are claimed here.

### Implemented

- Access JWT lifetime is 15 minutes with `sub`, `sid`, `jti`, `iat`, `exp`, and `typ`.
- Durable `UserSession`, hashed opaque `RefreshToken`, and database `RateLimitBucket` models.
- Refresh rotation and replay-family revocation; current-session and all-session logout.
- HttpOnly refresh cookie and memory-only frontend access token; localStorage auth removed.
- Origin validation for cookie refresh/logout; production secure-cookie and explicit HTTPS CORS validation.
- Fetch-based SSE with Authorization header; query bearer tokens removed.
- PostgreSQL `RuntimeEvent` replay through `Last-Event-ID`/cursor.
- Local SSE queues bounded at 100 with no in-memory replay history.
- Database rate limits for login, registration, refresh, upload, and investigation creation.
- Upload/parser limits for bytes, workspace storage, PDF pages, image pixels, audio duration, DOCX paragraphs, extracted text, OOXML expansion, traversal, and macros.
- Production config fails closed for missing/weak secrets, non-PostgreSQL DB, invalid origins/cookies, or missing remote runner settings.
- JSON request logs, request correlation, safe errors, Prometheus-format per-process metrics, liveness, and truthful readiness.
- Bounded production DB pool and separate Alembic migration step.
- Migration head: `20260911_phase6_sessions`.
- Multi-stage Dockerfiles, non-root application users, healthchecks, small contexts, and `docker-compose.prod.yml`.
- CI, live-provider, and release workflows under `.github/workflows`.
- `OPERATIONS.md`, `PHASE_6_REMEDIATION.md`, and qualified README claims.
- Frontend audit fixed to zero vulnerabilities; backend requirements audit reported none.

### Completed evidence

- Phase 1: 15/15.
- Phase 3 PostgreSQL: 27 passed.
- Phase 4 security including existing adversarial/sandbox/SSRF modules: 71 passed, 0 skipped (16.64 s).
- Phase 5 deterministic: 27 passed.
- PostgreSQL retrieval: 5/5.
- Phase 6 focused: 13 passed, 0 failed, 0 skipped (3.92 s).
- Backend full: 178 passed, 0 failed, 0 skipped with PostgreSQL enabled (73.04 s).
- Frontend TypeScript, lint, build, and npm audit: PASS; 0 vulnerabilities.
- Alembic live upgrade, downgrade one revision, re-upgrade, and head check: PASS.
- Production Compose config validation: PASS.
- Backend image context about 978 KB; frontend context about 466 KB.
- Backend/frontend use UID/GID 10001; sandbox payload uses 65532.
- All four images built. The runner remains root as the isolated Docker control plane; the backend has no Docker socket.
- Hardened frontend container served HTTP 200 with security headers on port 13000.

### Final closure evidence

- Both production-mode replicas individually ready on loopback ports 18001/18002; frontend on 13000, separate worker and authenticated runner, persistent test storage. Inspect existing `omniops-phase6-*` containers before changing them.
- Fourteen PostgreSQL events replayed across A/B; A was SIGKILLed with an SSE connection open and restarted, with exact event-history preservation. Six reconnect cycles and the actual frontend hook dedupe probe passed.
- Fixed demonstrated SSE pool exhaustion by releasing DB connections between 500-event batches. Ten held streams no longer block ordinary reads. A 2,000-event slow HTTP client replayed everything; local broadcaster remains capped at 100.
- Real worker killed before attempt commit; rollback/restart recovered work and failed closed without invented evidence. Fresh Phase 3 PostgreSQL regression separately verifies committed-lease fencing/idempotency.
- Refresh replay family revocation, cross-worker rate limits, expiry/reconnect, and dependency-failure readiness were live-tested. JSON request/audit events confirmed without credential patterns.
- Docker Scout final counts: backend/sandbox/runner each 0 critical, 5 high, 13 medium, 80 low; frontend 0 in every severity after compatible OpenSSL update and unused npm-runtime removal. Every critical/high finding is reviewed in remediation documentation; do not hide accepted residuals.
- Initial restricted Docker Scout commands falsely appeared blocked on login; approved Docker access worked. Windows subprocess capture must decode Scout output as UTF-8.
- All final images built and smoke passed. CI configuration VERIFIED LOCALLY; GitHub-hosted run NOT_RUN. Production external runner host/TLS ingress remain not live-deployed.

## Security boundaries and truthful limitations

- Never fabricate metrics, evidence, provider output, transcripts, timestamps, speakers, OCR, or semantic results.
- Preserve deterministic validation, seven-stage lineage, PostgreSQL pgvector/FTS/RRF, SQL tenant filters, and explicit provider failures.
- Never add a production Docker socket to the backend or an insecure sandbox fallback.
- Production web retrieval must use the centralized SSRF-safe fetcher.
- Never log or commit keys, Authorization headers, cookies, refresh tokens, signed URLs, or provider payloads.
- Malware scanning is `DEPLOYMENT_CONTROL`, not implemented.
- PostgreSQL RLS is not enabled. Application SQL filtering is authoritative because pooled transactions do not set transaction-scoped tenant identity.
- Metrics are per process, not a shared aggregation system.
- TLS/HSTS termination is external.
- Do not alter the Phase 2 provider just to clear its blocked semantic evaluation.

## Useful commands

Run from repository root:

```powershell
git status --short
python -m pytest backend/tests/test_phase6_platform.py -q --disable-warnings
python -m pytest backend/tests -q --disable-warnings
python -m evals.runner
python -m evals.retrieval_runner
python -m pip_audit -r backend/requirements.txt

Set-Location frontend
npx tsc --noEmit
npm run lint
npm run build
npm audit
Set-Location ..

docker build -f docker/Dockerfile.backend -t omniops-backend:phase6 .
docker build -f docker/Dockerfile.frontend -t omniops-frontend:phase6 .
docker build -f docker/Dockerfile.sandbox --build-arg BACKEND_IMAGE=omniops-backend:phase6 -t omniops-python-sandbox:phase6 .
docker build -f docker/Dockerfile.sandbox-runner --build-arg BACKEND_IMAGE=omniops-backend:phase6 -t omniops-sandbox-runner:phase6 .
docker scout cves omniops-backend:phase6 --only-severity critical,high
docker scout cves omniops-frontend:phase6 --only-severity critical,high
```

Never print local `.env` values; report only safe presence/status.

## Working-tree rules

- Inspect before editing; preserve unrelated work.
- Use `apply_patch` for manual edits.
- Never use `git reset --hard`, `git checkout -- .`, or broad destructive cleanup.
- Do not modify `audit.md`.
- Do not claim verification from file existence when live execution is required.
- Record actual commands, counts, and limitations in remediation documentation.
