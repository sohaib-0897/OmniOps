# OmniOps intelligence workspace — visual refinement

Date: 2026-09-23. Local UI work only; no backend changes, release amendment, tag, push, or remote mutation.

## Rendered baseline and diagnosis

The running production application was captured before application edits. The baseline includes 22 screenshots at 1600, 1280, 768, and 390px. Screenshots are retained locally in `.tmp_test/design-before/` and are deliberately not release artifacts. Analytical screenshot content is explicitly authored test data, not provider output.

The old composition exposed source administration beside every task, used small text and bordered containers to establish hierarchy, and allowed the persistent follow-up composer to obscure much of the answer. Empty activity was accessible before there was an investigation. The evidence inspector exposed seven categories with empty records, while the actual quote appeared below implementation details.

## Architecture and design decisions

- Routes remain `/`, `/workspaces/[id]`, and the existing `/wallboard` redirect. No API contracts changed.
- WorkspaceHeader owns workspace selection, navigation collapse, mobile source access, and contextual Activity. Activity is absent until an investigation exists.
- A collapsible 224px desktop navigation surface supports a centered, 880px maximum conversation column. Paragraph measure is independently constrained to 68ch.
- Source upload, catalog, filtering, previews, and table profiles use existing components in contextual dialogs. Source search/filter is collapsed for small catalogs and initially exposed for catalogs above five files; it remains discoverable for every nonempty catalog.
- ObjectiveInput remains the real upload/start boundary, with multiline input, automatic height, attachment validation, source readiness, focus treatment, and Enter/Shift+Enter behavior.
- ConversationReport presents the executive answer, findings, actual citation references, three recommendations, and limitations. ExecutiveReportView retains all report sections and all recommendations.
- The follow-up composer rests as a compact expandable control; opening focuses the textarea. The UI continues to disclose independent investigation semantics.
- EvidenceLineageDrawer uses the same persisted graph traversal. Evidence and claims precede source details. Empty categories move into expandable lineage coverage; no relationships are inferred or deleted.

## Design system

Shared CSS roles cover canvas, navigation, interactive surface, inspector, primary/secondary/muted text, hairlines, control borders, radius, section spacing, prose measure, typography, and motion. System fonts avoid an external font dependency. Display type is 32–44px, headings 22px, analytical body 16px, labels 13px, and metadata 12px. Existing monospace metadata and citation roles remain.

Surface luminance establishes depth. Shadows are reserved for elevated controls and dialogs. Report sections use typography and spacing instead of repeated cards. The composer has a 20px radius, controls 8px, and floating surfaces 16px. The monochrome identity and semantic error colors remain.

## Runtime and motion

| Real state/event group | Presentation |
| --- | --- |
| Created, started, planning | Understanding your request |
| Plan, step, tool, observation, execution, replanning | Finding and reviewing evidence |
| Final verification (`all_steps_complete` / `verified_outputs`) | Verifying findings |
| Synthesis | Preparing your answer |
| Completed | Analysis complete |
| Failed/cancelled | Stop at the last known stage; show terminal state |

Rows retain stage keys and move from their previous measured position to their new position in 360ms. Completion resolves the previous surface height to the compact summary in 320ms. No animation drives application state. Reduced-motion preference disables movement, including cancelling active stage animations when the preference changes. Completed details enumerate only stages observed in runtime history. Unknown events do not invent progress. Zero-duration/missing timing is omitted.

## Critique and correction cycle

The first rendered pass was reviewed as a separate screenshot set in `.tmp_test/design-first-pass/`. Corrections addressed:

1. Mobile header truncation: compact brand treatment gives the workspace selector more room.
2. Clipped completion metadata: counts wrap below the title on narrow screens.
3. Excessive question-to-answer gap: reduced the transition spacing.
4. Duplicate evidence statement: the claim heading now uses its recorded identifier instead of repeating its body.
5. Competing duplicate source controls: the desktop header source control is hidden when navigation is open.
6. Inconsistent display wrapping: a shared 18ch display measure stabilizes the hero heading.
7. Trust issues: unverified finding actions no longer say verified; completed stage history is based on recorded events.

## Information preservation

| Capability | Before | After | Preserved? |
| --- | --- | --- | --- |
| New investigation | Composer and header action | Hero composer and navigation action | Yes |
| History | Current investigation, URL/browser history; no listing API | Same real model, lighter current-investigation navigation | Yes; same limitation |
| Source upload | Persistent upload zone and attachment | Attachment plus contextual source manager | Yes |
| Source processing | Catalog status and errors | Catalog status/errors plus composer readiness | Yes |
| Source search/filter | Always visible | Progressive disclosure | Yes |
| Executive Summary | Conversation and boxed report | Typeset brief and full report | Yes |
| Key Findings | Numbered findings | Stronger heading/body hierarchy | Yes |
| Claims | Structured report and inspection | Same data and inspection, fewer containers | Yes |
| Evidence | Seven-category lineage drawer | Evidence-first drawer and lineage coverage | Yes |
| Citations | Persisted IDs mapped to markers | Same mapping with quieter markers | Yes |
| Calculations | Formula/lineage section | Same section and source inspection | Yes |
| Inferences | Full report | Full report with existing qualifications | Yes |
| Recommendations | First in brief, all in full report | First three in brief, all in full report | Yes |
| Charts | MetricChartRenderer renders actual counts; no business time-series contract | Same renderer; no invented charts | Yes |
| Tables | Source table preview/profile | Same responsive table preview/profile | Yes |
| Verification | Actual status badges | Same statuses; more accurate action labels | Yes |
| Runtime stages | Previous/current/next from runtime | Same mapping with row continuity and completion resolution | Yes |
| Technical activity | Activity drawer | Contextual Activity drawer, less card styling | Yes |
| Full analysis | Expandable complete report | Expandable complete report | Yes |
| Errors | Message, retry, code and trace | Human-first message plus code and trace | Yes |

## Verification evidence

Final production-container screenshots are in `.tmp_test/design-final/`: 28 captures, zero page errors, no page-level horizontal overflow. Before/after fixtures use the same application components and contract shapes. Browser checks cover empty workspaces, sources, composer focus and growth/shrink, Shift+Enter, attachment, search/reset, source preview, mobile table preview, navigation collapse, all active stages, completion, brief, citations, full analysis, calculations, recommendations, Activity, provider failure, follow-up focus, and reduced motion.

Native dialogs were checked for keyboard focus containment and Escape closure, including stacked source/table inspection. This is focused accessibility verification, not a complete assistive-technology certification.

Commands:

- `npx tsc --noEmit` (frontend): PASS.
- `npm run lint` (frontend): PASS, no warnings/errors; Next.js prints its existing command-deprecation notice.
- `npm run build` (frontend): PASS.
- `node --test scripts/ui_frontend_tests.cjs`: 23 passed, 0 failed.
- `UI_BASE=http://localhost UI_PHASE=final node scripts/ui_design_browser.cjs` (equivalent PowerShell environment syntax used): PASS, 28 screenshots, 0 page errors.
- `UI_PHASE=after node scripts/ui_design_live_browser.cjs`: PASS for the actual persisted failure and Activity capture.
- Frontend-only Compose build/recreation: healthy, public frontend HTTP 200.

Workspace route bundle: 27.6kB, first-load JS 145kB (preceding refinement: 26.7kB / 145kB rounded). No dependency added. No performance benchmark beyond bundle comparison and browser responsiveness is claimed.

## Real business-report investigation

The existing `OmniOps_Test_Business_Performance_Report.pdf` was found in local deployment storage, copied into ignored QA storage, and uploaded through the real API in a dedicated QA workspace. Source processing reached `ready`. The exact requested investigation question was submitted to the existing runtime.

Investigation `bc2b6b71-592e-44b8-af13-16165e0afeff` failed with normalized code `PROVIDER_UNAVAILABLE`, zero reported token usage, and no final response. No provider settings were changed and no deliberate provider outage was introduced. The actual failed UI and persisted activity were captured before and after in `.tmp_test/design-live/`. Successful real long-form output could not be verified; the completed report screenshots are explicitly fixture-based.

## Remaining limits

- No investigation-list API exists; no fictitious history was added.
- No parent/thread memory contract exists; additional questions start independent investigations using workspace sources.
- There is no token-streaming report contract; the brief appears when the real final response is available.
- MetricChartRenderer currently displays actual report counts, not business time-series charts. The redesign does not fabricate quantitative series from prose.
- The real report run did not complete because of the provider failure above.
- Existing local HTTP session-refresh behavior required in-app navigation in the live QA browser; no authentication/backend changes were made.

Changes remain local and uncommitted. `audit.md`, backend implementation, provider configuration, and `.env.ubuntu.local` were not changed by this pass.

## Files changed in this pass

- `frontend/src/app/globals.css`
- `frontend/src/app/workspaces/[id]/page.tsx`
- `frontend/src/components/workspace/WorkspaceHeader.tsx`
- `frontend/src/components/workspace/ObjectiveInput.tsx`
- `frontend/src/components/workspace/SourceDataCatalog.tsx`
- `frontend/src/components/workspace/SourcePreviewModal.tsx`
- `frontend/src/components/workspace/LiveActivityStepper.tsx`
- `frontend/src/components/workspace/InvestigationProgress.tsx`
- `frontend/src/components/workspace/ConversationReport.tsx`
- `frontend/src/components/workspace/ExecutiveReportView.tsx`
- `frontend/src/components/workspace/EvidenceLineageDrawer.tsx`
- `frontend/src/lib/investigation-stages.ts`
- `scripts/ui_frontend_tests.cjs`
- `scripts/ui_design_browser.cjs`
- `scripts/ui_design_live.cjs`
- `scripts/ui_design_live_browser.cjs`
- `UI_DESIGN_REFINEMENT.md`

Earlier uncommitted UI work was preserved, including the existing changes in `FileUploadZone.tsx`, `useInvestigationStream.ts`, and `scripts/ui_refinement_browser.cjs`.
