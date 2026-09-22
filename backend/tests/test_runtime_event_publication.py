"""Regression tests for durable runtime-event publication across transactions.

The live failure-path E2E killed the durable worker: `fail_investigation`
rolls back a partially applied transaction before persisting the explicit
failure, which expired the ORM `RuntimeEvent` instances still queued in
`Session.info`. Publishing them then attempted a lazy refresh inside the async
publish loop and raised `MissingGreenlet`, terminating `python -m app.worker`.
"""
import pytest

from app.agent.runtime import (
    PENDING_RUNTIME_EVENTS,
    RuntimeEventNotice,
    logical_identity,
    persist_runtime_event,
    publish_persisted_runtime_events,
)
from app.agent.service import InvestigationRuntime
from app.agent.sse_manager import sse_manager
from app.llm.base import ProviderError, ProviderState
from app.models.evidence import RuntimeEvent
from app.models.investigation import InvestigationSession, RuntimeState
from sqlalchemy import select


@pytest.mark.asyncio
async def test_pending_events_are_transaction_independent_snapshots(db_session, test_user, test_workspace):
    investigation = InvestigationSession(workspace_id=test_workspace.id, user_id=test_user.id, objective="notice")
    db_session.add(investigation)
    await db_session.commit()

    await persist_runtime_event(
        db_session, investigation.id, "investigation.created",
        logical_identity(investigation.id, "investigation.created"), {"a": 1},
    )

    queued = list(db_session.info[PENDING_RUNTIME_EVENTS].values())
    assert queued and all(isinstance(item, RuntimeEventNotice) for item in queued)
    assert queued[0].event_type == "investigation.created"
    assert queued[0].payload == {"a": 1}


@pytest.mark.asyncio
async def test_publish_after_commit_expiry_does_not_touch_orm(db_session, test_user, test_workspace, monkeypatch):
    """The original crash: commit expires instances, publish then refreshes."""
    investigation = InvestigationSession(workspace_id=test_workspace.id, user_id=test_user.id, objective="publish")
    db_session.add(investigation)
    await db_session.commit()

    await persist_runtime_event(
        db_session, investigation.id, "investigation.completed",
        logical_identity(investigation.id, "investigation.completed"), {"plan_version": 1},
    )
    await db_session.commit()
    # Expire everything exactly as a commit boundary does before publication.
    db_session.expire_all()

    emitted = []

    async def capture(session_id, event_type, payload):
        emitted.append((session_id, event_type, payload))

    monkeypatch.setattr(sse_manager, "emit", capture)
    await publish_persisted_runtime_events(db_session)

    assert [item[1] for item in emitted] == ["investigation.completed"]
    assert emitted[0][2]["payload"] == {"plan_version": 1}
    assert PENDING_RUNTIME_EVENTS not in db_session.info


@pytest.mark.asyncio
async def test_rollback_discards_pending_events_so_only_committed_work_publishes(
    db_session, test_user, test_workspace, monkeypatch,
):
    """Reproduces the failure path: rollback, then persist + publish the failure."""
    investigation = InvestigationSession(workspace_id=test_workspace.id, user_id=test_user.id, objective="rollback")
    db_session.add(investigation)
    await db_session.commit()
    # Held as a scalar exactly as the runtime holds `investigation_id`; the
    # rollback below expires every ORM instance bound to this session.
    investigation_id = investigation.id

    await persist_runtime_event(
        db_session, investigation_id, "step.started",
        logical_identity(investigation_id, "step.started"), {},
    )
    # The partially applied transaction is abandoned; its events never existed.
    await db_session.rollback()
    assert PENDING_RUNTIME_EVENTS not in db_session.info

    await persist_runtime_event(
        db_session, investigation_id, "investigation.failed",
        logical_identity(investigation_id, "investigation.failed"),
        {"code": "PROVIDER_UNAVAILABLE"},
    )
    await db_session.commit()

    emitted = []

    async def capture(session_id, event_type, payload):
        emitted.append(event_type)

    monkeypatch.setattr(sse_manager, "emit", capture)
    # Publication must succeed rather than raising MissingGreenlet.
    await publish_persisted_runtime_events(db_session)

    assert emitted == ["investigation.failed"]


class UnavailableProvider:
    """Stands in for an unreachable Ollama endpoint."""

    def __init__(self):
        self.calls = 0

    def provenance(self):
        return {"provider": "OllamaProvider", "state": "UNAVAILABLE"}

    async def generate_investigation_plan(self, *_args, **_kwargs):
        self.calls += 1
        raise ProviderError(ProviderState.UNAVAILABLE, "PROVIDER_UNAVAILABLE", "Ollama is unavailable.")


@pytest.mark.asyncio
async def test_provider_unavailable_fails_investigation_without_killing_the_worker(
    db_session, test_user, test_workspace, monkeypatch,
):
    """End-to-end reproduction of the crash that terminated `python -m app.worker`.

    Before the fix, `fail_investigation` rolled back with ORM-bound events still
    queued and publication raised `MissingGreenlet` out of `run_worker_once`.
    """
    workspace_id, user_id = test_workspace.id, test_user.id
    investigation = InvestigationSession(
        workspace_id=workspace_id, user_id=user_id,
        objective="failure path", current_state=RuntimeState.CREATED.value,
    )
    db_session.add(investigation)
    await db_session.commit()
    investigation_id = investigation.id

    # The worker's session already carries a committed, not-yet-published
    # lifecycle event when execution begins -- this is the instance the failure
    # path's rollback used to expire out from under the publisher.
    await persist_runtime_event(
        db_session, investigation_id, "investigation.created",
        logical_identity(investigation_id, "investigation.created"),
        {"workspace_id": str(workspace_id)},
    )
    await db_session.commit()

    emitted = []

    async def capture(session_id, event_type, payload):
        emitted.append(event_type)

    monkeypatch.setattr(sse_manager, "emit", capture)

    provider = UnavailableProvider()
    runtime = InvestigationRuntime(db_session, llm_client=provider)
    # Must return normally rather than propagating and terminating the worker.
    result = await runtime.run_worker_once("worker-failure-path")

    assert provider.calls == 1
    assert result["status"] == RuntimeState.FAILED.value
    assert result["error_code"] == "PROVIDER_UNAVAILABLE"

    row = (await db_session.execute(
        select(InvestigationSession).where(InvestigationSession.id == investigation_id)
    )).scalar_one()
    assert row.status == "failed"
    assert row.failure_code == "PROVIDER_UNAVAILABLE"
    assert row.final_response is None
    assert row.worker_id is None and row.lease_expires_at is None

    persisted = (await db_session.execute(
        select(RuntimeEvent.event_type).where(RuntimeEvent.investigation_id == investigation_id)
    )).scalars().all()
    assert "investigation.failed" in persisted
    assert "investigation.completed" not in persisted
    assert "investigation.failed" in emitted
    assert "investigation.completed" not in emitted


@pytest.mark.asyncio
async def test_worker_accepts_further_work_after_a_failed_investigation(
    db_session, test_user, test_workspace, monkeypatch,
):
    """The worker identity must stay usable for the next claim."""
    async def capture(*_args, **_kwargs):
        return None

    monkeypatch.setattr(sse_manager, "emit", capture)
    # Held as scalars: the failure path rolls back, expiring these instances.
    workspace_id, user_id = test_workspace.id, test_user.id

    failing = InvestigationSession(
        workspace_id=workspace_id, user_id=user_id,
        objective="first failure", current_state=RuntimeState.CREATED.value,
    )
    db_session.add(failing)
    await db_session.commit()

    worker_id = "worker-survivor"
    first = await InvestigationRuntime(db_session, llm_client=UnavailableProvider()).run_worker_once(worker_id)
    assert first["status"] == RuntimeState.FAILED.value

    second_session = InvestigationSession(
        workspace_id=workspace_id, user_id=user_id,
        objective="second claim", current_state=RuntimeState.CREATED.value,
    )
    db_session.add(second_session)
    await db_session.commit()
    second_id = second_session.id

    second = await InvestigationRuntime(db_session, llm_client=UnavailableProvider()).run_worker_once(worker_id)
    assert second is not None

    row = (await db_session.execute(
        select(InvestigationSession).where(InvestigationSession.id == second_id)
    )).scalar_one()
    assert row.failure_code == "PROVIDER_UNAVAILABLE"
