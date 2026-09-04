import uuid
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field, ConfigDict
from app.models.user import WorkspaceRole
from app.schemas.auth import UserResponse

class WorkspaceCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    description: Optional[str] = None

class WorkspaceUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=255)
    description: Optional[str] = None

class WorkspaceMemberAddRequest(BaseModel):
    email: EmailStr
    role: WorkspaceRole = WorkspaceRole.EDITOR

class WorkspaceMemberResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    role: str
    created_at: datetime
    user: Optional[UserResponse] = None

    model_config = ConfigDict(from_attributes=True)

class WorkspaceResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str] = None
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime
    user_role: Optional[str] = None
    members_count: Optional[int] = None
    documents_count: Optional[int] = None
    tables_count: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)
