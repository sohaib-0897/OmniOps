# Session handoff: 2026-09-23, part 2 (Concept B · Signature)

Read this with `AGENTS.md` and `SESSION_HANDOFF_2026-09-23.md` at the start of a fresh session. This file supersedes sections 3 and 4 of `SESSION_HANDOFF_2026-09-23.md`.

## 0. Current status and next step

**Concept B · Signature is APPROVED** as the visual direction. A technical and truthfulness feasibility pass is done, and its Figma corrections are applied.

**Recommendation: NEEDS API DECISION.** Before implementing the UI, the user must decide on:

1. **REQUIRED: a passage-map endpoint.** Without it the source track only works for small documents, by downloading full passage text. See section 6.
2. **OPTIONAL: summary fields on the history endpoint.** These decide whether Home shows per-question counts.

**Rules until the user decides:**
- Do NOT start the UI implementation or write production code.
- Do NOT push to GitHub. Before any push, ask: "The fix is verified locally. Do you want me to push it to GitHub?"

**Git state:**
- At the start of this session the tree had only untracked files: `SESSION_HANDOFF_2026-09-23.md`, `SKILL.md` and `UI Screenshots/`.
- The regression fix and the UI work appear to be committed already (`9106365 fix(runtime)…`, `c2a99ca feat(ui)…`). The "nothing committed" note in the first handoff is stale.
- Whether these commits were pushed is unverified.

## 1. Figma

**File:** https://www.figma.com/design/n8HW71cO0tdfkr7VzilqhJ (file key `n8HW71cO0tdfkr7VzilqhJ`).

**Account and budget:**
- Account `i220897@nu.edu.pk`, student team `team::1684564809586171082` (200 MCP calls a day).
- Do not use the Starter team `team::1684508844111154153`.

**Page `Concept B · Signature`** (id `22:5`). The earlier Casefile pages are untouched.

- **Direction board:** `31:740`. It contains the signature idea, signature motion, graphics strategy, before-vs-after, restraint, and a "Feasibility pass" corrections section.
- **Desktop, dark** (row y=0 / y=1100):

| Screen | Node |
|---|---|
| B03 Empty workspace | `22:6` |
| B04 Investigation starting | `35:740` |
| B05 Mid-investigation | `35:937` |
| B06 Motion spec (the fold, the pull, motion vocabulary) | `28:419` |
| B07 Completed brief (1500 tall) | `25:259` |
| B08 Evidence interaction / inspector | `25:679` |
| B02 Home | `27:404` |
| B01 Authentication | `27:741` |

- **Desktop, light** (clones set to Light mode, y=2300):

| Screen | Node |
|---|---|
| L03 | `40:753` |
| L05 | `40:864` |
| L07 | `40:1021` |
| L08 | `40:1286` |
| L02 | `40:1479` |
| L01 | `40:1742` |

- **Mobile** (y=3400):

| Screen | Node |
|---|---|
| M1 mid-investigation, dark | `30:722` |
| M2 brief with evidence sheet, dark | `30:852` |
| M2 light | `40:2188` |
| M1 light | `40:2320` |

- **Prototype flow** "Concept B · Investigation flow": B03 → B04 → B05 → B06 → B07 → B08 → back to B07 (smart animate).
- **Light frames are clones.** After editing a dark frame, delete its light clone, re-clone it, and call `setExplicitVariableModeForCollection(Color, '2:2')`. Never use per-frame opacity overrides.

**Variables** (collection Color `VariableCollectionId:2:36`, modes Dark `2:1` and Light `2:2`):

- **Existing:** canvas `2:37`, surface `2:38`, raised `2:39`, line `2:40`, line-strong `2:41`, ink `2:42`, ink-2 `2:43`, ink-3 `2:44`, inverse `2:45`, action `2:46`, provenance `2:48`, provenance-strong `2:49`, provenance-wash `2:50`, caution `2:51`, critical `2:53`.
- **New semantic track tokens:**

| Token | Id | Dark | Light | Meaning |
|---|---|---|---|---|
| `color/track/indexed` | `34:5` | #868C94 @ 0.30 | #656B73 @ 0.22 | Passage indexed, not used |
| `color/track/evidence` | `34:6` | #A9AEB5 | #4A5058 | Retrieved as evidence but not cited; neutral, never green |
| `color/track/cited` | `34:7` | alias → provenance | alias → provenance | Cited by a VERIFIED claim; the only green state |
| `color/track/focus` | `34:8` | alias → ink | alias → ink | Passage open in the inspector |
| `color/track/pending` | `34:9` | #868C94 @ 0.45 | #656B73 @ 0.40 | Dashed stroke while a source is processing |

- **CSS names at implementation:** `--track-indexed`, `--track-evidence`, `--track-cited`, `--track-focus`, `--track-pending`.

**Components reused:**
- Rail `9:150`
- Brand mark `4:84`
- Icons: check `4:12`, alert `4:21`, clock `4:30`, table `4:49`

**Figma working rules:**
- Load the `figma:figma-use` skill before any `use_figma` call.
- A `use_figma` script that errors is rolled back **entirely**. Re-run the whole script, not just the remainder.
- Text node names default to their characters, so filter by `type==='FRAME'` when searching for frames by name.
- `setBoundVariableForPaint` drops the paint's opacity. Use tokens that carry alpha instead.

## 2. Concept B design summary

- **Signature visual: the source track.** Each source is drawn as one row of segments, one segment per indexed passage, with width proportional to the passage's length. Page, timestamp or heading boundaries sit beneath.
  - **States, carried by shape as well as colour:**
    - indexed: half height, `track/indexed`;
    - evidence: full height, `track/evidence`;
    - cited: full height plus a dot, `track/cited`;
    - focus: plus an outline, `track/focus`.
  - **Where it appears:** the empty-state shelf, the investigation field, the brief receipt, sidenote locators, the inspector's vertical spine, Home inventory, and the sign-in motif (decorative, `aria-hidden`).
  - **Spreadsheets are NOT passages.** They render as table blocks sized by `row_count`.
- **Signature motion: "the pull".** Clicking a citation draws a thread to the passage. The inspector slides in beside the brief (no modal), its vertical track scrolls to and marks the passage, and the whole passage highlights. The Verified seal shows the saved status. Numbers that appear in both claim and passage get a neutral underline, labelled "text match, not verification".
- **Supporting motion: "the fold"**, triggered only by `investigation.completed` plus the saved report:
  1. Tracks rise into the receipt.
  2. Cited passages turn green (the first green of the whole run).
  3. Cited evidence cards become sidenotes, and uncited ones fade.
  4. Report sections fade up with a 70 ms stagger. This reveals finished text; it is not token streaming.
  5. The receipt stamps.
  - The whole fold takes 1.2 s. Under reduced motion it is a 150 ms cross-fade.
- **Stages** (the corrected real order): Understanding → Searching → Evidence → Writing → Verification.
- **Rejected ideas:**
  - a knowledge-graph hairball;
  - "thinking" particles;
  - percentage progress or an ETA;
  - confidence gauges;
  - glow, gradients or glass;
  - a 3D document stack;
  - animating every list;
  - a different hue per source.

## 3. Verified backend facts

All routes are under `/api/v1` and wrapped in `ResponseEnvelope{success,data,error,meta}`.

**Sources and passages:**
- `GET /workspaces/{id}/files` returns `DocumentResponse`. It has **no chunk count**. `processing_status` is `pending|processing|ready|partially_ready|failed`.
- `GET /workspaces/{id}/files/{file_id}/preview` returns ALL chunks with full `content`, ordered by `chunk_index`, **unpaginated**. Fields: `id, source_id, chunk_index, content, modality, page_number, cell_range, audio_start_ms, audio_end_ms, chunk_metadata, extraction_method, …`
- **No length or token column exists.** Only PDFs have `chunk_metadata.char_count`.
- DOCX `page_number` is always null; it has `chunk_metadata.heading` instead.
- **Spreadsheets create no chunks**, only `TabularDataset` rows (`files.py:133-163`). `cell_range` is never populated.
- Tables: `GET /workspaces/{id}/tables` returns `row_count, column_count, table_name, source_id`.

**Investigations:**
- `GET /investigations/{id}` returns `final_response`:
  - `executive_summary` is plain text with **no citations**;
  - `key_findings[{title,detail,claim_id|null}]`;
  - `claims` (VERIFIED only, until a source is deleted);
  - `claims[].citations` is a list of EvidenceItem UUIDs;
  - also `inferences`, `recommendations`, `rejected_proposals`, `missing_data_warnings`, `contradictions` (topic strings only) and `provider`.
- `GET /investigations/{id}/evidence` returns the lineage graph:
  - Node types: `source`, `extracted_content` (`data.content_id` = chunk id, `locator`, full `content`), `evidence` (`quote`, `coordinates`), `calculation` (`code`, `output`, `reproducibility_hash`), and claim nodes (`claim_code`, `verification_status`, `verification_errors`).
  - Edges: `EXTRACTED_FROM`, `SUPPORTED_BY_CONTENT`, `BACKED_BY`, `INPUT_TO`, `CALCULATED_FROM`, `DERIVED_FROM`, `SUPPORTS_INFERENCE`, `SUPPORTS_RECOMMENDATION`.
  - **No status gate:** it works mid-run once the evidence batch is committed.
  - **Caveats:** chunk nodes are not de-duplicated; evidence whose `chunk_id` is null is dropped (INNER JOIN); `chunk_index` appears only in the label string; `BACKED_BY` edges can point at deleted evidence.
- **No endpoint lists the investigations in a workspace** yet.

**Runtime:**
- Every retrieved chunk becomes an EvidenceItem, and `exact_quote` is the whole chunk (`service.py:137-150`). There is no "kept / set aside" filtering and there are no sub-span offsets.
- **Commit boundaries:**
  - `investigation.created` is committed immediately.
  - Planning and all tool steps, through the move to `synthesizing`, form ONE transaction committed at `runtime.py:662`.
  - Synthesis (LLM call, then claim validation, then the report) is a second transaction committed at `service.py:509`, emitting `synthesis.started`, `synthesis.completed` and `investigation.completed` together.
  - A failure rolls back and commits only `investigation.failed {code, failed_state}`.
  - So the browser sees nothing between creation and the end of search.
- **Events:** no event carries chunk, evidence, claim or score data. Payloads are small, for example `{from,to,reason}`, `{tool,attempt}`, `{step}`.
- **SSE** (`GET /investigations/{id}/stream`) reads the database every 1 s. It supports `Last-Event-ID` replay and has **no token streaming** (`ollama "stream": False`).
- **Frontend legacy SSE listeners are dead code:** `evidence_found`, `final_report` and the rest are never emitted by the backend.
- **Verification** (`validator.py:28-99`) checks citation integrity only: the evidence exists, belongs to this investigation and workspace, and the quote is a substring of the chunk.
  - It does NOT compare numbers or check whether the passage supports the claim.
  - The calculation hash check is circular; the calculation is never re-executed.
  - `detect_numeric_contradictions` is unused.
  - Contradiction detection is never called in production.
- **Claims** are created and validated only after the synthesis LLM call. Only VERIFIED or REJECTED statuses are written.
  - Rejected claims go to `rejected_proposals`.
  - If no claim is valid, the run fails with `EVIDENCE_INVALID` and everything rolls back.
- **Calculations:**
  - SQL (`tabular_sql_query`): `computed_output` is rows; `evidence_ids=[]`; `source_ids` = ALL workspace tables.
  - Python sandbox: `evidence_ids` = ALL session evidence.
  - In both cases provenance is loose, so never draw passage threads from calculations.
- **Deleting a source is a hard delete.**
  - Its chunks, evidence and contradictions are deleted.
  - Dependent claims are set to REJECTED with `SOURCE_DELETED`, and `final_response.claims` is rewritten with a warning added.
  - `key_findings` and `recommendations` are **not** updated, so the frontend must join findings to their claim's status.
- **No export feature exists.**

## 4. Truthfulness rules for implementation

- **Verified** may show only after BOTH `investigation.completed` (or a poll showing completed) AND a GET returning `claims[].verification_status === "VERIFIED"`. Re-read it on every view.
- Copy must say that Verified means the citation chain is verified, not the conclusion.
- During a run, evidence stays neutral (`track/evidence`). Green appears only from the fold.
- **Live stage mapping:**

| Browser receives | UI shows |
|---|---|
| `created` | Understanding is current: "Planning and searching" plus real elapsed time, and an empty tray note |
| The batch arrives | One 240 ms sweep marks Understanding, Searching and Evidence done, with real timestamps under "Saved events". Fetch `/evidence` and show neutral evidence. Writing is current. |
| `completed` | Verification done, then the fold |
| `failed` | Shown at `failed_state` |

- Findings whose `claim_id` is null get no citation. The summary is labelled uncited.
- **Charts appear only when** a VERIFIED claim cites a `calculation_id` of type `sql_query` whose output has at least 2 rows, one label column and one numeric column.
  - Plot exactly those rows.
  - The caption shows the query, the hash and the claim marker.
  - Label any non-zero axis.
  - Never chart numbers from prose. Never attribute a chart to a specific table by parsing the SQL; show the query verbatim.
- **Figure chips** are a frontend text match only: neutral styling, no check icons.
- **Edge cases:**
  - multiple citations: one thread each, and the Claim tab pages through them;
  - a shared passage: "Cited by claims 1, 3", grouped by chunk ID;
  - a rejected claim: listed under "What we couldn't support" with reason codes in plain language;
  - no evidence: `EVIDENCE_NOT_FOUND` failure copy;
  - a deleted source: a tombstone row plus REJECTED;
  - a missing passage: "Passage unavailable";
  - a calculation: ƒ marker and code, output and hash, with no passage threads.
- **Illustrative data to replace or remove:**
  - The other workspaces, file names and Northstar figures in Figma are example data.
  - Home per-question counts: only if the optional history fields are approved; otherwise remove them.
  - Home "10 sources" is the sum of `documents_count`.
  - "Last question X ago" comes from the history endpoint.

## 5. Scale, accessibility and responsive behaviour

**Scale:**
- Rendering: one `<svg>` per track with one `<path>` per state (about 4 DOM nodes at any passage count). Hit-testing uses a binary search over cumulative offsets.
- A segment needs about 3 px, so a 552 px field fits about 184 segments and a 326 px mobile track about 108.
- Above that, use **truthful bins**:
  - each bin is a contiguous range of `chunk_index`, with width equal to its total length;
  - its state is the strongest inside it (focus > cited > evidence > indexed);
  - cited passages always get a marker;
  - hover and aria text read like "Passages 1,204–1,230 · p.88–90 · 2 cited";
  - clicking opens a zoomed per-passage strip, so each cited passage resolves to its real chunk.
- The inspector's vertical track (780 px) stays per-passage up to about 250 passages.

**Accessibility:**
- Each track is one tab stop, and arrow keys move between evidence and cited passages. Labels read like "Passage 10 of 48, page 2, cited by claim 1".
- A "Passages used" list sits under a disclosure.
- Threads are `aria-hidden`; the relationship is stated in text in the inspector ("Cites" / "Cited by").
- Opening the inspector moves focus to its heading; Esc returns focus to the marker; [ and ] step through citations.
- The receipt has a spoken summary.
- Reduced motion: threads appear without drawing, and the fold becomes a cross-fade.

**Responsive:**

| Width | Layout |
|---|---|
| 1600 / 1440 | As designed |
| 1280 | Icon rail, sidenotes kept |
| 1024 | No sidenotes, only markers. The inspector is a right pane over the margin, not a modal, and threads draw only while it is open. The ledger moves below the tracks. |
| 768 | Rail drawer, inspector as a bottom sheet, no threads (a horizontal track with a you-are-here marker instead) |
| 390 | M1/M2 layouts, binned tracks, compact stage labels |

## 6. Backend/API change budget (none implemented)

| Change | Class |
|---|---|
| `GET /workspaces/{id}/investigations`: id, objective, status, created_at, completed_at; paginated; tenant-filtered; with tests | **REQUIRED** (already approved) |
| Passage map, e.g. `GET /workspaces/{id}/files/{file_id}/outline` → `{chunk_id, chunk_index, char_length (SQL length(content)), page_number, audio_start_ms, heading}`. No content; ideally columnar; tenant-filtered; read-only. | **REQUIRED** (needs user approval) |
| History row summary fields: `failure_code`, cited-evidence count, verified-claim count | OPTIONAL |
| Lineage cleanup: de-duplicate chunk nodes, put chunk_id/source_id on evidence data, LEFT JOIN null chunks | OPTIONAL (the client can work around it) |
| Per-step commits plus evidence events for live retrieval | OPTIONAL, **not recommended** (changes the verified Phase 3 commit and rollback semantics) |
| Token streaming, numeric verification, sub-passage offsets, cross-investigation coverage | NOT NEEDED |

## 7. Implementation plan once the API decision is made

Keep:
- `useInvestigationStream` (but ignore or remove its dead legacy listeners);
- `investigation-stages.ts`, updated to the five corrected stages;
- the api client and SWR;
- the routes and contracts;
- the fonts: Plex Sans, Source Serif 4 and Plex Mono via `next/font/local`;
- the `data-theme` System/Light/Dark setting with a pre-paint script.

Build on the existing committed UI work.

**Phases:**
1. Tokens (including `--track-*`) and themes.
2. Primitives plus the SourceTrack component: an SVG path renderer, bins and the a11y layer.
3. Shell, rail and the history endpoint.
4. Investigation field with batch-aware stages.
5. Brief: receipt, citations, sidenotes, SQL-only charts, the fold.
6. Inspector and the pull, replacing the `EvidenceLineageDrawer` modal.
7. Sources view.
8. Auth and Home.
9. Failure copy.
10. Keyboard layer and responsive behaviour.

**Verify each phase with:**
- `node --test scripts/ui_frontend_tests.cjs`;
- `npx tsc --noEmit`, lint and build;
- screenshots at 1600/1440/1280/1024/768/390 in both themes;
- a keyboard check and a reduced-motion check;
- a live E2E run on the `omniops-ubuntu` stack at http://localhost. Deployment notes are in section 2 of the first handoff.
