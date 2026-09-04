import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict

class EvidenceItemResponse(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    source_id: uuid.UUID
    source_name: Optional[str] = None
    source_modality: Optional[str] = None
    chunk_id: Optional[uuid.UUID] = None
    page_number: Optional[int] = None
    cell_range: Optional[str] = None
    audio_start_ms: Optional[int] = None
    audio_end_ms: Optional[int] = None
    exact_quote: Optional[str] = None
    coordinates: Optional[Dict[str, Any]] = None
    confidence_score: Optional[float] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class CalculationRecordResponse(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    calculation_type: str
    formula_or_code: str
    input_values: Dict[str, Any]
    computed_output: Any
    reproducibility_hash: str
    evidence_ids: List[str] = Field(default_factory=list)
    source_ids: List[str] = Field(default_factory=list)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class VerifiedClaimResponse(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    claim_id_code: str
    statement: str
    epistemic_type: str  # fact, calculation, inference, assumption, recommendation
    confidence_score: Optional[float] = None
    calculation_id: Optional[uuid.UUID] = None
    supporting_citations: List[str] = Field(default_factory=list)
    calculation_ids: List[str] = Field(default_factory=list)
    supporting_claims: List[str] = Field(default_factory=list)
    verification_status: str
    verification_errors: List[str] = Field(default_factory=list)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class LineageNode(BaseModel):
    id: str
    type: str  # source, extracted, evidence, calculation, claim, inference, recommendation
    label: str
    data: Dict[str, Any]

class LineageEdge(BaseModel):
    source: str
    target: str
    relation: str  # EXTRACTED_FROM, BACKED_BY, CALCULATED_FROM, DERIVED_FROM, SUPPORTS

class EvidenceLineageGraphResponse(BaseModel):
    session_id: uuid.UUID
    nodes: List[LineageNode]
    edges: List[LineageEdge]
    claims_count: int
    citations_count: int
    calculations_count: int
