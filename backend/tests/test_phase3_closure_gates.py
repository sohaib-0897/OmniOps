"""Live PostgreSQL closure tests for Phase 3 ownership and idempotency gates."""
import asyncio
import os
from datetime import datetime, timezone, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from pydantic import BaseModel
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.agent.persistence import persist_evidence, persist_calculation, persist_claim
from app.agent.runtime import (
    DurablePlanExecutor, PlanSpec, PlanStepSpec, RuntimeBudget, ToolDefinition,
    ToolRegistry, SimulatedWorkerCrash, acquire_lease, claim_next_investigation, owns_lease, release_lease, resume_investigation,
)
from app.agent.service import InvestigationRuntime, RetrievalInput
from app.models.document import DocumentChunk, SourceDocument
from app.models.evidence import EvidenceItem, CalculationRecord, VerifiedClaim, RuntimeEvent
from app.models.investigation import AgentObservation, AgentPlan, AgentPlanStep, AgentToolAttempt, InvestigationSession, RuntimeState
from app.models.user import User, Workspace

PG_URL = os.getenv("POSTGRES_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not PG_URL, reason="POSTGRES_TEST_DATABASE_URL is required")


class EmptyInput(BaseModel):
    pass


@pytest_asyncio.fixture
async def pg_factory():
    engine = create_async_engine(PG_URL, pool_size=8, max_overflow=0)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


async def _fixture_ids(factory):
    async with factory() as db:
        user = (await db.execute(select(User).limit(1))).scalar_one()
        workspace = (await db.execute(select(Workspace).where(Workspace.created_by == user.id).limit(1))).scalar_one()
        await db.execute(update(InvestigationSession).where(
            InvestigationSession.current_state.in_([RuntimeState.READY.value, RuntimeState.EXECUTING.value, RuntimeState.REPLANNING.value])
        ).values(current_state=RuntimeState.COMPLETED.value, worker_id=None, lease_expires_at=None))
        source = SourceDocument(workspace_id=workspace.id, file_name=f"closure-{uuid4()}.txt", storage_path="/tmp/closure.txt", mime_type="text/plain", byte_size=8, sha256_hash=uuid4().hex + uuid4().hex, modality="text", processing_status="READY")
        db.add(source)
        await db.flush()
        chunk = DocumentChunk(workspace_id=workspace.id, source_id=source.id, chunk_index=0, content="authoritative closure evidence", modality="text", extraction_method="test")
        db.add(chunk)
        investigation = InvestigationSession(workspace_id=workspace.id, user_id=user.id, objective=f"closure-{uuid4()}", current_state=RuntimeState.READY.value)
        db.add(investigation)
        await db.commit()
        return user.id, workspace.id, source.id, chunk.id, investigation.id


async def _race(factory, operation):
    barrier = asyncio.Barrier(2)

    async def call():
        async with factory() as db:
            await barrier.wait()
            try:
                result = await operation(db)
                await db.commit()
                return result.id, None
            except Exception as exc:  # callers must complete safely, not poison sessions
                await db.rollback()
                return None, repr(exc)

    return await asyncio.gather(call(), call())


@pytest.mark.asyncio
async def test_live_concurrent_domain_idempotency(pg_factory):
    _, workspace_id, source_id, chunk_id, investigation_id = await _fixture_ids(pg_factory)
    evidence_kwargs = dict(session_id=investigation_id, workspace_id=workspace_id, source_id=source_id, chunk_id=chunk_id, locator={"page": 1}, exact_quote="authoritative closure evidence")
    evidence_results = await _race(pg_factory, lambda db: persist_evidence(db, **evidence_kwargs))
    assert all(error is None for _, error in evidence_results), evidence_results
    assert len({row_id for row_id, _ in evidence_results}) == 1

    calc_kwargs = dict(session_id=investigation_id, step_id="closure-step", formula="1+1", inputs={"a": 1}, calculation_type="python_math", computed_output={"value": 2}, reproducibility_hash="a" * 64, evidence_ids=[], source_ids=[str(source_id)])
    calc_results = await _race(pg_factory, lambda db: persist_calculation(db, **calc_kwargs))
    assert all(error is None for _, error in calc_results), calc_results
    assert len({row_id for row_id, _ in calc_results}) == 1

    claim_kwargs = dict(session_id=investigation_id, step_id="closure-step", statement="Closure evidence is authoritative.", lineage={"evidence": [str(chunk_id)]}, epistemic_type="FACT", verification_status="VERIFIED", supporting_citations=[])
    claim_results = await _race(pg_factory, lambda db: persist_claim(db, **claim_kwargs))
    assert all(error is None for _, error in claim_results), claim_results
    assert len({row_id for row_id, _ in claim_results}) == 1

    async with pg_factory() as db:
        assert (await db.scalar(select(func.count()).select_from(EvidenceItem).where(EvidenceItem.session_id == investigation_id))) == 1
        assert (await db.scalar(select(func.count()).select_from(CalculationRecord).where(CalculationRecord.session_id == investigation_id))) == 1
        assert (await db.scalar(select(func.count()).select_from(VerifiedClaim).where(VerifiedClaim.session_id == investigation_id))) == 1


@pytest.mark.asyncio
async def test_live_stale_worker_rejected_before_tool_and_finalization(pg_factory):
    _, workspace_id, _, _, investigation_id = await _fixture_ids(pg_factory)
    async with pg_factory() as db:
        inv = (await db.execute(select(InvestigationSession).where(InvestigationSession.id == investigation_id))).scalar_one()
        assert await acquire_lease(db, inv, "worker-a", ttl_seconds=1)
        await db.commit()
    async with pg_factory() as db:
        await db.execute(update(InvestigationSession).where(InvestigationSession.id == investigation_id).values(lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)))
        await db.commit()
        takeover = await claim_next_investigation(db, "worker-b", ttl_seconds=30)
        await db.commit()
        assert takeover is not None and takeover.worker_id == "worker-b"

    calls = 0
    async def execute(context, input):
        nonlocal calls
        calls += 1
        return {"ok": True}
    registry = ToolRegistry()
    registry.register(ToolDefinition(name="closure-tool", description="test", input_model=EmptyInput, execute=execute))
    # Exercise the durable executor boundary, not only the lease helper.
    async with pg_factory() as db:
        stale = (await db.execute(select(InvestigationSession).where(InvestigationSession.id == investigation_id))).scalar_one()
        with pytest.raises(RuntimeError, match="WORKER_LEASE_UNAVAILABLE"):
            await DurablePlanExecutor(db, registry, RuntimeBudget(max_attempts_per_step=1)).execute(
                stale,
                PlanSpec(objective="stale", steps=[PlanStepSpec(step_id="stale-step", objective="stale", tool_name="closure-tool", inputs={})]),
                context={"worker_id": "worker-a"},
            )
        assert await owns_lease(db, investigation_id, "worker-a") is False
        assert calls == 0
        await db.rollback()


@pytest.mark.asyncio
async def test_live_stale_worker_result_is_fenced_at_finalization(pg_factory):
    _, _, _, _, investigation_id = await _fixture_ids(pg_factory)
    async with pg_factory() as db:
        inv = (await db.execute(select(InvestigationSession).where(InvestigationSession.id == investigation_id))).scalar_one()
        assert await acquire_lease(db, inv, "worker-a", ttl_seconds=30)
        await db.commit()

    calls = 0
    async def execute(context, input):
        nonlocal calls
        calls += 1
        # Simulate takeover while the external read-only action is in flight.
        await context["db"].execute(update(InvestigationSession).where(InvestigationSession.id == investigation_id).values(worker_id="worker-b", lease_expires_at=datetime.now(timezone.utc) + timedelta(seconds=30)))
        return {"ok": True}

    registry = ToolRegistry()
    registry.register(ToolDefinition(name="fenced-tool", description="test", input_model=EmptyInput, execute=execute, max_attempts=1))
    async with pg_factory() as db:
        stale = (await db.execute(select(InvestigationSession).where(InvestigationSession.id == investigation_id))).scalar_one()
        assert stale.worker_id == "worker-a"
        assert await owns_lease(db, investigation_id, "worker-a") is True
        with pytest.raises(RuntimeError, match="WORKER_LEASE_UNAVAILABLE"):
            await DurablePlanExecutor(db, registry, RuntimeBudget(max_attempts_per_step=1)).execute(
                stale,
                PlanSpec(objective="fence", steps=[PlanStepSpec(step_id="fenced-step", objective="fence", tool_name="fenced-tool", inputs={})]),
                context={"worker_id": "worker-a", "db": db},
            )
        await db.commit()
        assert calls == 1
        assert stale.current_state != RuntimeState.COMPLETED.value
        assert await db.scalar(select(func.count()).select_from(RuntimeEvent).where(RuntimeEvent.investigation_id == investigation_id, RuntimeEvent.event_type == "tool.completed")) == 0


@pytest.mark.asyncio
async def test_live_crash_before_commit_recovers_through_worker_runtime(pg_factory):
    _, workspace_id, source_id, chunk_id, investigation_id = await _fixture_ids(pg_factory)
    attempts = 0

    async def read_only_tool(context, input):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise SimulatedWorkerCrash()
        evidence = {"source_id": str(source_id), "chunk_id": str(chunk_id), "locator": {"page": 1}, "exact_quote": "authoritative closure evidence"}
        return {
            "results": [{"content": "recovered evidence"}],
            "evidence": [evidence],
            "claims": [{"statement": "The closure evidence was recovered.", "evidence_ids": [], "calculation_ids": []}],
        }

    registry = ToolRegistry()
    registry.register(ToolDefinition(name="hybrid_document_search", description="deterministic recovery tool", input_model=RetrievalInput, execute=read_only_tool, max_attempts=1))
    # Worker A uses the same service operation as production workers.
    async with pg_factory() as db:
        worker_a = InvestigationRuntime(db, registry=registry, budget=RuntimeBudget(max_attempts_per_step=1))
        with pytest.raises(SimulatedWorkerCrash):
            await worker_a.run_worker_once("crash-worker-a")
        await db.commit()
        assert await db.scalar(select(func.count()).select_from(AgentToolAttempt).join(AgentPlanStep).join(AgentPlan).where(AgentPlan.investigation_id == investigation_id)) == 1

    # Expire A's lease and recover through the durable resume operation.
    async with pg_factory() as db:
        await db.execute(update(InvestigationSession).where(InvestigationSession.id == investigation_id).values(lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)))
        await db.commit()
        recovered = await resume_investigation(db, investigation_id, "crash-worker-b", ttl_seconds=30)
        await db.commit()
        assert recovered.current_state == RuntimeState.READY.value
        worker_b = InvestigationRuntime(db, registry=registry, budget=RuntimeBudget(max_attempts_per_step=1))
        result = await worker_b.execute_claimed(recovered, "crash-worker-b")
        await release_lease(db, investigation_id, "crash-worker-b")
        await db.commit()
        assert result["status"] == "completed"
        assert attempts == 2
        assert await db.scalar(select(func.count()).select_from(AgentToolAttempt).join(AgentPlanStep).join(AgentPlan).where(AgentPlan.investigation_id == investigation_id)) == 2
        assert await db.scalar(select(func.count()).select_from(AgentObservation).where(AgentObservation.investigation_id == investigation_id, AgentObservation.success.is_(True))) == 1
        assert await db.scalar(select(func.count()).select_from(EvidenceItem).where(EvidenceItem.session_id == investigation_id)) == 1
        assert await db.scalar(select(func.count()).select_from(VerifiedClaim).where(VerifiedClaim.session_id == investigation_id, VerifiedClaim.verification_status == "VERIFIED")) == 1
