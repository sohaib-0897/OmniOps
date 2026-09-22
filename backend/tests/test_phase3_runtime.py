import asyncio
import uuid
from datetime import datetime, timezone

import pytest
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.agent.runtime import (
    DurablePlanExecutor,
    ObservationDecision,
    PlanSpec,
    PlanStepSpec,
    RuntimeBudget,
    RuntimeState,
    ToolDefinition,
    ToolRegistry,
    acquire_lease,
    claim_next_investigation,
    detect_numeric_contradictions,
    get_or_create_logical_output,
    logical_identity,
    persist_runtime_event,
    record_contradiction,
    release_lease,
    replan,
    resume_investigation,
    transition,
)
from app.agent.service import InvestigationRuntime, run_investigation, RetrievalInput
from app.models.evidence import RuntimeEvent
from app.models.investigation import AgentObservation, AgentPlan, AgentToolAttempt, InvestigationSession
from app.models.user import User


class Input(BaseModel):
    value: int


def test_plan_rejects_unknown_duplicate_and_cycles():
    with pytest.raises(ValueError, match="unknown tool"):
        PlanSpec(objective="x", steps=[PlanStepSpec(step_id="a", objective="x", tool_name="missing")]).validate_graph([])
    with pytest.raises(ValueError, match="duplicate"):
        PlanSpec(objective="x", steps=[PlanStepSpec(step_id="a", objective="x", tool_name="ok"), PlanStepSpec(step_id="a", objective="y", tool_name="ok")]).validate_graph(["ok"])
    with pytest.raises(ValueError, match="cycle"):
        PlanSpec(objective="x", steps=[PlanStepSpec(step_id="a", objective="x", tool_name="ok", dependencies=["b"]), PlanStepSpec(step_id="b", objective="y", tool_name="ok", dependencies=["a"])]).validate_graph(["ok"])


@pytest.mark.asyncio
async def test_registry_invokes_new_tool_without_orchestrator_branch():
    registry = ToolRegistry()
    registry.register(ToolDefinition(name="new_tool", description="test", input_model=Input, execute=lambda context, input: {"value": input.value + 1}))
    assert await registry.invoke("new_tool", {"value": 4}) == {"value": 5}
    with pytest.raises(RuntimeError, match="TOOL_UNAVAILABLE"):
        await registry.invoke("missing", {})


@pytest.mark.asyncio
async def test_registry_timeout_is_bounded():
    async def slow(context, input):
        await asyncio.sleep(1)
    registry = ToolRegistry()
    registry.register(ToolDefinition(name="slow", description="test", input_model=Input, execute=slow, timeout_seconds=0.01))
    with pytest.raises(asyncio.TimeoutError):
        await registry.invoke("slow", {"value": 1})


@pytest.mark.asyncio
async def test_transition_rules_are_explicit_and_persisted(db_session, test_user, test_workspace):
    investigation = InvestigationSession(workspace_id=test_workspace.id, user_id=test_user.id, objective="state")
    db_session.add(investigation)
    await db_session.commit()
    await transition(db_session, investigation, RuntimeState.PLANNING, "start")
    await db_session.commit()
    assert investigation.current_state == RuntimeState.PLANNING.value
    with pytest.raises(ValueError, match="INVALID_STATE_TRANSITION"):
        await transition(db_session, investigation, RuntimeState.COMPLETED, "skip")


@pytest.mark.asyncio
async def test_durable_executor_persists_plan_attempt_and_observation(db_session, test_user, test_workspace):
    investigation = InvestigationSession(workspace_id=test_workspace.id, user_id=test_user.id, objective="execute")
    db_session.add(investigation)
    await db_session.commit()
    registry = ToolRegistry()
    registry.register(ToolDefinition(name="answer", description="test", input_model=Input, execute=lambda context, input: input.value, max_attempts=1))
    plan = PlanSpec(objective="execute", steps=[PlanStepSpec(step_id="one", objective="answer", tool_name="answer", inputs={"value": 7})])
    result = await DurablePlanExecutor(db_session, registry, RuntimeBudget(max_steps=2)).execute(investigation, plan)
    await db_session.commit()
    assert result == {"status": "completed", "outputs": {"one": 7}}
    assert (await db_session.execute(select(AgentPlan))).scalars().all()
    assert (await db_session.execute(select(AgentToolAttempt))).scalars().all()
    assert (await db_session.execute(select(AgentObservation))).scalars().all()


@pytest.mark.asyncio
async def test_replan_preserves_version_history(db_session, test_user, test_workspace):
    investigation = InvestigationSession(workspace_id=test_workspace.id, user_id=test_user.id, objective="replan")
    db_session.add(investigation)
    await db_session.commit()
    registry = ToolRegistry()
    registry.register(ToolDefinition(name="answer", description="test", input_model=Input, execute=lambda context, input: input.value))
    await transition(db_session, investigation, RuntimeState.PLANNING, "start")
    await transition(db_session, investigation, RuntimeState.READY, "planned")
    await transition(db_session, investigation, RuntimeState.EXECUTING, "execute")
    await transition(db_session, investigation, RuntimeState.OBSERVING, "empty_result")
    revised = await replan(db_session, investigation, PlanSpec(objective="replan", steps=[PlanStepSpec(step_id="replacement", objective="retry", tool_name="answer", inputs={"value": 2})]), registry, "missing evidence", RuntimeBudget(max_plan_versions=2))
    await db_session.commit()
    assert revised.version == 1
    assert investigation.current_state == RuntimeState.READY.value


@pytest.mark.asyncio
async def test_automatic_observation_replan_increments_version(db_session, test_user, test_workspace):
    investigation = InvestigationSession(workspace_id=test_workspace.id, user_id=test_user.id, objective="missing evidence")
    db_session.add(investigation)
    await db_session.commit()
    registry = ToolRegistry()
    registry.register(ToolDefinition(name="empty", description="empty", input_model=Input, execute=lambda context, input: {}, max_attempts=1))
    registry.register(ToolDefinition(name="answer", description="answer", input_model=Input, execute=lambda context, input: input.value, max_attempts=1))
    async def replanner(**kwargs):
        return PlanSpec(objective="missing evidence", steps=[PlanStepSpec(step_id="replacement", objective="answer", tool_name="answer", inputs={"value": 9})])
    plan = PlanSpec(objective="missing evidence", steps=[PlanStepSpec(step_id="first", objective="find", tool_name="empty", inputs={"value": 1}, completion_criteria={"evidence_required": True})])
    result = await DurablePlanExecutor(db_session, registry, RuntimeBudget(max_plan_versions=2), replanner=replanner).execute(investigation, plan)
    assert result["status"] == "replanned"
    assert investigation.plan_version == 2
    assert investigation.current_state == RuntimeState.READY.value


@pytest.mark.asyncio
async def test_lease_and_resume_orphan_running_attempt(db_session, test_user, test_workspace):
    investigation = InvestigationSession(workspace_id=test_workspace.id, user_id=test_user.id, objective="resume")
    db_session.add(investigation)
    await db_session.commit()
    assert await acquire_lease(db_session, investigation, "worker-a")
    await db_session.commit()
    with pytest.raises(RuntimeError, match="WORKER_LEASE_UNAVAILABLE"):
        await resume_investigation(db_session, investigation.id, "worker-b")


@pytest.mark.asyncio
async def test_release_lease_uses_stable_id_after_orm_expiration(db_session, test_user, test_workspace):
    investigation = InvestigationSession(workspace_id=test_workspace.id, user_id=test_user.id, objective="expired cleanup")
    db_session.add(investigation)
    await db_session.commit()
    investigation_id = investigation.id
    assert await acquire_lease(db_session, investigation, "worker-a")
    await db_session.commit()

    db_session.expire(investigation)
    await release_lease(db_session, investigation_id, "worker-a")
    await db_session.commit()

    stored = await db_session.get(InvestigationSession, investigation_id)
    assert stored.worker_id is None
    assert stored.lease_expires_at is None


@pytest.mark.asyncio
async def test_worker_cleanup_rolls_back_failed_flush_before_releasing_lease(
    db_session, test_user, test_workspace, monkeypatch,
):
    investigation = InvestigationSession(
        workspace_id=test_workspace.id,
        user_id=test_user.id,
        objective="failed flush cleanup",
    )
    db_session.add(investigation)
    await db_session.commit()
    investigation_id = investigation.id
    runtime = InvestigationRuntime(db_session)

    async def fail_with_invalid_transaction(_investigation, _worker_id):
        db_session.add(User(
            email=test_user.email,
            hashed_password="duplicate",
            full_name="Duplicate",
        ))
        await db_session.flush()

    monkeypatch.setattr(runtime, "execute_claimed", fail_with_invalid_transaction)
    with pytest.raises(IntegrityError):
        await runtime.run_worker_once("cleanup-worker")

    stored = await db_session.get(InvestigationSession, investigation_id)
    assert stored.worker_id is None
    assert stored.lease_expires_at is None


@pytest.mark.asyncio
async def test_contradictions_are_explicit_and_preserve_both_evidence(db_session, test_user, test_workspace):
    from app.models.document import SourceDocument
    from app.models.evidence import EvidenceItem
    investigation = InvestigationSession(workspace_id=test_workspace.id, user_id=test_user.id, objective="conflict")
    db_session.add(investigation)
    await db_session.flush()
    source_a = SourceDocument(workspace_id=test_workspace.id, file_name="a.txt", storage_path="a", mime_type="text/plain", byte_size=1, sha256_hash="a"*64, modality="document", processing_status="ready")
    source_b = SourceDocument(workspace_id=test_workspace.id, file_name="b.txt", storage_path="b", mime_type="text/plain", byte_size=1, sha256_hash="b"*64, modality="document", processing_status="ready")
    db_session.add_all([source_a, source_b]); await db_session.flush()
    a = EvidenceItem(session_id=investigation.id, source_id=source_a.id, exact_quote="Q2 operating margin was 18%.")
    b = EvidenceItem(session_id=investigation.id, source_id=source_b.id, exact_quote="Q2 operating margin was 14%.")
    db_session.add_all([a, b]); await db_session.flush()
    pairs = detect_numeric_contradictions([{"id": a.id, "exact_quote": a.exact_quote}, {"id": b.id, "exact_quote": b.exact_quote}])
    assert pairs
    record = await record_contradiction(db_session, investigation.id, "Q2 operating margin", a.id, b.id)
    await db_session.commit()
    assert record.status == "UNRESOLVED"


@pytest.mark.asyncio
async def test_worker_claim_and_event_output_idempotency(db_session, test_user, test_workspace):
    investigation = InvestigationSession(workspace_id=test_workspace.id, user_id=test_user.id, objective="claim")
    db_session.add(investigation); await db_session.commit()
    await transition(db_session, investigation, RuntimeState.PLANNING, "start")
    await transition(db_session, investigation, RuntimeState.READY, "planned")
    claimed = await claim_next_investigation(db_session, "worker-a")
    await db_session.commit()
    assert claimed.id == investigation.id
    assert await claim_next_investigation(db_session, "worker-b") is None
    identity = logical_identity(investigation.id, "step-1", "completed")
    first = await persist_runtime_event(db_session, investigation.id, "step.completed", identity)
    second = await persist_runtime_event(db_session, investigation.id, "step.completed", identity)
    await db_session.commit()
    assert first.id == second.id


@pytest.mark.asyncio
async def test_terminal_investigation_is_noop(db_session, test_user, test_workspace):
    investigation = InvestigationSession(workspace_id=test_workspace.id, user_id=test_user.id, objective="done", current_state=RuntimeState.COMPLETED.value)
    db_session.add(investigation); await db_session.commit()
    registry = ToolRegistry()
    registry.register(ToolDefinition(name="answer", description="answer", input_model=Input, execute=lambda context, input: input.value))
    result = await DurablePlanExecutor(db_session, registry).execute(investigation, PlanSpec(objective="done", steps=[PlanStepSpec(step_id="x", objective="x", tool_name="answer", inputs={"value": 1})]))
    assert result["status"] == "completed"


@pytest.mark.asyncio
async def test_production_entrypoint_uses_registry_runtime(db_session, test_user, test_workspace):
    calls = []
    registry = ToolRegistry()
    async def retrieval(context, input):
        calls.append(input.query)
        return {"results": [{"content": "verified evidence"}]}
    registry.register(ToolDefinition(name="hybrid_document_search", description="test", input_model=RetrievalInput, execute=retrieval, max_attempts=1))
    investigation = InvestigationSession(workspace_id=test_workspace.id, user_id=test_user.id, objective="find revenue")
    db_session.add(investigation); await db_session.commit()
    result = await run_investigation(investigation.id, db_session, worker_id="production-test", registry=registry)
    assert result["status"] == "completed"
    assert calls == ["find revenue"]
    assert investigation.current_state == RuntimeState.COMPLETED.value
    events = (await db_session.execute(select(RuntimeEvent).where(RuntimeEvent.investigation_id == investigation.id))).scalars().all()
    event_types = {e.event_type for e in events}
    assert {"state.changed", "plan.created", "tool.started", "tool.completed", "observation.created", "synthesis.started", "synthesis.completed"}.issubset(event_types)
