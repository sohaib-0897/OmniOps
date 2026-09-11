# Phase 6 Production Hardening

## 1. Production Architecture

The vendor-neutral production reference separates immutable frontend/backend images, a one-shot migration job, managed PostgreSQL/pgvector, durable shared file storage, HTTPS ingress, and an authenticated external sandbox runner. Development Docker-socket execution remains isolated in `docker-compose.dev.yml`.

## 2. Authentication & Session Model

Access JWTs last 15 minutes and contain `sub`, `sid`, `jti`, `iat`, `exp`, and `typ`. Each access request validates the durable session. A 30-day opaque refresh credential is stored only in an HttpOnly cookie; only its SHA-256 secret hash is persisted. Refresh rotates transactionally. Reuse of a consumed token revokes the complete session token family. Logout revokes the current session; logout-all revokes every user session. Passwords use bcrypt cost 12 and inputs are bounded to bcrypt's 72-byte limit.

## 3. Browser Security

Access tokens are held only in JS memory; refresh credentials use HttpOnly cookies with Secure required in production, a restricted auth path, and SameSite Lax/Strict. SameSite plus explicit production origins is the CSRF boundary. API and frontend security headers are configured. No `dangerouslySetInnerHTML` or HTML/markdown renderer is used for source/report content; React renders it as text.

## 4. SSE / Event Delivery

The bearer query parameter was removed. The browser uses fetch streaming with an Authorization header. Runtime events remain authoritative in PostgreSQL. Every connection polls the persisted event cursor, sends SSE `id`, accepts `Last-Event-ID`, and deduplicates client-side. This survives web-worker changes and process restarts without an unbounded process-local replay queue.

## 5. Rate Limiting

Database-backed fixed windows protect login by IP and account hash, registration by IP, refresh by IP, uploads by workspace, and investigation/provider-triggering creation by user and workspace. PostgreSQL advisory transaction locks serialize shared-worker counters. This is an abuse guard, not a billing system; deployments may add edge controls.

## 6. Tenant Isolation

Workspace membership remains mandatory, child resources are filtered by both workspace and identifier, and retrieval filters workspace inside SQL. PostgreSQL RLS is not enabled because pooled connections do not establish a transaction-scoped tenant identity; application-layer filtering and adversarial route tests remain authoritative.

## 7. File / Parser Security

Uploads are streamed with a 50 MiB limit, magic validation, sanitized names, workspace quota, PDF page/pixel/audio duration/extracted-text bounds, DOCX paragraph/text bounds, and Office archive expansion/path/macro checks. Arbitrary archives are unsupported. Malware scanning is `DEPLOYMENT_CONTROL`, not a built-in claim. Parser concurrency is bounded per worker/deployment resources; provider and OCR calls retain their explicit timeout/failure semantics.

## 8. Secrets & Configuration

Production validates PostgreSQL, strong explicit JWT secret, secure cookies, explicit CORS origins, and remote authenticated sandbox settings. Development-only defaults do not pass production validation. Request logs exclude headers, cookies, tokens, source content, and provider payloads.

## 9. Observability

Every response carries `X-Request-ID`; structured request logs contain method, route, status, duration, and correlation ID. Prometheus text metrics expose request counts/latency sums and active SSE connections without fabricated success ratios. Liveness is dependency-free; readiness checks database, pgvector in PostgreSQL, and the required remote runner.

## 10. Database Operations

Production uses bounded pre-ping pools (5 base, 5 overflow, 30-second timeout, 30-minute recycle). Migrations are a separate release job rather than application startup. Backup, restore, retention, rollback, and object consistency procedures are in `OPERATIONS.md`.

## 11. Dependency Security

CI runs `pip-audit` and `npm audit --audit-level=high`. Local findings and container-scan status are recorded under Test Results; unresolved findings are never silently suppressed.

## 12. Docker Hardening

Backend and frontend use multi-stage builds and UID/GID 10001, healthchecks, reduced contexts, read-only production roots, bounded tmpfs, and resource guidance. The runner control plane necessarily retains its isolated Docker-host privilege and must be separately protected/rootless where possible.

## 13. CI/CD

PR CI defines PostgreSQL migrations, full backend tests, Phase 1 evaluation, deterministic retrieval metrics and PostgreSQL retrieval tests, frontend type/lint/build, dependency audits, migration downgrade/upgrade, and all production image builds. The manual/scheduled provider workflow currently executes deterministic provider contract tests, not a live paid-provider smoke. The separate semantic embedding evaluation requires its own compatible credential and is not silently treated as a passing PR check. Release packaging publishes immutable SHA images; deployment remains platform-specific. CI configuration is verified locally; GitHub-hosted execution was not run in this pass.

## 14. Production Deployment Model

Use `docker-compose.prod.yml` as the topology reference with externally injected secrets, managed PostgreSQL, persistent storage, external runner, two backend replicas, and HTTPS termination. It intentionally does not invent a cloud destination.

## 15. Failure Tests

Targeted tests cover expiry, rotation, replay revocation, logout, malformed tokens, rate limiting, CORS/headers, secret validation, SSE auth contract/replay logic, tenant IDOR paths, and upload bounds. Earlier phase failure suites cover worker recovery, sandbox unavailability, SSRF, and provider fail-closed behavior.

## 16. Test Results

Phase 6 classification: **VERIFIED**. Fresh closure evidence is recorded below. All four final images were scanned successfully; the frontend's critical findings were remediated and rescanned to zero findings. Five high advisory entries remain in each Python-based image and are explicitly reviewed as residual risks below. VERIFIED describes the requested local closure gates, not a live production deployment.

## 17. Remaining Limitations

Malware scanning is a deployment control. S3-compatible storage and PostgreSQL RLS are not implemented. TLS/HSTS require the external HTTPS edge. Phase 2 live semantic evaluation still depends on a compatible configured embedding credential. Container scans completed; residual high/medium/low findings are recorded without suppression below.

# Final Closure Verification

## Regression Evidence

Executed on the current tree during the 2026-09-08 local closure pass. The Docker host clock reports UTC dates on 2026-09-07 for this session; no performance timestamp has been invented.

| Gate | Fresh result | Duration |
| --- | --- | --- |
| Phase 6 targeted | 13 passed, 0 failed, 0 skipped | 3.92 s |
| Entire backend, real PostgreSQL configured | 178 passed, 0 failed, 0 skipped | 73.04 s |
| Phase 1 deterministic evaluation | 15/15 passed; quality metrics NOT_MEASURED | mean scenario 108.1 ms |
| Phase 3 durable runtime, including PostgreSQL concurrency/closure | 27 passed, 0 failed, 0 skipped | 14.37 s |
| Phase 4 security, including existing sandbox/SSRF/adversarial tests | 71 passed, 0 failed, 0 skipped | 16.64 s |
| Phase 5 deterministic multimodal and provider contracts | 27 passed, 0 failed, 0 skipped | 4.19 s |
| PostgreSQL pgvector/FTS/RRF regression | 5 passed, 0 failed, 0 skipped | 17.84 s |
| Frontend TypeScript / lint / production build | PASS / PASS / PASS | build compiled in 8.6 s; complete command exited 0 |
| npm audit | `found 0 vulnerabilities`, exit 0 | not separately timed |
| pip-audit, backend requirements | `No known vulnerabilities found`, exit 0 | not separately timed |
| CI deterministic retrieval-metrics command | 1 passed | 0.04 s |

Commands: `python -m pytest backend/tests/test_phase6_platform.py -q --disable-warnings -ra`; `python -m pytest backend/tests -q --disable-warnings -ra` with `POSTGRES_TEST_DATABASE_URL` pointing to the dedicated `omniops_phase2_test` database; `python -m evals.runner`; the five `test_phase3_*` modules named in CI; `test_phase4_sandbox_security.py`, `test_phase4_ssrf_policy.py`, `test_phase4_runner_boundary.py`, `test_python_sandbox.py`, `test_ssrf.py`, `test_adversarial_security.py`; both Phase 5 modules; `test_postgres_hybrid_retrieval.py`. Frontend commands were `npx tsc --noEmit`, `npm run lint`, `npm run build`, `npm audit`; backend dependency command was `python -m pip_audit -r backend/requirements.txt`.

The initial no-PostgreSQL-URL rerun had 164 passed and 11 skipped in 46.77 s. Every skip was inspected: four Phase 3 closure cases, two Phase 3 live concurrency cases, and five PostgreSQL retrieval cases were intentionally environment-dependent. None were optional-provider or unsupported-platform skips. These required cases were subsequently executed successfully with the database configured; **the final full run has no skipped tests**. Earlier numbers before the closure fixes are superseded by the table above.

Concrete failures and minimal corrections:

- Ten open SSE connections retained all ten pool slots, causing an unrelated authenticated read to return 500 after 30,065.97 ms. The stream now closes the authorization transaction and each materialized event-batch transaction before yielding to the client. PostgreSQL remains the authoritative replay source; batch size remains 500.
- An event cursor outside the authorized investigation previously returned 200 and reset replay. It now returns a scoped 404 without disclosing foreign event metadata.
- The worker inherited the web image's HTTP healthcheck and was marked unhealthy despite having no HTTP listener. Production Compose now checks the worker process identity. This is process liveness, not a claim of job-progress monitoring.
- Container logs did not emit INFO-level structured request events under the default logging configuration. The dedicated JSON request logger now has an INFO handler, and committed refresh-family replay revocation emits a credential-free audit event.
- The PR workflow invoked `evals.retrieval_runner` without its required database/provider configuration; local reproduction returned NOT_RUN/nonzero. That invalid unconditional invocation was replaced with the deterministic retrieval-metrics test. PostgreSQL retrieval tests remain required. The independent Phase 2 semantic credential blocker remains unchanged.

## Multi-Worker SSE

`scripts/phase6_topology.py` created production-mode containers without the development Compose override, sharing `omniops_phase6_closure_test` and the persistent volume `omniops_phase6_closure_storage`. PostgreSQL is `omniops-postgres` on the isolated local Docker network; migration job `omniops-phase6-migrate` exited 0. Backend A is `omniops-phase6-a` (`290b7d9baaf8`, direct port 18001); B is `omniops-phase6-b` (`e412e007db0f`, direct port 18002); worker is `omniops-phase6-worker` (`cf12f5a13811`). Both backend replicas and worker run production validation, Secure cookies, explicit HTTPS origins, read-only roots, bounded pools/resources, and UID/GID 10001. Their only bind/volume destination is `/app/storage`; **neither backend nor worker has a Docker socket**.

Both replicas independently returned ready with database, pgvector, migration head, and external runner checks passing. Provider-dependent capabilities correctly reported unavailable when no credentials were injected. These closure tests intentionally incurred no provider spend.

Final replay fixture: workspace `c3b4ba44-7205-4569-b692-3432c9a32f6a`, investigation `773213de-b548-4377-805f-ac2e300cb508`. Creation used the production authenticated API on A. PostgreSQL contained its actual creation/failure events plus twelve explicitly labeled deterministic `closure.probe` fixture events. This is replay infrastructure evidence, not a fabricated successful investigation. The complete ordered list of fourteen event IDs is in `phase6-live-evidence.json`.

A received the first three IDs and disconnected at `9351c88d-0c44-4659-b6d8-812e8e79790b`. B received `Last-Event-ID` and replayed the remaining eleven in exact PostgreSQL `(created_at, id)` order: no missing IDs, no duplicate IDs. A second authenticated SSE connection was explicitly held open on A during `docker kill`; its client observed `RemoteProtocolError`. The investigation remained accessible and the same suffix replayed through B. After `docker start`, A returned ready and replayed from the old cursor. PostgreSQL history was exactly unchanged across the kill/restart. No prior subscriber memory was required.

Six rapid reconnect cycles across A/B retained fourteen logically unique events after ID dedupe. The actual frontend hook was also executed by `node scripts/phase6_frontend_dedupe.cjs` with controlled REST hydration, replay, and reconnect inputs: two transport connections, three unique timeline entries, one step, one evidence item. This is hook-state testing, not browser DOM/TLS deployment testing.

User B accessing A's stream returned 403; guessed investigation returned 404; foreign/guessed workspace mutations returned 403. A's cursor against B's own investigation returned 404. Responses contained no fixture event IDs. Access was always carried in the Authorization header, never a query string.

The real `app.worker` process was killed while a temporary test-only PostgreSQL trigger paused an attempt insert before commit. The delay trigger/function was removed afterward. The worker claim was still uncommitted, so PostgreSQL rollback made it recoverable immediately. The restarted worker reclaimed the same investigation, committed one attempt, and failed closed with `EVIDENCE_NOT_FOUND`; evidence, calculation, and verified-claim counts were all zero, with no fabricated completion. Committed-lease expiry, takeover, stale-worker fencing, and nonzero domain-idempotency cases are separately covered by the fresh 27-test PostgreSQL Phase 3 regression. This fault probe does not claim a completed paid-provider investigation or that it waited out a committed lease.

## Backpressure

The local broadcaster caps each queue at 100 and retains no replay history. A 1,000-emission probe left the slow queue exactly at 100 and detached it, while the fast client consumed all 1,000 events. The HTTP stream does not consume that local queue: it polls PostgreSQL in batches of at most 500 and releases its DB connection before network delivery or delay. Persisted events remain available on reconnect.

A real HTTP client deliberately read no response body while 2,000 events of 32,768 payload bytes each were committed. A's RSS samples were 242,596, 259,452, 259,468, and 259,476 KiB. After the first blocked sample, observed growth was 24 KiB. Unrelated authenticated reads stayed at 200. Disconnecting that slow client and replaying through B recovered all 2,000 IDs in order, with zero missing/duplicate IDs. This demonstrates bounded behavior for the tested workload, not a universal byte-memory bound for arbitrary event sizes or infinite-duration load.

## Auth / Rate Limit Live Verification

Production login and two normal refresh rotations succeeded across A/B. Reusing R1 returned 401, R2 then returned 401, and the rotated access token returned 401. PostgreSQL confirmed session revocation. Cookies retained Secure and HttpOnly attributes. The test client supplied the cookie explicitly over loopback HTTP, as a non-browser protocol probe; production browser TLS termination remains external and was not weakened.

A test-only two-second access JWT for a real durable session exercised expiry without changing the production 15-minute lifetime. An already accepted stream continued; a new connection with the expired bearer returned 401. A normally refreshed bearer reconnected successfully. No refresh credential entered query strings or persistent JS storage.

Alternating login requests across A/B hit the shared 10-per-300-second limit: after one valid login, nine invalid attempts returned 401 and subsequent attempts returned 429, with Retry-After 298 seconds at observation. Investigation creation hit the shared 20-per-hour user limit: twelve prior requests plus eight allowed alternating requests, then twelve 429 responses; observed Retry-After 3,570 seconds. No limiter threshold was weakened. The repeatable harness resets buckets only in its dedicated closure database before each complete test run. Final container-log inspection confirmed structured request events and `auth.refresh_replay` events, with no bearer/cookie/JWT credential patterns found; session identifiers and request correlation are recorded without token contents.

Stopping only `omniops-phase6-runner` produced health 200 and readiness 503 with `sandbox_runner=unavailable`. After restart, readiness returned ready. Database, pgvector, and migration checks remained truthful.

## Performance Sanity

**LOCAL PRODUCTION-LIKE SANITY OBSERVATION** — Windows host with Docker Desktop Linux containers, local PostgreSQL/pgvector, two production-mode backends limited to 2 CPUs/2 GiB each, and other local services running. These are modest observations, not a production benchmark or capacity projection.

| Probe | Observation |
| --- | --- |
| Authenticated `/auth/me` reads | 100 requests, concurrency 10, median 39.32 ms, p95 384.98 ms, 0 errors |
| Ten held SSE streams on A plus unrelated read | HTTP 200 in 15.50 ms after the pool fix |
| Concurrent SSE | 20/20 successful, 0 failed; connections split across A/B |
| Reconnect | Six cross-replica cycles, no logical duplicates after ID dedupe |
| Five concurrent idempotent submissions | 5 accepted, 0 throttled, one authoritative investigation ID |
| Five concurrent distinct small investigations | 5 accepted, 0 throttled, five unique IDs; all failed closed with LLM_PROVIDER_REQUIRED, no provider spend |
| DB after load | 11 idle connections across the stack, one active observer query, 0 idle transactions; normal read 200 |

Pool bounds remained 5 base + 5 overflow per backend, 30-second timeout. The pre-fix pool saturation failure was controlled but unacceptable; after correction, open streams no longer monopolized connections and normal reads recovered without restarts. No connection leak was observed in this bounded test.

## Container Scan

Docker Scout completed successfully for all four final images. Initial restricted-environment attempts requested login; the approved Docker environment could scan. A Windows cp1252 decoding failure in the collector was corrected to UTF-8, then all scans completed with exit 0. `phase6-container-evidence.json` and the four `phase6-omniops-*-scout.sarif` files retain actual final results. Counts below are Scout SARIF advisory rules per image, not distinct underlying bugs or a sum of duplicated base-image occurrences.

| Final image | Critical | High | Medium | Low |
| --- | ---: | ---: | ---: | ---: |
| backend | 0 | 5 | 13 | 80 |
| frontend | 0 | 0 | 0 | 0 |
| sandbox | 0 | 5 | 13 | 80 |
| sandbox-runner | 0 | 5 | 13 | 80 |

The pre-remediation frontend scan had 3 critical, 16 high, 8 medium, 1 low advisory rules (one high advisory matched two installed pacote versions). Its original SARIF and full triage inventory are preserved in `phase6-frontend-before-remediation.sarif` and `phase6-container-before-remediation.json`. The final runtime upgrades only Alpine libssl3/libcrypto3 from 3.5.7-r0 to 3.5.8-r0 and removes the unused global npm installer and its dependencies. It keeps the same Node/Next.js architecture and non-root identity. The standalone frontend rebuilt, started healthy, and served 200 after remediation. The compatible OpenSSL release is listed by [Alpine's package repository](https://dl-cdn.alpinelinux.org/alpine/latest-stable/main/x86_64/).

### Every original critical/high finding: decision

| Image / package | Advisory IDs | Reachability / exploit assessment | Fix and disposition |
| --- | --- | --- | --- |
| Frontend OpenSSL 3.5.7-r0 | Critical: CVE-2026-75803, CVE-2026-63073. High: CVE-2026-14456, CVE-2026-14457, CVE-2026-18798, CVE-2026-54874, CVE-2026-63072, CVE-2026-63075, CVE-2026-63076 | Installed crypto libraries; exact exploit prerequisites were not established, so findings were treated conservatively as requiring remediation. | Compatible distro 3.5.8-r0 update applied; all absent from final scan. |
| Frontend npm-bundled tar 7.5.11 | Critical CVE-2026-59873; high CVE-2026-73566, CVE-2026-59874 | Archive parser/replace/list functionality belongs to the global installer, not the standalone app. No frontend untrusted archive-extraction endpoint invokes it. | Upstream fixed versions reported as 7.5.19 / 7.5.21 / 7.5.18. Entire unused npm runtime tree removed; findings absent. |
| Frontend npm-bundled brace-expansion 2.0.2 | CVE-2026-14257, CVE-2026-69152, CVE-2026-13149 | Requires attacker-controlled glob expressions reaching installer glob expansion; production app does not call that installer. | Compatible 2.x fixes are indicated by affected ranges (2.1.3 / 2.1.4 / 2.1.2; Scout's first preferred fix also names 5.0.8). Runtime npm tree removed; findings absent. |
| Frontend npm-bundled picomatch 4.0.3 | CVE-2026-33671 | Requires malicious glob patterns in this installer dependency, not a production app input path. | 4.0.4 reported fixed; installer removed. |
| Frontend npm-bundled sigstore 3.1.0 | CVE-2026-48815 | Requires certificateOID verification policy in installer artifact verification; no such app API exists. | 4.1.1 reported fixed; installer removed instead of imposing a major transitive upgrade. |
| Frontend npm-bundled ip-address 10.1.0 | CVE-2026-69192 | No production SSRF trust decision uses this global npm package; backend uses its separate SSRF-safe fetcher. | 10.3.1 reported fixed; installer removed. |
| Frontend npm-bundled pacote 19.0.2 and 20.0.1 | CVE-2026-9496 | Malicious git package spec reaches installer package resolution, which does not run on application requests. | 21.5.1 reported fixed; both bundled copies removed with npm. |
| Backend, sandbox, runner: pip-vendored msgpack 1.1.2 | CVE-2026-57585 and GHSA-6v7p-g79w-8964 (same underlying issue) | Scout locates these through pip's bundled SBOM. Vendor package exists, but production routes do not invoke pip or reuse a streaming Unpacker on untrusted data. Sandbox import policy excludes it. No reachable application exploit identified. | Scout reports 1.2.1. A standalone msgpack install would not update pip's private copy; a compatible pip vendor refresh is the appropriate future maintenance path. Retained as two unsuppressed high scan entries, accepted for this runtime scope. |
| Backend, sandbox, runner: setuptools 70.3.0 attribution in pip SBOM | CVE-2025-47273 | Inspection found pip's pkg_resources, but no vendored setuptools directory or package_index.py. The vulnerable PackageIndex downloader is not in that vendor tree; no runtime package installation path exists. | Full setuptools >=78.1.1 fixes the upstream package; replacing a standalone setuptools would not change the SBOM attribution. Accepted as non-reachable vendor attribution; scan entry retained. |
| Backend, sandbox, runner: Debian libxml2 2.12.7+dfsg+really2.9.14-2.1+deb13u3 | CVE-2026-86140 | Specific fault is xmlSnprintfElements validation formatting. No application DTD-validation path was found; Python lxml uses its own reported 2.14.6 library. XML parsing is still part of ingestion, so complete native-parser unreachability is not claimed. Potential parser exposure remains an accepted high residual. | Debian trixie has no fixed compatible package; upstream 2.15.4/sid has a fix. Do not mix unstable system libraries into the verified image. Retain parser limits/non-root execution and revisit on a stable security update. |
| Backend, sandbox, runner: Debian zlib 1:1.3.dfsg+really1.3.1-1 | CVE-2026-85091 | Specific fault requires nonblocking gzwrite stall followed by gzprintf/gzvprintf with stale buffers. No such application call path was found. Presence of compression code alone is not proof of exploitation; entry remains unsuppressed. | Debian reports no fixed package. No compatible update applied; accepted high residual with future distro security-update review. |

Upstream references used for this assessment: [msgpack maintainer advisory](https://github.com/msgpack/msgpack-python/security/advisories/GHSA-6v7p-g79w-8964), [setuptools maintainer advisory](https://github.com/pypa/setuptools/security/advisories/GHSA-5rjg-fvgr-3xxf), [Debian libxml2 tracker](https://security-tracker.debian.org/tracker/CVE-2026-86140), and [Debian zlib tracker](https://security-tracker.debian.org/tracker/CVE-2026-85091). No finding has been hidden, and no known exploitable critical finding remains in the final scan.

Backend, sandbox, and runner were rebuilt after the final backend change; frontend also rebuilt successfully. Backend image ID: `sha256:f4e0c77ee4e0ef177566b7d031e10843dc37bd387317f8e2b817645f03fee5e9`; frontend: `sha256:dfcd2913de73b5a61289c71ff5d7765b7a24b9eb4e4843d62c1972facb985087`; sandbox: `sha256:25a13230a2c1021a36a5128affacbb98a8f706831803103c93f8769a5688ef38`; runner: `sha256:d20a503c34ab6c9dd8186923743931857b657f4e987ccb65189e5e4f8e1c3363`. Final frontend container is `844f207b2184`; external runner is `a77ea8c1ae3c`. `phase6-final-smoke.json` confirms all five application/control containers healthy, both backend readiness responses 200, frontend 200, and actual authenticated external sandbox execution of `1 + 1` returning `2`.

Backend/frontend/worker run as UID/GID 10001; an executed sandbox-image process reported UID 65532. The local dedicated runner runs as root with a Docker socket. It is an external authenticated local control plane, **not proof of a production-safe isolated/rootless runner host**. Actual production deployment must retain that external host boundary.

## Migration, CI and Static Security Review

`scripts/phase6_migration_check.py` created clean database `omniops_phase6_migration_test_bc6cd7a1`, ran upgrade head, current, downgrade -1, upgrade head, current, then the production readiness handler against that schema. Every command exited 0; both head checks reported `20260911_phase6_sessions`; schema-dependent readiness passed. Details are in `phase6-migration-evidence.json`.

All three workflow YAML files parsed successfully; command paths, PostgreSQL readiness options, scoped test credentials, scripts, and PR-secret exposure were reviewed. PR CI uses test secrets only; the provider workflow is manual/scheduled with a protected environment, and the release workflow is manual. Equivalent local regression, build, audit, and migration commands passed. **CI configuration: VERIFIED LOCALLY. GitHub-hosted run: NOT_RUN.** The provider contract workflow is not evidence of live provider availability.

The requested production-path security search is retained in `phase6-static-security.txt`. Matches were reviewed: `create_all` is restricted to SQLite development, whose production configuration is rejected; wildcard CORS fallback cannot pass production validation; Docker socket access is isolated to the external runner implementation/development overlay; `token=` matches are cookie/response construction or environment-variable names, not query authentication. `placeholder` matches are HTML input hints, SQL bind-parameter construction, and the SQLite tsvector stand-in. Test mock/fake fixtures are not production provider outputs. No production `localStorage`, query bearer URL, `verify=False`, `debug=True`, `Math.random`, or fake-result fallback was found. README, operations, and frontend copy do not claim RLS, built-in malware scanning, unlimited scalability, live deployment, or benchmark capacity. Stale README test counts were removed/corrected. `audit.md` was not modified.

## Remaining Limitations

- No remaining Phase 6 closure blocker. Five high advisory entries per Python image remain explicitly accepted residual risks with the package-specific assessment above; medium/low counts are not suppressed. A newly demonstrated exploitable critical vulnerability would invalidate VERIFIED.
- PostgreSQL RLS is not implemented; tested application SQL tenant enforcement remains authoritative.
- Malware scanning is a deployment control, not built in.
- The production external isolated/rootless runner host and browser-facing TLS/HSTS ingress were not live-deployed in this local test.
- Provider capabilities were unavailable by design in the closure stack. The independent Phase 2 compatible semantic embedding credential blocker remains unchanged and is not itself a Phase 6 blocker.
- Metrics are per process. Local timing/RSS observations do not establish production capacity. Browser DOM rendering and GitHub-hosted execution were not claimed.

### Final security evidence table

| Control | Evidence / status |
| --- | --- |
| Sessions and refresh-family replay | Live A/B rotation and replay rejection PASS; DB revocation checked |
| Shared abuse limits | Alternating A/B login and investigation requests reached DB limits PASS |
| Tenant SSE and cursor isolation | 403/404 with no event-ID metadata leakage PASS |
| Durable replay and restart | Exact PostgreSQL sequence across A/B and killed/restarted A PASS |
| Backpressure / pool isolation | 100-entry local queue; 500-row DB batches; 2,000-event slow HTTP replay PASS |
| Worker rollback/recovery | Actual process kill, transaction rollback, restarted reclaim, truthful failure PASS |
| Liveness vs readiness | Runner outage: 200 vs 503; recovery PASS |
| Non-root payload/application processes | UID 10001 applications; UID 65532 sandbox PASS |
| Container vulnerabilities | All four scans complete; 0 critical; frontend 0 findings; Python images each 5 high / 13 medium / 80 low, reviewed residuals |
| Dependency package audits | npm 0 vulnerabilities; pip-audit no known vulnerabilities |
| Production deployment | NOT_DEPLOYED; local socket-bearing runner not production-safe proof |
