# Frontend revamp verification

## Design and motion

The public story, authentication, Home, Sources, workspace, runtime, brief, and evidence inspector share a warm paper canvas, ink typography, and sea-glass provenance accent. Source sheets, passage tracks, and evidence threads explain the product. The public examples are labelled as illustrative; authenticated counts, stages, verification states, and citations come from the backend.

The design review covered all 22 files in `refs/`: 19–25 showed varied interactive pacing, 26–29 showed open composition and restraint, and 30–40 showed precise diagram and document treatments. The useful principles were direct interaction, space, and material clarity. The external artwork, layouts, copy, and identity were not copied. `refs/` remains local research and is ignored by Git.

The final landing page uses CSS transitions and small React state changes for source, passage, and evidence exhibits. It has visible hover and click invitations, keyboard controls, no continuous idle loop, and reduced-motion fallbacks. The authenticated application retains Motion for React for stage, evidence, composer, and view changes tied to observed backend state. GSAP and its superseded landing component were removed because the final route did not use them. Lenis, Anime.js, React Spring, and WebGL were not added. Public animation code does not load in the workspace bundle.

Every fresh page load begins light before first paint. Light, Dark, and System are available during the current page; System follows OS changes while selected. A reload returns to light as requested. The theme transition respects reduced motion.

## Password reset

`/forgot-password` requests a reset; `/reset-password` accepts the token from a URL fragment. Known and unknown accounts receive the same response. The backend rate limits by IP and hashed account key, stores only a SHA-256 hash of a cryptographically random token, and defaults to a 30-minute expiry. Confirmation consumes the token, changes the password, revokes all sessions and refresh tokens, and clears the refresh cookie. The visitor signs in with the new password. Invalid, expired, superseded, and reused tokens fail.

Development without SMTP writes the one-time link to a private file under the configured `STORAGE_DIR/dev-password-reset-outbox/`. Production requires authenticated STARTTLS SMTP and an HTTPS reset base URL unless the existing explicit insecure-HTTP deployment exception is enabled. `docker-compose.prod.yml` requires the mail settings. The Ubuntu Compose profile defaults to production unless `ENVIRONMENT=development` is set for local development. Apply Alembic head `20260928_password_reset` before starting the updated backend.

## Final local verification

- `node scripts/ui_frontend_tests.cjs`: 41 passed, 0 failed.
- `npx tsc --noEmit`, `npm run lint`, `npm run build`: passed. The final Next build reports first-load JS of 112 kB for `/`, login, and reset routes; 138 kB for `/app`; and 205 kB for `/workspaces/[id]`.
- `python .tmp_test/revamp_migration_check.py --pytest`: 248 backend tests passed, 3 warnings, on a dedicated local PostgreSQL test database. The same script without `--pytest` passed upgrade, one-step downgrade, and re-upgrade to the password-reset migration head.
- Browser QA against the final production frontend image: landing exhibits, sign in, forgot password, Home, Sources, empty workspace, genuine running investigation, completed brief, and evidence inspector were captured at 1440 × 900. A new investigation completed with 3 cited passages, 5 claims with verified citations, and 0 rejected claims. The UI reported no page errors.
- The updated backend was exercised separately in a production-frontend browser flow: registration, session restoration, reset request, reset confirmation, new-password sign-in, and one-time-link rejection passed with zero page errors. The source upload and delete-confirmation dialog passed against the existing local full stack.
- Responsive landing and authenticated Home probes at 1600, 1440, 1280, 1024, 768, and 390 px found zero horizontal overflow and zero page errors. The 390 px landing capture is in `docs/screenshots/mobile.png`. Reduced motion computed `0s` for decorative source transitions. Keyboard focus reached the skip link first and Enter opened a hero source. Theme checks observed light on first load, dark selection, System following OS changes, and light after reload.
- `docker build -f docker/Dockerfile.frontend -t omniops-frontend:revamp-final .`: passed. The final image served HTTP 200 with security headers and ran as UID/GID 10001.
- Earlier local production-browser sampling measured landing LCP 536 ms at 1440 px and 148 ms at 390 px, CLS 0 at both widths, 2 and 1 long tasks, 123 kB and 122 kB transferred JavaScript, and no running idle animation. These are local synthetic samples from before the final dependency cleanup, not field INP, GPU, or deployed performance measurements. No shader or WebGL effect ships.

The source backend used for the genuine investigation was the existing local Ubuntu stack, while the password-reset browser flow used the updated backend in an isolated local development database. The archived provider-failure rendering was inspected in an earlier browser pass from a real saved failure payload; it was not a fresh provider-failure run. External TLS ingress, a hosted runner, and field performance remain deployment work.
