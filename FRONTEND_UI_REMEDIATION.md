# Final UI/UX Polish

Frontend UI classification: POLISHED

This record supersedes the earlier frontend-overhaul notes. Scope is frontend presentation and interaction, with small client corrections identified during verification. No backend, authentication policy, database schema, evidence semantics, deployment configuration, or historical `audit.md` changes were made in this pass.

## Design Direction

Calm, compact enterprise analytics: graphite canvas, restrained raised surfaces, fine borders, neutral navigation, and text hierarchy. Red identifies failures/destructive actions; amber identifies partial extraction or conflicts. Statuses include labels and icons. No gradients, decorative charts, or invented business metrics.

The pre-edit inventory covered every existing route (`/`, `/wallboard`, `/workspaces/[id]`), every workspace component, shared primitives, both data hooks, the API client, types, global styles, layout, and metadata. Findings included the sign-in restoration flash, oversized authenticated landing page, crowded source rows, silent deletion errors, missing modal focus containment, false verification labels, prose-derived chart values, generic lineage placeholders, and terminal-state loading/replay defects.

## Design System

- One dark token set; system font stack; compact heading/body/metadata hierarchy; tabular numbers.
- Consistent 4/8-based spacing and small radii. Dividers and rows replace unnecessary nested cards.
- Shared primary, secondary, outline, ghost, destructive and icon button styles, with hover, pressed, disabled and visible focus states.
- Lucide icons, generally 14–16 px; no functional emoji. Shared status, empty, loading and error components.
- Standard byte/count/duration formatting. Dates use the browser locale, with full local timestamps on hover where helpful. Missing measurements remain unavailable; null confidence is not invented.

## Navigation / Shell

Compact persistent workspace header, native keyboard-operable workspace selector, directory link, and new-investigation action. The authenticated root is the workspace directory; `/wallboard` redirects there to preserve bookmarks. Custom not-found and route-loading screens follow the same visual system. A monochrome SVG favicon and application metadata are included.

## Dashboard

Workspace directory with search, compact rows, updated dates, and actual API workspace/file/table counts. Unknown counts are unavailable rather than zero. Workspace creation uses a compact modal with inline feedback. No unsupported recent-investigation, revenue, growth, or provider-capacity statistics are displayed.

## Sources / Upload

Source rows show actual name, modality, formatted size, date, processing status, inspection and removal. Status filtering includes pending, processing, ready, partially ready and failed. Extracted tables are counted separately from uploaded files.

Drag/drop and file selection use an explicit queued/uploading/accepted/failed queue. Acceptance is distinguished from extraction readiness; no percentage progress is fabricated. Processing files poll at 2.5 seconds, and ready transitions refresh derived tables and workspace counts. Upload errors wrap without pushing filenames offscreen. Deletion requires confirmation, preserves the dialog on failure, and reports the error.

## Investigation UX

Focused objective composer with Ctrl/Cmd+Enter, clear submit state and synchronous duplicate-submit guard. Removed misleading depth presets: the backend accepts the parameter, but the current dispatcher does not use it to configure execution. The existing default request value remains unchanged.

An active or completed investigation shows its persisted objective in a compact header instead of another blank composer. Run identity is retained in the URL for reload/back navigation. Failed and cancelled investigations show explicit terminal views; no endless output spinner or fabricated completion.

## Runtime / Timeline

Operational trace with labeled lifecycle events, local timestamps, expandable safe identifiers, task status where supplied, durations where recorded, and observed evidence. Technical details use an allowlist of operational fields; reasoning and raw tool payloads are not displayed. The most recent 50 events render initially, with explicit disclosure of earlier events.

## Evidence / Provenance

Claims expose their actual verification status. Missing status is explicitly unreported; `REJECTED` is not verified. Null confidence is omitted. Calculations show available formula/code, output and recorded relationships.

The lineage drawer traverses actual ancestor and descendant edges for the selection. Its seven groups show linked source, extracted content, evidence, calculation, claim, inference and recommendation records; missing stages say “No linked record.” Generic source/calculation/recommendation placeholders were removed. Citations can open the underlying extracted source without losing the investigation URL.

Source previews show extracted content, page/cell/audio locations and extraction method where supplied. Table previews have horizontal overflow containment, column filtering, aligned numeric cells, a sticky sample header and explicit null values. Original-file PDF/image/audio playback is not advertised.

## Final Synthesis

Executive summary, supported key findings, separately labeled claims/inferences/recommendations, conflicts, caveats and references render only when present. Reference verification is qualified; it does not establish semantic truth. Copy feedback includes a visible failure path.

Removed regex-derived mixed-unit charts and average-confidence presentation. The remaining metric strip counts actual response records. No quantitative visualization is inferred from narrative numbers or dates.

## Responsive Design

- 1440 px and wider: source, investigation and trace columns.
- 1024–1439 px: source column plus a wide canvas; investigation/trace navigation.
- Below 1024 px: Sources / Investigation / Trace navigation; one primary panel at a time.
- Mobile forms avoid input zoom and use larger targets. Previews contain their own wide tables rather than widening the page.

## Accessibility

Visible focus, skip link, named icon buttons, labeled fields, related form errors, semantic headings/table headers, status text and reduced-motion support. Native modal dialogs make the background inert; explicit Tab/Shift+Tab wrapping addresses the browser focus-cycle issue found during QA. Escape, scroll locking, close controls and focus return are implemented. Workspace switching uses native select keyboard behavior.

## Authentication UX

Session restoration renders a neutral loading surface before choosing the authenticated or sign-in view. Access remains memory-only; Secure HttpOnly refresh cookies and refresh rotation are unchanged. Revoked sessions transition to sign-in with concise copy. Successful logout discards protected component/cache state through a full navigation before another account signs in. A failed logout is not reported as successful.

## SSE / Reconnect UX

Fetch streaming still uses the Authorization header and Last-Event-ID. No query bearer or browser token storage was introduced. Connection labels distinguish live, connecting, reconnecting and offline. Existing event/step/evidence identity dedupe remains in place; persisted legacy payload envelopes are also read correctly.

A focused reproduction found that a completed REST snapshot could close SSE before its second replay batch (one received instead of two). The client now stops terminal REST polling but retains SSE for the current view so replay can finish. Terminal status is not regressed by historical state transitions; navigation aborts the connection. A transport `done` event alone does not imply domain completion. New connections with an unrefreshable session return to sign-in.

The fallback REST poller permits only one outstanding read. Transient sync errors clear after a successful read; views do not reset during reconnect.

## Performance

No production dependency was added. Browser automation was installed temporarily and moved outside the application dependency tree; `npm ci` restored the lockfile before final verification. Recharts is no longer imported into the report route. Source filtering is memoized and trace DOM rendering is limited initially to 50 events; full list virtualization was not introduced.

Completed views keep one SSE connection while open to avoid truncating replay. This uses the existing server polling contract. These are local observations, not capacity or benchmark claims.

## Visual QA

Actual Microsoft Edge through Playwright, against a local Next.js production build and the existing production-mode Phase 6 backend/PostgreSQL stack. A temporary loopback HTTPS ingress uses the backend's existing allowed `https://localhost:13000` Origin and Secure cookies. It contains a test-only stream-disconnection control, not production code. No backend configuration was weakened.

Screenshots and machine-readable results are in `frontend-ui-evidence/`. Required desktop sizes are 1440×900 and 1280×800; mobile is 390×844. Additional 1024×800 and 768×900 views are checked. Auth, directory, sources, upload, composer, extracted preview, active trace, report/evidence, terminal/error and mobile panel states are covered by the two browser scripts.

Live auth, uploads, source/table extraction, investigation creation, provider-unavailable failure and cancellation use actual API routes. Completed report/lineage and held active-runtime states use explicitly labeled, authored QA fixtures in the dedicated closure database. Their verification labels are test inputs, not a live provider or semantic-verification result. No provider-generated report is claimed.

## Test Results

Final verification completed against the current frontend tree:

- `npx tsc --noEmit`: PASS (fresh serial run)
- `npm run lint`: PASS; no ESLint warnings or errors (Next.js deprecation notice only)
- `npm run build`: PASS; production route build completed successfully
- `npm audit --json`: PASS; 0 info/low/moderate/high/critical vulnerabilities across 464 dependencies
- Focused frontend interaction tests: 7 passed, 0 failed, 0 skipped
- SSE dedupe and persisted replay checks: PASS
- Browser QA: PASS at 1440x900, 1280x800, 1024/768 responsive breakpoints, and 390x844, including auth, upload, source preview, runtime, reconnect, report, lineage, table preview, cancellation, error, and not-found states.

The browser evidence uses authored local QA fixtures only; no provider output or production capacity claim is implied.

Final result collection is in progress. Commands:

```text
npm ci
npx tsc --noEmit
npm run lint
npm run build
npm audit --json
node --test scripts/ui_frontend_tests.cjs
node scripts/phase6_frontend_dedupe.cjs
node scripts/ui_stream_replay_test.cjs
node scripts/ui_browser_qa.cjs
python scripts/ui_qa_seed.py
node scripts/ui_runtime_browser_qa.cjs
```

The seven focused rendering/formatting/security tests pass. The existing REST/replay/reconnect dedupe probe passes. The new terminal replay regression passes after reproducing the failure. Final fresh gate and browser evidence will be recorded here before closure.

## Remaining UI Limitations

## Local Runtime Verification

- The local Next.js development server runs at `http://localhost:3001` when port 3000 is occupied.
- Development CSP permits Next.js hydration evaluation and explicitly permits the local API origins; production CSP remains stricter.
- The development API client targets `http://localhost:8000/api/v1` when no public API URL is configured and applies a bounded 10-second request timeout.
- Local sign-in requires the FastAPI backend to be listening on port 8000 with `localhost:3001` included in its development CORS origins. When the backend is unavailable, the UI now exits restoration and reports a recoverable error.
- Validation errors include backend field locations and messages where supplied.

- No compatible analysis provider is configured in the local production-like test stack; completed report presentation is tested with labeled fixtures, not a paid live analysis.
- Original PDF/image rendering and audio playback are not exposed by the existing preview contract. Extracted text and available provenance are supported.
- The canonical runtime currently exposes plan lifecycle/version events, not a full task list through the session API. The task view renders only when actual task payloads are supplied; no plan is reconstructed from hidden reasoning.
- Contradictions arrive as narrative strings; a structured two-evidence comparison cannot be invented. Calculation numeric inputs are not included in the lineage endpoint; available formulas, outputs and input relationships are shown.
- No cross-workspace investigation listing is exposed by the existing frontend contract, so the directory does not invent recent-run metrics.
- No screen-reader certification, physical mobile-device run, or production capacity benchmark is claimed.
- `next lint` reports upstream command deprecation, not lint errors. No tooling migration was added to this visual pass.

## Refined dark polish — 2026-09-11

The requested presentation pass adds shared graphite surfaces, 12px panels, 8px controls, larger headings and supporting labels, soft shadows, an elevated sign-in panel with password visibility, a focused composer, and roomier directory/source rows. Shared primitives carry this treatment into reports, previews, lineage, loading, error and not-found screens. Existing routes, authentication, evidence contracts and stream transport are preserved. No backend or schema changes are part of this pass; `audit.md` remains untouched.

Motion uses CSS and React only: 140ms control feedback, 200ms content, 240ms modal/drawer entrances and 160ms exits. Native modal focus/inertness persists through exit; content is retained, pending closes are cancelled on reopening/unmount, and overlapping drawer-to-preview handoffs share a scroll lock. Reduced motion removes CSS movement and exit delays. Trace motion is restricted to unseen timestamped events during an established live connection. Panel changes keep investigation state and streams mounted.

Evidence: `frontend-ui-evidence/polish/before` preserves screenshots from the earlier UI pass as historical baselines, not freshly executed pre-change captures. New sign-in captures cover 1440×900, 1280×800, 768×900 and 390×844. WebM recordings use an authored dialog harness executing the actual component and production CSS; the harness adds no application route. Report fixtures remain authored test data, not provider output.

Executed checks: TypeScript, lint and production builds passed; seven existing frontend tests passed; actual-hook reconnect/dedupe and terminal two-batch replay probes passed. The dialog browser harness passed closure, rapid reopening, focus return, scroll restoration, reduced motion and navigation cleanup. Live browser checks passed sign-in, search/create workspace, real TXT/CSV upload and processing, preview focus return, responsive panels, investigation submission and truthful provider failure, URL restoration, logout and not-found. Initial authentication test attempts exposed a submit-button accessibility issue; moving its live status outside the button resolved the regression. Browser launching and video encoder installation used approved execution outside the Windows sandbox.

Final production build (`$env:NEXT_PUBLIC_API_URL='/api/v1'; npm run build`) passed, including its TypeScript/lint gate. Fresh `node scripts/ui_frontend_tests.cjs` passed 7/7; `node scripts/phase6_frontend_dedupe.cjs` and `node scripts/ui_stream_replay_test.cjs` passed. The explicit public API setting is for the local HTTPS QA ingress only.

`node scripts/ui_browser_qa.cjs` passed the live workflow described above. `python scripts/ui_qa_seed.py` seeded only the dedicated QA database. `node scripts/ui_runtime_browser_qa.cjs` passed real SSE/offline/reconnect/cursor/dedupe, cancellation, report clipboard feedback, report/citation/source inspection, unknown verification and null-confidence presentation, extracted table preview, safe removal cancellation, and revoked-session redirect. These runs reported zero browser page errors. Results and screenshots are in `frontend-ui-evidence/browser-results.json` and `frontend-ui-evidence/runtime-browser-results.json`. Reports were captured at all four requested widths; source, composer, trace and preview captures additionally cover their responsive panel layouts.

`node scripts/ui_motion_qa.cjs` runs the actual Dialog component in an isolated authored browser fixture and writes `frontend-ui-evidence/polish/motion-results.json` plus WebM recordings. Sign-in buttons are checked for 44px width/height at 390px. Report and sign-in 200% **CSS zoom** overflow checks supplement responsive captures; OS/browser zoom and physical devices are not claimed. The original before screenshots are preserved, but no pre-change motion recording was available. Loading/error presentation uses shared primitives; no screen-reader certification or exhaustive contrast scan is claimed.

Calculated sRGB token contrast ratios: body `#d4d4d8` on panel `#181a1e` 11.79:1; supporting `#a1a1aa` on raised `#22252a` 6.00:1; primary `#09090b` on `#f4f4f5` 18.10:1; error `#fca5a5` on panel 9.18:1; warning `#fde68a` on panel 13.99:1. These cover selected opaque token pairs, not every composited rendered element. Desktop workspace and mobile sign-in captures were visually inspected. Provider-backed report generation remains unavailable; this pass does not change that limitation.

Final extended motion run: **7/7 PASS**, exit 0, including all four sign-in viewports, mobile button dimensions, 200% CSS zoom, rapid reopening, animated focus/scroll restoration, reduced motion and navigation cleanup. Runtime/report browser run exited 0 with nine recorded checks and 21 screenshots without horizontal overflow. Live workflow evidence contains 13 recorded checks. Final scoped `git diff --check` passed; only normal Windows LF/CRLF notices were emitted.
