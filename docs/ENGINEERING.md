# Engineering notes

This is a code reading route for the implemented investigation path. The [README](../README.md) covers setup and current checks; the [Phase 7 audit](../PHASE_7_FINAL_AUDIT.md) and [later closure record](../FINAL_AUDIT.md) preserve the adversarial findings and follow-up evidence.

## Retrieval

Start with [hybrid_search.py](../backend/app/rag/hybrid_search.py) and the [PostgreSQL integration tests](../backend/tests/test_postgres_hybrid_retrieval.py). The query restricts candidates by workspace in SQL, builds lexical candidates with PostgreSQL full text, optionally adds pgvector candidates, and fuses ranks with reciprocal rank fusion. The absence of an embedding provider is represented explicitly, allowing lexical retrieval without synthetic semantic output. Database query behavior is tested separately from semantic relevance; live embedding quality is not measured here.

## Evidence and calculations

The [models](../backend/app/models/evidence.py), [validator](../backend/app/evidence/validator.py), and [calculation identity](../backend/app/evidence/calculation_identity.py) show how extracted source locations, quotes, calculations, claims, inferences, and recommendations are linked. Validation checks workspace and source chains, exact quote presence, and canonical calculation hashes. These checks establish reference consistency. They do not establish semantic entailment or recompute arbitrary code from a stored hash.

## Durable execution

[service.py](../backend/app/agent/service.py) registers the production tools and calls the configured provider for planning and synthesis. [runtime.py](../backend/app/agent/runtime.py) persists states, attempts, leases, and events. The [worker](../backend/app/worker.py) claims work from the database. Read the [runtime tests](../backend/tests/test_phase3_runtime.py) and [closure tests](../backend/tests/test_final_audit_closure.py) beside those modules: ordinary completion, retry, stale ownership, and recovery each test different invariants.

## Execution boundary

[python_sandbox.py](../backend/app/tools/python_sandbox.py) calls the [runner service](../backend/app/sandbox_runner_server.py). The runner creates a constrained payload container without network access. The API has no Docker socket. The runner host remains a privileged control boundary; local Compose uses the host Docker daemon, while the production profile requires a separately hosted runner.

## Provider and browser behavior

[The provider client](../backend/app/llm/client.py) selects a configured text provider for planning and synthesis. [Multimodal contracts](../backend/app/llm/multimodal.py) distinguish native extraction, OCR, provider results, and unavailable capabilities. The [frontend API client](../frontend/src/lib/api-client.ts) keeps access credentials in memory; [the SSE hook](../frontend/src/hooks/useInvestigationStream.ts) reconnects with an Authorization header and deduplicates events. A completed UI brief is model output with checked references, so the reader still needs to inspect its source passages.
