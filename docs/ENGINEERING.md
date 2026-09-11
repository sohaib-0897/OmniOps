# Engineering walkthrough

This guide is a short route through the code and the decisions worth discussing in a technical interview. Capability implementation and end-to-end verification are distinguished deliberately.

## 1. Retrieval belongs in the database

Start with [hybrid_search.py](../backend/app/rag/hybrid_search.py). The production path restricts workspace/source candidates in SQL, combines PostgreSQL full-text and vector retrieval through reciprocal rank fusion, and returns bounded results. [Retrieval integration tests](../backend/tests/test_postgres_hybrid_retrieval.py) exercise PostgreSQL rather than substituting Python ranking.

Tradeoff: optional embeddings allow useful lexical retrieval when credentials are missing. Synthetic vectors can test SQL ordering and isolation, but cannot measure semantic relevance. HNSW/GIN indexes exist; the audit's production-shaped query did not establish index acceleration.

## 2. References are not the same as truth

Read the [evidence models](../backend/app/models/evidence.py), [validator](../backend/app/evidence/validator.py) and [persistence helpers](../backend/app/agent/persistence.py). The model represents source, extracted content, evidence, calculation, claim, inference and recommendation. Coordinates and provider provenance make an assertion inspectable.

Tradeoff: relational rows plus JSON support lists are convenient for multiple links, but do not enforce every edge as a foreign key. The audit exposed a nested source-chain bypass and claims remaining VERIFIED after evidence deletion. Reference resolution also does not prove semantic entailment or recompute a calculation.

## 3. Recovery is a transaction-ordering problem

Read [runtime.py](../backend/app/agent/runtime.py), [service.py](../backend/app/agent/service.py) and the [database probes](../scripts/phase7_database_probes.py). Runtime state, attempts, identities and events are persisted; workers acquire leases and streams replay database events.

The useful counterexample: two event writers can commit out of creation order. A cursor based on creation time can skip the late commit even though the row is durable. Another probe let a stale worker overwrite a new owner's final response. Passing normal reconnect or duplicate-identity tests does not establish these invariants.

## 4. Put execution behind a separate boundary

The [Python tool](../backend/app/tools/python_sandbox.py) calls an [authenticated runner](../backend/app/sandbox_runner_server.py). Payloads run in a fixed image with constrained resources and network access disabled. The application backend has no Docker socket.

Tradeoff: the runner controls container execution, so its host is a separate trust boundary. Non-root payloads do not make a root Docker control plane harmless. Local development topology is explicitly different from an independently isolated production runner.

## 5. Treat provider absence as a product state

[Multimodal contracts](../backend/app/llm/multimodal.py), [extraction contracts](../backend/app/ingestion/contracts.py) and [capabilities](../backend/app/ingestion/capabilities.py) distinguish ready, partial, invalid and unavailable results. Native text and OCR remain useful when semantic vision is unavailable. Speech timestamps and speakers originate from the provider rather than invented segment boundaries.

Direct live extraction/persistence/retrieval succeeded in the audit. That does not imply the default investigation worker uses provider planning or synthesis: it currently registers retrieval only.

## 6. Browser types need runtime contracts

Review the [API client](../frontend/src/lib/api-client.ts), [SSE hook](../frontend/src/hooks/useInvestigationStream.ts) and [report renderer](../frontend/src/components/workspace/ExecutiveReportView.tsx). Access tokens remain in memory, refresh credentials use HttpOnly cookies, and SSE uses bearer headers rather than query tokens. Dialogs preserve native focus containment while closing.

The report renderer passed compilation and authored-fixture checks, but real worker output lacked the report fields it expected. This is why the audit includes actual browser flows alongside static and component tests.

## Suggested review route

1. Read the [README capability table](../README.md).
2. Follow a source through extraction and SQL retrieval.
3. Inspect the default runtime registry and compare it with the intended report contract.
4. Read the [seven release blockers](../PHASE_7_FINAL_AUDIT.md#release-blockers).
5. Compare ordinary tests with the adversarial probes that invalidated broader claims.

The strongest supported portfolio claim is building and critically testing these systems components. A complete production autonomous agent is not yet a supported claim.
