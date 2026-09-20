"""Authenticated A/B SSE replay, out-of-order commit, and restart probe."""

import asyncio
import json
import subprocess
import sys
import uuid
from pathlib import Path

import httpx
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.agent.runtime import persist_runtime_event
from app.core.config import settings
from app.core.security import get_password_hash
from app.models.investigation import InvestigationSession
from app.models.user import User, Workspace, WorkspaceMembership, WorkspaceRole


async def read_ids(base: str, headers: dict[str, str], expected: int, last_id: str | None = None) -> list[str]:
    request_headers = dict(headers)
    if last_id:
        request_headers["Last-Event-ID"] = last_id
    observed: list[str] = []
    async with httpx.AsyncClient(timeout=15) as client:
        async with asyncio.timeout(12):
            async with client.stream(
                "GET", f"{base}/investigations/{INVESTIGATION_ID}/stream", headers=request_headers,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("id:"):
                        observed.append(line[3:].strip())
                        if len(observed) == expected:
                            break
    return observed


INVESTIGATION_ID: uuid.UUID


async def main() -> None:
    global INVESTIGATION_ID
    engine = create_async_engine(settings.DATABASE_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    email = f"final-sse-{uuid.uuid4()}@example.com"
    password = "FinalSseOnlyStrongPass123!"
    async with factory() as db:
        user = User(email=email, hashed_password=get_password_hash(password), full_name="Final SSE Audit")
        db.add(user)
        await db.flush()
        workspace = Workspace(name="Final SSE Audit", created_by=user.id)
        db.add(workspace)
        await db.flush()
        db.add(WorkspaceMembership(
            workspace_id=workspace.id, user_id=user.id, role=WorkspaceRole.OWNER.value,
        ))
        investigation = InvestigationSession(
            workspace_id=workspace.id, user_id=user.id,
            objective="Authored persisted SSE ordering fixture",
            status="failed", current_state="failed",
        )
        db.add(investigation)
        await db.flush()
        INVESTIGATION_ID = investigation.id
        initial = []
        for number in range(1, 6):
            event = await persist_runtime_event(
                db, investigation.id, "final.sse.probe",
                f"final-sse-{investigation.id}-{number}", {"sequence": number},
            )
            initial.append(str(event.id))
        await db.commit()

    base_a = "http://127.0.0.1:18201/api/v1"
    base_b = "http://127.0.0.1:18202/api/v1"
    async with httpx.AsyncClient(timeout=10) as client:
        login = await client.post(f"{base_a}/auth/login", json={"email": email, "password": password})
        login.raise_for_status()
        headers = {"Authorization": f"Bearer {login.json()['data']['token']['access_token']}"}

    observed_a = await read_ids(base_a, headers, 5)
    if observed_a != initial:
        raise RuntimeError("BACKEND_A_REPLAY_ORDER_MISMATCH")

    async with factory() as db:
        remaining = []
        for number in range(6, 11):
            event = await persist_runtime_event(
                db, INVESTIGATION_ID, "final.sse.probe",
                f"final-sse-{INVESTIGATION_ID}-{number}", {"sequence": number},
            )
            remaining.append(str(event.id))
        await db.commit()
    observed_b = await read_ids(base_b, headers, 5, initial[-1])
    if observed_b != remaining:
        raise RuntimeError("BACKEND_B_CURSOR_REPLAY_ORDER_MISMATCH")

    # Create in one transaction, commit in the opposite order, then verify the
    # committed late row is delivered both live and from the issued cursor.
    async with factory() as late, factory() as early:
        late_event = await persist_runtime_event(
            late, INVESTIGATION_ID, "final.sse.late_commit",
            f"final-sse-{INVESTIGATION_ID}-late", {"sequence": 12},
        )
        early_event = await persist_runtime_event(
            early, INVESTIGATION_ID, "final.sse.early_commit",
            f"final-sse-{INVESTIGATION_ID}-early", {"sequence": 11},
        )
        await early.commit()
        live = []
        async with httpx.AsyncClient(timeout=15) as client:
            async with asyncio.timeout(12):
                async with client.stream(
                    "GET", f"{base_a}/investigations/{INVESTIGATION_ID}/stream",
                    headers={**headers, "Last-Event-ID": remaining[-1]},
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.startswith("id:"):
                            continue
                        live.append(line[3:].strip())
                        if len(live) == 1:
                            await late.commit()
                        if len(live) == 2:
                            break
        expected_commit_order = [str(early_event.id), str(late_event.id)]
        if live != expected_commit_order:
            raise RuntimeError("LATE_COMMIT_LIVE_REPLAY_FAILED")
        reconnect = await read_ids(base_b, headers, 1, str(early_event.id))
        if reconnect != [str(late_event.id)]:
            raise RuntimeError("LATE_COMMIT_CURSOR_REPLAY_FAILED")

    subprocess.run(
        ["docker", "restart", "omniops-final-a"], check=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    async with httpx.AsyncClient(timeout=2) as client:
        for _ in range(30):
            try:
                response = await client.get(f"{base_a}/readiness")
                if response.status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            await asyncio.sleep(1)
        else:
            raise RuntimeError("BACKEND_A_DID_NOT_RECOVER")
    after_restart = await read_ids(base_a, headers, 2, remaining[-1])
    if after_restart != expected_commit_order:
        raise RuntimeError("RESTART_HISTORY_MISMATCH")

    await engine.dispose()
    print(json.dumps({
        "status": "PASS",
        "a_initial": len(observed_a),
        "b_cursor_suffix": len(observed_b),
        "exact_order": True,
        "duplicates": 0,
        "loss": 0,
        "late_commit_live": True,
        "late_commit_reconnect": True,
        "restart_history": True,
        "query_token": False,
    }, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
