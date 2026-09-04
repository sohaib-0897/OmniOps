import uuid
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User, Workspace
from app.models.investigation import InvestigationSession, InvestigationStatus
from app.agent.orchestrator import AgentOrchestrator
from app.agent.state import AgentStatus
from app.agent.sse_manager import sse_manager

@pytest.mark.asyncio
async def test_agent_orchestrator_execution_lifecycle(
    db_session: AsyncSession,
    test_user: User,
    test_workspace: Workspace,
    monkeypatch
):
    from app.core.config import settings
    monkeypatch.setattr(settings, "OPENAI_API_KEY", None)
    monkeypatch.setattr(settings, "GEMINI_API_KEY", None)
    session = InvestigationSession(
        workspace_id=test_workspace.id,
        user_id=test_user.id,
        objective="Investigate why Q3 revenue declined and compute the percentage contraction.",
        status=InvestigationStatus.PLANNING.value
    )
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)

    orchestrator = AgentOrchestrator(
        session_id=session.id,
        workspace_id=test_workspace.id,
        db=db_session
    )

    result = await orchestrator.run(
        objective=session.objective,
        max_steps=5
    )

    assert result is not None
    assert result["status"] == "failed"
    assert result["error_code"] == "LLM_PROVIDER_REQUIRED"

    # Verify session persisted as COMPLETED
    await db_session.refresh(session)
    assert session.status == InvestigationStatus.FAILED.value
    assert session.completed_at is not None

@pytest.mark.asyncio
async def test_agent_cancellation(
    db_session: AsyncSession,
    test_user: User,
    test_workspace: Workspace
):
    session = InvestigationSession(
        workspace_id=test_workspace.id,
        user_id=test_user.id,
        objective="Run long-running investigation to test cancellation token.",
        status=InvestigationStatus.PLANNING.value
    )
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)

    # Request cancellation before execution
    session_id_str = str(session.id)
    sse_manager.request_cancellation(session_id_str)

    orchestrator = AgentOrchestrator(
        session_id=session.id,
        workspace_id=test_workspace.id,
        db=db_session
    )

    cancel_res = await orchestrator.run(
        objective=session.objective,
        max_steps=5
    )

    assert cancel_res["status"] == "cancelled"
    await db_session.refresh(session)
    assert session.status == InvestigationStatus.CANCELLED.value
