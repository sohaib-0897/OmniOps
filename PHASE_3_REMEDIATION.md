# OmniOps Phase 3 Remediation

## Starting architecture

The existing runtime was bounded in intent but not durable in execution. `AgentOrchestrator.run()` owned catalog discovery, provider planning, tool selection, tool dispatch, evidence creation, verification, synthesis, and SSE emission in one linear loop. Tool dispatch was a central `if/elif` chain for DuckDB, document retrieval, Python, and web fetch. The Pydantic `AgentState` lived in memory and was not the authoritative execution record.

`InvestigationSession` persisted a coarse status, final response, and error, while `AgentStep` stored a lossy per-step snapshot. There was no persisted plan version, dependency graph, tool-attempt history, structured observation, or transition journal. Cancellation primarily used an in-memory SSE event, and the API directly changed the database status. Planner/action/synthesis provider output had Pydantic models, but there was no unified registry-driven execution boundary or dependency-aware durable scheduler.

The Phase 1 evidence validator already validates evidence, calculation, workspace, and claim references. Phase 2 `HybridRetriever` is the production retrieval capability and must be consumed rather than reimplemented. Existing tests cover bounded state behavior and provider failure, but do not prove durable resume, dependency scheduling, registry extensibility, observations, retries, replans, or persisted transitions.

## Phase 3 scope

This phase adds a durable runtime foundation around the existing tools and evidence verifier: explicit transition validation, persisted plans/steps/attempts/observations/transitions, a capability registry, strict dependency-aware plans, bounded retries/replanning, durable cancellation intent, and recovery metadata. Existing Phase 1/2 implementations are preserved unless a regression is exposed.

## Changes made

- Added `RuntimeState`, persisted investigation runtime fields, and append-only transition records.
- Added persisted `AgentPlan`, `AgentPlanStep`, `AgentToolAttempt`, and `AgentObservation` models.
- Added Alembic revisions `20260904_phase3` and `20260905_phase3_inputs`.
- Added strict `PlanSpec`/`PlanStepSpec` graph validation and registry metadata/input validation with bounded timeouts; the existing `app.tools.registry` contract was extended for availability, version, retry, safety, and side-effect metadata.
- Added `DurablePlanExecutor` with dependency-aware scheduling, attempt/observation persistence, cancellation and hard budgets.
- Wired orchestrator start, ready, execution, observation, verification, failure, and cancellation states into the persisted transition journal.
- Made cancellation API requests durable via `cancellation_requested` and failure metadata.
- Added canonical runtime state fields to backend/frontend investigation contracts.
- Qualified product/API copy from “autonomous” to “evidence-grounded” where the full Phase 3 runtime is not yet complete.

## State machine

Allowed transitions are enforced centrally: `CREATED → PLANNING → READY → EXECUTING → OBSERVING → VERIFYING → SYNTHESIZING → COMPLETED`, with bounded `REPLANNING`, `FAILED`, and `CANCELLED` exits. Invalid transitions raise `INVALID_STATE_TRANSITION`; each valid transition is persisted.

## Persistence model

Investigation sessions persist current state, plan version, start/completion times, failure code/message, and cancellation intent. Plans are versioned and immutable after creation. Steps retain dependency/status/attempt counters and validated inputs. Attempts are append-only with timestamps, status, retryability, classification, and duration. Observations retain structured result classification and payload.

## Tool registry

`ToolRegistry` supports runtime registration, metadata, input models, availability, safety/side-effect labels, timeout, version, and retry policy. Invocation validates input before execution and applies `asyncio.wait_for`. A newly registered tool can execute without modifying the registry consumer, proven by targeted tests.

The legacy orchestrator still contains its existing tool-operation handlers; full extraction of every handler into registry definitions remains a follow-up limitation. The new durable executor is registry-native and is the intended migration boundary.

## Planner schema

`PlanSpec` requires bounded structured steps with stable IDs, objectives, tool names, dependencies, inputs, expected evidence type, and completion criteria. Duplicate IDs, unknown tools, missing dependencies, and cycles are rejected before persistence.

## Observation model

Observations classify success, tool failure, timeout, and future verifier/provider outcomes separately from raw payloads. They are linked to investigation, step, and attempt IDs.

## Verification architecture

The existing Phase 1 deterministic evidence validator remains the authority for claim/evidence correctness and is still called by the orchestrator before `VERIFIED` claims are persisted. Runtime observations do not override evidence validation. Model critique is not used as a verification override.

## Replanning behavior

The durable primitives support versioned plans and explicit `REPLANNING` transitions, but automatic provider-driven replanning from every observation is not yet wired through the legacy orchestrator. This is intentionally recorded as incomplete rather than represented as fake autonomy.

## Retry behavior

Registry definitions declare retryable error markers and maximum attempts. `DurablePlanExecutor` records every attempt and retries only classified retryable failures, without sleeping in tests. Deterministic validation and malformed input failures are not retried.

## Cancellation semantics

Cancellation is persisted on the investigation, blocks the durable executor at safe checkpoints, marks the final state `CANCELLED`, and emits the existing cancellation event. API cancellation now records cancellation intent even if the worker process is later restarted.

## Resumption/idempotency

Persisted plans, statuses, attempts, and observations provide the recovery record and avoid overwriting failed attempts. A complete worker-level restart/resume endpoint and side-effect idempotency keys are not yet wired into the legacy background-task API.

## Evidence integration

The existing evidence/calculation/claim/inference/recommendation persistence and validator remain in the synthesis path. Rejected claims and unsupported recommendations are excluded from verified output. Phase 3 runtime observations do not create evidence by themselves.

## Database migrations

Phase 3 migrations extend investigation sessions and create the runtime tables. PostgreSQL live migration upgrade/downgrade/re-upgrade was verified against `omniops_phase2_test`; the Phase 2 pgvector regression suite remains green after the new head.

## Tests added

`backend/tests/test_phase3_runtime.py` covers plan validation, registry extensibility, timeout enforcement, explicit transitions, and persistence of plans, attempts, and observations. Existing state, evidence, security, and retrieval tests were rerun.

## Commands executed

```text
python -m pytest backend/tests/test_phase3_runtime.py -q
python -m pytest backend/tests -q
POSTGRES_TEST_DATABASE_URL=... python -m pytest backend/tests/test_postgres_hybrid_retrieval.py -q
DATABASE_URL=... alembic downgrade -1
DATABASE_URL=... alembic upgrade head
python -m compileall -q backend
```

## Exact results

- Phase 3 targeted tests: **6 passed** in the dedicated runtime module; runtime plus legacy state tests: **8 passed in 1.57s**.
- Full backend run after Phase 3 changes: **53 passed, 5 skipped in 9.46s**. The five skips are the PostgreSQL-only module when no URL is supplied to that command; the live PostgreSQL run below executed them separately.
- Full backend run after final state-transition/replan changes: **54 passed, 5 skipped in 9.98s**; compileall passed.
- Live PostgreSQL retrieval regression after final changes: **5 passed in 8.57s**, no skips.
- Live Phase 3 migration downgrade/re-upgrade (latest `20260905_phase3_inputs` head): **exit 0 / exit 0**.
- Python compileall: **passed**.
- Frontend TypeScript: **passed**.
- Frontend lint: **passed with no warnings or errors**.
- Frontend production build: **passed**; five static pages generated and the dynamic workspace route compiled.
- Phase 1/benchmark evaluation: **12/15 scenarios passed (80.0%)**; three pre-existing scenario failures remain and quality metrics are correctly `NOT_MEASURED`.

## Remaining limitations

Automatic replanning, durable worker resume endpoint, complete registry extraction from the legacy orchestrator, contradiction-aware runtime behavior, and provider-backed semantic evaluation are not complete. The current Phase 3 result is therefore not a fully verified autonomous runtime.

## Security implications

State transitions and cancellation intent are now durable, and tool inputs are schema-validated and timed out at the registry boundary. Tenant/evidence validation remains enforced by Phase 1/2 code. The legacy dispatcher and background-task lifecycle still require hardening before multi-worker production use; no new authorization bypass is introduced by these changes.

## Phase classification

**PARTIALLY VERIFIED** — durable runtime primitives, migrations, targeted tests, and live PostgreSQL regression pass, but critical runtime gates (automatic replanning, complete registry migration, durable resume/idempotency, and full end-to-end provider-backed execution) remain incomplete or untested.
Phase 3.5 added bounded observation decisions, automatic replan reachability in the durable executor, structured reflection, contradiction records/detection, worker leases, orphan-attempt handling, idempotency-key support on start requests, and a resume API. The legacy orchestrator's historical handler block remains isolated for follow-up extraction; the durable executor is registry-authoritative.
 
| Gate | Result | Evidence |
|---|---|---|
| Phase 1 regression restored | PASS | `python -m evals.runner`: 15/15; metrics NOT_MEASURED |
| Registry-only dispatch | PARTIAL | runtime registry extensibility test passes; legacy orchestrator extraction remains |
| Automatic observation decisions | PASS | `decide_after_observation` is consumed by `DurablePlanExecutor` |
| Automatic replanning | PASS | normal executor test observes empty evidence, increments plan version, persists revised plan |
| Bounded reflection | PASS | validated `ReflectionResult`; deterministic evidence failure cannot be overridden |
| Contradiction handling | PASS | `ContradictionRecord`, conservative numeric detector, unresolved-preservation test |
| Durable resume | PASS | resume service/API acquires lease and classifies RUNNING attempts as ORPHANED |
| Worker lease | PASS | atomic lease acquisition test rejects concurrent worker |
| Idempotency | PARTIAL | start `Idempotency-Key` and stable attempt numbers added; claim/event idempotency remains |
| Retry behavior | PASS | append-only attempts and bounded retry policy retained |
| Cancellation recovery | PASS | persisted cancellation remains authoritative on resume |
| Provider E2E | BLOCKED | no provider credentials configured; no heuristic substitution used |
| State machine | PASS | explicit transitions, VERIFYING execution, terminal-state enforcement |
| VERIFYING runtime | PASS | executor enters VERIFYING for deterministic checks |
| Transition trace tests | PARTIAL | core traces persisted; full replan/failure trace coverage remains |
| PostgreSQL regression | PASS | `5 passed` live PostgreSQL retrieval tests |
| Migrations | PASS | downgrade/upgrade exit 0/0 |
| Frontend | PASS | TypeScript, lint, and production build passed |
 
## Phase 3.5 remaining blockers
Provider-backed end-to-end execution and retrieval evaluation remain blocked by unavailable credentials. The legacy orchestrator still needs complete handler extraction into the registry, and broader idempotency (claims/calculations/events) plus full durable worker scheduling are follow-up work. Accordingly Phase 3 remains **PARTIALLY VERIFIED**, not VERIFIED.

# Phase 3 Final Verification Patch

The former `AgentOrchestrator` implementation has been deleted; the remaining class is a compatibility delegate only. Production domain writes are now centralized in `agent.persistence`/runtime logical-identity services, and cancellation events are persisted before transport publication.

| Gate | Result | Evidence |
|---|---|---|
| Evidence write-path migration | IMPLEMENTED | no production direct `EvidenceItem` construction outside persistence/runtime |
| Calculation write-path migration | IMPLEMENTED | no production direct `CalculationRecord` construction outside persistence/runtime |
| Claim write-path migration | IMPLEMENTED | no production direct `VerifiedClaim` construction outside persistence/runtime |
| Lifecycle event migration | PARTIAL | cancellation persisted; other runtime transport events require migration |
| Synthesis idempotency | IMPLEMENTED | stable `synthesis_identity` and finalization helper |
| Replan idempotency | IMPLEMENTED | stable plan logical identity |
| Lease renewal | IMPLEMENTED | owner-checked bounded renewal |
| Live worker race/takeover | NOT_VERIFIED | live concurrency run incomplete in this execution window |
| Crash before/after commit | NOT_VERIFIED | end-to-end worker scenarios remain |
| Backend regression | PARTIAL | targeted tests pass; full run affected by Windows temp-file locking |
| PostgreSQL regression | PARTIAL | existing retrieval tests pass historically; latest run exceeded window |
| Frontend build | PARTIAL | TypeScript/lint pass; latest build did not complete in window |

Phase 3 remains **PARTIALLY VERIFIED** because live concurrency/takeover and complete end-to-end crash/replay verification are not objectively complete.

# Phase 3.6 Final Integration

The durable runtime now exposes PostgreSQL-safe worker claiming (`SELECT ... FOR UPDATE SKIP LOCKED`), bounded leases, terminal-state no-op protection, orphan-attempt classification, deterministic logical identities for domain outputs, and persisted idempotent runtime events. Repeated logical event writes resolve to the existing record; attempts remain append-only. Runtime semantics are at-least-once delivery/execution with idempotent domain persistence, not distributed exactly-once execution.

| Gate | Result | Evidence |
|---|---|---|
| Claim/calculation/evidence identity boundaries | PASS | logical identity fields and unique `(session_id, logical_identity)` indexes migrated live |
| Event idempotency | PASS | `RuntimeEvent` unique identity and deduplication test |
| Worker scheduling | PASS | `claim_next_investigation` with `SKIP LOCKED` and concurrency test |
| Lease/concurrency | PASS | competing worker cannot claim leased investigation |
| Terminal state protection | PASS | durable executor returns terminal result without tool execution |
| Crash/resume | PASS | resume classifies running attempts as ORPHANED |
| Migration cycle | PASS | Phase 3.6 upgrade/downgrade/re-upgrade exit 0/0 |
| PostgreSQL regression | PASS | 5 passed, 0 skipped |
| Legacy dispatch removal | BLOCKED | historical branches remain in `AgentOrchestrator.run` |
| Provider E2E | BLOCKED | provider credentials unavailable |

## Phase 3.6 classification

**PARTIALLY VERIFIED**. The durable executor, persistence identities, worker claim/lease primitives, and live migration/retrieval regressions are verified. Phase 3 cannot be marked VERIFIED while the legacy orchestrator remains an active alternate execution path and provider-backed E2E is unavailable.

# Phase 3.7 Production Cutover

## Previous state

The API background task instantiated `AgentOrchestrator` directly, while a separate durable executor existed for targeted runtime tests.

## Authoritative runtime after cutover

API â†’ `run_investigation` service â†’ worker lease/claim â†’ `InvestigationRuntime` â†’ `DurablePlanExecutor` â†’ `ToolRegistry` â†’ observation/verification â†’ terminal state. The service is also the compatibility target of `AgentOrchestrator.run`; it no longer independently executes tools.

## Legacy runtime status

**DEPRECATED DELEGATING ONLY.** The old handler implementation remains in the source file for compatibility but is unreachable from `run()`; production API/background execution uses the durable service.

## Idempotency matrix

| Domain | Identity | DB enforcement | Retry verified |
|---|---|---|---|
| Investigation | `Idempotency-Key` | unique index | partial |
| Plan | investigation/version | versioned rows | partial |
| Step | plan/step key | application graph validation | pass |
| Tool attempt | separate attempt number | append-only | pass |
| Observation | attempt linkage | persisted rows | partial |
| Evidence | session/logical identity | unique index | partial |
| Calculation | session/logical identity | unique index | partial |
| Claim | session/logical identity | unique index | partial |
| Contradiction | evidence pair | application record | pass |
| Event | logical identity | unique constraint | pass |
| Synthesis | investigation output | not yet unique | blocked |

## Worker report

`claim_next_investigation` uses PostgreSQL `FOR UPDATE SKIP LOCKED`, excludes terminal/cancelled work, and assigns a bounded lease. `run_worker_once` executes claimed work and releases the lease. Resume classifies running attempts as `ORPHANED`; lease renewal and full multi-worker execution remain deployment follow-ups.

## Verification

- Production-path registry test: **12 Phase 3 runtime tests passed**.
- Full backend suite: **60 passed, 5 skipped** (PostgreSQL-only tests are run separately).
- Live PostgreSQL retrieval: **5 passed, 0 skipped**.
- Phase 1 evaluation: **15/15**; quality metrics `NOT_MEASURED`.
- Live migration cycle: **upgrade/downgrade/re-upgrade 0/0/0**.
- Frontend TypeScript validation: **passed**.

## Phase 3.7 classification

**PARTIALLY VERIFIED**. Production entry now delegates to the durable runtime and worker claim primitives are integrated, but legacy source remains as unreachable compatibility code, domain idempotency helpers are not yet wired through every historical persistence path, synthesis/replan idempotency is incomplete, and provider-backed E2E remains unavailable.

# Phase 3.8 Final Closure Verification

| Gate | Result | Evidence |
|---|---|---|
| Legacy engine | DELEGATE ONLY | `AgentOrchestrator` contains only compatibility delegation |
| Production runtime | PASS | API background path calls `run_investigation` |
| Registry | PASS | durable service resolves through `ToolRegistry` |
| Evidence/calculation/claim identity | IMPLEMENTED | logical identity columns, unique indexes, persistence services |
| Contradiction identity | PASS | canonical evidence-pair identity and unique constraint |
| Event identity | PASS | unique persisted runtime-event identity |
| Synthesis identity | IMPLEMENTED | investigation synthesis identity and finalization helper |
| Replan identity | IMPLEMENTED | stable plan logical identity and replay lookup |
| Lease renewal/ownership | IMPLEMENTED | owner-checked renewal and pre-action ownership check |
| Worker acquisition | PASS | PostgreSQL `SKIP LOCKED` claim path |
| Migration cycle | PASS | upgrade/downgrade/re-upgrade 0/0/0 on live PostgreSQL |
| Gemini provider E2E | PASS | `gemini-3.6-flash` structured planning and synthesis |
| OpenAI retrieval evaluation | BLOCKED | `OPENAI_API_KEY` unavailable; no fallback used |
| Frontend | PARTIAL | TypeScript/lint pass; latest build did not complete in execution window |

Phase 3.8 remains **PARTIALLY VERIFIED**. Structural durability and provider verification are implemented, but live multi-worker race/takeover tests, complete historical domain-write migration, and a completed frontend build remain outstanding.

## Live Gemini provider verification

The root Compose `.env` supplies `GEMINI_API_KEY` without exposing its value. The backend container initialized `GeminiProvider` using `gemini-3.6-flash`; live structured planning returned one task and live synthesis returned one claim with a non-empty summary. An earlier `gemini-2.5-flash` request returned HTTP 404 because that model is unavailable to new users; the local model setting and Compose pass-through were corrected. Retrieval evaluation remains blocked because the configured semantic embedding path requires an OpenAI embedding credential, which is not available in this execution environment.
# Phase 3 Final Verification

Final checks: Phase 1 evaluation 15/15; Phase 3 targeted tests 14 passed; live PostgreSQL retrieval tests 5 passed/0 skipped; compileall passed. Production runtime and legacy delegate-only cutover remain in place. Live worker race, lease takeover, stale-worker end-to-end rejection, crash/replay scenarios, universal lifecycle event migration, and a completed frontend production build remain unverified. Phase 2 retrieval evaluation remains BLOCKED because the configured semantic embedding path requires OPENAI_API_KEY.
# Phase 3 Closure B — Live PostgreSQL Concurrency

Live PostgreSQL concurrency tests (`backend/tests/test_phase3_live_concurrency.py`) passed: 2 passed, 0 skipped. Separate async sessions verified single-worker claim race, lease takeover, stale renewal rejection, and concurrent event identity deduplication.

# Phase 3 Closure C — Crash, Resume & Replay Verification

Deterministic recovery tests were added in `backend/tests/test_phase3_crash_recovery.py` and run through the persisted runtime primitives. The suite covers orphan-attempt classification before result commit, committed-output replay, persisted verification state, synthesis replay, replan replay, and terminal cancellation recovery.

| Scenario | Result | Evidence |
|---|---|---|
| Crash before result commit | PASS (orphan retained; safe recovery path bounded) | `test_crash_before_commit_orphans_attempt_and_recovery_is_bounded` |
| Crash after result commit | PASS (authoritative synthesis reused) | `test_crash_after_commit_reuses_authoritative_synthesis` |
| Crash after verification | PASS (persisted verification state retained) | `test_crash_after_verification_preserves_terminal_step_state` |
| Synthesis replay | PASS; provider call count 1 | `test_synthesis_replay_provider_not_called_again` |
| Replan replay | PASS; existing logical plan reused | `test_replan_replay_reuses_v2` |
| Cancellation recovery | PASS; terminal cancellation cannot be resumed | `test_cancellation_survives_recovery` |

Command: `python -m pytest backend/tests/test_phase3_crash_recovery.py -q` — **6 passed** (one pytest cache permission warning on Windows; no test failure).

The tests are deterministic mechanics coverage; a full process-level domain crash test across live workers remains a separate integration follow-up.

# Phase 3 Final Execution Patch — Verification Ledger

| Gate | Result | Evidence |
|---|---|---|
| Lifecycle investigation.created / step.failed | PARTIAL | Existing runtime coverage; no new lifecycle implementation in this execution |
| Live PostgreSQL worker race/takeover | PASS | `test_phase3_live_concurrency.py`: 2 passed with `POSTGRES_TEST_DATABASE_URL` |
| Crash/replay targeted scenarios | PASS | `test_phase3_crash_recovery.py`: 6 passed |
| Phase 3 focused regression | PASS | Runtime + crash + live concurrency: 20 passed, 0 failed |
| Backend full suite | PASS | 66 passed, 7 skipped; skips are environment/provider-dependent |
| PostgreSQL retrieval regression | PASS | `test_postgres_hybrid_retrieval.py`: 5 passed, 0 skipped |
| Phase 1 evaluation | PASS | 15/15; quality metrics NOT_MEASURED |
| Migrations | PASS | Alembic head `20260910_phase38_replan` confirmed on PostgreSQL |
| Frontend TypeScript | PASS | `npx tsc --noEmit` |
| Frontend lint | PASS | `npm run lint` |
| Frontend production build | PASS | `npm run build` completed successfully |
| Backend compile | PASS | `python -m compileall backend` |
| Docker smoke | PARTIAL | Docker Compose services healthy under elevated CLI; `/api/v1/health` and frontend returned HTTP 200 |

The Windows parquet test initially reproduced a `PermissionError` under the restricted execution sandbox; it passed (`2 passed`) with elevated local execution. The DuckDB connection now explicitly unregisters Arrow tables before close to release file handles. Crash tests remain deterministic runtime mechanics rather than a full process-kill domain continuation harness.
