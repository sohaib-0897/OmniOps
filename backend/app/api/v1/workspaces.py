import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.database import get_db
from app.models.user import User, Workspace, WorkspaceMembership, WorkspaceRole
from app.models.document import SourceDocument, TabularDataset
from app.schemas.workspace import (
    WorkspaceCreateRequest, 
    WorkspaceResponse, 
    WorkspaceMemberAddRequest, 
    WorkspaceMemberResponse
)
from app.schemas.common import ResponseEnvelope
from app.api.deps import get_current_user, get_workspace_membership, require_role

router = APIRouter(prefix="/workspaces", tags=["Workspaces"])

@router.get("", response_model=ResponseEnvelope[List[WorkspaceResponse]])
async def list_user_workspaces(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List all workspaces where the current user is a member."""
    docs_subq = (
        select(func.count(SourceDocument.id))
        .where(SourceDocument.workspace_id == Workspace.id)
        .scalar_subquery()
    )
    tables_subq = (
        select(func.count(TabularDataset.id))
        .where(TabularDataset.workspace_id == Workspace.id)
        .scalar_subquery()
    )
    stmt = (
        select(Workspace, WorkspaceMembership.role, docs_subq, tables_subq)
        .join(WorkspaceMembership, Workspace.id == WorkspaceMembership.workspace_id)
        .where(WorkspaceMembership.user_id == current_user.id)
        .order_by(Workspace.created_at.desc())
    )
    result = await db.execute(stmt)
    rows = result.all()

    workspaces_out = [
        WorkspaceResponse(
            id=ws.id,
            name=ws.name,
            description=ws.description,
            created_by=ws.created_by,
            created_at=ws.created_at,
            updated_at=ws.updated_at,
            user_role=role,
            documents_count=docs_count or 0,
            tables_count=tables_count or 0
        )
        for ws, role, docs_count, tables_count in rows
    ]

    return ResponseEnvelope.ok(workspaces_out)

@router.post("", response_model=ResponseEnvelope[WorkspaceResponse])
async def create_workspace(
    req: WorkspaceCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new isolated workspace and set current user as Owner."""
    workspace = Workspace(
        name=req.name.strip(),
        description=req.description,
        created_by=current_user.id
    )
    db.add(workspace)
    await db.flush()

    membership = WorkspaceMembership(
        workspace_id=workspace.id,
        user_id=current_user.id,
        role=WorkspaceRole.OWNER.value
    )
    db.add(membership)
    await db.commit()
    await db.refresh(workspace)

    return ResponseEnvelope.ok(WorkspaceResponse(
        id=workspace.id,
        name=workspace.name,
        description=workspace.description,
        created_by=workspace.created_by,
        created_at=workspace.created_at,
        updated_at=workspace.updated_at,
        user_role=WorkspaceRole.OWNER.value,
        documents_count=0,
        tables_count=0
    ))

@router.get("/{workspace_id}", response_model=ResponseEnvelope[WorkspaceResponse])
async def get_workspace_detail(
    workspace_id: uuid.UUID,
    membership: WorkspaceMembership = Depends(get_workspace_membership),
    db: AsyncSession = Depends(get_db)
):
    """Get single workspace details with dataset metrics."""
    ws = (await db.execute(select(Workspace).where(Workspace.id == workspace_id))).scalar_one()
    
    docs_count = (await db.execute(
        select(func.count(SourceDocument.id)).where(SourceDocument.workspace_id == ws.id)
    )).scalar() or 0
    
    tables_count = (await db.execute(
        select(func.count(TabularDataset.id)).where(TabularDataset.workspace_id == ws.id)
    )).scalar() or 0

    return ResponseEnvelope.ok(WorkspaceResponse(
        id=ws.id,
        name=ws.name,
        description=ws.description,
        created_by=ws.created_by,
        created_at=ws.created_at,
        updated_at=ws.updated_at,
        user_role=membership.role,
        documents_count=docs_count,
        tables_count=tables_count
    ))

@router.post("/{workspace_id}/members", response_model=ResponseEnvelope[WorkspaceMemberResponse])
async def add_workspace_member(
    workspace_id: uuid.UUID,
    req: WorkspaceMemberAddRequest,
    membership: WorkspaceMembership = Depends(require_role(WorkspaceRole.OWNER)),
    db: AsyncSession = Depends(get_db)
):
    """Invite/add user to workspace with specified role (Owner only)."""
    target_user = (await db.execute(
        select(User).where(User.email == req.email.lower().strip())
    )).scalar_one_or_none()

    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with email '{req.email}' not found."
        )

    # Check if already a member
    existing_mem = (await db.execute(
        select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == workspace_id,
            WorkspaceMembership.user_id == target_user.id
        )
    )).scalar_one_or_none()

    if existing_mem:
        existing_mem.role = req.role.value
        await db.commit()
        await db.refresh(existing_mem)
        return ResponseEnvelope.ok(WorkspaceMemberResponse.model_validate(existing_mem))

    new_mem = WorkspaceMembership(
        workspace_id=workspace_id,
        user_id=target_user.id,
        role=req.role.value
    )
    db.add(new_mem)
    await db.commit()
    await db.refresh(new_mem)

    return ResponseEnvelope.ok(WorkspaceMemberResponse.model_validate(new_mem))
