import asyncio
import uuid
from typing import List, AsyncGenerator
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Request, Header
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_
from app.models.evidence import RuntimeEvent

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
from app.agent.runtime import persist_runtime_event, logical_identity, publish_persisted_runtime_events
from app.core.rate_limit import client_ip, enforce_rate_limit
from app.core.config import settings
from app.core.observability import SSE_CONNECTIONS

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
    request: Request,
    current_user: User = Depends(get_current_user),
    membership: WorkspaceMembership = Depends(require_role(WorkspaceRole.EDITOR)),
    db: AsyncSession = Depends(get_db)
    , idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")
):
    """Start an evidence-grounded investigation and dispatch the bounded runtime."""
    await enforce_rate_limit(db, key=f"investigation:user:{current_user.id}", limit=settings.RATE_LIMIT_INVESTIGATION_PER_HOUR, window_seconds=3600)
    await enforce_rate_limit(db, key=f"investigation:workspace:{workspace_id}", limit=settings.RATE_LIMIT_INVESTIGATION_PER_HOUR * 3, window_seconds=3600)
    if idempotency_key:
        existing = (await db.execute(select(InvestigationSession).where(InvestigationSession.idempotency_key == idempotency_key, InvestigationSession.workspace_id == workspace_id, InvestigationSession.user_id == current_user.id))).scalar_one_or_none()
        if existing:
            # Avoid lazy-loading the steps relationship from an async session
            # during response validation; the idempotent replay only needs to
            # return the authoritative investigation identity/state.
            return ResponseEnvelope.ok(InvestigationResponse(
                id=existing.id, workspace_id=existing.workspace_id,
                user_id=existing.user_id, objective=existing.objective,
                status=existing.status, current_state=existing.current_state,
                plan_version=existing.plan_version,
                failure_code=existing.failure_code,
                failure_message=existing.failure_message,
                final_response=existing.final_response,
                token_usage=existing.token_usage or {},
                error_message=existing.error_message,
                created_at=existing.created_at,
                completed_at=existing.completed_at, steps=[],
            ))
    session = InvestigationSession(
        workspace_id=workspace_id,
        user_id=current_user.id,
        objective=req.objective.strip(),
        status=InvestigationStatus.PLANNING.value,
        idempotency_key=idempotency_key
    )
    db.add(session)
    # Creation and its authoritative lifecycle event commit together.  The
    # event is persisted before any background execution is scheduled.
    await db.flush()
    await persist_runtime_event(
        db,
        session.id,
        "investigation.created",
        logical_identity(session.id, "investigation.created"),
        {"workspace_id": str(workspace_id), "user_id": str(current_user.id)},
        session.id,
    )
    await db.commit()
    await publish_persisted_runtime_events(db)
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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Authenticated DB-cursor SSE; persisted events are the sole replay source."""
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
            WorkspaceMembership.user_id == current_user.id
        )
    )).scalar_one_or_none()

    if not mem:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this investigation stream."
        )

    last_id = request.headers.get("last-event-id")
    cursor_time = None
    if last_id:
        try:
            previous = (await db.execute(select(RuntimeEvent).where(RuntimeEvent.id == uuid.UUID(last_id), RuntimeEvent.investigation_id == investigation_id))).scalar_one_or_none()
            if previous is None:
                raise HTTPException(status_code=404, detail="Event cursor not found in this investigation.")
            cursor_time = previous.created_at
        except ValueError:
            raise HTTPException(status_code=400, detail="Malformed event cursor.")

    # Authorization is complete. A long-lived stream must not retain the
    # transaction/connection used for authentication while waiting on a client.
    await db.close()

    async def event_generator() -> AsyncGenerator[str, None]:
        nonlocal cursor_time, last_id
        SSE_CONNECTIONS.inc()
        try:
            yield f"event: connected\ndata: {{\"session_id\": \"{investigation_id}\"}}\n\n"
            heartbeat = 0
            while not await request.is_disconnected():
                stmt = select(RuntimeEvent).where(RuntimeEvent.investigation_id == investigation_id)
                if cursor_time is not None and last_id:
                    stmt = stmt.where(or_(RuntimeEvent.created_at > cursor_time, and_(RuntimeEvent.created_at == cursor_time, RuntimeEvent.id > uuid.UUID(last_id))))
                events = (await db.execute(stmt.order_by(RuntimeEvent.created_at.asc(), RuntimeEvent.id.asc()).limit(500))).scalars().all()
                # Materialized rows remain readable after detaching. Return the
                # connection before any network yield or polling delay; the next
                # query starts a fresh transaction and sees newly committed rows.
                await db.close()
                for event in events:
                    data = {"event_id": str(event.id), "event_type": event.event_type, "entity_id": str(event.entity_id) if event.entity_id else None, "payload": event.payload or {}, "created_at": event.created_at.isoformat()}
                    import json
                    yield f"id: {event.id}\nevent: {event.event_type}\ndata: {json.dumps(data, default=str)}\n\n"
                    cursor_time, last_id = event.created_at, str(event.id)
                heartbeat += 1
                if heartbeat >= 15: heartbeat = 0; yield ": heartbeat\n\n"
                await asyncio.sleep(1)
        finally: SSE_CONNECTIONS.dec()

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
    await publish_persisted_runtime_events(db)

    return ResponseEnvelope.ok(InvestigationCancelResponse(
        investigation_id=investigation_id,
        status="cancelled",
        message="Cancellation signal dispatched successfully."
    ))
