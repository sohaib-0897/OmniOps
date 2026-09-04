import asyncio
import os
from datetime import datetime, timezone, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select, delete, update
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.models.user import User, Workspace
from app.models.investigation import InvestigationSession, RuntimeState
from app.models.document import SourceDocument
from app.models.evidence import EvidenceItem, CalculationRecord, VerifiedClaim, RuntimeEvent
from app.agent.runtime import claim_next_investigation, acquire_lease, renew_lease, logical_identity, persist_runtime_event

PG_URL = os.getenv("POSTGRES_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not PG_URL, reason="POSTGRES_TEST_DATABASE_URL is required for live concurrency verification")


@pytest_asyncio.fixture
async def pg_factory():
    engine = create_async_engine(PG_URL, pool_size=10, max_overflow=0)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_live_worker_race_and_lease_takeover(pg_factory):
    async with pg_factory() as db:
        user = (await db.execute(select(User).limit(1))).scalar_one()
        ws = (await db.execute(select(Workspace).limit(1))).scalar_one()
        # Isolate the race: leave exactly one eligible row in the test DB.
        await db.execute(update(InvestigationSession).where(
            InvestigationSession.current_state.in_([RuntimeState.READY.value, RuntimeState.EXECUTING.value, RuntimeState.REPLANNING.value])
        ).values(current_state=RuntimeState.COMPLETED.value, cancellation_requested=False, worker_id=None, lease_expires_at=None))
        await db.execute(delete(InvestigationSession).where(InvestigationSession.objective == "live race"))
        await db.commit()
        inv = InvestigationSession(workspace_id=ws.id, user_id=user.id, objective="live race", current_state=RuntimeState.READY.value)
        db.add(inv); await db.commit(); inv_id = inv.id
    async def claim(worker):
        async with pg_factory() as s:
            x = await claim_next_investigation(s, worker, ttl_seconds=30)
            await s.commit()
            return x
    a, b = await asyncio.gather(claim("race-a"), claim("race-b"))
    assert (a is None) ^ (b is None)
    owner = a or b
    async with pg_factory() as s:
        row = (await s.execute(select(InvestigationSession).where(InvestigationSession.id == inv_id))).scalar_one()
        assert row.worker_id == owner.worker_id
        await s.execute(__import__('sqlalchemy').update(InvestigationSession).where(InvestigationSession.id == inv_id).values(lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)))
        await s.commit()
    async with pg_factory() as s:
        takeover = await claim_next_investigation(s, "race-takeover", ttl_seconds=30)
        await s.commit()
        assert takeover is not None
        assert takeover.worker_id == "race-takeover"
        assert await renew_lease(s, takeover, owner.worker_id) is False
    async with pg_factory() as s:
        await s.execute(delete(InvestigationSession).where(InvestigationSession.id == inv_id)); await s.commit()


@pytest.mark.asyncio
async def test_live_concurrent_event_idempotency(pg_factory):
    async with pg_factory() as db:
        user = (await db.execute(select(User).limit(1))).scalar_one(); ws = (await db.execute(select(Workspace).limit(1))).scalar_one()
        inv = InvestigationSession(workspace_id=ws.id, user_id=user.id, objective="event race", current_state=RuntimeState.READY.value)
        db.add(inv); await db.commit(); inv_id = inv.id
    identity = logical_identity(inv_id, "event", "same")
    async def write():
        async with pg_factory() as s:
            try:
                e = await persist_runtime_event(s, inv_id, "state.changed", identity)
                await s.commit(); return e.id
            except Exception:
                await s.rollback(); return None
    ids = await asyncio.gather(write(), write())
    assert len({x for x in ids if x}) == 1
    async with pg_factory() as s:
        assert len((await s.execute(select(RuntimeEvent).where(RuntimeEvent.logical_identity == identity))).scalars().all()) == 1
        await s.execute(delete(InvestigationSession).where(InvestigationSession.id == inv_id)); await s.commit()
