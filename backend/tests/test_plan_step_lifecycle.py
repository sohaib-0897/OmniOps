"""Regression tests for terminal plan-step status on a successful investigation.

The live E2E completed an investigation whose `agent_plan_steps` row was still
`PENDING`, because the executor only mirrored the FAILED outcome into the
persisted row. Plan-step status must be authoritative for both outcomes.
"""
import pytest
from pydantic import BaseModel
from sqlalchemy import select

from app.agent.runtime import (
    DurablePlanExecutor,
    PlanSpec,
    PlanStepSpec,
    RuntimeState,
    ToolDefinition,
    ToolRegistry,
)
from app.models.investigation import AgentPlan, AgentPlanStep, InvestigationSession


class Value(BaseModel):
    value: int


def _registry(execute):
    registry = ToolRegistry()
    registry.register(ToolDefinition(
        name="answer", description="answer", input_model=Value, execute=execute,
    ))
    return registry


async def _plan_step_statuses(db, investigation_id):
    return (await db.execute(
        select(AgentPlanStep.step_key, AgentPlanStep.status)
        .join(AgentPlan, AgentPlan.id == AgentPlanStep.plan_id)
        .where(AgentPlan.investigation_id == investigation_id)
        .order_by(AgentPlanStep.sequence)
    )).all()


def _plan(step_ids):
    return PlanSpec(objective="lifecycle", steps=[
        PlanStepSpec(step_id=step_id, objective="lifecycle", tool_name="answer", inputs={"value": 1})
        for step_id in step_ids
    ])


@pytest.mark.asyncio
async def test_successful_steps_reach_a_terminal_persisted_status(db_session, test_user, test_workspace):
    investigation = InvestigationSession(
        workspace_id=test_workspace.id, user_id=test_user.id, objective="lifecycle",
    )
    db_session.add(investigation)
    await db_session.commit()

    registry = _registry(lambda context, input: input.value)
    result = await DurablePlanExecutor(db_session, registry).execute(
        investigation, _plan(["step-a", "step-b"]),
    )

    assert result["status"] == "completed"
    assert investigation.current_state == RuntimeState.COMPLETED.value
    assert await _plan_step_statuses(db_session, investigation.id) == [
        ("step-a", "COMPLETED"), ("step-b", "COMPLETED"),
    ]


@pytest.mark.asyncio
async def test_failed_step_status_remains_failed(db_session, test_user, test_workspace):
    investigation = InvestigationSession(
        workspace_id=test_workspace.id, user_id=test_user.id, objective="lifecycle-failure",
    )
    db_session.add(investigation)
    await db_session.commit()
    investigation_id = investigation.id

    def explode(context, input):
        raise RuntimeError("TOOL_EXECUTION_FAILED")

    with pytest.raises(Exception):
        await DurablePlanExecutor(db_session, _registry(explode)).execute(
            investigation, _plan(["step-a"]),
        )

    statuses = await _plan_step_statuses(db_session, investigation_id)
    assert statuses == [("step-a", "FAILED")]


@pytest.mark.asyncio
async def test_cancellation_leaves_unrun_steps_non_terminal(db_session, test_user, test_workspace):
    investigation = InvestigationSession(
        workspace_id=test_workspace.id, user_id=test_user.id, objective="lifecycle-cancel",
    )
    investigation.cancellation_requested = True
    db_session.add(investigation)
    await db_session.commit()

    result = await DurablePlanExecutor(db_session, _registry(lambda context, input: input.value)).execute(
        investigation, _plan(["step-a"]),
    )

    assert result["status"] == RuntimeState.CANCELLED.value
    assert await _plan_step_statuses(db_session, investigation.id) == [("step-a", "PENDING")]
