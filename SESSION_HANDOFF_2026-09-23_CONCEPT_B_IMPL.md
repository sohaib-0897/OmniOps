# Session handoff: 2026-09-23, part 3 (Concept B implementation)

Read at the start of a fresh session, together with `AGENTS.md`, `SESSION_HANDOFF_2026-09-23.md` (deployment notes, section 2) and `SESSION_HANDOFF_2026-09-23_CONCEPT_B.md` (design, backend facts, truthfulness rules). This file supersedes their "next steps" sections.

## 0. Status and immediate next step

**Concept B implementation is IN PROGRESS.** The code is written and typechecks, lints and unit-tests cleanly. It is **NOT yet visually verified, NOT E2E tested, and the backend regression suite has NOT been rerun.**

**Blocked on the user.** The new backend image is built but not deployed. Before visual QA can start, the user must run:

```
! docker compose -p omniops-ubuntu -f docker-compose.ubuntu.yml --env-file .env.ubuntu.local up -d --no-deps --no-build backend worker
```

- A guard hook blocks Claude from any command that references `.env.ubuntu.local`, so the user always runs compose.
- Image `omniops-backend:ubuntu` is `sha256:c2a32c209c37…`, built 2026-09-23 17:28 UTC. It contains both new routes (verified with `docker run … python -c`).
- The old frontend container keeps working against the new backend.

**Rules (unchanged):**
- No push, no tags, no remote changes. Local commits are allowed only after the implementation and verification are complete.
- Before any remote operation, ask exactly: **"Concept B is implemented and verified locally. Do you want me to push it to GitHub?"**
- Never print `.env` values.
- Do not modify `audit.md`.

## 1. User's approved decisions (2026-09-23)

1. **Passage-map endpoint:** APPROVED and implemented.
2. **`GET /workspaces/{id}/investigations`:** APPROVED and implemented. Fields: id, objective, status, created_at, completed_at; paginated.
3. **Home summary fields** (cited-evidence count, verified-claim count, passage count): **NOT approved.** Remove per-question counts from the production Home. Home uses real objective, status, time and source context only.
4. **Per-step commits / live retrieval events:** NOT approved. Keep the runtime transaction model; animate the real batch arrival.
5. **Not approved:** token streaming, numeric verification, sub-passage offsets, cross-investigation coverage, fake progress, and fake counters.
6. **Wording:** `VERIFIED` means citation/lineage integrity only. The UI must say "citation verified", "claims with verified citations" or "supporting passage verified", never a bare fact-check claim. The persisted status stays unchanged.
7. **Figma is the visual source of truth** (file `n8HW71cO0tdfkr7VzilqhJ`, page `Concept B · Signature` `22:5`). Do not accept "close enough" CSS.
8. **Final live QA** uses the FY2026 PDF (`.tmp_test/OmniOps_Test_Business_Performance_Report.pdf`) plus one source large enough to trigger binning. It covers every item in the user's list: auth, Home/history, upload, track, binning, stages, batch, fold, citations, pull, inspector, chart provenance, failure, dark/light/system themes, responsive widths, keyboard and reduced motion.
9. **Technical verification:** focused endpoint tests, the backend regression suite, frontend tests, `tsc`, lint and build. Do not weaken tests.

## 2. Backend changes (done; uncommitted)

| File | Change |
|---|---|
| `backend/app/schemas/document.py` | `PassageMapResponse`: columnar `source_id, modality, processing_status, passage_count, chunk_id[], chunk_index[], char_length[], page_number[], audio_start_ms[], audio_end_ms[], heading[]` |
| `backend/app/schemas/investigation.py` | `InvestigationSummary`, `InvestigationHistoryPage{items,total,limit,offset}` |
| `backend/app/api/v1/files.py` | `GET /workspaces/{workspace_id}/files/{file_id}/outline` |
| | Membership via `get_workspace_membership` |
| | Source must belong to the workspace (else 404) |
| | Chunks filtered by source **and** workspace, ordered by `chunk_index` |
| | `char_length = func.length(content)` in SQL; content is never selected |
| | Heading comes from `chunk_metadata.heading`, truncated to 200 characters |
| `backend/app/api/v1/investigations.py` | `GET /workspaces/{workspace_id}/investigations?limit=1..100 (default 20)&offset=0..100000` |
| | Ordered newest first (`created_at desc, id desc`), with a total count |
| `backend/tests/test_concept_b_endpoints.py` | **13 tests, all pass (SQLite):** auth 401, ordering, PDF pages, DOCX headings, audio timestamps, empty/spreadsheet source, unknown/deleted 404, foreign workspace 403, cross-workspace source id 404, no content leakage (exact key set), history pagination/order/minimal fields, 422 out-of-range, tenant filtering |

**Still to do:**
- Full backend regression suite against a throwaway pgvector container. The last verified run was 232 passed.
- Recipe from the first handoff: container `omniops-regress-pgtest` on 127.0.0.1:15433, user `omniops`, password `testpass`, db `omniops_test`. Set `POSTGRES_TEST_DATABASE_URL`, then remove the container afterwards.

## 3. Frontend changes (done; uncommitted)

### Foundations
- **`frontend/src/app/globals.css`:** fully rewritten.
  - Tokens are channel variables (`--ink-rgb` etc.) with Dark as the default and Light under `:root[data-theme="light"]`, plus a `prefers-color-scheme` fallback when JS is off.
  - Semantic vars: `--canvas`, `--surface`, `--raised`, `--line(-strong)`, `--ink(-2/-3/-inverse)`, `--action(-hover)`, `--provenance(-strong/-wash)`, `--caution`, `--critical`, and `--track-indexed/evidence/cited/focus/pending`.
  - Text-style classes: `t-meta`, `t-label`, `t-body`, `t-body-strong`, `t-title`, `t-overline`, `r-body`, `r-heading`, `r-lead`, `r-title`, `r-display`, `mono`.
  - Component classes for the shell, track, composer, stage bar, field, brief, inspector, Home and auth, with motion keyframes.
  - **Breakpoints:** 1439 (icon rail when the inspector is open), 1279 (icon rail), 1199 (no sidenotes; inspector becomes a fixed right pane), 1023 (rail drawer and bottom-sheet inspector), 767 (mobile).
  - **Reduced motion:** `animation:none !important`; the fold becomes the `reduced-fade 150ms` cross-fade; thread `stroke-dashoffset:0`.
- **`frontend/tailwind.config.ts`:** `zinc` and `neutral` are remapped to tokens (50–200 → ink, 300 → ink-2, 400/500 → ink-3, 600/700 → line-strong, 800 → line, 900 → raised, 950 → canvas); `red` → critical and `amber` → caution. Adds semantic colours (`canvas`, `surface`, `raised`, `line`, `ink`, `provenance`…) and radii (`control` 6, `chip` 10, `pane` 14, `composer` 22). As a result, retained components follow the theme automatically.
- **`frontend/src/app/layout.tsx`:** `next/font/local` fonts: Plex Sans 400/500/600, Source Serif 4 variable, and Plex Mono 400 (`--font-plex-sans`, `--font-source-serif`, `--font-plex-mono`). Also adds the inline pre-paint theme script (the CSP already allows `'unsafe-inline'` and `font-src 'self'`).
- **`frontend/src/fonts/`:** latin woff2 subsets from @fontsource 5.3.0, plus `LICENSE-IBM-Plex.txt` and `LICENSE-Source-Serif-4.txt`. ƒ and → fall back to system fonts (not in the latin subset).
- **`frontend/next.config.mjs`:** dev-only `rewrites()` proxy when `OMNIOPS_DEV_API_PROXY` is set (for example `http://localhost`). It is never active in builds.

### Library
- **`lib/theme.ts`:** `THEME_BOOTSTRAP_SCRIPT`, `applyThemePreference` (localStorage key `omniops-theme`; a 200 ms `theme-transition` class, skipped under reduced motion) and `resolveTheme`.
- **`lib/source-track.ts`:** pure geometry.
  - `layoutTrack`: width proportional to `char_length` with a 1 px floor. It bins when `passages > floor((width+gap)/(minSegment+gap))`.
  - `binRanges`: contiguous ranges of roughly equal length; a bin's state is the strongest inside it.
  - Also: `unitAt` (binary search), `trackPaths` (one path per state; indexed half height, cited adds a dot, focus adds an outline), `unitLabel` (for example "Passage 10 of 48, page 2, cited by claims 1, 3" or "Passages 1,204–1,230 · p.88–90 · 2 cited"), `trackTicks`, `keyboardStops` and `passageLocator`.
- **`lib/brief-model.ts`:** `indexLineage`, `buildBrief`, `dedupeClaims`, `chartFromCalculation`, `sharedFigures` and `explainReason`.
  - `indexLineage` resolves evidence → content (`SUPPORTED_BY_CONTENT`) → source (`EXTRACTED_FROM`) and groups by chunk id. Calculations are keyed without the `calc_` prefix; the type comes from the label "Calc (sql_query)".
  - Citations come only from VERIFIED claims, numbered per distinct passage in reading order. `citedBy` records claim ordinals.
  - **Findings join:** by `claim_id`, or by an exact whitespace-normalised statement match with a VERIFIED claim. Otherwise the finding is uncited. Unmatched verified claims go into `otherClaims` ("Also supported").
  - `dedupeClaims` removes identical duplicates (same id, statement, citations and status). This was seen in real run `38ba7a3d` (CLM-006 twice).
  - Charts: only `sql_query` output of 2–24 rows with exactly 2 columns (one label, one numeric), cited by a VERIFIED claim.
  - The "unsupported" list covers REJECTED claims, `rejected_proposals`, `missing_data_warnings` and `contradictions`. `explainReason` maps backend codes (SOURCE_DELETED, DUPLICATE_CLAIM_ID, EVIDENCE_CONTENT_MISMATCH…) to plain language.
- **`lib/investigation-stages.ts`:** rewritten for the five stages `understand, search, evidence, write, verify` (Understanding → Searching → Evidence → Writing → Verification).
  - Runtime states map as: created/planning → 0, ready/running/executing → 1, observing/verifying/replanning → 2, synthesizing → 3 (4 if the failure code is EVIDENCE_INVALID).
  - A failure uses `payload.failed_state`.
  - `batchReceived` = a plan/tool/observation/synthesis event, **or** any `state.changed` whose `to` is beyond created/planning.
  - Completed gives index 5 (current = verify, next = null).
  - Also exports `describeEvent`, which gives safe labels and never echoes payload text. There are no timers.
- **`lib/failure-copy.ts`:** plain copy plus actions (edit/sources/retry/trace) per code: EVIDENCE_NOT_FOUND, EVIDENCE_INSUFFICIENT, EVIDENCE_INVALID, PROVIDER_* (including CONTEXT_EXCEEDED), CANCELLED and INVESTIGATION_FAILED, with a fallback.

### Hooks
- **`hooks/useInvestigationStream.ts`:** dead legacy SSE listeners removed (`investigation_started`, `evidence_found`, `final_report`…, the alias map and `eventData`). State gains `createdAt`, `completedAt` and `workspaceId`.
- **`hooks/useCasefileData.ts`:**
  - `useOutlines(workspaceId, files)` fetches outlines for non-spreadsheet sources. The SWR key includes processing status.
  - `useInvestigationHistory` polls at 4 s while any item is running.
  - `useLineage(id, generation)` fetches at "batch" and again at "completed". It guards with `session_id === id` so stale data from another investigation never shows.
- **`types/api.ts`:** adds `PassageMap`, `InvestigationSummary` and `InvestigationHistoryPage`.

### Components (`frontend/src/components/casefile/`)
- **`Brand.tsx`:** `BrandMark` (the Figma 4:84 geometry, tokenised) and `BrandLockup`. `ThemeToggle` cycles System → Light → Dark, with an optional "Theme: X" label.
- **`SourceTrack.tsx`:**
  - SVG track with hover tooltip, one tab stop, arrow/Home/End between evidence and cited passages, Enter to open, and an aria-live label.
  - Clicking a bin opens a zoomed per-passage strip (`sliceMap`).
  - Supports a vertical orientation (the inspector spine) and a decorative mode.
  - `TableBlocks` draws spreadsheets as one block per table, sized by `row_count`.
- **`SourceRow.tsx`:** file name, meta line (real pages, duration, passages, tables, rows), and a track or table blocks. Processing sources get a dashed outline; failed or empty sources get a message.
- **`Rail.tsx`:** brand row, collapse button, workspace switcher (menu of `/workspaces` plus "All casefiles"), New investigation, Sources count, day-grouped history with status icons (check = provenance, clock, alert = critical), and the account row (initials, name, sign-out menu, theme). Also exports `MobileBar`, `StatusIcon`, `groupByDay` and `initials`.
- **`Composer.tsx`:** upload logic from the old ObjectiveInput. Enter sends and Shift+Enter adds a newline. Has the scope chip and a round send button; minimum 5 characters. `ref.setObjective` supports prefill.
- **`EmptyWorkspace.tsx` (B03):** overline, serif display heading, composer, starter questions built from real file names, the "In scope" shelf with tracks and ticks, and the upload zone when there are no sources. Accepts `prefill`.
- **`InvestigationField.tsx` (B04/B05):**
  - `StageBar`, plus the field: source tracks with neutral evidence and "N of M passages retrieved as evidence", and evidence cards (6, then "+N more").
  - The ledger shows indexed / evidence / SQL calculations / "Claims with verified citations", with "—" until each is known.
  - Saved events show real timestamps.
  - A "Stop investigation" button (editors only) with the note that the run continues.
  - SQL is attributed to a spreadsheet only when there is exactly one spreadsheet.
- **`Brief.tsx` (B07):**
  - Receipt: seal, tracks of cited sources, counts ("N cited passages · M calculations | K claims with verified citations | R rejected"), a Trace link and a spoken summary.
  - Summary labelled "SUMMARY · uncited; the claims below carry the citations".
  - Key findings with inline citation markers; the `ƒN` calculation markers; "Also supported"; recommended actions (numbers in provenance colour only when backed by verified claims, otherwise a "Not linked…" note).
  - Disclosures: "What we couldn't support" and "Passages used".
  - Margin sidenotes: measured anchors stacked 96 px apart, with a tab and curved thread. The effect keys on a signature string to avoid a render loop.
  - Exports `Selection`, `Markers`, `passageLocatorLabel`, `excerpt` and `shortName`.
- **`EvidenceChart.tsx`:** a line for ordinal labels (Q1, FY, dates, months) with a non-zero axis labelled "Axis starts at X"; bars from zero for categories. The caption shows "SQL calculation · query and output in the inspector · hash abcd…xyz" plus the ƒ marker.
- **`Inspector.tsx` (B08):**
  - Tabs Passage / Claim / Source / Trace, and a `N / total` counter with ‹ › controls. `[` and `]` step through citations; Esc closes.
  - Focus moves to a hidden heading. The vertical spine track appears on the Passage tab.
  - **Seal copy:**
    - Before completion, or for an uncited passage: "Retrieved as evidence".
    - When VERIFIED: "Citation verified — …This checks the citation chain, not the conclusion."
    - Otherwise: rejected, with plain reasons.
  - Figure chips read "Also appears in this passage · text match, not verification", with `<mark>` underlines.
  - Also: shared passage "Cited by claims 1, 3", a 4-node lineage, a calculation panel (query, saved output, hash, no thread), and the Trace tab (reuses `LiveActivityStepper`).
- **`PullThread.tsx`:** a fixed SVG cubic from the marker to the passage block. Drawn only at ≥1200 px, re-measured on scroll/resize and after the 230 ms slide, animated with stroke-dashoffset.
- **`FailureView.tsx`:** "Analysis couldn't continue · stopped during <stage>", the plain title and body, the runtime message and the mono code, plus action buttons.
- **`SourcesView.tsx`:** the first-class Sources view: upload zone, rows with tracks, "Read passages" or table previews, and delete through a confirm dialog that explains claims will be REJECTED.

### Pages
- **`app/workspaces/[id]/page.tsx`:** rewritten orchestrator.
  - **Views** come from the URL: `?investigation=ID`, `?view=sources`, otherwise ask. Navigation uses `pushState` and `popstate`.
  - **Rail collapse** is stored in localStorage (`omniops-rail`); the drawer is used on mobile.
  - **Phases** go `field` → `folding` (280 ms, `fold-away`) → `brief`. The fold plays only if this view *witnessed* the run (`witnessedRun` ref), and uses a 150 ms fade under reduced motion. `Brief fold={foldPlayed}`.
  - **Brief model:** built only when `status==='completed'` and a `finalResponse` and lineage exist.
  - **Actions:** Failure → edit (prefills the composer), sources, retry (re-POST the objective) or trace. The inspector column (`data-inspector="open"`), the PullThread and the preview modals are mounted here. `canEdit = user_role !== 'viewer'`.
- **`app/page.tsx`:** rewritten.
  - **Sign-in (B01):** a 560 px left panel and the decorative `TraceMotif` (aria-hidden, deterministic segments) with "Every answer, traced to the passage it came from."
  - **Home "Casefiles" (B02):** "N workspaces · M sources" (the sum of `documents_count`) and a 3-column card grid. Each card fetches files, tables, history (limit 3) and outlines for the first 5 sources. Recent questions show the status icon, objective, relative time and status text ("Completed · X ago", "Running · started X ago", "Stopped before a brief was saved", "Cancelled"). **There are no per-question counts.**
  - Also: the New workspace dialog and the account menu with sign-out.
  - `relativeTime` is deliberately *not* exported, because Next pages cannot export extras.

### Retained and restyled via tokens
`ui/Dialog.tsx` (bg → `bg-surface`), `ui/Primitives.tsx`, `workspace/FileUploadZone.tsx`, `workspace/LiveActivityStepper.tsx`, `workspace/SourcePreviewModal.tsx` and `workspace/TabularPreviewModal.tsx`. The `wallboard` redirect is unchanged.

### Deleted (replaced)
`workspace/ConversationReport.tsx`, `ExecutiveReportView.tsx`, `InvestigationProgress.tsx`, `EvidenceLineageDrawer.tsx` (modal replaced by the inspector), `ObjectiveInput.tsx`, `WorkspaceHeader.tsx`, `SourceDataCatalog.tsx` and `MetricChartRenderer.tsx`.

### Tests
- **`scripts/ui_frontend_tests.cjs`:** rewritten, **37/37 pass** (`node --test scripts/ui_frontend_tests.cjs`).
  - Every previous truthfulness assertion was ported to the new components: missing verification never shows as verified, an unverified finding gets no marker, observed stages, failed_state mapping, recommendations, rejected claims, no charts from prose, HTML escaping, trace excludes reasoning/raw output, formatting, SSE errors, stage transitions, no timers and reduced-motion CSS.
  - New coverage: exact-statement join, dedupe, track proportionality, binning (1,500 passages), hit-testing/labels/ticks/keyboard stops, neutral evidence during a run, the citation-chain wording, shared passages, unresolved citations, figure chips, reason and failure copy, day grouping and theme resolution.
  - Note: the vm context in the test loader needs globals (Math, JSON…) and the markup is `renderToStaticMarkup` (no `<!-- -->`).
- **`npx tsc --noEmit`:** PASS. **`npm run lint`:** PASS (0 warnings). **`npm run build`:** NOT yet run.

## 4. Remaining work (in order)

1. The user deploys backend and worker (the command in section 0). Then confirm readiness: `/api/v1/health` and the new routes on http://localhost.
2. Run the dev frontend against the live stack for visual iteration:
   `cd frontend; $env:OMNIOPS_DEV_API_PROXY="http://localhost"; $env:NEXT_PUBLIC_API_URL="/api/v1"; npx next dev -p 3001`
   - The browser uses http://localhost:3001. Login works.
   - Refresh-cookie origin validation will reject `:3001`, so each page reload needs a re-login. That is acceptable for QA.
   - SSE through the Next proxy has not been verified; if it buffers, rely on the 1 s REST poller or QA on the deployed frontend.
3. **Visual comparison against Figma** (the reference PNGs are in the scratchpad `.../scratchpad/figma/`, which may be gone after restart; re-fetch with `get_screenshot`). Frames: B01 `27:741`, B02 `27:404`, B03 `22:6`, B04 `35:740`, B05 `35:937`, B06 motion `28:419`, B07 `25:259`, B08 `25:679`, light L08 `40:1286`, mobile M1 `30:722`, M2 `30:852`, direction board `31:740`.
   - **Key Figma measurements:**
     - Rail 264 px wide, padding 12. Brief content starts 80 px from the rail.
     - Brief text column 600 px, margin gap 56, sidenote column 300. Tab at column + 12 (−44 from the sidenote), thread 41 px.
     - Receipt 880×52, radius 12. Receipt track 150×6. Sidenote track 274×4.
     - B05 column is 880 px, centred. Field panel: main plus a 280 px ledger. Evidence cards in 2 columns.
     - B03 composer 720 px wide; heading r-display 34/40, max-width about 380.
     - Home cards about 384 px wide, 3 columns, gap 24, min height about 560 in the design.
     - Inspector 440 px; tabs row 56 px.
   - Screenshot at 1600/1440/1280/1024/768/390 in both themes, and check keyboard and reduced motion.
   - Possible QA tools: the `claude-in-chrome` skill, or Playwright if installed (unchecked).
4. **Known gaps and risks to check during QA:**
   - **Field threads** (the curved line from a track segment to an evidence card in B05) are NOT implemented.
   - **"Tracks rise into the receipt"** in the fold is approximated: the field fades up/away, then the brief sections write in with a 70 ms stagger, the receipt stamps, and sidenotes and threads fade in.
   - **Home "Processing"** is ink-2, not the green in the Figma B02 frame, so provenance colour stays reserved for citations. This is a deliberate deviation; mention it to the user.
   - The Brand mark uses the Figma geometry but tokenised colours (the exported asset hardcodes #ECEEF0, which is invisible in light mode).
   - The Sidenotes layout depends on measuring anchors; check the overlap stacking.
   - Check `SourceTrack` measurement inside flex containers (`initialWidth` fallback 552).
   - Check the vertical spine sizing, and the inspector at the 1199/1023 breakpoints (fixed pane, then bottom sheet).
   - The `.inspector-body` grid keeps an empty 24 px column when there is no spine.
   - The composer hint shows "↵"; the design showed "⌘ ↵".
5. Run `npm run build`, then the full backend regression (PostgreSQL throwaway), then `pip_audit` / `npm audit` if dependencies changed. No npm dependencies were added; the fonts were copied in as files.
6. Build the frontend image: `docker build -f docker/Dockerfile.frontend -t omniops-frontend:ubuntu .`. Make sure `src/fonts` is inside the build context and the `.dockerignore` doesn't exclude it. Then the user runs:
   `docker compose -p omniops-ubuntu -f docker-compose.ubuntu.yml --env-file .env.ubuntu.local up -d --no-deps --no-build frontend`
7. Final live E2E at http://localhost with the FY2026 PDF.
   - A binning test also needs a large source: generate a long PDF or DOCX locally (≥ ~200 passages for a 552 px track).
   - Record the run ids, then write the results into a remediation doc (for example a new section in `FINAL_AUDIT.md` or a `CONCEPT_B_IMPLEMENTATION.md`) with the real commands, counts and limitations.
8. A local commit is allowed only after verification. Then ask the push question in section 0 and wait.

## 5. Environment notes

- **Live stack:** Caddy at http://localhost. Containers include `omniops-ubuntu-backend-1`, `-worker-1`, `-frontend-1`, `-postgres-1` and `-sandbox-runner-1`. The live `CORS_ORIGINS` has no localhost entry.
- **Other containers:** `omniops-backend` (:8000) and `omniops-frontend` (:3000) are a *different*, older dev stack. Do not confuse them with omniops-ubuntu.
- **Live DB access:** `docker exec -i omniops-ubuntu-postgres-1 sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < file.sql`
- **Real report shape (run `38ba7a3d`):** `key_findings[].claim_id` is null, claim citations are bare EvidenceItem UUIDs, `calculation_ids` is empty, and CLM-006 is duplicated. The latest SQL calculation was `SELECT * FROM sales_data LIMIT 10` (6 columns, so no chart, correctly).
- **Working tree:** the untracked handoff files, `SKILL.md` and `UI Screenshots/` belong to the user. Leave them alone.
- **Tooling tip:** avoid bash/sed edits on files created with Write. The harness then echoes the whole file as a "changed on disk" notice, which wastes context. Use the Edit tool.
