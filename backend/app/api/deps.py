import uuid
from typing import Optional, Callable
from fastapi import Depends, HTTPException, status, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.user import User, Workspace, WorkspaceMembership, WorkspaceRole, UserSession
from datetime import datetime, timezone

bearer_scheme = HTTPBearer(auto_error=False)

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db)
) -> User:
    """Validate Bearer token and return active authenticated user."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please provide a valid Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = credentials.credentials
    payload = decode_access_token(token)
    if not payload or "sub" not in payload or "sid" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    try:
        user_id = uuid.UUID(payload["sub"])
        session_id = uuid.UUID(payload["sid"])
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed token subject identifier.",
        )
    
    auth_session = (await db.execute(select(UserSession).where(UserSession.id == session_id, UserSession.user_id == user_id))).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if not auth_session or auth_session.revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication session is revoked or expired.")
    expiry = auth_session.expires_at.replace(tzinfo=timezone.utc) if auth_session.expires_at.tzinfo is None else auth_session.expires_at
    if expiry <= now:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication session is revoked or expired.")

    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account inactive or not found.",
        )
    
    return user

async def get_workspace_membership(
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> WorkspaceMembership:
    """Verify tenant isolation: assert current user is a member of the requested workspace."""
    stmt = select(WorkspaceMembership).where(
        WorkspaceMembership.workspace_id == workspace_id,
        WorkspaceMembership.user_id == current_user.id
    )
    result = await db.execute(stmt)
    membership = result.scalar_one_or_none()
    
    if not membership:
        # Prevent workspace enumeration: return 404 or 403
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You are not a member of this workspace.",
        )
    
    return membership

def require_role(min_role: WorkspaceRole) -> Callable:
    """Dependency factory checking if user has at least the required role in the workspace."""
    role_hierarchy = {
        WorkspaceRole.VIEWER: 1,
        WorkspaceRole.EDITOR: 2,
        WorkspaceRole.OWNER: 3
    }
    
    async def role_checker(
        membership: WorkspaceMembership = Depends(get_workspace_membership)
    ) -> WorkspaceMembership:
        user_role = membership.role
        user_level = role_hierarchy.get(WorkspaceRole(user_role), 0)
        required_level = role_hierarchy.get(min_role, 0)
        
        if user_level < required_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operation requires '{min_role.value}' role, but your role is '{user_role}'.",
            )
        return membership
        
    return role_checker
