# Session handoff: 2026-09-23, part 4 (Concept B visual QA, in progress)

Read with `AGENTS.md` and `SESSION_HANDOFF_2026-09-23_CONCEPT_B_IMPL.md` (whose rules still apply: no push/tags, ask the exact push question, never print `.env` values, do not touch `audit.md`, the user runs every compose command that references `.env.ubuntu.local`).

## Done this session (all uncommitted)

**Verification (pre-QA):**
- Backend full regression: 245 passed, 0 failed, 0 skipped (91 s), run against a throwaway pgvector container that was removed afterwards (232 earlier + 13 Concept B endpoint tests).
- Frontend: 37/37 unit tests, `tsc` and lint pass. `npm run build` passed before the QA edits.
- The user deployed backend and worker on image `c2a32c20`. The live `/outline` and `/investigations` history routes were verified with a throwaway user `qa-conceptb-*@example.com`. Credentials are only in the scratchpad `qa_creds.json`, and the workspace is "FY2026 performance review" `105f8d5c-…` with the FY2026 PDF.

**Live runs through the UI:** `8b86273a` (89 s) and `a2ee8a6d` (63 s), both completed.

**QA harness:**
- Dev server: `OMNIOPS_DEV_API_PROXY=http://localhost NEXT_PUBLIC_API_URL=/api/v1 npx next dev -p 3005`. Port 3001 is a different project (VigilAi); do not touch it.
- Persistent Playwright session: `scratchpad/qa-server.mjs` on 127.0.0.1:4777.
- Logins are rate-limited to 10 per 5 minutes. A page reload loses the memory-only token.
- **The Next dev proxy buffers SSE.** Through :3005 there are 0 events; directly through Caddy, 28 events with the first at 0.28 s. The dev QA therefore shows no live "Saved events" timeline. **Re-verify the timeline on the deployed frontend.**

**Fixes made from the Figma comparison (measured against Figma metadata, not by eye):**
- **Serif font:** now `source-serif-4-latin-opsz-normal.woff2` (wght + opsz axes). The old weight-only file rendered about 9% wider than Figma.
- **B01 sign-in:** spacing and tagline width.
- **B02 Home:**
  - 1200 content width;
  - 384×560 cards with 22/24 padding;
  - compact rows pitched at 40 px with a 6 px track;
  - divider at max(244, content);
  - header meta styling.
- **B03:**
  - composer 114 px tall (18 px rhythm, 34 px send button; a disabled send is shown at 45% opacity);
  - suggestions at weight 400;
  - shelf spacing;
  - tracks 10 px tall;
  - ticks 5 px, 3 px under the track, with the label beside the tick;
  - table blocks take a height.
- **B04/B05:**
  - 880 px column (`page-frame` max-width 960);
  - elapsed and stage spacing;
  - **bug:** the running stage sub-status was never shown (the page passed `detail=null`). Now `useStageDetail`;
  - field padding 20/24, label gap 4, ledger label 12 px, event rows 10 px padding, Stop button 34 px.
- **B07:**
  - grid 600 / 56 / 300 (it was 44, which crushed the margin);
  - `page-frame-wide` 1076, receipt 880, rhythm per Figma;
  - `.action-note` for recommendation sub-lines.
  - **Bug:** sidenotes never rendered on first mount. The parent ref is null during the child's layout effect; the grid is now resolved via `closest('.brief-grid')`, and the component re-measures on `animationend` and once fonts are ready.
  - Excerpts skip a running header repeated across passages (`sharedLeadLines`), plus a bare "Page N" line.
- **B08 (inspector open):**
  - brief at 32 px from the rail, single 600 px column, margin hidden, receipt track hidden;
  - inspector body: content at x52, spine column 16 px (a 6 px column had scaled the SVG to 37%), and the spine fills its height;
  - passage block 17/28 with a 3 px rule at x44;
  - the counter no longer wraps and the header gap no longer overflows.
  - **The pull thread now runs along the marker's line to the block edge and curves only in the gutter** (it used to cross the text).
- **Responsive:**
  - at 1024 the brief is padded clear of the fixed inspector pane;
  - below 1024 the bottom sheet is single-column, has a scrim that closes it on tap, and uses 14 px tab gaps.

## Update (later the same session)
- **Also fixed:**
  - stage nodes are evenly spaced edge to edge, and the sub-status sits under the current node;
  - evidence-card quotes are 12/16 ink-2;
  - a polled state past planning now counts as `batchReceived`, so without SSE the evidence appeared at 11 s rather than only at completion;
  - Esc returns focus to the element that opened the inspector;
  - stopped runs use the caution colour (Figma B02);
  - tick labels keep clear of each other on binned tracks;
  - the mobile sheet (single column, scrim, close button on screen);
  - the "Grounded" word is hidden on mobile.
- **Verified in dev:**
  - keyboard: Enter, `[`, `]`, Esc, track arrows and End;
  - reduced motion: no animations, and the thread is shown fully drawn;
  - binning with a synthetic 260-page PDF (workspace "Binning QA (synthetic)", run `307a56ae`);
  - failure `d486fc80` (`EVIDENCE_NOT_FOUND` on "Sales tables (QA)");
  - further completed runs `5abf2dc2` and `ab9912af`.
- **Checks:** frontend tests 39/39, `tsc`, lint and build all PASS.
- **Frontend image:** `omniops-frontend:ubuntu` `sha256:1ba705fd…` built, with 5 fonts and UID 10001. **Waiting for the user to deploy the frontend.**
- **Next:** live E2E on http://localhost. Confirm the SSE "Saved events" timeline and that the failure shows its real `failed_state` stage. Then the remediation document, a local commit, and the push question.

## Remaining (in order)

1. Re-shoot the 390 sheet and confirm the close button is on screen. Run lint, since the scrim is a clickable div.
2. Capture B05 mid-run: a new run, detected while `.stage-bar` and `.evidence-grid` both exist.
3. Failure view (for example `EVIDENCE_NOT_FOUND`), the Sources view, and Home with history.
4. Light theme at every width. Keyboard: `[`, `]`, Esc, track arrows, focus. Reduced motion (the harness takes `newContext(true)`).
5. Binning: a large generated PDF (≥200 passages).
6. Add unit tests for `sharedLeadLines` / `excerpt` and `useStageDetail`, then run tests, `tsc`, lint and build.
7. Build `omniops-frontend:ubuntu`. The user deploys the frontend. Run the live E2E on http://localhost, including the SSE timeline.
8. Write the results into a remediation document, commit locally, then ask the push question.

## Deliberate deviations to report
- Inline citation markers are kept, with the thread routed around them. In Figma, the sidenote tabs or an edge chip act as the markers.
- The mini track on the receipt is hidden while the inspector is open.
- "Processing" on Home is ink-2, not green.
- The composer hint is "↵" because Enter sends.
- The composer attach button is retained.
