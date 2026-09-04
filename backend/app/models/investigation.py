import enum
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy import String, Text, Integer, ForeignKey, JSON, DateTime, Boolean, Float, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base
from app.models.base import BaseMixin, GUID

class InvestigationStatus(str, enum.Enum):
    PLANNING = "planning"
    RUNNING = "running"
    VERIFYING = "verifying"
    SYNTHESIZING = "synthesizing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RuntimeState(str, enum.Enum):
    CREATED = "created"
    PLANNING = "planning"
    READY = "ready"
    EXECUTING = "executing"
    OBSERVING = "observing"
    VERIFYING = "verifying"
    REPLANNING = "replanning"
    SYNTHESIZING = "synthesizing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class StepType(str, enum.Enum):
    PLAN = "plan"
    TOOL_CALL = "tool_call"
    REFLECTION = "reflection"
    VERIFICATION = "verification"
    SYNTHESIS = "synthesis"

class InvestigationSession(Base, BaseMixin):
    __tablename__ = "investigation_sessions"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), 
        ForeignKey("workspaces.id", ondelete="CASCADE"), 
        nullable=False,
        index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), 
        ForeignKey("users.id", ondelete="RESTRICT"), 
        nullable=False,
        index=True
    )
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), 
        default=InvestigationStatus.PLANNING.value, 
        nullable=False
    )
    final_response: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    token_usage: Mapped[Dict[str, Any]] = mapped_column(
        JSON, 
        default=lambda: {"prompt_tokens": 0, "completion_tokens": 0, "total_cost_usd": 0.0}, 
        nullable=False
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    current_state: Mapped[str] = mapped_column(String(30), default=RuntimeState.CREATED.value, nullable=False, index=True)
    plan_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_code: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    failure_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cancellation_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, unique=True, index=True)
    worker_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    lease_acquired_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    synthesis_identity: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, unique=True)

    # Relationships
    workspace: Mapped["Workspace"] = relationship("Workspace", back_populates="investigations")
    user: Mapped["User"] = relationship("User", back_populates="investigations")
    steps: Mapped[List["AgentStep"]] = relationship(
        "AgentStep", 
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="AgentStep.step_number"
    )
    evidence_items: Mapped[List["EvidenceItem"]] = relationship(
        "EvidenceItem", 
        back_populates="session",
        cascade="all, delete-orphan"
    )
    calculations: Mapped[List["CalculationRecord"]] = relationship(
        "CalculationRecord", 
        back_populates="session",
        cascade="all, delete-orphan"
    )
    verified_claims: Mapped[List["VerifiedClaim"]] = relationship(
        "VerifiedClaim", 
        back_populates="session",
        cascade="all, delete-orphan"
    )
    inferences: Mapped[List["InferenceRecord"]] = relationship("InferenceRecord", cascade="all, delete-orphan")
    recommendations: Mapped[List["RecommendationRecord"]] = relationship("RecommendationRecord", cascade="all, delete-orphan")
    plans: Mapped[List["AgentPlan"]] = relationship("AgentPlan", back_populates="investigation", cascade="all, delete-orphan")
    observations: Mapped[List["AgentObservation"]] = relationship("AgentObservation", back_populates="investigation", cascade="all, delete-orphan")
    transitions: Mapped[List["AgentTransition"]] = relationship("AgentTransition", back_populates="investigation", cascade="all, delete-orphan")


class AgentPlan(Base, BaseMixin):
    __tablename__ = "agent_plans"
    investigation_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("investigation_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    generated_by: Mapped[str] = mapped_column(String(50), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    logical_identity: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, unique=True)
    investigation: Mapped["InvestigationSession"] = relationship("InvestigationSession", back_populates="plans")
    steps: Mapped[List["AgentPlanStep"]] = relationship("AgentPlanStep", back_populates="plan", cascade="all, delete-orphan", order_by="AgentPlanStep.sequence")


class AgentPlanStep(Base, BaseMixin):
    __tablename__ = "agent_plan_steps"
    plan_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("agent_plans.id", ondelete="CASCADE"), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    step_key: Mapped[str] = mapped_column(String(100), nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)
    dependencies: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    expected_evidence_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    completion_criteria: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    inputs: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="PENDING", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    result_reference: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    failure_reference: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    plan: Mapped["AgentPlan"] = relationship("AgentPlan", back_populates="steps")
    tool_attempts: Mapped[List["AgentToolAttempt"]] = relationship("AgentToolAttempt", back_populates="step", cascade="all, delete-orphan")


class AgentToolAttempt(Base, BaseMixin):
    __tablename__ = "agent_tool_attempts"
    step_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("agent_plan_steps.id", ondelete="CASCADE"), nullable=False, index=True)
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)
    tool_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    validated_input: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    output_reference: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    error_classification: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    retryable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    attempt_no: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    step: Mapped["AgentPlanStep"] = relationship("AgentPlanStep", back_populates="tool_attempts")


class AgentObservation(Base, BaseMixin):
    __tablename__ = "agent_observations"
    investigation_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("investigation_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    step_id: Mapped[Optional[uuid.UUID]] = mapped_column(GUID(), ForeignKey("agent_plan_steps.id", ondelete="SET NULL"), nullable=True, index=True)
    attempt_id: Mapped[Optional[uuid.UUID]] = mapped_column(GUID(), ForeignKey("agent_tool_attempts.id", ondelete="SET NULL"), nullable=True)
    classification: Mapped[str] = mapped_column(String(50), nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    investigation: Mapped["InvestigationSession"] = relationship("InvestigationSession", back_populates="observations")


class AgentTransition(Base, BaseMixin):
    __tablename__ = "agent_transitions"
    investigation_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("investigation_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    from_state: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    to_state: Mapped[str] = mapped_column(String(30), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    investigation: Mapped["InvestigationSession"] = relationship("InvestigationSession", back_populates="transitions")

class AgentStep(Base, BaseMixin):
    __tablename__ = "agent_steps"

    session_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), 
        ForeignKey("investigation_sessions.id", ondelete="CASCADE"), 
        nullable=False,
        index=True
    )
    step_number: Mapped[int] = mapped_column(Integer, nullable=False)
    step_type: Mapped[str] = mapped_column(String(50), nullable=False)
    user_activity_summary: Mapped[str] = mapped_column(String(500), nullable=False)
    tool_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    tool_input: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    tool_output: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    session: Mapped["InvestigationSession"] = relationship("InvestigationSession", back_populates="steps")
