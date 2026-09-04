from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field

class SSEEventPayload(BaseModel):
    event: str
    data: Dict[str, Any]
    investigation_id: str

class StepActivityEvent(BaseModel):
    step_number: int
    step_type: str
    summary: str
    tool_name: Optional[str] = None
    duration_ms: Optional[int] = 0

class PlanCreatedEvent(BaseModel):
    objective: str
    tasks: List[Dict[str, Any]]
    total_tasks: int

class ToolExecutionEvent(BaseModel):
    tool_name: str
    input_args: Dict[str, Any]
    output_preview: Optional[str] = None
    success: bool
    duration_ms: int

class EvidenceDiscoveredEvent(BaseModel):
    citation_id: str
    source_name: str
    quote: str
    modality: str
    page_or_cell: Optional[str] = None

class FinalReportEvent(BaseModel):
    status: str
    executive_summary: str
    key_findings: List[Dict[str, Any]]
    recommendations: List[Dict[str, Any]]
    claims_count: int
    citations_count: int
