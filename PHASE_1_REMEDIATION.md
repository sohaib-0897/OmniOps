# Phase 1 Remediation

## Summary

Phase 1 establishes a non-fabrication invariant: unavailable data or provider capabilities now produce explicit unavailable/failed states. Model output is treated as a proposal and only reference-valid claims, inferences, and recommendations enter completed reports.

## Files Changed

- LLM contract/providers: `backend/app/llm/base.py`, `client.py`, `analytical_provider.py`, `openai_provider.py`, `gemini_provider.py`
- Agent and validation: `backend/app/agent/orchestrator.py`, `state.py`, `backend/app/evidence/validator.py`
- Persistence/API: evidence, investigation, and document models/schemas; evidence graph and file ingestion routes
- Ingestion: audio, image, PDF, and web extraction behavior
- Migration: `backend/alembic.ini` and `backend/alembic/versions/20260902_phase1_evidence_contract.py`
- Frontend: API types, SSE step reconciliation, lineage/report copy and rendering
- Evaluations/tests: `evals/metrics.py`, `evals/runner.py`, `backend/tests/test_phase1_integrity.py`
- Product description: `README.md` and user-facing frontend copy
- Frontend tooling: ESLint dependencies in `frontend/package.json` and lockfile

## Fake Behaviors Removed

- Offline metrics are no longer seeded with invented values.
- The deterministic provider no longer creates factual, inference, or recommendation prose.
- Audio failures no longer create transcript sentences, speaker names, or estimated semantic segments.
- Image ingestion no longer labels images as business charts or supplies default dimensions.
- Empty PDF pages and failed web extraction no longer create placeholder evidence.
- Retrieval scores are no longer stored as evidence confidence probabilities.
- Missing confidence is represented as `null`/`NOT_PROVIDED`, not 100%.
- Provider failures no longer substitute a semantically different provider.

## Evidence Contract

The persisted lineage is now capable of representing:

`SOURCE -> EXTRACTED_CONTENT -> EVIDENCE -> CALCULATION -> CLAIM -> INFERENCE -> RECOMMENDATION`

- `SourceDocument` remains the stable source record.
- `DocumentChunk` is the extracted-content record and now stores its extraction method and locator fields.
- `EvidenceItem` resolves to an extracted-content record and source.
- `CalculationRecord` stores explicit evidence/source inputs, formula/code, output, and reproducibility hash.
- `VerifiedClaim` stores evidence and calculation IDs plus verification status/errors.
- `InferenceRecord` and `RecommendationRecord` persist their supporting IDs and validation status.
- The lineage API emits explicit nodes and edges for all seven stages.

## Claim Validation Rules

A claim is `VERIFIED` only when every referenced record exists and resolves within the same investigation and workspace. Evidence must resolve through extracted content to its source, and its exact quote must be present in that extracted content. Calculations must have formula/code, output, reproducibility hash, and permitted evidence/source input provenance. Missing, cross-investigation, cross-workspace, incomplete, or unsupported references cause `REJECTED` with deterministic error codes. Rejected proposals are retained separately and are not presented as verified report claims.

## Provider Failure Behavior

Provider states are `AVAILABLE`, `UNAVAILABLE`, `RATE_LIMITED`, `AUTHENTICATION_FAILED`, `TIMEOUT`, `MALFORMED_RESPONSE`, and `DEGRADED`. Failures stop the investigation with an explicit code/state. Successful and failed sessions persist provider provenance in report/session metadata. The deterministic provider is limited to reproducible structured-data profiling; semantic work returns `LLM_PROVIDER_REQUIRED`.

## Audio Behavior

Successful Whisper responses create genuine transcript chunks with provider timestamps. Without successful transcription, the upload remains valid but stores `TRANSCRIPTION_UNAVAILABLE` and deterministic file metadata. No semantic chunk or evidence is created.

## Image Behavior

Image ingestion stores only proven file type, byte size, and header-derived dimensions when available. Without a vision provider it records `VISION_ANALYSIS_UNAVAILABLE`; no description, OCR text, or semantic evidence is created.

## Frontend/API Contract Fixes

- `confidence_score` is canonical and nullable across backend and frontend.
- Claims expose calculation IDs and validation metadata.
- Inferences, rejected proposals, and recommendation IDs are represented in the report contract.
- SSE tool events use persisted database step IDs; REST and SSE steps merge by stable ID.
- Calculation display resolves the graph edge for the selected claim instead of selecting the first calculation.
- Unsupported BM25, pgvector, cryptographic, and zero-hallucination product claims were removed or explicitly qualified.

## Tests Added

- Unsupported claim and nonexistent evidence/calculation rejection
- Cross-workspace/cross-investigation evidence rejection
- Four calculations mapped to four exact claim calculation IDs
- Unsupported recommendation rejection
- Explicit provider timeout behavior
- Audio transcription-unavailable behavior with no transcript
- Image vision-unavailable behavior with metadata only

## Exact Test Results

- `python -m pytest backend/tests -v`: **39 passed in 14.15s**
- `python -m evals.runner`: **15/15 executable scenarios passed**; factual precision, citation precision, and hallucination rate are **NOT_MEASURED**
- `npx tsc --noEmit`: **exit 0**
- `npm run lint`: **exit 0, no warnings or errors**
- `npm run build`: **exit 0**, 5 static/dynamic routes generated successfully

## Remaining Issues

- No PostgreSQL-native vector/full-text retrieval yet; retrieval remains application-side prototype logic.
- Semantic truth/entailment is not established merely by valid references; Phase 1 validates provenance, not factual entailment.
- The Python execution boundary, SSRF DNS pinning, durable workers/SSE, and production tenant controls remain later-phase work.
- OCR and local speech/vision models are intentionally not included in Phase 1.
- Existing databases must run the new Alembic migration before the updated application models are deployed.
- `npm install` reports three dependency vulnerabilities (two high, one critical); forced dependency upgrades were not applied in this focused phase.
- `next build` still reports that lint is skipped internally, although `npm run lint` was executed independently and passed.

## Phase 2 Recommendations

1. Implement PostgreSQL-native tenant-filtered vector and full-text retrieval with measured relevance evaluation.
2. Add deterministic claim-entailment checks and structured provider schemas beyond reference existence.
3. Move investigations and event delivery to durable worker/event infrastructure.
4. Replace the Python subprocess boundary and harden SSRF/network egress.
5. Add genuine OCR/vision/transcription providers without reintroducing semantic fallback content.
