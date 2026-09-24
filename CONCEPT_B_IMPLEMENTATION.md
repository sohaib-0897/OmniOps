# Concept B implementation: verification record

Date of final verification: 2026-09-24. Everything below comes from commands actually run. When a claim relies on an earlier session, the text says so.

## Status

**VERIFIED LOCALLY. Committed locally, not pushed.**

The Concept B "casefile" frontend and its two supporting backend endpoints are implemented. The deployed frontend passed live end-to-end QA on the single-VM Ubuntu stack at `http://localhost`. `audit.md` was not modified.

## Scope

The Figma file `n8HW71cO0tdfkr7VzilqhJ`, page `Concept B · Signature`, is the visual source of truth. The approved decisions, the design and the component map are recorded in `SESSION_HANDOFF_2026-09-23_CONCEPT_B.md` and `SESSION_HANDOFF_2026-09-23_CONCEPT_B_IMPL.md`.

### Backend

- **`GET /workspaces/{id}/files/{file_id}/outline`:** a columnar passage map.
  - Contains chunk ids, `char_length` (computed in SQL; content is never selected), pages, audio times and headings.
  - The query is filtered by membership, source and workspace.
- **`GET /workspaces/{id}/investigations`:** paginated history with only `id`, `objective`, `status`, `created_at` and `completed_at`.
- **Tests:** `backend/tests/test_concept_b_endpoints.py`, 13 in total. They cover auth, tenant isolation, cross-workspace ids, the exact key set (no content leakage), pagination and 422 bounds.

### Frontend

- **Tokens and theming:** a new token system with dark, light and system themes, and a pre-paint theme script. Fonts are self-hosted: IBM Plex Sans/Mono and Source Serif 4, with their licences included.
- **Screens:** sign-in (B01); Home "Casefiles" with real history (B02); the Ask view (B03); the live investigation field (B04/B05); the brief with receipt, citations and sidenotes (B07); the inspector with passage, claim, source and trace (B08); the failure view; and Sources.
- **Library:** track geometry and binning, the brief model built from verified lineage only, and stage derivation from persisted runtime state only.
- **Retired:** the legacy workspace components, whose replacements are listed in the implementation handoff.

## Truthfulness rules that the UI enforces

- A citation marker is drawn only for a claim whose persisted status is `VERIFIED`. The wording says "citation verified" or "claims with verified citations" and never presents a verified conclusion as fact-checked.
- Stages advance only on persisted runtime state or events. There is no elapsed-time advancement; a unit test checks that the stage module has no timers.
- Planning and search commit together as one batch, so the UI says so ("Planning and search in progress. Their events are saved together when this phase ends.") and animates the real arrival of that batch. It never fakes per-step progress.
- A failed run names the stage it stopped in only when the persisted `investigation.failed` event (`failed_state`) has been received. This was added in this session; see fix 2.
- Charts come only from saved SQL output with exactly two columns and 2–24 rows. Nothing is charted from prose.
- Home shows no per-question counts; they were not approved.

## Fixes made during final QA (2026-09-24)

1. **The pull thread struck through neighbouring citation markers.** When a claim had markers `1 2`, opening `1` drew the horizontal part of the thread through `2`.
   - **Fix:** `PullThread.tsx` now starts that part after the last marker that follows on the same line.
   - **Verified:** a geometric check clicked every marker. Across 18 markers on two briefs, in both themes, on dev and on the deployed build, 0 threads crossed another marker. A run of five markers `1–5` was also checked visually on the binned brief.
2. **The failure view could name a stage it had not observed.** When the persisted failure event had not been received (dev SSE buffering, or any SSE outage), a failed run fell back to stage 0: "stopped during understanding". The real run `a78bd0bc` had stopped in `observing`, which is **Evidence**.
   - **Fix:** the stage snapshot gains a `stageKnown` flag (`investigation-stages.ts`). When it is false, the stage bar marks no stage, the sub-status reads "Stopped · stage not received · CODE", and the failure view omits "stopped during …".
   - **Tests:** one test corrected (its fixture had lacked the failure event) and one added.
   - **Deployed build:** shows Evidence with `EVIDENCE_NOT_FOUND` and the runtime message.
3. **Added a unit test for `useStageDetail`.** It checks four things: the description plus real elapsed time, no clock without a persisted start time, the Writing clock counting from the persisted synthesis transition, and no sub-status on terminal runs. The existing `sharedLeadLines`/`excerpt` test already covered the excerpt rules, so nothing was added for them.

## Frontend Docker image (`docker/Dockerfile.frontend`)

### What failed

Two image builds failed:
- `apk upgrade libssl3 libcrypto3`: I/O error reaching the Alpine repository;
- `npm ci`: "Exit handler never called!"

### Diagnosis (evidence, not assumption)

- With the exact lockfile, `npm ci` **succeeded on `node:22-alpine`** (80 s) and on `node:22-trixie-slim` (92 s). The failure did not happen again in two tries (a standalone `npm ci`, then the image build).
- Every Node 22 image ships the same npm, 10.9.9, so changing distribution does not change npm.
- The failures coincided with an unreliable network and critically low host memory; a background build in this session was also stopped for low memory. The exact trigger of the npm crash in the failed run was not captured.
- The `apk upgrade` step was a no-op: the base image already has `libssl3`/`libcrypto3` 3.5.8-r0, and the index had nothing newer. Node bundles OpenSSL 3.5.8 statically and does not link the system library.

### Base image decision

The Alpine base was kept for both stages (musl in builder and runner, so the libc stays consistent). Debian slim was evaluated and rejected:
- `node:22-bookworm-slim` carries 2 critical CVEs in its Debian 12 base.
- `node:22-trixie-slim` would add OS-layer findings to the runtime (1 high each in `perl` and `zlib`, plus mediums and lows), where the current runtime scans at 0.

### Changes

- Removed the network-dependent, no-op `apk upgrade`.
- `RUN --mount=type=cache,target=/root/.npm npm ci` keeps npm's download cache between builds. The lockfile and integrity hashes are still enforced, and there are no retries.
- The runtime now also removes `corepack` and `yarn`/`yarnpkg`. Yarn 1.22.22 was present in the previously deployed image as well.

### Native dependencies

- sharp 0.35.4 (Next's optional image-optimization dependency) is copied into the standalone output. Because the lockfile records no libc, npm installs both the musl and glibc variants; the musl one loads in the runtime (libvips 8.18.6).
- SWC is used at build time only.
- `unrs-resolver` and `fsevents` never reach the runtime.

### Image verification

Image `sha256:f0fc8a689a59ee8b8c586d04bf347e4935cfa75e87366fdfd834d4032c048f08` was run read-only with a tmpfs `/tmp`, as compose runs it.

| Check | Result |
|---|---|
| Health | healthy |
| HTTP | 200 |
| Next start-up | ready in 342 ms |
| Runtime user | uid/gid 10001 |
| Root filesystem | not writable |
| npm, npx, corepack, yarn, pnpm | absent |
| Security headers | CSP, X-Frame-Options and X-Content-Type-Options present |
| Docker Scout | **0 critical, 0 high, 0 medium, 0 low**, the same as the previous image and the Phase 6 baseline |

### Deployment

- The user recreated the frontend with `up -d --no-deps --no-build frontend`.
- The container was created at 2026-09-24T11:59:50Z on image `f0fc8a689a59…`, which matches the `omniops-frontend:ubuntu` tag. It reported healthy with 0 restarts.
- The new code was confirmed in the served JavaScript: the `workspaces/[id]` chunk returned over HTTP contains the new text "stage not received". The previous image contained it in 0 files.
- Rollback tag: `omniops-frontend:ubuntu-prev-1ba705fd`.

## Verification commands and results

| Check | Command | Result |
|---|---|---|
| Frontend unit tests | `node --test scripts/ui_frontend_tests.cjs` | 41 passed, 0 failed |
| TypeScript | `npx tsc --noEmit` | exit 0 |
| Lint | `npm run lint` | no warnings or errors |
| Production build | `npm run build` | exit 0 |
| npm audit | `npm audit` | 0 vulnerabilities |
| Backend focused | `python -m pytest backend/tests/test_concept_b_endpoints.py -q` | 13 passed |
| Backend full regression | PostgreSQL throwaway container (previous session, 2026-09-23) | 245 passed, 0 failed, 0 skipped. Backend files were unchanged after that run (last modified 2026-09-23 16:45 UTC) |
| pip-audit | `python -m pip_audit -r backend/requirements.txt` | no known vulnerabilities |
| Dependencies | `git diff` of `package*.json` and `requirements.txt` | unchanged |

## Live QA on `http://localhost` (deployed frontend `f0fc8a68…`, backend `c2a32c20…`)

Everything used a throwaway user `qa-conceptb-*@example.com`. Credentials were kept only in a session scratchpad. The QA used Playwright (Chromium 1243) with a harness that drives the real UI; logins went through the real form.

### Live runs

| Run | Source | Result |
|---|---|---|
| `0212d241` | FY2026 PDF | completed. Brief with 6 claims with verified citations and 3 cited passages |
| `7f549d01` | FY2026 PDF | completed |
| `a78bd0bc` | CSV-only workspace, question about board minutes | failed with `EVIDENCE_NOT_FOUND`; persisted `failed_state = observing` |
| `fab37401` | FY2026 PDF, 1440 px, observed live | completed in 38 s |
| `13c4fb99` | FY2026 PDF, 390 px, observed live | completed in 37 s |
| `08757d3e` | synthetic PDF, 260 pages and 260 passages | completed. 5 cited passages and 1 claim with verified citations |

### SSE "Saved events" and stage truthfulness (run `fab37401`)

An independent SSE reader and a 150 ms DOM sampler ran on one clock.

| Run clock | Persisted state / SSE | UI |
|---|---|---|
| 5.0 s | run created (saved 12:01:46.47) | Understanding current, with the batch placeholder row |
| 19.4 s | planning, search and evidence batch committed (12:02:00.52–.82) | no change |
| 20.05 s | | Writing current |
| 20.21 s | | 5 evidence cards appear |
| 20.30 s | 37 batch events arrive over SSE | |
| 21.97 s | | "Saved events" lists the persisted events with their saved clock times, plus "32 earlier events in the trace" |
| 20–42.7 s | real synthesis | Writing stays current throughout |
| 42.67 s | synthesis and completion committed together (12:02:23.58) | |
| 42.77 s | | all stages done |
| 43.40 s | | brief opens |

- Every UI change happened after the matching persisted commit. When the UI moved slightly before the separate SSE reader saw an event, it had learned from the REST status poll, which reads persisted state.
- Run `13c4fb99` at 390 px showed the same ordering. The batch committed at 23.9 s and the UI changed at 24.25 s; completion committed at 40.66 s and the UI changed at 40.90 s.

### Screens and interaction checks

| Area | Result |
|---|---|
| B05 mid-run | Captured at 1440 and 390 px during genuine running investigations, with the stage bar and evidence grid both visible |
| Failure view | Deployed: Understanding and Searching done, Evidence stopped, "stopped during evidence", `EVIDENCE_NOT_FOUND`, and the runtime message with actions |
| Width and theme matrix | Home with history, Ask, Sources, brief, inspector and failure, in dark and light at 1440, 1024, 768 and 390: **48/48** with no horizontal overflow and the correct theme applied |
| Inspector | Close button on screen at every width (44×44 at 390). The scrim exists only below 1024. Esc closes it and returns focus to the citation that opened it |
| 390 px bottom sheet | Tapping the scrim closes it without activating anything underneath, in both themes. The close button is on screen |
| Theme | The toggle cycles System → Light → Dark on Home and in the workspace and stores only the preference. System follows the operating system both ways |
| Reduced motion | No running animations; the thread is drawn complete (`stroke-dashoffset: 0`) |
| Animations | The only infinite animation is the loading skeleton (`role="status"`), shown only while data loads. Stage and evidence animations fire on real state changes |
| Binning (260 passages) | The track uses mixed single-passage and two-passage bins ("Passages 127–128 · p.127–128"). Ticks: 21 on Sources and 19 on the Ask shelf, 0 overlapping. Clicking a bin opens the zoom strip; the keyboard announces "Passage 3 of 260, page 3". The inspector spine shows cited positions |
| Rate limiting | The QA's own burst of logins correctly triggered HTTP 429 (10 per 5 minutes). The affected check was rerun after the window cleared and passed |

## Deliberate design deviations from Figma

1. **Inline citation markers are kept in the text.** In Figma, the sidenote tabs or an edge chip act as the markers. Inline markers keep each citation next to the sentence it supports and are keyboard-reachable; the pull thread runs clear of them.
2. **The mini track on the receipt is hidden while the inspector is open**, to keep the narrowed brief column uncluttered. The inspector's spine shows the same source position.
3. **"Processing" on Home is ink-2, not the green used in Figma B02.** The provenance colour is reserved for verified citations.
4. **The composer hint is "↵", not "⌘ ↵",** because Enter sends and Shift+Enter adds a newline.
5. **The composer attach button is kept**, so a source can be added from the question box.

## Known limitations and items not verified

- **Not implemented from the design:** the field threads in B05 (a curved line from a track segment to an evidence card). The "tracks rise into the receipt" fold is approximated with a fade-and-stagger sequence.
- **No new Figma comparison in this session.** The earlier session's measurement-based comparison is recorded in `SESSION_HANDOFF_2026-09-23_CONCEPT_B_QA.md`; this session verified behaviour, layout integrity and themes.
- **Dev server buffers SSE.** Through the Next dev proxy (`next dev` with `OMNIOPS_DEV_API_PROXY`), SSE is buffered, so dev shows no live "Saved events". The deployed build streams correctly. This is dev-only.
- **Console 403 at first load.** The first page load logs a 403 from `POST /auth/refresh` when no refresh cookie exists yet. That is existing Phase 6 behaviour, not something Concept B changed.
- **Sources at 390 px:** the Delete action wraps onto its own line. It remains usable.
- **Backend regression evidence:** the full PostgreSQL regression (245 passed) comes from the previous session. This session re-ran only the 13 focused endpoint tests, and the backend files did not change in between.
- **Deployment gaps (unchanged):** the GitHub-hosted CI run and the production external runner and TLS ingress remain `NOT_RUN` / not live-deployed, as recorded in `AGENTS.md`.
