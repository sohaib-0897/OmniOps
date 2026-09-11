"""Slow-reader, worker kill, foreign-cursor, migration and identity evidence."""
import asyncio
import json
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
import httpx
from sqlalchemy import select, delete, text, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
import phase6_live_closure as probe
from phase6_topology import docker
from app.models.user import User, RateLimitBucket
from app.models.investigation import InvestigationSession, AgentToolAttempt, AgentPlanStep, AgentPlan
from app.models.evidence import RuntimeEvent, EvidenceItem, CalculationRecord, VerifiedClaim
from app.models.document import SourceDocument, DocumentChunk
from app.agent.runtime import renew_lease


async def main():
    probe.results.update(json.loads(probe.REPORT.read_text()))
    cfg = json.loads(docker("inspect", "omniops-phase6-a"))[0]
    env = dict(v.split("=", 1) for v in cfg["Config"]["Env"] if "=" in v)
    url = env["DATABASE_URL"].replace("@omniops-postgres:", "@127.0.0.1:")
    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        await db.execute(delete(RateLimitBucket))
        user = (await db.execute(select(User).where(User.email.like("closure-a-%")).order_by(User.created_at.desc()).limit(1))).scalar_one()
        await db.commit()
    async with httpx.AsyncClient(timeout=45, limits=httpx.Limits(max_connections=60)) as client:
        response = await client.post(probe.A + "/auth/login", json={"email": user.email, "password": "ClosureTestPass123!"})
        assert response.status_code == 200
        auth = {"Authorization": "Bearer " + response.json()["data"]["token"]["access_token"]}
        ws = (await client.get(probe.A + "/workspaces", headers=auth)).json()["data"][0]["id"]
        async with factory() as db:
            inv = InvestigationSession(workspace_id=uuid.UUID(ws), user_id=user.id, objective="Closure slow-reader fixture")
            db.add(inv)
            await db.commit()
            inv_id = inv.id
        foreign = probe.results["persisted_stream"]["event_ids"][0]
        async with client.stream("GET", probe.B + f"/investigations/{inv_id}/stream", headers={**auth, "Last-Event-ID": foreign}) as r:
            probe.record("foreign_cursor_status", r.status_code)
        async def insert_batch(start):
            async with factory() as db:
                now = datetime.now(timezone.utc)
                for i in range(start, start + 500):
                    db.add(RuntimeEvent(investigation_id=inv_id, event_type="closure.slow", logical_identity=f"slow:{inv_id}:{i}", payload={"sequence": i, "padding": "x" * 32768}, created_at=now + timedelta(microseconds=i)))
                await db.commit()
        def rss():
            value = docker("exec", "omniops-phase6-a", "python", "-c", "from pathlib import Path; print(next(x.split()[1] for x in Path('/proc/1/status').read_text().splitlines() if x.startswith('VmRSS:')))")
            return int(value)
        await insert_batch(0)
        memory = [rss()]
        async with client.stream("GET", probe.A + f"/investigations/{inv_id}/stream", headers=auth) as slow:
            assert slow.status_code == 200
            for start in (500, 1000, 1500):
                await insert_batch(start)
                await asyncio.sleep(2)
                memory.append(rss())
                assert (await client.get(probe.A + "/auth/me", headers=auth)).status_code == 200
            # No body is consumed: the TCP send window, not an eager client reader, applies backpressure.
        async with factory() as db:
            ids = [str(x) for x in (await db.execute(select(RuntimeEvent.id).where(RuntimeEvent.investigation_id == inv_id).order_by(RuntimeEvent.created_at, RuntimeEvent.id))).scalars()]
        replay = await probe.stream(client, probe.B, inv_id, auth, len(ids))
        assert replay == ids and len(set(replay)) == 2000
        probe.record("slow_reader", {"persisted_events": 2000, "payload_bytes_each": 32768, "rss_kib_samples": memory, "growth_after_first_blocked_sample_kib": max(memory[1:])-min(memory[1:]), "other_reads": "200 throughout", "replay_missing": 0, "replay_duplicates": 0, "batch_limit": 500})
        # Exercise the real app.worker process while a database trigger deterministically
        # holds its first attempt insert. This is test-only fault injection, not a tool mock.
        objective = "closure-worker-" + uuid.uuid4().hex
        async with factory() as db:
            source = SourceDocument(workspace_id=uuid.UUID(ws), file_name="closure-worker.txt", storage_path="/tmp/closure-worker.txt", mime_type="text/plain", byte_size=24, sha256_hash=uuid.uuid4().hex*2, modality="text", processing_status="READY")
            db.add(source)
            await db.flush()
            db.add(DocumentChunk(workspace_id=uuid.UUID(ws), source_id=source.id, chunk_index=0, content="Closure deterministic worker evidence", modality="text", extraction_method="closure-test"))
            work = InvestigationSession(workspace_id=uuid.UUID(ws), user_id=user.id, objective=objective, current_state="ready")
            db.add(work)
            await db.execute(text("CREATE OR REPLACE FUNCTION phase6_pause_attempt() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.validated_input->>'query' = '" + objective + "' THEN PERFORM pg_sleep(60); END IF; RETURN NEW; END $$"))
            await db.execute(text("CREATE TRIGGER phase6_pause_attempt BEFORE INSERT ON agent_tool_attempts FOR EACH ROW EXECUTE FUNCTION phase6_pause_attempt()"))
            await db.commit()
            work_id = work.id
        try:
            owner, lease = None, None
            for _ in range(25):
                async with factory() as db:
                    row = await db.get(InvestigationSession, work_id)
                    sleeping = await db.scalar(text("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND wait_event='PgSleep'"))
                    if sleeping:
                        owner, lease = row.worker_id or "uncommitted-worker-claim", row.lease_expires_at
                        break
                await asyncio.sleep(1)
            assert owner, "real worker did not reach injected attempt boundary"
            docker("kill", "omniops-phase6-worker")
            probe.record("worker_killed", {"investigation": str(work_id), "owner": owner, "lease_expires": lease.isoformat() if lease else None, "fault_boundary": "attempt insert before commit"})
        finally:
            async with factory() as db:
                await db.execute(text("DROP TRIGGER IF EXISTS phase6_pause_attempt ON agent_tool_attempts"))
                await db.execute(text("DROP FUNCTION IF EXISTS phase6_pause_attempt()"))
                await db.commit()
        # Observe the actual 120-second production lease; never shorten it to manufacture proof.
        while lease and datetime.now(timezone.utc) <= lease:
            await asyncio.sleep(min(10, max(0.1, (lease-datetime.now(timezone.utc)).total_seconds())))
            print("Waiting for persisted worker lease expiry", flush=True)
        async with factory() as db:
            stale = await db.get(InvestigationSession, work_id)
            assert not await renew_lease(db, stale, owner)
        docker("start", "omniops-phase6-worker")
        state = None
        for _ in range(45):
            async with factory() as db:
                row = await db.get(InvestigationSession, work_id)
                if row.current_state in ("completed", "failed", "cancelled"):
                    state, failure = row.current_state, row.failure_code
                    counts = {model.__tablename__: await db.scalar(select(func.count()).select_from(model).where(model.session_id == work_id)) for model in (EvidenceItem, CalculationRecord, VerifiedClaim)}
                    attempts = await db.scalar(select(func.count()).select_from(AgentToolAttempt).join(AgentPlanStep).join(AgentPlan).where(AgentPlan.investigation_id == work_id))
                    break
            await asyncio.sleep(1)
        assert state == "failed", (state, "provider-free fixture must not fabricate completion")
        assert all(value == 0 for value in counts.values())
        probe.record("worker_restart", {"state": state, "failure_code": failure, "stale_renewal": False, "domain_counts": counts, "committed_attempts": attempts, "production_lease_seconds": 120, "recovery": "real app.worker reclaimed work after killed transaction rolled back; unavailable evidence failed closed", "committed_lease_expiry_and_fencing": "covered separately by fresh Phase 3 PostgreSQL regression"})
        topology = []
        for name in ("a", "b", "worker", "front", "runner"):
            item = json.loads(docker("inspect", "omniops-phase6-" + name))[0]
            topology.append({"name": item["Name"], "id": item["Id"][:12], "image_id": item["Image"], "user": item["Config"]["User"], "read_only": item["HostConfig"]["ReadonlyRootfs"], "mount_destinations": [m["Destination"] for m in item["Mounts"]]})
        probe.record("topology_identities", topology)
        payload_uid = docker("run", "--rm", "--entrypoint", "python", "omniops-python-sandbox:phase6", "-c", "import os; print(os.getuid())")
        assert payload_uid == "65532"
        probe.record("sandbox_payload_uid", payload_uid)
        r = await client.get("http://127.0.0.1:13000")
        probe.record("frontend_http", {"status": r.status_code, "nosniff": r.headers.get("x-content-type-options")})
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
