import enum
import uuid
from typing import List, Optional
from datetime import datetime
from sqlalchemy import String, Text, Boolean, ForeignKey, UniqueConstraint, Enum, DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base
from app.models.base import BaseMixin, GUID

class WorkspaceRole(str, enum.Enum):
    OWNER = "owner"
    EDITOR = "editor"
    VIEWER = "viewer"

class User(Base, BaseMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    created_workspaces: Mapped[List["Workspace"]] = relationship(
        "Workspace", 
        back_populates="creator",
        foreign_keys="Workspace.created_by"
    )
    memberships: Mapped[List["WorkspaceMembership"]] = relationship(
        "WorkspaceMembership", 
        back_populates="user",
        cascade="all, delete-orphan"
    )
    investigations: Mapped[List["InvestigationSession"]] = relationship(
        "InvestigationSession", 
        back_populates="user"
    )
    sessions: Mapped[List["UserSession"]] = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")

class UserSession(Base, BaseMixin):
    __tablename__ = "user_sessions"
    user_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    user_agent_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    rotation_counter: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    user: Mapped["User"] = relationship("User", back_populates="sessions")
    refresh_tokens: Mapped[List["RefreshToken"]] = relationship("RefreshToken", back_populates="session", cascade="all, delete-orphan")

class RefreshToken(Base, BaseMixin):
    __tablename__ = "refresh_tokens"
    session_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("user_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    replaced_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(GUID(), nullable=True)
    session: Mapped["UserSession"] = relationship("UserSession", back_populates="refresh_tokens")

class RateLimitBucket(Base):
    __tablename__ = "rate_limit_buckets"
    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    request_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

class Workspace(Base, BaseMixin):
    __tablename__ = "workspaces"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        GUID(), 
        ForeignKey("users.id", ondelete="RESTRICT"), 
        nullable=False
    )

    # Relationships
    creator: Mapped["User"] = relationship(
        "User", 
        back_populates="created_workspaces",
        foreign_keys=[created_by]
    )
    memberships: Mapped[List["WorkspaceMembership"]] = relationship(
        "WorkspaceMembership", 
        back_populates="workspace",
        cascade="all, delete-orphan"
    )
    source_documents: Mapped[List["SourceDocument"]] = relationship(
        "SourceDocument", 
        back_populates="workspace",
        cascade="all, delete-orphan"
    )
    tabular_datasets: Mapped[List["TabularDataset"]] = relationship(
        "TabularDataset", 
        back_populates="workspace",
        cascade="all, delete-orphan"
    )
    investigations: Mapped[List["InvestigationSession"]] = relationship(
        "InvestigationSession", 
        back_populates="workspace",
        cascade="all, delete-orphan"
    )

class WorkspaceMembership(Base, BaseMixin):
    __tablename__ = "workspace_memberships"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), 
        ForeignKey("workspaces.id", ondelete="CASCADE"), 
        nullable=False,
        index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), 
        ForeignKey("users.id", ondelete="CASCADE"), 
        nullable=False,
        index=True
    )
    role: Mapped[WorkspaceRole] = mapped_column(
        String(50),
        default=WorkspaceRole.EDITOR.value,
        nullable=False
    )

    __table_args__ = (
        UniqueConstraint("workspace_id", "user_id", name="uq_workspace_user_membership"),
    )

    workspace: Mapped["Workspace"] = relationship("Workspace", back_populates="memberships")
    user: Mapped["User"] = relationship("User", back_populates="memberships")
