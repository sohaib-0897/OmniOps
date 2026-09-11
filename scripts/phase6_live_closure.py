"""Local closure probes. Test credentials stay in process memory, never in reports."""
import asyncio
import json
import statistics
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from sqlalchemy import select, text, delete
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from phase6_topology import docker

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.models.evidence import RuntimeEvent
from app.models.investigation import InvestigationSession
from app.agent.sse_manager import SSEBroadcaster
from app.models.user import RateLimitBucket, UserSession, RefreshToken

A, B = "http://127.0.0.1:18001/api/v1", "http://127.0.0.1:18002/api/v1"
REPORT = Path("phase6-live-evidence.json")
results = {}


def record(key, value):
    results[key] = value
    REPORT.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(key, json.dumps(value), flush=True)


async def ready(client, base):
    for _ in range(30):
        try:
            response = await client.get(base + "/readiness")
            if response.status_code == 200:
                return response.json()["data"]
        except httpx.HTTPError:
            pass
        await asyncio.sleep(1)
    raise AssertionError("replica did not become ready")


async def stream(client, base, inv, auth, count, cursor=None):
    headers = dict(auth)
    if cursor:
        headers["Last-Event-ID"] = cursor
    found = []
    async with client.stream("GET", f"{base}/investigations/{inv}/stream", headers=headers) as response:
        assert response.status_code == 200, response.status_code
        async for line in response.aiter_lines():
            if line.startswith("id: "):
                found.append(line[4:])
                if len(found) == count:
                    return found
    raise AssertionError("stream ended early")


async def main():
    if REPORT.exists():
        results.update(json.loads(REPORT.read_text(encoding="utf-8")))
    cfg = json.loads(docker("inspect", "omniops-phase6-a"))[0]
    env = dict(v.split("=", 1) for v in cfg["Config"]["Env"] if "=" in v)
    url = env["DATABASE_URL"].replace("@omniops-postgres:", "@127.0.0.1:")
    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    # Dedicated closure DB only: give each repeatable run fresh abuse-control windows.
    assert url.rsplit("/", 1)[-1] == "omniops_phase6_closure_test"
    async with factory() as db:
        await db.execute(delete(RateLimitBucket))
        await db.commit()
    async with httpx.AsyncClient(timeout=40, limits=httpx.Limits(max_connections=60)) as client:
        record("readiness_a", await ready(client, A))
        record("readiness_b", await ready(client, B))
        suffix = uuid.uuid4().hex[:8]
        auths, workspaces = [], []
        for who in ("a", "b"):
            response = await client.post(A + "/auth/register", json={"email": f"closure-{who}-{suffix}@example.com", "password": "ClosureTestPass123!", "full_name": "Closure Test"})
            assert response.status_code == 200, response.status_code
            auth = {"Authorization": "Bearer " + response.json()["data"]["token"]["access_token"]}
            auths.append(auth)
            ws = (await client.get(A + "/workspaces", headers=auth)).json()["data"][0]["id"]
            workspaces.append(ws)
        auth = auths[0]
        # The production endpoint commits investigation.created before scheduling work.
        response = await client.post(A + f"/workspaces/{workspaces[0]}/investigations", headers=auth,
                                     json={"objective": "Closure test: report missing evidence without inventing facts.", "max_steps": 2})
        assert response.status_code == 200, response.status_code
        inv = response.json()["data"]["id"]
        await asyncio.sleep(3)
        async with factory() as db:
            # Explicit fixture events exercise >1 DB batch without paid providers.
            now = datetime.now(timezone.utc)
            for i in range(12):
                db.add(RuntimeEvent(investigation_id=uuid.UUID(inv), event_type="closure.probe", logical_identity=f"closure:{inv}:{i}", payload={"test_sequence": i}, created_at=now + timedelta(microseconds=i)))
            await db.commit()
            rows = (await db.execute(select(RuntimeEvent).where(RuntimeEvent.investigation_id == uuid.UUID(inv)).order_by(RuntimeEvent.created_at, RuntimeEvent.id))).scalars().all()
            expected = [str(row.id) for row in rows]
        record("persisted_stream", {"workspace": workspaces[0], "investigation": inv, "event_ids": expected})
        first = await stream(client, A, inv, auth, 3)
        assert first == expected[:3]
        record("initial_sse_a", {"ids": first, "last_event_id": first[-1]})
        replay = await stream(client, B, inv, auth, len(expected)-3, first[-1])
        assert first + replay == expected
        record("cross_worker_replay", {"count": len(replay), "missing": 0, "duplicates": 0})
        async with client.stream("GET", A + f"/investigations/{inv}/stream", headers={**auth, "Last-Event-ID": first[-1]}) as active:
            assert active.status_code == 200
            docker("kill", "omniops-phase6-a")
            try:
                await active.aread()
                connection_end = "EOF"
            except httpx.RemoteProtocolError:
                connection_end = "RemoteProtocolError"
            record("active_stream_kill", {"accepted_before_kill": 200, "connection_end": connection_end})
        assert (await client.get(B + f"/investigations/{inv}", headers=auth)).status_code == 200
        assert await stream(client, B, inv, auth, len(expected)-3, first[-1]) == expected[3:]
        record("backend_kill_replay", "PASS")
        docker("start", "omniops-phase6-a")
        await ready(client, A)
        assert await stream(client, A, inv, auth, len(expected)-3, first[-1]) == expected[3:]
        async with factory() as db:
            unchanged = [str(x) for x in (await db.execute(select(RuntimeEvent.id).where(RuntimeEvent.investigation_id == uuid.UUID(inv)).order_by(RuntimeEvent.created_at, RuntimeEvent.id))).scalars()]
        assert unchanged == expected
        record("backend_restart_replay", "PASS; exact PostgreSQL event history unchanged")
        seen = set(first)
        for i in range(6):
            ids = await stream(client, A if i % 2 else B, inv, auth, len(expected)-3, first[-1])
            seen.update(ids)
        assert seen == set(expected)
        record("rapid_reconnect", {"cycles": 6, "unique_after_id_dedupe": len(seen)})
        attacks = []
        for path, headers in [(f"/investigations/{inv}/stream", auths[1]), (f"/investigations/{uuid.uuid4()}/stream", auths[1]), (f"/workspaces/{workspaces[0]}/investigations", auths[1]), (f"/workspaces/{uuid.uuid4()}/investigations", auths[1])]:
            if path.endswith("/stream"):
                r = await client.get(B + path, headers={**headers, "Last-Event-ID": first[-1]})
            else:
                r = await client.post(B + path, headers=headers, json={"objective": "Closure tenant attack test"})
            assert r.status_code in (403, 404), r.status_code
            assert not any(event_id in r.text for event_id in expected)
            attacks.append(r.status_code)
        record("cross_tenant", attacks)
        other = await client.post(B + f"/workspaces/{workspaces[1]}/investigations", headers=auths[1], json={"objective": "Closure other-tenant cursor test", "max_steps": 2})
        assert other.status_code == 200
        other_id = other.json()["data"]["id"]
        async with client.stream("GET", B + f"/investigations/{other_id}/stream", headers={**auths[1], "Last-Event-ID": first[-1]}) as foreign_cursor:
            assert foreign_cursor.status_code == 404
            record("cross_tenant_foreign_cursor", foreign_cursor.status_code)
        async def read_once(i):
            started = time.perf_counter()
            r = await client.get((A if i % 2 else B) + "/auth/me", headers=auth)
            return (time.perf_counter()-started)*1000, r.status_code
        semaphore = asyncio.Semaphore(10)
        async def bounded(i):
            async with semaphore:
                return await read_once(i)
        reads = await asyncio.gather(*(bounded(i) for i in range(100)))
        latencies = sorted(x[0] for x in reads)
        record("api_sanity", {"label": "LOCAL PRODUCTION-LIKE SANITY OBSERVATION", "requests": 100, "concurrency": 10, "median_ms": round(statistics.median(latencies), 2), "p95_ms": round(latencies[94], 2), "errors": sum(x[1] != 200 for x in reads)})
        # Hold ten streams on one replica, then check whether a normal read can acquire a DB connection.
        contexts = []
        try:
            for i in range(10):
                ctx = client.stream("GET", A + f"/investigations/{inv}/stream", headers=auth)
                r = await ctx.__aenter__()
                assert r.status_code == 200
                contexts.append(ctx)
            started = time.perf_counter()
            r = await client.get(A + "/auth/me", headers=auth)
            record("sse_pool_probe", {"open_streams": len(contexts), "read_status": r.status_code, "read_ms": round((time.perf_counter()-started)*1000, 2)})
        finally:
            for ctx in contexts:
                await ctx.__aexit__(None, None, None)
        await asyncio.sleep(1)
        record("pool_after_disconnect", (await client.get(A + "/auth/me", headers=auth)).status_code)
        assert results["sse_pool_probe"]["read_status"] == 200
        # Twenty clients across both replicas; slow consumers hold their connections open.
        async def concurrent_stream(i):
            base = A if i % 2 else B
            async with client.stream("GET", base + f"/investigations/{inv}/stream", headers=auth) as response:
                assert response.status_code == 200
                await asyncio.sleep(2)
                return response.status_code
        statuses = await asyncio.gather(*(concurrent_stream(i) for i in range(20)))
        record("sse_concurrency", {"clients": 20, "successful": statuses.count(200), "failed": len(statuses)-statuses.count(200)})
        # Expiration on a new connection is checked by the real bearer dependency.
        # Sign a short-lived test access token for the real DB-backed session;
        # the configured production lifetime remains fifteen minutes.
        import jwt
        claims = jwt.decode(auth["Authorization"].split()[1], env["SECRET_KEY"], algorithms=["HS256"])
        claims.update(iat=int(time.time()), exp=int(time.time()) + 2)
        short = {"Authorization": "Bearer " + jwt.encode(claims, env["SECRET_KEY"], algorithm="HS256")}
        async with client.stream("GET", A + f"/investigations/{inv}/stream", headers=short) as response:
            assert response.status_code == 200
            await asyncio.sleep(3)
            async for line in response.aiter_lines():
                if line.startswith("id:"):
                    break
        expired = await client.get(B + f"/investigations/{inv}/stream", headers=short)
        assert expired.status_code == 401
        record("access_expiry", {"existing_connection_survives": True, "new_connection": expired.status_code, "test_token_seconds": 2, "production_token_minutes": 15})
        login = await client.post(A + "/auth/login", json={"email": f"closure-a-{suffix}@example.com", "password": "ClosureTestPass123!"})
        assert login.status_code == 200
        cookie_name = "omniops_refresh"
        r0 = login.cookies[cookie_name]
        async def refresh(base, cookie):
            return await client.post(base + "/auth/refresh", headers={"Cookie": f"{cookie_name}={cookie}", "Origin": "https://localhost:13000"})
        r1 = await refresh(A, r0)
        assert r1.status_code == 200
        r2 = await refresh(B, r1.cookies[cookie_name])
        assert r2.status_code == 200
        refreshed_auth = {"Authorization": "Bearer " + r2.json()["data"]["token"]["access_token"]}
        assert await stream(client, B, inv, refreshed_auth, 1, first[-1]) == expected[3:4]
        replay = await refresh(A, r1.cookies[cookie_name])
        revoked = await refresh(B, r2.cookies[cookie_name])
        assert replay.status_code == revoked.status_code == 401
        assert (await client.get(B + "/auth/me", headers=refreshed_auth)).status_code == 401
        async with factory() as db:
            row = await db.get(RefreshToken, uuid.UUID(r1.cookies[cookie_name].split(".")[0]))
            session = await db.get(UserSession, row.session_id)
            assert session.revoked_at is not None
        record("refresh_rotation_replay", {"login": 200, "normal_rotations": [200, 200], "refreshed_stream": 200, "reused_r1": 401, "r2_after_replay": 401, "access_after_replay": 401, "db_session_revoked": True, "secure_httponly_cookie": "Secure" in login.headers["set-cookie"] and "HttpOnly" in login.headers["set-cookie"]})
        login_statuses = []
        for i in range(12):
            response = await client.post((A if i % 2 else B) + "/auth/login", json={"email": f"absent-{suffix}@example.com", "password": "wrong"})
            login_statuses.append(response.status_code)
            if response.status_code == 429:
                assert 0 < int(response.headers["retry-after"]) <= 300
        assert 429 in login_statuses and all(x in (401, 429) for x in login_statuses)
        record("shared_login_limit", {"alternating_statuses": login_statuses, "prior_successful_login": 1, "retry_after_seconds": response.headers.get("retry-after")})
        # Idempotent creation exercises limiter on both replicas without provider spend.
        enqueue_key = "closure-enqueue-" + suffix
        async def enqueue(i):
            return await client.post((A if i % 2 else B) + f"/workspaces/{workspaces[0]}/investigations", headers={**auth, "Idempotency-Key": enqueue_key}, json={"objective": "Closure missing-evidence enqueue test", "max_steps": 2})
        initial = await enqueue(0)
        assert initial.status_code == 200
        responses = await asyncio.gather(*(enqueue(i) for i in range(1, 6)))
        record("enqueue_sanity", {"concurrency": 5, "accepted": sum(r.status_code == 200 for r in responses), "throttled": sum(r.status_code == 429 for r in responses), "unique_ids": len({r.json()["data"]["id"] for r in responses if r.status_code == 200}), "kind": "idempotent small investigation submissions"})
        async def distinct_enqueue(i):
            return await client.post((A if i % 2 else B) + f"/workspaces/{workspaces[0]}/investigations", headers=auth, json={"objective": f"Closure distinct missing-evidence test {i}", "max_steps": 2})
        distinct = await asyncio.gather(*(distinct_enqueue(i) for i in range(5)))
        accepted_ids = [r.json()["data"]["id"] for r in distinct if r.status_code == 200]
        assert len(set(accepted_ids)) == 5
        await asyncio.sleep(2)
        states = [(await client.get(A + f"/investigations/{item}", headers=auth)).json()["data"]["failure_code"] for item in accepted_ids]
        assert all(state == "LLM_PROVIDER_REQUIRED" for state in states)
        record("distinct_enqueue_sanity", {"concurrency": 5, "accepted": 5, "throttled": 0, "unique_ids": 5, "queue_behavior": "all five committed then failed closed with LLM_PROVIDER_REQUIRED; no provider spend"})
        statuses = []
        for i in range(20):
            response = await enqueue(i)
            statuses.append(response.status_code)
        assert 429 in statuses and all(x in (200, 429) for x in statuses)
        record("shared_creation_limit", {"alternating_statuses": statuses, "prior_creation_requests": 12, "retry_after_seconds": response.headers.get("retry-after")})
        async with factory() as db:
            activity = dict((await db.execute(text("SELECT state, count(*) FROM pg_stat_activity WHERE datname=current_database() AND backend_type='client backend' GROUP BY state"))).all())
        assert activity.get("idle in transaction", 0) == 0
        record("db_pool_after_load", {"connection_states": activity, "idle_in_transaction": 0, "configured_per_backend_max": 10, "post_load_read": (await client.get(A + "/auth/me", headers=auth)).status_code})
        docker("stop", "omniops-phase6-runner")
        try:
            health = await client.get(A + "/health")
            unready = await client.get(A + "/readiness")
            assert health.status_code == 200 and unready.status_code == 503
            record("dependency_failure", {"health": health.status_code, "readiness": unready.status_code, "checks": unready.json()["data"]["checks"]})
        finally:
            docker("start", "omniops-phase6-runner")
        record("dependency_restored", (await ready(client, A))["status"])
        broadcaster = SSEBroadcaster()
        slow = broadcaster.subscribe("closure")
        fast = broadcaster.subscribe("closure")
        for i in range(1000):
            await broadcaster.emit("closure", "test", {"n": i})
            await fast.get()
        assert slow.qsize() == 100 and slow not in broadcaster._subscribers["closure"]
        record("local_backpressure", {"emitted": 1000, "slow_queue": slow.qsize(), "slow_detached": True, "fast_received": 1000})
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
