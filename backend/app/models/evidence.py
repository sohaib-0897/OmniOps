import enum
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy import String, Text, Float, Integer, ForeignKey, JSON, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base
from app.models.base import BaseMixin, GUID

class EpistemicType(str, enum.Enum):
    FACT = "fact"                      # Verifiable quote from primary source
    CALCULATION = "calculation"        # Reproducible computation output
    INFERENCE = "inference"            # Correlated logical conclusion
    ASSUMPTION = "assumption"          # Stated domain/business prior
    RECOMMENDATION = "recommendation"  # Actionable advice

class CalculationType(str, enum.Enum):
    SQL_QUERY = "sql_query"
    PYTHON_MATH = "python_math"
    AGGREGATION = "aggregation"

class EvidenceItem(Base, BaseMixin):
    __tablename__ = "evidence_items"

    session_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), 
        ForeignKey("investigation_sessions.id", ondelete="CASCADE"), 
        nullable=False,
        index=True
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), 
        ForeignKey("source_documents.id", ondelete="CASCADE"), 
        nullable=False,
        index=True
    )
    chunk_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), 
        ForeignKey("document_chunks.id", ondelete="SET NULL"), 
        nullable=True
    )
    page_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    cell_range: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    audio_start_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    audio_end_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    exact_quote: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    coordinates: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    confidence_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    logical_identity: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    session: Mapped["InvestigationSession"] = relationship("InvestigationSession", back_populates="evidence_items")
    source: Mapped["SourceDocument"] = relationship("SourceDocument", back_populates="evidence_items")

class CalculationRecord(Base, BaseMixin):
    __tablename__ = "calculation_records"

    session_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), 
        ForeignKey("investigation_sessions.id", ondelete="CASCADE"), 
        nullable=False,
        index=True
    )
    calculation_type: Mapped[str] = mapped_column(String(50), nullable=False)
    formula_or_code: Mapped[str] = mapped_column(Text, nullable=False)
    input_values: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    computed_output: Mapped[Any] = mapped_column(JSON, nullable=False)
    reproducibility_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_ids: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    source_ids: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    logical_identity: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    session: Mapped["InvestigationSession"] = relationship("InvestigationSession", back_populates="calculations")

class VerifiedClaim(Base, BaseMixin):
    __tablename__ = "verified_claims"

    session_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), 
        ForeignKey("investigation_sessions.id", ondelete="CASCADE"), 
        nullable=False,
        index=True
    )
    claim_id_code: Mapped[str] = mapped_column(String(50), nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    epistemic_type: Mapped[str] = mapped_column(
        String(50), 
        default=EpistemicType.FACT.value, 
        nullable=False
    )
    confidence_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    calculation_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), 
        ForeignKey("calculation_records.id", ondelete="SET NULL"), 
        nullable=True
    )
    supporting_citations: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    calculation_ids: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    supporting_claims: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    verification_status: Mapped[str] = mapped_column(String(30), default="PROPOSED", nullable=False)
    verification_errors: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    logical_identity: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    session: Mapped["InvestigationSession"] = relationship("InvestigationSession", back_populates="verified_claims")
    calculation: Mapped[Optional["CalculationRecord"]] = relationship("CalculationRecord")


class InferenceRecord(Base, BaseMixin):
    __tablename__ = "inference_records"

    session_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("investigation_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    inference_id_code: Mapped[str] = mapped_column(String(50), nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    supporting_claim_ids: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    verification_status: Mapped[str] = mapped_column(String(30), default="PROPOSED", nullable=False)
    verification_errors: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)


class RecommendationRecord(Base, BaseMixin):
    __tablename__ = "recommendation_records"

    session_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("investigation_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    recommendation_id_code: Mapped[str] = mapped_column(String(50), nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(String(30), nullable=False)
    supporting_claim_ids: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    supporting_inference_ids: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    verification_status: Mapped[str] = mapped_column(String(30), default="PROPOSED", nullable=False)
    verification_errors: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)


class ContradictionRecord(Base, BaseMixin):
    """Durable record of materially conflicting, otherwise valid evidence."""
    __tablename__ = "contradiction_records"

    investigation_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("investigation_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    topic: Mapped[str] = mapped_column(String(255), nullable=False)
    evidence_a_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("evidence_items.id", ondelete="CASCADE"), nullable=False)
    evidence_b_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("evidence_items.id", ondelete="CASCADE"), nullable=False)
    conflict_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="UNRESOLVED")
    resolution: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    logical_identity: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)


class RuntimeEvent(Base, BaseMixin):
    __tablename__ = "runtime_events"
    investigation_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("investigation_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(GUID(), nullable=True)
    logical_identity: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    payload: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
