# OmniOps Operations

Production uses `docker-compose.prod.yml` as a vendor-neutral reference. PostgreSQL, HTTPS/load balancing, secret injection, durable storage, and the authenticated sandbox runner are deployment services—not containers hidden inside the web process. Run the one-shot migration service before scaling backend replicas and admit traffic only after `/api/v1/readiness` succeeds.

## Backup and restore

Back up PostgreSQL with managed snapshots plus regular custom-format dumps:

```sh
pg_dump --format=custom --no-owner --file=omniops.dump "$DATABASE_URL"
pg_restore --list omniops.dump
```

Back up the persistent upload volume/object store on the same recovery schedule. A database-only restore leaves source paths without their corresponding objects. To restore, provision a clean compatible PostgreSQL major version, restore the dump, restore objects at their original keys, run `alembic upgrade head`, then verify readiness and perform authorized source-preview and retrieval smoke tests before reopening traffic. Test this procedure periodically in an isolated recovery environment. Never restore over the active production database.

## Retention and recovery policy hooks

Operators must define retention periods for source files, derived Parquet files, runtime events, audit/security logs, and revoked/expired sessions. Session/token rows may be purged only after session expiry plus the security investigation window. Runtime events are the SSE replay source and must not be deleted while investigations remain inspectable. Application logs should be shipped with access controls and bounded retention; credentials and source content are excluded by design.

Local filesystem storage is supported through a persistent volume. Ephemeral container filesystems are not durable production storage. S3-compatible storage is not yet implemented; deployments needing multi-region/object-level durability must supply a shared persistent mount or add an authorized object-storage adapter.

## Release and rollback

The CI configuration defines tests, audits, and immutable SHA-tagged image builds. Its configuration and equivalent commands have been verified locally; a GitHub-hosted run has not been observed in this closure pass. The release workflow packages images; operators must run migrations once, deploy those images, wait for readiness, and run health/auth/retrieval smoke tests. Roll back application images only when the current database revision is backward-compatible. Schema rollback requires a reviewed maintenance procedure and a verified backup.

## Deployment controls

TLS/HSTS are enforced at the HTTPS edge. Malware scanning is a deployment control and is not built into OmniOps: place a real scanner/quarantine workflow before accepted objects become available, fail closed on scanner timeout, and retain scan results. The sandbox runner belongs on a separately protected/rootless-capable host; the development Docker-socket overlay is never a production topology.

The durable worker requires controlled outbound access to the configured model provider in addition to database, storage, and authenticated runner connectivity. That egress must not be attached to the sandbox runner or its untrusted payloads; sandbox payload execution remains network-disabled. Provider authentication, rate-limit, quota, timeout, and availability failures are explicit and never produce fallback reports. Semantic embedding availability depends separately on a compatible configured embedding provider, while lexical PostgreSQL retrieval remains available when embeddings are unavailable.

## Local Ollama text provider

Set `LLM_PROVIDER=ollama`, `OLLAMA_BASE_URL=http://host.docker.internal:11434`,
and `OLLAMA_MODEL=qwen3:4b` for the Docker Desktop topology. Install Ollama on
the host, run `ollama pull qwen3:4b`, and confirm `/api/v1/readiness` reports the
configured model as ready. Direct host processes should use
`OLLAMA_BASE_URL=http://127.0.0.1:11434`. The worker and backend may reach that
endpoint; the sandbox runner does not receive this configuration and launches
untrusted payloads with networking disabled.

Ollama supplies only planning, tool selection, and evidence-aware synthesis.
Gemini remains the optional hosted text provider and the configured provider for
genuine image vision and audio transcription. Provider selection never fails
over automatically. Ollama does not supply embeddings in this release; semantic
retrieval truthfully reports unavailable when no compatible embedding provider
exists, while lexical PostgreSQL retrieval continues to operate.
