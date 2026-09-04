import enum
import uuid
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from app.models.evidence import EpistemicType

class AgentStatus(str, enum.Enum):
    INITIALIZING = "initializing"
    PLANNING = "planning"
    EXECUTING = "executing"
    REPLANNING = "replanning"
    VERIFYING = "verifying"
    SYNTHESIZING = "synthesizing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class InvestigationTask(BaseModel):
    id: str
    title: str
    description: str
    target_modality: str
    expected_output: str
    status: str = "pending"  # "pending", "in_progress", "completed", "skipped", "blocked"

class InvestigationPlan(BaseModel):
    objective: str
    reasoning_summary: str
    tasks: List[InvestigationTask]
    current_task_index: int = 0

class ToolCallRecord(BaseModel):
    call_id: str
    tool_name: str
    arguments: Dict[str, Any]
    result: Any
    duration_ms: int
    success: bool
    error_message: Optional[str] = None
    reproducibility_hash: Optional[str] = None

class EpistemicClaim(BaseModel):
    claim_id: str
    statement: str
    epistemic_type: str
    confidence_score: Optional[float] = None
    citation_ids: List[str] = Field(default_factory=list)
    calculation_ids: List[str] = Field(default_factory=list)
    supporting_claim_ids: List[str] = Field(default_factory=list)

class AgentState(BaseModel):
    session_id: uuid.UUID
    workspace_id: uuid.UUID
    objective: str
    status: AgentStatus = AgentStatus.INITIALIZING
    plan: Optional[InvestigationPlan] = None
    execution_history: List[ToolCallRecord] = Field(default_factory=list)
    evidence_ids: List[uuid.UUID] = Field(default_factory=list)
    calculation_ids: List[uuid.UUID] = Field(default_factory=list)
    verified_claims: List[EpistemicClaim] = Field(default_factory=list)
    current_step: int = 0
    max_steps: int = 12
    tool_signature_history: List[str] = Field(default_factory=list)
    cancellation_requested: bool = False
    error_message: Optional[str] = None
