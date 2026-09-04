import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict

class InvestigationCreateRequest(BaseModel):
    objective: str = Field(..., min_length=5, description="High-level business objective/question")
    max_steps: Optional[int] = Field(12, ge=1, le=20)

class AgentStepResponse(BaseModel):
    id: uuid.UUID
    step_number: int
    step_type: str
    user_activity_summary: str
    tool_name: Optional[str] = None
    tool_input: Optional[Dict[str, Any]] = None
    tool_output: Optional[Dict[str, Any]] = None
    duration_ms: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class InvestigationResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    objective: str
    status: str
    current_state: str = "created"
    plan_version: int = 0
    failure_code: Optional[str] = None
    failure_message: Optional[str] = None
    final_response: Optional[Dict[str, Any]] = None
    token_usage: Dict[str, Any] = Field(default_factory=dict)
    error_message: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    steps: Optional[List[AgentStepResponse]] = None

    model_config = ConfigDict(from_attributes=True)

class InvestigationCancelResponse(BaseModel):
    investigation_id: uuid.UUID
    status: str = "cancelled"
    message: str
