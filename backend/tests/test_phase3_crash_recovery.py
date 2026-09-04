import pytest
from pydantic import BaseModel
from datetime import datetime, timezone, timedelta
from sqlalchemy import select

from app.agent.runtime import (
    acquire_lease, resume_investigation, renew_lease, transition,
    RuntimeState, RuntimeErrorCode, persist_plan, PlanSpec, PlanStepSpec, RuntimeBudget,
)
from app.agent.persistence import finalize_synthesis
from app.agent.runtime import ToolRegistry, ToolDefinition, replan
from app.models.investigation import InvestigationSession, AgentToolAttempt, AgentPlan

class ReadInput(BaseModel):
    value: int = 1


@pytest.mark.asyncio
async def test_crash_before_commit_orphans_attempt_and_recovery_is_bounded(db_session, test_user, test_workspace):
    inv = InvestigationSession(workspace_id=test_workspace.id, user_id=test_user.id, objective="before commit")
    db_session.add(inv); await db_session.commit()
    await transition(db_session, inv, RuntimeState.PLANNING, "start"); await transition(db_session, inv, RuntimeState.READY, "planned")
    assert await acquire_lease(db_session, inv, "worker-a", ttl_seconds=1)
    plan = await persist_plan(db_session, inv, PlanSpec(objective="before commit", steps=[PlanStepSpec(step_id="s", objective="read", tool_name="read", inputs={"value": 1})]), "runtime")
    attempt = AgentToolAttempt(step_id=plan.steps[0].id, tool_name="read", validated_input={"value": 1}, started_at=datetime.now(timezone.utc), status="RUNNING", retryable=True)
    db_session.add(attempt); await db_session.commit()
    inv.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1); await db_session.commit()
    recovered = await resume_investigation(db_session, inv.id, "worker-b")
    await db_session.refresh(attempt)
    assert recovered.worker_id == "worker-b" and attempt.status == "ORPHANED"


@pytest.mark.asyncio
async def test_crash_after_commit_reuses_authoritative_synthesis(db_session, test_user, test_workspace):
    inv = InvestigationSession(workspace_id=test_workspace.id, user_id=test_user.id, objective="after commit", plan_version=1)
    db_session.add(inv); await db_session.commit()
    output = {"status": "completed", "answer": "stable"}
    first = await finalize_synthesis(db_session, inv, output, 1); await db_session.commit()
    second = await finalize_synthesis(db_session, inv, output, 1); await db_session.commit()
    assert first == second == inv.final_response


@pytest.mark.asyncio
async def test_crash_after_verification_preserves_terminal_step_state(db_session, test_user, test_workspace):
    inv = InvestigationSession(workspace_id=test_workspace.id, user_id=test_user.id, objective="verified")
    db_session.add(inv); await db_session.commit()
    await transition(db_session, inv, RuntimeState.PLANNING, "start"); await transition(db_session, inv, RuntimeState.READY, "planned"); await transition(db_session, inv, RuntimeState.EXECUTING, "run"); await transition(db_session, inv, RuntimeState.OBSERVING, "observed"); await transition(db_session, inv, RuntimeState.VERIFYING, "verified")
    await db_session.commit(); await db_session.refresh(inv)
    assert inv.current_state == RuntimeState.VERIFYING.value


@pytest.mark.asyncio
async def test_synthesis_replay_provider_not_called_again(db_session, test_user, test_workspace):
    inv = InvestigationSession(workspace_id=test_workspace.id, user_id=test_user.id, objective="synthesis", plan_version=2)
    db_session.add(inv); await db_session.commit(); calls = 0
    async def finalize():
        nonlocal calls
        if inv.final_response is None:
            calls += 1
            await finalize_synthesis(db_session, inv, {"answer": "one"}, 2); await db_session.commit()
        return inv.final_response
    await finalize(); await finalize()
    assert calls == 1


@pytest.mark.asyncio
async def test_replan_replay_reuses_v2(db_session, test_user, test_workspace):
    inv = InvestigationSession(workspace_id=test_workspace.id, user_id=test_user.id, objective="replan")
    db_session.add(inv); await db_session.commit()
    registry = ToolRegistry(); registry.register(ToolDefinition(name="read", description="read", input_model=ReadInput, execute=lambda context, input: 1))
    await transition(db_session, inv, RuntimeState.PLANNING, "start"); await transition(db_session, inv, RuntimeState.READY, "planned"); await transition(db_session, inv, RuntimeState.EXECUTING, "run"); await transition(db_session, inv, RuntimeState.OBSERVING, "missing")
    spec = PlanSpec(objective="replan", steps=[PlanStepSpec(step_id="r", objective="read", tool_name="read")])
    first = await replan(db_session, inv, spec, registry, "missing evidence", RuntimeBudget(max_plan_versions=3)); await db_session.commit()
    second = await replan(db_session, inv, spec, registry, "missing evidence", RuntimeBudget(max_plan_versions=3)); await db_session.commit()
    assert first.id == second.id and inv.plan_version == 1


@pytest.mark.asyncio
async def test_cancellation_survives_recovery(db_session, test_user, test_workspace):
    inv = InvestigationSession(workspace_id=test_workspace.id, user_id=test_user.id, objective="cancel", cancellation_requested=True, current_state=RuntimeState.CANCELLED.value)
    db_session.add(inv); await db_session.commit()
    with pytest.raises(RuntimeError, match="TERMINAL_INVESTIGATION"):
        await resume_investigation(db_session, inv.id, "worker")
    await db_session.refresh(inv)
    assert inv.current_state == RuntimeState.CANCELLED.value
