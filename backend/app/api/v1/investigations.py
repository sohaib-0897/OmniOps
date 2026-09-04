import asyncio
import uuid
from typing import List, AsyncGenerator
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Request, Header
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db, AsyncSessionLocal
from app.models.user import User, WorkspaceMembership, WorkspaceRole
from app.models.investigation import InvestigationSession, AgentStep, InvestigationStatus, RuntimeState
from app.schemas.investigation import (
    InvestigationCreateRequest, 
    InvestigationResponse, 
    AgentStepResponse, 
    InvestigationCancelResponse
)
from app.schemas.common import ResponseEnvelope
from app.api.deps import get_current_user, get_workspace_membership, require_role
from app.agent.service import run_investigation
from app.agent.sse_manager import sse_manager
from app.agent.runtime import resume_investigation
from app.agent.runtime import persist_runtime_event, logical_identity

router = APIRouter(tags=["Investigations"])

import logging
logger = logging.getLogger(__name__)

async def _run_agent_task(session_id: uuid.UUID, workspace_id: uuid.UUID, objective: str, max_steps: int):
    """Background task runner for agent state machine."""
    async with AsyncSessionLocal() as db:
        try:
            await run_investigation(session_id=session_id, db=db, worker_id=f"background:{session_id}")
        except Exception as e:
            logger.exception("Investigation background task %s failed: %s", session_id, e)

@router.post("/workspaces/{workspace_id}/investigations", response_model=ResponseEnvelope[InvestigationResponse])
async def create_investigation(
    workspace_id: uuid.UUID,
    req: InvestigationCreateRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    membership: WorkspaceMembership = Depends(require_role(WorkspaceRole.EDITOR)),
    db: AsyncSession = Depends(get_db)
    , idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")
):
    """Start an evidence-grounded investigation and dispatch the bounded runtime."""
    if idempotency_key:
        existing = (await db.execute(select(InvestigationSession).where(InvestigationSession.idempotency_key == idempotency_key, InvestigationSession.workspace_id == workspace_id, InvestigationSession.user_id == current_user.id))).scalar_one_or_none()
        if existing:
            return ResponseEnvelope.ok(InvestigationResponse.model_validate(existing))
    session = InvestigationSession(
        workspace_id=workspace_id,
        user_id=current_user.id,
        objective=req.objective.strip(),
        status=InvestigationStatus.PLANNING.value,
        idempotency_key=idempotency_key
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    # Launch background state machine
    background_tasks.add_task(
        _run_agent_task,
        session.id,
        workspace_id,
        req.objective.strip(),
        req.max_steps or 12
    )

    resp = InvestigationResponse(
        id=session.id,
        workspace_id=session.workspace_id,
        user_id=session.user_id,
        objective=session.objective,
        status=session.status,
        current_state=session.current_state,
        plan_version=session.plan_version,
        failure_code=session.failure_code,
        failure_message=session.failure_message,
        final_response=session.final_response,
        token_usage=session.token_usage or {},
        error_message=session.error_message,
        created_at=session.created_at,
        completed_at=session.completed_at,
        steps=[]
    )
    return ResponseEnvelope.ok(resp)


@router.post("/investigations/{investigation_id}/resume", response_model=ResponseEnvelope[InvestigationResponse])
async def resume_investigation_endpoint(
    investigation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Acquire a durable worker lease and resume only non-terminal work."""
    session = (await db.execute(select(InvestigationSession).where(InvestigationSession.id == investigation_id))).scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Investigation not found.")
    mem = (await db.execute(select(WorkspaceMembership).where(WorkspaceMembership.workspace_id == session.workspace_id, WorkspaceMembership.user_id == current_user.id))).scalar_one_or_none()
    if not mem:
        raise HTTPException(status_code=403, detail="Access denied to this investigation.")
    try:
        await resume_investigation(db, investigation_id, f"api:{current_user.id}")
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    await db.refresh(session)
    return ResponseEnvelope.ok(InvestigationResponse.model_validate(session))

@router.get("/investigations/{investigation_id}", response_model=ResponseEnvelope[InvestigationResponse])
async def get_investigation(
    investigation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get investigation session, final report, and executed steps."""
    session = (await db.execute(
        select(InvestigationSession).where(InvestigationSession.id == investigation_id)
    )).scalar_one_or_none()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Investigation not found."
        )

    # Authorize workspace membership
    mem = (await db.execute(
        select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == session.workspace_id,
            WorkspaceMembership.user_id == current_user.id
        )
    )).scalar_one_or_none()

    if not mem:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this investigation."
        )

    steps = (await db.execute(
        select(AgentStep).where(AgentStep.session_id == investigation_id).order_by(AgentStep.step_number.asc())
    )).scalars().all()

    resp = InvestigationResponse(
        id=session.id,
        workspace_id=session.workspace_id,
        user_id=session.user_id,
        objective=session.objective,
        status=session.status,
        current_state=session.current_state,
        plan_version=session.plan_version,
        failure_code=session.failure_code,
        failure_message=session.failure_message,
        final_response=session.final_response,
        token_usage=session.token_usage or {},
        error_message=session.error_message,
        created_at=session.created_at,
        completed_at=session.completed_at,
        steps=[AgentStepResponse.model_validate(s) for s in steps]
    )
    return ResponseEnvelope.ok(resp)

@router.get("/investigations/{investigation_id}/stream")
async def stream_investigation_events(
    investigation_id: uuid.UUID,
    request: Request,
    token: str,  # Query param for SSE browser event source
    db: AsyncSession = Depends(get_db)
):
    """SSE Stream for real-time agent execution activity with strict tenant authorization."""
    # 1. Verify token
    from app.core.security import decode_access_token
    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    try:
        user_id = uuid.UUID(payload["sub"])
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Malformed token subject")

    # 2. Verify investigation exists and user is an authorized workspace member
    session = (await db.execute(
        select(InvestigationSession).where(InvestigationSession.id == investigation_id)
    )).scalar_one_or_none()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Investigation not found."
        )

    mem = (await db.execute(
        select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == session.workspace_id,
            WorkspaceMembership.user_id == user_id
        )
    )).scalar_one_or_none()

    if not mem:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this investigation stream."
        )

    session_id_str = str(investigation_id)
    queue = sse_manager.subscribe(session_id_str)

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            # Send initial connection event
            yield f"event: connected\ndata: {{\"session_id\": \"{session_id_str}\"}}\n\n"
            
            while True:
                if await request.is_disconnected():
                    break
                try:
                    # Wait for next event with 15s heartbeat timeout
                    event_payload = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield event_payload
                except asyncio.TimeoutError:
                    # Heartbeat comment
                    yield ": heartbeat\n\n"
        finally:
            sse_manager.unsubscribe(session_id_str, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

@router.post("/investigations/{investigation_id}/cancel", response_model=ResponseEnvelope[InvestigationCancelResponse])
async def cancel_investigation(
    investigation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Request immediate cancellation of running investigation."""
    session = (await db.execute(
        select(InvestigationSession).where(InvestigationSession.id == investigation_id)
    )).scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Investigation not found.")

    mem = (await db.execute(
        select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == session.workspace_id,
            WorkspaceMembership.user_id == current_user.id
        )
    )).scalar_one_or_none()

    if not mem or mem.role not in [WorkspaceRole.OWNER.value, WorkspaceRole.EDITOR.value]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only workspace editors or owners can cancel investigations.")

    # Signal cancellation
    session_id_str = str(investigation_id)
    sse_manager.request_cancellation(session_id_str)

    session.cancellation_requested = True
    session.current_state = RuntimeState.CANCELLED.value
    session.status = InvestigationStatus.CANCELLED.value
    session.failure_code = "CANCELLED"
    session.failure_message = "Cancellation requested by user."
    await persist_runtime_event(db, investigation_id, "investigation.cancelled", logical_identity(investigation_id, "investigation.cancelled"), {"reason": "user_request"})
    await db.commit()

    return ResponseEnvelope.ok(InvestigationCancelResponse(
        investigation_id=investigation_id,
        status="cancelled",
        message="Cancellation signal dispatched successfully."
    ))
