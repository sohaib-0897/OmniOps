# Phase 4 Security Remediation

## Starting architecture

Before this phase, `PythonSandboxRunner` parsed code with an AST visitor and then launched the generated runner script with the backend host Python interpreter. The child received a reduced environment, but it still shared the host process/filesystem/network boundary and wrote its result to a host temporary path. `DuckDBTool` already used an in-memory connection with external access disabled and remains a separate, read-only tabular path.

`fetch_web_page_content` used `httpx.AsyncClient` with redirects disabled and manually revalidated redirect URLs. Its URL helper resolved DNS and rejected several private ranges, but it did not enforce a canonical port/content-size policy, stream response limits, or bind the validated DNS result to the actual connection target.

## Phase 4 implementation ledger

The implementation below establishes a dedicated sandbox execution service boundary and a single URL security policy. Runtime code fails closed when the configured sandbox service is unavailable; it never falls back to host `exec`, `eval`, or a direct Python subprocess for untrusted code. Web retrieval uses the centralized policy, bounded streaming, explicit timeouts, redirect revalidation, and untrusted-content labeling.

Detailed threat, test, deployment, and regression evidence is appended after the implementation and test runs.

# Phase 4 Security Remediation

## 1. Threat model

| Threat | Previous exposure | Mitigation | Verified |
| --- | --- | --- | --- |
| Host Python/repository access | AST plus host `Popen` shared the host boundary | Dedicated Docker image, no host mounts, read-only root, non-root UID | PASS — live container tests |
| Application secrets/environment | Reduced child env, but host process boundary | Explicit two-variable container environment; production backend calls internal runner | PASS — secret probe returned `{}` |
| Host/internal network | Host subprocess could open sockets | `network=none` / Docker `NetworkMode=none` | PASS — public, localhost, and PostgreSQL probes failed |
| CPU, memory, PID, output exhaustion | Only a wall-clock timeout | Docker CPU/memory/PID limits plus bounded stdout/stderr/result protocol | PASS — timeout, PID, output tests |
| SSRF loopback/private/metadata | Partial string/range checks | Canonical URL policy, global-IP classification, metadata/IPv4-mapped blocking | PASS — adversarial policy tests |
| DNS rebinding | Validation and request resolution could differ | Validation returns one allowed address; pinned transport connects to that address while preserving SNI/Host | PASS — pinned backend test and live example.com fetch |
| Redirect escape | Manual redirect validation but incomplete policy | Redirects disabled in client; every Location is normalized and fully revalidated | PASS — redirect/private and loop tests |
| Web response exhaustion | Full response buffered in memory | Content-Length precheck and bounded decoded streaming | PASS — oversized/chunked tests |
| Prompt injection from web data | No explicit trust label | Fetch results carry `content_trusted=false`, `content_label=UNTRUSTED_WEB_DATA`; no web content becomes runtime instructions | PASS — boundary regression |

## 2. Python sandbox architecture

`PythonSandboxRunner` validates syntax and known dangerous constructs, then delegates to either the internal `sandbox-runner` service or, in development/test only, the trusted Docker CLI launcher. It never executes user code with `exec`, `eval`, or a host Python subprocess. The dedicated image runs as UID/GID 65532, with `network=none`, a read-only root filesystem, all capabilities dropped, `no-new-privileges`, a 32-process limit, 256 MB memory limit, one CPU, and a 64 MB disposable `/tmp` tmpfs. Code and input are sent as bounded JSON; there are no repository, storage, home-directory, Docker-socket, or environment mounts.

The backend container has no Docker socket. Compose places the socket only in the internal runner service, which accepts a bearer-authenticated structured request and creates the constrained execution container through the Docker Engine API. Runner cleanup is forced and idempotent after normal completion, timeout, or infrastructure failure. Results distinguish success, policy rejection, timeout, resource limit, user-code failure, and infrastructure failure.

The local execution and runner images are built from the locally pinned `omniops-backend:2026.09.05` image; `/app` is removed from both final images and live probes show application paths are absent. Production should publish a separately pinned minimal Python image (preferably by immutable digest) and run the runner on a rootless/isolated worker host.

## 3. Sandbox test matrix

| Attack | Result |
| --- | --- |
| Read backend secrets | PASS — no `GEMINI_API_KEY`, `OPENAI_API_KEY`, `DATABASE_URL`, or `SECRET_KEY` |
| Read host repo | PASS — `/app`, `/workspace`, and `/host` are absent |
| Write host file | PASS — read-only root rejects `/outside-marker`; only disposable `/tmp` works |
| Internet access | PASS — `1.1.1.1:80` unavailable with network disabled |
| Localhost/backend access | PASS — localhost:8000 and PostgreSQL:5432 unavailable |
| Infinite loop | PASS — `SANDBOX_TIMEOUT` |
| Memory exhaustion | PASS — 512 MiB allocation was contained/terminated by the 256 MB Docker memory limit |
| Process explosion | PASS — PID-limited container terminated/bounded |
| Output flood | PASS — `SANDBOX_OUTPUT_LIMIT`, 64 KiB captured cap |
| Concurrent isolation | PASS — concurrent runs have distinct execution IDs and disposable filesystems |

## 4. Web retrieval architecture

`URLSecurityError` is the single policy error type. Only `http`/`https` are allowed; URL credentials, malformed/control/encoded hostnames, ambiguous numeric notation, and non-80/443 explicit ports are rejected. Hostnames are lowercased/IDNA-normalized, trailing dots are removed, and fragments are discarded. DNS resolution inspects every `getaddrinfo` answer and rejects non-global, loopback, private, link-local, multicast, reserved, unspecified, CGNAT, benchmarking, and metadata addresses, including IPv4-mapped IPv6.

The selected validated address is passed to `_PinnedNetworkBackend`, so the actual TCP connection cannot perform a second DNS lookup. TLS still uses the original hostname for certificate/SNI verification. The HTTP client disables proxy environment use and automatic redirects. Each redirect Location is resolved, normalized, DNS-checked, port-checked, and pinned again; redirect count is bounded at three. Content-Length is rejected early when oversized, and streamed decoded bytes are capped at 2 MiB with connect/read/total timeouts. Only HTML/XHTML/plain text is accepted. TLS verification remains enabled. Compressed responses are subject to the decoded-byte cap after HTTPX decompression.

Provider calls in `llm/*`, embeddings, and the fixed OpenAI Whisper endpoint are trusted outbound integrations with hardcoded HTTPS destinations; they do not accept user-controlled URLs. All user-controlled web retrieval uses `SafeWebRetriever`/`fetch_web_page_content`.

## 5. SSRF test matrix

| Attack | Result |
| --- | --- |
| 127.0.0.1 / 127.1 / localhost | PASS |
| RFC1918 IPv4 | PASS |
| Link-local / metadata IP | PASS |
| `::1`, ULA, link-local IPv6 | PASS |
| IPv4-mapped IPv6 | PASS |
| Integer/hex/octal/short IP notation | PASS — ambiguous forms rejected |
| DNS private result | PASS — any blocked answer rejects |
| DNS rebinding | PASS — validated address pinned into transport; no second resolution |
| Redirect to private | PASS |
| Redirect loop | PASS — bounded at three |
| Unsupported scheme | PASS |
| Embedded credentials | PASS |
| Oversized Content-Length | PASS before body read |
| Chunked oversized response | PASS — streaming cap |
| Compressed oversized response | PASS — decoded cap |
| Slow response | PASS — explicit total/read timeout policy |

## 6. Prompt-injection boundary

Fetched text is returned as source data with `content_trusted=false` and `content_label=UNTRUSTED_WEB_DATA`. The current agent registry has no web-content-to-instruction execution path; if a web capability is added, this labeled content must remain evidence/context and must never be concatenated into system/developer instructions or executable plan/tool input. The regression fixture containing “Ignore previous instructions” remained ordinary returned content.

## 7. Production deployment boundary

Local development/test may use the trusted Docker CLI launcher when Docker is available. The Compose deployment uses a separate internal `sandbox-runner`; the web/backend container does not mount `/var/run/docker.sock`, and the runner API is bearer-authenticated. This is a real boundary between the API process and user code, but the current local Compose runner still has a Docker Engine socket and the sandbox image is derived from the locally pinned backend image for reproducible offline builds. For production, deploy the runner on a dedicated/rootless or isolated worker host with a separately pinned minimal image; the external host and immutable production image digest remain deployment requirements.

## 8. Security configuration

Defaults are explicit in `Settings` and `.env.example`: 5-second sandbox timeout, 256 MB memory, one configurable CPU, 32 PIDs, 64 KiB stdout/stderr, 256 KiB protocol output, 10 artifacts, no network, HTTP/HTTPS only, ports 80/443 only, 5-second connect, 10-second read, 20-second total web timeout, three redirects, and 2 MiB received/decoded response limits.

## 9. Static scan

| Match | Classification |
| --- | --- |
| `python_sandbox.py` `subprocess.Popen` | Trusted Docker CLI launcher only; it starts the constrained image, never user Python on the host |
| `sandbox_runner_server.py` Docker Engine UDS | Dedicated runner service only; not mounted into backend |
| `docker-compose.dev.yml` Docker socket | Intentional local-development-only runner mount; explicitly labeled not production safe |
| production `docker-compose.yml` | No Docker socket or runner service; backend requires authenticated remote runner |
| `docker/sandbox_runner.py` `exec` | Trusted code wrapper inside the isolated image; user source is static-validated before production request and contained by OS isolation |
| `llm/*`, `rag/embeddings.py`, `audio_parser.py` HTTP clients | Fixed provider integrations, not user-controlled URL retrieval; TLS/protocol endpoints are hardcoded |

No `--privileged`, `network=host`, `verify=False`, or automatic-follow-redirect production fetch remains.

## 10. Regression results

- Phase 4 security suite: **66 passed, 0 failed, 0 skipped** (`test_phase4_sandbox_security.py`, `test_phase4_ssrf_policy.py`, `test_phase4_runner_boundary.py`, existing sandbox/SSRF tests), run with Docker engine access (20.06 seconds); the direct production-launcher fail-closed regression is included.
- Backend suite: **138 passed, 0 failed, 0 skipped** (final run, including all Phase 4 tests; 72.94 seconds).
- Phase 3 durability regression: **27 passed, 0 failed, 0 skipped** (20.81 seconds; live PostgreSQL configured for concurrency cases).
- Phase 1 evaluation: **15/15 passed**; quality metrics `NOT_MEASURED` (mean scenario latency 186.1 ms).
- Live PostgreSQL retrieval regression: **5 passed, 0 failed, 0 skipped** (30.04 seconds).
- Frontend TypeScript: **PASS** (`npx tsc --noEmit`, exit 0); lint: **PASS** (`npm run lint`, exit 0); production build: **PASS** (`npm run build`, exit 0; Next.js 15.1.0).
- Migrations: **PASS** — current live PostgreSQL head `20260910_phase38_replan`; `alembic upgrade head` exit 0; no Phase 4 schema change.
- Backend compile: **PASS** — `python -m compileall -q backend` exit 0.
- Docker build: **PASS** — backend, frontend, sandbox image, and runner images built.
- Production base Compose smoke: **PASS** — backend container has no `docker.sock` mount; with `SANDBOX_EXECUTION_MODE=remote` and no runner URL, execution returned `SANDBOX_UNAVAILABLE`.
- Local development Compose smoke: **PASS** — PostgreSQL healthy, backend healthy, sandbox-runner healthy, frontend running; backend health HTTP 200 and frontend HTTP 200; backend-to-runner isolated computation returned 42.
- Production runner live verification: **NOT LIVE-VERIFIED** — this environment provides Docker Desktop, not a separately provisioned rootless/isolated production host; repository production mode is remote-only and fail-closed.
- Controlled live web fetch: **PASS** — `https://example.com` returned HTTP 200 through the pinned transport.

## 11. Remaining security risks

1. A production rootless/isolated runner host is not instantiated in this local environment; production configuration requires the external runner and fails closed without it.
2. The development Compose token fallback is a local-development convenience; production must inject a strong secret through `SANDBOX_RUNNER_TOKEN` rather than use the documented local default.
3. Python’s stdlib image intentionally does not bundle heavy analytical packages; adding packages requires a reviewed, pinned image rebuild.
4. Web DNS pinning is implemented for this HTTPX/httpcore version and tested with a pinned backend; future HTTP library upgrades must preserve that transport contract.
5. Web content is labeled untrusted, but no system can guarantee semantic prompt-injection resistance; downstream prompts must preserve the data/instruction separation.
6. `pip-audit` is not installed in the available environment (`python -m pip_audit --version` returned `No module named pip_audit`), so no automated Python dependency vulnerability inventory was produced in this run.

## 12. Phase 4 classification

**VERIFIED (repository implementation); production host deployment not live-verified.** The production Compose configuration contains no Docker socket and forces `SANDBOX_EXECUTION_MODE=remote`; missing runner configuration returns `SANDBOX_UNAVAILABLE`. The socket-bearing runner exists only in the explicitly named development override. Production still requires deployment of that narrow runner API on a dedicated/rootless or isolated host with a pinned image digest; that external host is not available in this local environment.

## 13. Final production boundary verification

### Deployment modes

| Mode | Runner | Docker socket | Production safe |
| --- | --- | --- | --- |
| Local development | `docker-compose.dev.yml` dedicated runner | Development override only | DEVELOPMENT ONLY — NOT PRODUCTION SAFE |
| Test | `ContainerSandboxRunner` with Docker CLI and constrained image | Test host only | Test-only boundary |
| Production | External authenticated `SANDBOX_RUNNER_URL` | None in backend or production Compose | YES, when deployed on rootless/isolated runner host |

### Privilege boundaries

| Boundary | Result |
| --- | --- |
| API → Docker host | PASS — base/production Compose has no socket and backend has no Docker client launcher in remote mode |
| API → runner | PASS — narrow `/v1/execute` contract over authenticated URL; no public runner port in base Compose |
| Runner → execution runtime | IMPLEMENTED — runner creates only fixed-policy containers; rootless/isolated host is a deployment requirement |
| Sandbox → runner | PASS — sandbox network is disabled and no socket is mounted |
| Sandbox → network | PASS — `NetworkMode=none` |
| Sandbox → host filesystem | PASS — no host mounts, read-only root, disposable tmpfs |
| Sandbox → backend secrets | PASS — explicit minimal environment |

### Fail-closed tests

| Scenario | Result |
| --- | --- |
| Runner unavailable | PASS — `SANDBOX_UNAVAILABLE` |
| Local Docker available in production mode | PASS — local launcher not called |
| Invalid runner authentication | PASS — HTTP 401 |
| Arbitrary image request | PASS — contract rejects unknown field |
| Host mount request | PASS — contract rejects unknown field |
| Network-enable request | PASS — contract rejects unknown field |
| Privileged request | PASS — contract rejects unknown field |

### Image security

The execution image is fixed to `omniops-python-sandbox:2026.09.05` in local/test defaults; users cannot select an image through the runner contract. Production deployment must replace the version tag with an immutable digest, publish the reviewed minimal image, and update it through a controlled image-review process. The image runs as UID/GID 65532 with no network, read-only root, dropped capabilities, `no-new-privileges`, bounded CPU/memory/PIDs, and isolated tmpfs.

### Production deployment requirement

Deploy `sandbox_runner_server.py` as an internal, bearer-authenticated service on a dedicated/rootless or isolated worker host. Only the runner may access that host's container runtime. Configure the backend with `SANDBOX_EXECUTION_MODE=remote`, a private `SANDBOX_RUNNER_URL`, a strong injected `SANDBOX_RUNNER_TOKEN`, and an immutable `SANDBOX_IMAGE` digest. Never mount `/var/run/docker.sock` into the web/API container; the development override is explicitly not production safe.
