import asyncio
from uuid import UUID

import pytest
from pydantic import BaseModel
from sqlalchemy import select, func

from app.agent.runtime import DurablePlanExecutor, PlanSpec, PlanStepSpec, RuntimeBudget, RuntimeState, ToolDefinition, ToolRegistry
from app.agent.service import run_investigation, RetrievalInput
from app.agent.sse_manager import sse_manager
from app.models.evidence import RuntimeEvent
from app.models.investigation import AgentPlanStep, InvestigationSession


@pytest.mark.asyncio
async def test_investigation_creation_persists_event(client, db_session, test_workspace, auth_headers, monkeypatch):
    async def no_background(*_args, **_kwargs):
        return None
    monkeypatch.setattr("app.api.v1.investigations._run_agent_task", no_background)
    response = await client.post(
        f"/api/v1/workspaces/{test_workspace.id}/investigations",
        headers={**auth_headers, "Idempotency-Key": "closure-created"},
        json={"objective": "event creation", "max_steps": 1},
    )
    assert response.status_code == 200
    investigation_id = UUID(response.json()["data"]["id"])
    events = (await db_session.execute(select(RuntimeEvent).where(RuntimeEvent.investigation_id == investigation_id, RuntimeEvent.event_type == "investigation.created"))).scalars().all()
    assert len(events) == 1 and events[0].id and events[0].payload["workspace_id"] == str(test_workspace.id)

    replay = await client.post(
        f"/api/v1/workspaces/{test_workspace.id}/investigations",
        headers={**auth_headers, "Idempotency-Key": "closure-created"},
        json={"objective": "event creation", "max_steps": 1},
    )
    assert replay.status_code == 200 and replay.json()["data"]["id"] == str(investigation_id)
    assert await db_session.scalar(select(func.count()).select_from(RuntimeEvent).where(RuntimeEvent.investigation_id == investigation_id, RuntimeEvent.event_type == "investigation.created")) == 1


class EmptyInput(BaseModel):
    pass


@pytest.mark.asyncio
async def test_failed_step_persists_step_failed_event(db_session, test_user, test_workspace):
    investigation = InvestigationSession(workspace_id=test_workspace.id, user_id=test_user.id, objective="failure event")
    db_session.add(investigation)
    await db_session.commit()

    async def fail(_context, _input):
        raise RuntimeError("permanent failure")
    registry = ToolRegistry()
    registry.register(ToolDefinition(name="failing", description="failure", input_model=EmptyInput, execute=fail, max_attempts=1))
    plan = PlanSpec(objective="failure event", steps=[PlanStepSpec(step_id="failed-step", objective="fail", tool_name="failing", inputs={})])
    with pytest.raises(RuntimeError):
        await DurablePlanExecutor(db_session, registry, RuntimeBudget(max_attempts_per_step=1)).execute(investigation, plan)
    await db_session.commit()
    step = (await db_session.execute(select(AgentPlanStep).join(AgentPlanStep.plan).where(AgentPlanStep.step_key == "failed-step"))).scalar_one()
    assert step.status == "FAILED"
    events = (await db_session.execute(select(RuntimeEvent).where(RuntimeEvent.investigation_id == investigation.id, RuntimeEvent.event_type == "step.failed"))).scalars().all()
    assert len(events) == 1 and events[0].entity_id == step.id


@pytest.mark.asyncio
async def test_transport_publishes_persisted_event_identity(db_session, test_user, test_workspace):
    investigation = InvestigationSession(workspace_id=test_workspace.id, user_id=test_user.id, objective="transport events")
    db_session.add(investigation)
    await db_session.commit()
    queue = sse_manager.subscribe(str(investigation.id))
    registry = ToolRegistry()
    registry.register(ToolDefinition(name="hybrid_document_search", description="answer", input_model=RetrievalInput, execute=lambda context, input: {"results": [{"content": "evidence"}]}, max_attempts=1))
    result = await run_investigation(investigation.id, db_session, worker_id="transport-test", registry=registry)
    assert result["status"] == "completed", {"result": result, "state": investigation.current_state, "failure": investigation.failure_code}
    persisted = (await db_session.execute(select(RuntimeEvent).where(RuntimeEvent.investigation_id == investigation.id))).scalars().all()
    persisted_ids = {str(event.id) for event in persisted}
    payloads = []
    while not queue.empty():
        raw = await queue.get()
        if "event_id" in raw:
            import json
            payloads.append(json.loads(raw.split("data: ", 1)[1]))
    assert payloads
    assert all(item["event_id"] in persisted_ids for item in payloads)
    sse_manager.unsubscribe(str(investigation.id), queue)
