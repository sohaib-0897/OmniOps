import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import get_password_hash, verify_password, create_access_token
from app.core.config import settings
from app.models.user import User, Workspace, WorkspaceMembership, WorkspaceRole
from app.schemas.auth import (
    UserRegisterRequest, 
    UserLoginRequest, 
    AuthSessionResponse, 
    UserResponse, 
    TokenResponse
)
from app.schemas.common import ResponseEnvelope
from app.api.deps import get_current_user

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/register", response_model=ResponseEnvelope[AuthSessionResponse])
async def register_user(
    req: UserRegisterRequest,
    db: AsyncSession = Depends(get_db)
):
    """Register new user, initialize default workspace, and return access token."""
    # Check duplicate email
    stmt = select(User).where(User.email == req.email.lower().strip())
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email address already exists."
        )

    user = User(
        email=req.email.lower().strip(),
        hashed_password=get_password_hash(req.password),
        full_name=req.full_name.strip()
    )
    db.add(user)
    await db.flush()

    # Create default workspace
    workspace = Workspace(
        name=f"{req.full_name.split()[0]}'s Workspace",
        description="Default business intelligence workspace.",
        created_by=user.id
    )
    db.add(workspace)
    await db.flush()

    # Create Owner membership
    membership = WorkspaceMembership(
        workspace_id=workspace.id,
        user_id=user.id,
        role=WorkspaceRole.OWNER.value
    )
    db.add(membership)
    await db.commit()
    await db.refresh(user)

    token = create_access_token(subject=user.id)
    return ResponseEnvelope.ok(AuthSessionResponse(
        user=UserResponse.model_validate(user),
        token=TokenResponse(
            access_token=token,
            expires_in_seconds=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        )
    ))

@router.post("/login", response_model=ResponseEnvelope[AuthSessionResponse])
async def login_user(
    req: UserLoginRequest,
    db: AsyncSession = Depends(get_db)
):
    """Authenticate user credentials and issue JWT token."""
    stmt = select(User).where(User.email == req.email.lower().strip())
    user = (await db.execute(stmt)).scalar_one_or_none()
    
    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password."
        )

    token = create_access_token(subject=user.id)
    return ResponseEnvelope.ok(AuthSessionResponse(
        user=UserResponse.model_validate(user),
        token=TokenResponse(
            access_token=token,
            expires_in_seconds=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        )
    ))

@router.get("/me", response_model=ResponseEnvelope[UserResponse])
async def get_current_user_profile(
    current_user: User = Depends(get_current_user)
):
    """Return currently authenticated user profile."""
    return ResponseEnvelope.ok(UserResponse.model_validate(current_user))
