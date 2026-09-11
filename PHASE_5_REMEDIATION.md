# Phase 5 Multimodal Remediation

**Phase 5 classification: VERIFIED**

PDF native/OCR extraction, image validation/OCR, provenance, truthful failure
states, retrieval integration, and live Gemini multimodal provider execution
are implemented and verified. The known Phase 2 semantic-embedding credential
gap remains separate; live multimodal retrieval was verified through the
PostgreSQL lexical channel.

## 1. Multimodal Architecture

```text
UPLOAD
-> VALIDATION
-> MODALITY DETECTION
-> EXTRACTION
-> NORMALIZATION
-> PERSISTENCE (SourceDocument + DocumentChunk provenance)
-> CHUNKING / INDEXING
-> RETRIEVAL
-> EVIDENCE
```

`ExtractionRecord`/`ExtractionBatch` contracts normalize page, timestamp,
method, provider, model, status, and error information.  The existing durable
`DocumentChunk` store is the persisted extraction surface; each generated
chunk carries a deterministic `extraction_id` and source coordinates in
`chunk_metadata`.

## 2. Capability Matrix

| Capability | Provider/engine | Status | Live verified |
| --- | --- | --- | --- |
| PDF native text | PyMuPDF | PASS | PASS (test fixtures) |
| PDF OCR | Tesseract + pytesseract | PASS | PASS - live backend container recognized `PHASE FIVE OCR 120` from scanned pixels |
| Image OCR | Tesseract; Gemini detected text where configured | PASS | PASS - live backend container recognized `IMAGE OCR 456` |
| Image semantic vision | Gemini Interactions API (`gemini-3.8-flash`) | PASS | PASS - live structured chart analysis in the backend container and persisted through upload API |
| Audio transcription | Gemini Interactions/Files API (`gemini-3.5-transcribe`); OpenAI Whisper secondary | PASS | PASS - live two-speaker WAV transcription through upload API |
| Audio timestamps | Gemini verbatim word annotations (`gemini-3.5-transcribe`); OpenAI verbose JSON secondary | PASS | PASS - 11 live timestamped segments persisted with ordered offsets |
| Audio diarization | Gemini verbatim speaker annotations (`gemini-3.5-transcribe`) | PASS | PASS - 2 provider-returned speaker labels persisted; no local assignment |
| Web extraction | Existing SafeWebRetriever / trafilatura | PASS | Existing Phase 4 SSRF regression and `WEB_EXTRACTION` provenance label |

Capability discovery is exposed by the health response and is derived from
installed engines, configured credentials, and centralized model metadata. It
does not make provider calls or invent availability.

## 3. PDF Pipeline

PDFs are opened with PyMuPDF and processed page-by-page. Pages meeting the
native-text threshold use `NATIVE_TEXT`; table extraction, when supported by
the installed parser, is labeled `TABLE_EXTRACTION`. Image-only/empty pages
invoke real Tesseract OCR at a bounded DPI and timeout. OCR-unavailable,
OCR-failed, and no-text outcomes remain explicit and produce no placeholder
text. Mixed PDFs therefore retain native and OCR records independently, each
with page provenance.

## 4. Image Pipeline

Pillow verifies the bytes and reads actual PNG/JPEG format and dimensions,
with a pixel-count limit. Local Tesseract OCR and Gemini semantic analysis are
separate extraction methods. Gemini output is schema-validated and only
returned fields are persisted; unreadable values are not inferred. Provider
failure yields `VISION_FAILED`/`VISION_UNAVAILABLE` and never a generic image
description. The provider uses the current Gemini Interactions API with a
top-level JSON `response_format`; image-derived content is labeled
`UNTRUSTED_IMAGE_DATA`.

## 5. Audio Pipeline

WAV containers are structurally decoded for validity and duration; MP3, M4A,
and Ogg headers are checked before provider use. Gemini's dedicated
`gemini-3.5-transcribe` path uploads media through the resumable Files API and
requests verbatim word timestamps plus provider diarization annotations.
OpenAI Whisper remains a genuine secondary provider. Offsets and speaker
labels are persisted only when returned by the provider; no local timestamp or
speaker assignment is performed. Malformed media and provider failures have
distinct status/error codes. Audio text is labeled `UNTRUSTED_AUDIO_DATA`.

## 6. Provenance Model

Every persisted chunk includes `source_document_id`, modality, extraction
method, stable extraction identity, and applicable page/timestamp/metadata.
Provider/model and OCR engine versions are retained when supplied. Bounding
boxes and speakers are left null when the extractor does not provide them.

The existing web retriever remains the single outbound path. It returns
`WEB_EXTRACTION` metadata and `UNTRUSTED_WEB_DATA`; Phase 4 DNS/IP pinning,
redirect validation, byte caps, and TLS checks are unchanged.

## 7. Provider Failure Semantics

Malformed media is `INVALID_MEDIA`; unsupported/missing capability is reported
as `*_UNAVAILABLE`; provider authentication, rate limit, timeout, malformed
response, and execution failures remain distinct codes. No provider failure
falls back to fabricated text, speakers, confidence, dimensions, or semantic
descriptions.

## 8. Idempotency / Resumption

Source uploads are deduplicated by workspace and SHA-256. Extraction/chunk
identity is deterministic over source hash, modality, method, locator, and
content. Reprocessing the same source therefore resolves to the same logical
identities; the production PDF upload/retry test returns the same source and
one preview chunk on re-entry. Successful output is retained even when another
page/provider path is partial.

## 9. Multimodal Retrieval

The existing hybrid retriever consumes multimodal `DocumentChunk` content and
preserves modality and page/timestamp fields in results. Deterministic SQLite
development retrieval tests prove OCR PDF text, image vision observations,
and audio transcript segments remain searchable with modality/page/timestamp
provenance. PostgreSQL retrieval infrastructure remains passing (5 passed,
0 skipped); semantic provider evaluation remains separately blocked by the
missing OpenAI embedding credential.

## 10. Evidence Integration

The production upload path promotes extracted chunks into the existing source
and evidence-compatible document lineage. Deterministic extraction IDs and
coordinates are available to the established evidence/claim services without
fabricating verification. A live Gemini transcript was uploaded through the
production API, then driven through `persist_tool_domain_outputs`; the source,
extracted chunk, evidence item, and deterministically VERIFIED claim were all
persisted and validated, including audio coordinates and Gemini provenance.

## 11. Security

Media parsing preserves Phase 4 controls: no untrusted code is executed on the
host, OCR invokes only fixed infrastructure arguments, media is size/pixel/
duration bounded, and all image/audio/web-derived text is explicitly untrusted
source data. Existing sandbox and SSRF regressions remain green.

## 12. Test Results

Fresh targeted provider contract + multimodal tests: **27 passed, 0 failed, 0 skipped**.
The original multimodal tests remain **20 passed, 0 failed**. Full backend suite with
live PostgreSQL configured: **165 passed, 0 failed, 0 skipped**. Phase 1 evaluation:
**15/15 passed**, quality metrics `NOT_MEASURED`. Phase 3 regression:
**27 passed, 0 skipped**. Phase 4 focused regression: **58 passed, 0 failed**.
PostgreSQL retrieval regression: **5 passed, 0 skipped**. Backend compileall
passed. Frontend TypeScript, lint, and production build passed. Docker smoke
passed with PostgreSQL healthy and backend/frontend HTTP 200; the rebuilt
backend container includes the OCR runtime and the live OCR probe returned
recognized text.

## 13. Remaining Multimodal Limitations

The host environment has no Tesseract executable; the production backend image
installs Tesseract and the `pytesseract`/Pillow bindings, and live container OCR
was verified. Diarization is supported only when the configured provider emits
speaker annotations; no local speaker inference is performed. Semantic
embeddings remain a separate Phase 2 evaluation issue because `OPENAI_API_KEY`
is unavailable, so the live multimodal retrieval proof intentionally uses
PostgreSQL lexical retrieval. All provider failures remain explicit rather
than fabricated output.

## 14. Final Verification Ledger

| Gate | Result |
| --- | --- |
| Phase 5 targeted suite | PASS - 27 passed, 0 failed, 0 skipped |
| Backend full suite (live PostgreSQL configured) | PASS - 165 passed, 0 failed, 0 skipped |
| Phase 1 evaluation | PASS - 15/15; metrics NOT_MEASURED |
| Phase 3 regression | PASS - 27 passed, 0 skipped |
| Phase 4 security regression | PASS - 58 passed, 0 failed |
| PostgreSQL retrieval regression | PASS - 5 passed, 0 skipped |
| Migrations | PASS - no schema change; `20260910_phase38_replan` is current head |
| Backend compileall | PASS |
| Frontend TypeScript / lint / production build | PASS / PASS / PASS |
| Docker smoke | PASS - PostgreSQL healthy; backend HTTP 200; frontend HTTP 200; sandbox runner healthy |

## Final Provider Closure

The configured credential was checked without logging its value:
`GEMINI_KEY_PRESENT=YES`. Centralized defaults are
`GEMINI_VISION_MODEL=gemini-3.8-flash` and
`GEMINI_TRANSCRIPTION_MODEL=gemini-3.5-transcribe`; the rebuilt backend
container reports the same values. The provider implementation uses the
current Gemini Interactions API (`/v1beta/interactions`) for structured vision
and the resumable Files API followed by Interactions for audio transcription.
The general text Gemini provider was moved to the same Interactions endpoint so
the configured `gemini-3.8-flash` default does not use the obsolete
`generateContent` request shape.

| Gate | Result | Evidence |
| --- | --- | --- |
| Gemini key available | PASS | Safe status-only discovery: `GEMINI_KEY_PRESENT=YES` |
| gemini-3.8-flash accessible | PASS | Authenticated model discovery from the backend container returned HTTP 200 and vision access |
| live image request | PASS | Deterministic chart sent through production `analyze_image_file` and upload API |
| structured image output | PASS | Live Gemini response validated by `VisionAnalysis`; semantic chart signal present |
| image persisted | PASS | Upload API returned a READY source with 2 chunks (`IMAGE_OCR`, `VISION`) and persisted Gemini provenance |
| gemini-3.5-transcribe accessible | PASS | Authenticated model discovery from the backend container returned HTTP 200 and transcription access |
| live transcription | PASS | Real two-speaker WAV used through Files/Interactions and production upload API |
| word timestamps | PASS | 11 provider-returned timestamped segments persisted with non-negative ordered offsets |
| speaker diarization | PASS | 2 distinct provider-returned speakers persisted; no local labels generated |
| transcript persisted | PASS | Upload API returned READY source with 11 `TRANSCRIPTION` chunks and Gemini model provenance |
| audio retrieval | PASS | PostgreSQL lexical retrieval returned the correct live audio source for `Northwind` with timestamp provenance |
| audio evidence lineage | PASS | Live transcript source passed SOURCE -> EXTRACTED_CONTENT -> EVIDENCE -> VERIFIED CLAIM validation |
| no fallback fabrication | PASS | No heuristic transcript/semantic fallback exists; typed provider failures are returned |

The live provider tests were deliberately run separately from deterministic
tests. The initial `ConnectError` was traced to a stopped Docker Desktop Linux
engine: the host's provider connectivity was healthy, but the backend container
was unavailable while the probe was attempted. After Docker Desktop was
started, the backend container passed DNS/TCP/TLS/HTTP diagnostics, authenticated
model discovery, live image analysis, live transcription, persistence, lexical
retrieval, and evidence-lineage verification. No provider output, key, or
secret was logged.

## Transport Diagnostic

| Layer | Result | Safe evidence |
| --- | --- | --- |
| Host DNS | PASS | `generativelanguage.googleapis.com` resolved A and AAAA records |
| Host TCP 443 | PASS | `Test-NetConnection` succeeded |
| Host TLS | PASS | Unauthenticated HTTPS returned an HTTP response (403) with certificate verification enabled |
| Host HTTP | PASS | HTTP 403 received without credentials; transport established |
| Backend container DNS | PASS | Docker resolver (`127.0.0.11`) resolved Gemini and neutral public hostnames |
| Backend container TLS | PASS | `httpx` with `trust_env=True` and `False` both received HTTP responses; no `verify=False` |
| Backend container HTTP | PASS | Gemini host returned HTTP 404 unauthenticated; `example.com` returned HTTP 200 |
| Authenticated Gemini | PASS | Model discovery returned HTTP 200; both configured models accessible |

Proxy variables were absent on host and backend container. No VPN/firewall
block remained after Docker Desktop was started, and there was no CA-bundle
failure. The trusted Gemini client continues to use normal HTTPS with TLS
verification; the Phase 4 untrusted Python sandbox remains `network=none`.

## Live Provider Closure Evidence

* Vision: `gemini-3.8-flash` analyzed the deterministic `Quarterly Revenue`
  chart, returned schema-valid structured output with a chart signal, and the
  production upload path persisted both OCR and `VISION` chunks.
* Audio: `gemini-3.5-transcribe` processed the deterministic two-speaker WAV,
  returned 11 timestamped segments and 2 speaker labels, and the production
  upload path persisted 11 `TRANSCRIPTION` chunks with model/provider metadata.
* Retrieval: PostgreSQL lexical retrieval returned the live image source for
  `Quarterly Revenue` and the live audio source for `Northwind`, with audio
  timestamp provenance retained.
* Evidence: the live audio chunk was passed through the authoritative evidence
  and claim persistence boundary; source, extracted content, evidence, and a
  deterministically VERIFIED claim were committed and revalidated.



