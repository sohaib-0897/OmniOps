# Session handoff: 2026-09-23

Read this together with `AGENTS.md` at the start of a fresh session. It records everything from the 2026-09-23 session: a live regression fix and the start of a product redesign in Figma.

---

## 1. Live regression fix: DONE and verified, NOT committed

**Symptom:** the UI showed "Analysis couldn't continue / Durable runtime could not complete the investigation / Stopped while understanding your request."

### Root causes (all proven against the live runtime)

1. **Synthesis prompt exceeded Ollama's context window.**
   - The Ollama provider sent no `num_ctx`, so Ollama used its 4096-token default.
   - Syntheses built from 6 or more evidence chunks overflowed it: 4,284–4,841 prompt tokens.
   - Ollama answered with HTTP 400 `exceed_context_size_error`, which the adapter reported as the misleading `PROVIDER_UNAVAILABLE`.
   - Failed runs: `bc2b6b71-…`, `56bff88d-…`, `e5b16003-…`.
   - The earlier successful E2Es (`ab0d6688…`, `302ab499…`) used a single chunk, about 1,255 tokens, so they never hit this.
2. **The failure rollback hid how far a run had got.**
   - `service.py` rolls back uncommitted events on failure. A post-planning failure (such as `EVIDENCE_NOT_FOUND` from an empty retrieval) therefore persisted only `created → failed`.
   - The UI accurately rendered that as "understanding your request", even though the run had planned and searched.
   - Reproduced as `d24114ab-…`: the objective `hello` on an xlsx-only workspace.
3. **Duplicate provider claim IDs crashed synthesis.** This was latent and only surfaced once fix 1 was in place.
   - `qwen3:4b` reused `claim_id`s. `validate_supporting_claims` then raised `MultipleResultsFound`, surfacing as `INVESTIGATION_FAILED` (run `68b833f3-…`).
   - The earlier `FINAL_AUDIT.md` note called the collision "not a defect". That was wrong, and the new note corrects it.

### Fixes (uncommitted in the working tree)

| File | Change |
|---|---|
| `backend/app/core/config.py` | New `OLLAMA_NUM_CTX: int = 8192` |
| `backend/app/llm/client.py` | Passes `num_ctx` to `OllamaProvider` |
| `backend/app/llm/ollama_provider.py` | Sends `options.num_ctx`, which must be > 0 |
| | HTTP 400 `exceed_context_size` becomes `PROVIDER_CONTEXT_EXCEEDED`, not retried |
| | Synthesis prompt asks for unique claim IDs |
| `backend/app/agent/service.py` | `investigation.failed` payload gains `failed_state`, the state reached before rollback, read via `sa_inspect(...).dict` so there is no lazy load |
| | A reused claim ID rejects every claim that shares it, with `DUPLICATE_CLAIM_ID:<id>` |
| `backend/app/evidence/validator.py` | Multiple matching rows give `AMBIGUOUS_CLAIM_REFERENCE` / `AMBIGUOUS_INFERENCE_REFERENCE` instead of a crash |
| `frontend/src/lib/investigation-stages.ts` | The stage is derived from `payload.failed_state` too. This file is part of the uncommitted UI work, not tracked yet |
| `docker-compose.yml`, `docker-compose.prod.yml`, `docker-compose.ubuntu.yml`, `.env.example` | Add `OLLAMA_NUM_CTX` (default 8192) |

**Tests added:**
- `backend/tests/test_ollama_provider.py`: `num_ctx` is sent and configurable; context overflow is explicit and not retried.
- `backend/tests/test_runtime_event_publication.py`: a post-planning failure records `failed_state`.
- `backend/tests/test_final_audit_closure.py`: duplicate claim IDs are rejected rather than crashing; an ambiguous verified-claim reference is an error.
- `scripts/ui_frontend_tests.cjs`: the failure stage follows `failed_state`.

**`FINAL_AUDIT.md`:** a new section was appended, "Post-v1.0.1 Live Regression — 'Analysis couldn't continue' (2026-09-23)". The earlier text is untouched.

### Verification
- **Backend:** 232 passed, 0 failed, 0 skipped. This ran against a throwaway pgvector container (`omniops-regress-pgtest` on 127.0.0.1:15433, user `omniops`, password `testpass`, db `omniops_test`), since removed. The CI test credential does not match the local `omniops-postgres` on 5432, so a throwaway container is needed.
- **Frontend unit tests:** 24/24 (`node --test scripts/ui_frontend_tests.cjs`).
- **Frontend:** TypeScript, lint and build all pass.
- **Live post-fix E2E through the public API:** `38ba7a3d-8ff1-4ca7-b525-54a5c2e803f9` completed.
  - 6 chunks, 7 verified claims, 3 recommendations.
  - SSE delivered through `investigation.completed`, and the lease was released.
  - The same prompt at the old `num_ctx=4096` still returns 400 (4,303 tokens), so this run genuinely exercises the fix.
- **Failure path:** `32769008-…` is still `EVIDENCE_NOT_FOUND`, with a null report, 0 evidence and claims, and the lease released. Its payload is `{"code":"EVIDENCE_NOT_FOUND","failed_state":"observing"}`.
- **Worker:** PID 79547, 0 restarts, 0 MissingGreenlet, 0 Traceback.

**Residual (not fixed):** a claim identical in statement and citations but under a different `claim_id` maps to the same row through logical-identity idempotency. The report then lists that claim twice (seen once in `38ba7a3d`).

### Git state and pending decision
- **Nothing is committed, pushed or tagged.**
- **Why not:** the frontend part of the fix lives in the user's uncommitted UI work (`investigation-stages.ts` is untracked, `ui_frontend_tests.cjs` is modified). Committing it would sweep in that work.
- **Pending question:** commit only the backend, config and audit files, or everything together?
- **GitHub rule:** before any push, ask "The fix is verified locally. Do you want me to push it to GitHub?" The user has not answered yet. Never push without approval.

---

## 2. Live deployment state

- **Stack:** `omniops-ubuntu` compose project behind Caddy at **http://localhost** (port 80).
- **Images:**
  - backend and worker: `omniops-backend:ubuntu` `63f74370…`, recreated 2026-09-23 10:56 UTC;
  - frontend: `omniops-frontend:ubuntu` `f60f1b68…`.
- **Environment:**
  - backend and worker run `LLM_PROVIDER=ollama`, `OLLAMA_MODEL=qwen3:4b`, `OLLAMA_TIMEOUT_SECONDS=90`, `OLLAMA_NUM_CTX=8192`;
  - Ollama is 0.34.2 on the host at `host.docker.internal:11434`;
  - the GPU is an RTX 4050 with 6 GB; `qwen3:4b` at 8192 context uses 3.87 GB of VRAM.
- **Readiness:** all ready.
- **A guard hook blocks commands that reference `.env.ubuntu.local`.** Build images with plain `docker build -f docker/Dockerfile.backend -t omniops-backend:ubuntu .`, then have the USER run:
  `docker compose -p omniops-ubuntu -f docker-compose.ubuntu.yml --env-file .env.ubuntu.local up -d --no-deps --no-build backend worker frontend`
- **Live Postgres:** reach it with `docker exec -i omniops-ubuntu-postgres-1 sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < file.sql`.
- **Containers are read-only:** pipe diagnostic scripts in with `docker exec -i -w /app omniops-ubuntu-worker-1 python - < script.py`.
- **Test data:** the regression runs left throwaway `regress-*@example.com` users and workspaces in the live DB.
- **Real test files:** `.tmp_test/OmniOps_Test_Business_Performance_Report.pdf` and `C:/Users/Sohaib/Downloads/sales_data.xlsx`.

---

## 3. Product redesign ("The Casefile"): plan APPROVED, Figma built, awaiting user review

- **Plan:** `C:\Users\Sohaib\.claude\plans\floofy-tumbling-music.md` holds the full diagnosis, direction, structure, design system, key states, risks and implementation phases.
- **Current status:** the Figma design is complete. **Code implementation must not start until the user reviews and approves the Figma file.**

### User decisions (confirmed)
1. **Investigation history:** add a read-only, tenant-filtered `GET /workspaces/{id}/investigations` (id, objective, status, created_at, completed_at; paginated), with tests. No other backend change.
2. **Figma first**, then implementation after approval.
3. **Fonts:** self-hosted IBM Plex Sans (interface), Source Serif 4 (answer prose) and IBM Plex Mono (trace IDs only), via `next/font/local`.

### Direction summary
- **Color means provenance.** A neutral interface, with one hue (sea-glass) reserved for evidence: citations, Verified status and passage highlights.
- **Read beside, never instead of.** A non-modal inspector pane (Passage / Claim / Source / Trace) on screens of 1280px and wider; a bottom sheet on mobile.
- **The answer is a document.** Serif prose with a strong lead. Citation numbers sit inline in the prose. An evidence margin (sidenotes) appears on wide screens.
- **Progress becomes the receipt.** Real stages only; when finished it collapses to "Grounded in N passages from M sources | K verified claims | 0 unsupported".
- **Honest edges.** Plain-language failure copy for each code, showing the stage via `failed_state`, with Edit question / Add a source / Open trace. There is also a "What we couldn't support" section.
- **Structure:**
  - Home lists workspaces with their recent questions and source readiness; the stats strip is removed.
  - The workspace rail holds a switcher, New investigation, Sources, day-grouped history, and account plus theme toggle.
  - Sources is a first-class view.
  - Themes use `data-theme`, default to the system setting, offer a System/Light/Dark toggle, and use a pre-paint script to avoid a flash.

### Figma file
- **URL:** https://www.figma.com/design/n8HW71cO0tdfkr7VzilqhJ (file key `n8HW71cO0tdfkr7VzilqhJ`)
- **Account:** `i220897@nu.edu.pk`. Use the **student team `team::1684564809586171082`**, which gets 200 MCP calls a day. The old Starter team `team::1684508844111154153` is limited to 20 calls a month; don't use it.
- **Pages:** Cover `0:1`, Foundations `3:2`, Components `3:4`, Screens / Desktop `3:6` (dark), Screens / Desktop light `3:7`, Screens / Mobile `3:8`.
- **Variable collections:** Primitives `VariableCollectionId:2:2` (hidden), Color `VariableCollectionId:2:36` (modes Dark `2:1`, Light `2:2`), Spacing `2:57`, Radius `2:68`.
- **Components:** icons frame `4:2` (20 lucide icons, e.g. check `4:12`, x `4:16`, alert-circle `4:21`, clock `4:30`, search `4:37`, file-text `4:43`, table `4:49`, plus `4:53`, panel-left `4:57`, chevron-down `4:60`, upload `4:65`, activity `4:68`, moon `4:75`, pencil `4:78`), Brand/Mark `4:84`, Button `4:149`, IconButton `4:158`, Input `5:45`, Chip `5:50`, StatusBadge `5:80`, CitationMarker `5:91`, Composer `6:122`, RailItem `6:136`, ProgressRow `6:163`, Receipt `6:164`, InspectorPane `7:283`, Rail `9:150`, TopBar `9:227`.
- **Screens (dark):** 01 Sign in `10:2`, 02 Home `10:61`, 03 Empty workspace `12:62`, 04 In progress `12:212`, 05 Brief with evidence margin `12:332`, 06 Brief with inspector `13:395`, 07 Sources `13:570`, 08 Failure `13:740`.
- **Screens (light):** `14:765`, `14:795`, `14:836`, `14:848`, `14:860`, `14:908`, `14:926`, `14:973`.
- **Mobile:** dark `16:2`, `16:53`, `16:103`; light `16:159`, `16:172`, `16:185`.

### Tokens

**Color (Dark / Light):**

| Token | Dark | Light |
|---|---|---|
| canvas | #111315 | #F6F7F8 |
| surface | #181A1D | #FFFFFF |
| raised | #1F2226 | **#EEF0F2** (changed from white so selected and hover states are visible) |
| line | #2A2E33 | #E3E5E8 |
| line-strong | #3A3F45 | #CDD1D6 |
| ink | #ECEEF0 | #15171A |
| ink-2 | #A9AEB5 | #4A5058 |
| ink-3 | #868C94 | #656B73 |
| action | ink | ink |
| action-hover | #CDD1D6 | #2A2E33 |
| provenance | #5CC4B4 | #0E7466 |
| provenance-strong | #8AD8CB | #0A5A4F |
| provenance-wash | 14% / 10% alpha of provenance | |
| caution | #E0B25C | **#8F5D00** (darkened for AA) |
| critical | #F07A7A | #C0392B |
| focus | the ink color, never provenance | |
| scrim | black 55% | #15171A 30% |

- **CSS names:** `var(--canvas)`, `var(--surface)`, `var(--raised)`, `var(--line)`, `var(--line-strong)`, `var(--ink)`, `var(--ink-2)`, `var(--ink-3)`, `var(--ink-inverse)`, `var(--action)`, `var(--action-hover)`, `var(--provenance)`, `var(--provenance-strong)`, `var(--provenance-wash)`, `var(--caution)`, `var(--caution-wash)`, `var(--critical)`, `var(--critical-wash)`, `var(--focus)`, `var(--scrim)`.
- **Contrast:** every text/background pair passes WCAG AA in both themes. The lowest is about 4.7:1.
- **Spacing:** `--space-*`: 2, 4, 8, 12, 16, 20, 24, 32, 48, 64.
- **Radius:** control 6, chip 10, pane 14, composer 22 (the composer only), full.

**Text styles:**

| Style | Font | Size / line height |
|---|---|---|
| UI/Meta | Plex Sans | 12/16 |
| UI/Label | Plex Sans Medium | 13/18 |
| UI/Body | Plex Sans | 14/20 |
| UI/Body strong | Plex Sans SemiBold | 14/20 |
| UI/Large | Plex Sans | 16/24 |
| UI/Title | Plex Sans SemiBold | 20/28 |
| Reading/Body | Source Serif 4 | 17/28 |
| Reading/Heading | Source Serif 4 SemiBold | 20/28 |
| Reading/Lead | Source Serif 4 Medium | 20/30 |
| Reading/Title | Source Serif 4 SemiBold | 26/32 |
| Reading/Display | Source Serif 4 Medium | 34/40 |
| Mono/Code | Plex Mono | 12/16 |

**Effect styles:** Elevation/Pane and Elevation/Dialog.

### Implementation notes for later
- **Findings without claims:** the real run returns key findings with `claim_id: null`. The frontend must anchor citations on the verified claims and match findings to their claims; don't invent links.
- **Keep:**
  - `useInvestigationStream`;
  - `investigation-stages.ts`;
  - the api client and SWR;
  - the routes and API contracts;
  - the truthfulness rules: no invented metrics, "Verified" only when VERIFIED, null confidence omitted, no reasoning or raw payloads.
- **Build on the uncommitted UI work;** don't discard it.
- **Implementation phases** (from the plan):
  1. tokens, themes and fonts;
  2. primitives;
  3. shell and rail plus the history endpoint;
  4. casefile, brief, inline citations and the receipt;
  5. the inspector, replacing the `EvidenceLineageDrawer` modal;
  6. the Sources view;
  7. auth and Home;
  8. failure copy;
  9. sidenotes and the keyboard layer.
- **Verify each phase with:**
  - `node --test scripts/ui_frontend_tests.cjs`;
  - `npx tsc --noEmit`, lint and build;
  - screenshots at 1600/1280/768/390 in both themes;
  - a keyboard check and a reduced-motion check;
  - a live E2E run.

### Figma working rules
- Load the `figma:figma-use` skill before any `use_figma` call, plus `figma-generate-library` or `figma-generate-design` as relevant.
- Frames created with `figma.createAutoLayout()` get a default white fill; clear it with `fills = []`.
- `resize()` resets sizing. After resizing an auto-layout frame, set `layoutSizingVertical = 'HUG'`, and set `layoutGrow = 1` again on spacers.
- A component set's shared TEXT property forces one default across all variants, so avoid it for per-variant labels.

---

## 4. Next steps
1. Wait for the user's review of the Figma file. Apply requested changes, or start implementation once approved.
2. Resolve the commit-scope question for the regression fix. Do not push without explicit approval.
