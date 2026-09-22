from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field, AliasChoices

class PlannedTask(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    title: str
    description: str
    target_modality: str = Field(min_length=1, max_length=50)  # persisted evidence type
    expected_output: str

class PlanOutput(BaseModel):
    reasoning_summary: str
    tasks: List[PlannedTask] = Field(min_length=1, max_length=4)

class ToolDecision(BaseModel):
    tool_name: str
    arguments: Dict[str, Any]
    user_activity_summary: str
    thought_process: Optional[str] = None

class EpistemicClaim(BaseModel):
    claim_id: str
    statement: str
    epistemic_type: str  # "fact", "calculation", "inference", "assumption", "recommendation"
    confidence_score: Optional[float] = Field(default=None, validation_alias=AliasChoices("confidence_score", "confidence"))
    citations: List[str] = Field(default_factory=list)  # list of chunk or evidence IDs
    calculation_ids: List[str] = Field(default_factory=list)
    calculation_summary: Optional[str] = None
    supporting_claims: List[str] = Field(default_factory=list)

class RecommendationItem(BaseModel):
    recommendation_id: str
    title: str
    action: str
    priority: str  # "high", "medium", "low"
    supported_by_claims: List[str]
    supporting_inference_ids: List[str] = Field(default_factory=list)

class InferenceItem(BaseModel):
    inference_id: str
    statement: str
    supporting_claim_ids: List[str]

class SynthesisReport(BaseModel):
    executive_summary: str
    key_findings: List[Dict[str, Any]]
    claims: List[EpistemicClaim]
    inferences: List[InferenceItem] = Field(default_factory=list)
    recommendations: List[RecommendationItem]
    missing_data_warnings: List[str] = Field(default_factory=list)
    contradictions: List[str] = Field(default_factory=list)

class BaseLLMClient(ABC):
    """Abstract model provider interface."""

    @abstractmethod
    async def generate_investigation_plan(
        self,
        objective: str,
        catalog_summary: Dict[str, Any]
    ) -> PlanOutput:
        """Create structured DAG of investigation tasks."""
        pass

    @abstractmethod
    async def decide_next_action(
        self,
        objective: str,
        current_task: PlannedTask,
        prior_observations: List[Dict[str, Any]],
        available_tools: List[Dict[str, Any]]
    ) -> ToolDecision:
        """Select tool and arguments for current step."""
        pass

    @abstractmethod
    async def verify_and_synthesize(
        self,
        objective: str,
        observations: List[Dict[str, Any]],
        evidence_items: List[Dict[str, Any]],
        calculations: List[Dict[str, Any]]
    ) -> SynthesisReport:
        """Perform epistemic verification and generate executive answer."""
        pass
class ProviderState(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    RATE_LIMITED = "RATE_LIMITED"
    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
    TIMEOUT = "TIMEOUT"
    MALFORMED_RESPONSE = "MALFORMED_RESPONSE"
    DEGRADED = "DEGRADED"


class ProviderError(RuntimeError):
    def __init__(self, state: ProviderState, code: str, message: str):
        super().__init__(message)
        self.state = state
        self.code = code


class CapabilityLimitError(ProviderError):
    def __init__(self, message: str):
        super().__init__(ProviderState.UNAVAILABLE, "LLM_PROVIDER_REQUIRED", message)
