import enum
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy import String, Text, BigInteger, Integer, ForeignKey, JSON, UniqueConstraint, DateTime, FetchedValue
from sqlalchemy.types import TypeDecorator
from sqlalchemy.dialects.postgresql import TSVECTOR
from pgvector.sqlalchemy import Vector
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base
from app.models.base import BaseMixin, GUID
from app.core.config import settings


class EmbeddingVector(TypeDecorator):
    """PostgreSQL vector in production; JSON only for the labeled SQLite development fallback."""
    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(Vector(settings.EMBEDDING_SCHEMA_DIMENSION))
        return dialect.type_descriptor(JSON())


class SearchVector(TypeDecorator):
    """PostgreSQL tsvector; text placeholder in SQLite development schemas."""
    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(TSVECTOR())
        return dialect.type_descriptor(Text())

class SourceModality(str, enum.Enum):
    PDF = "pdf"
    DOCX = "docx"
    SPREADSHEET = "spreadsheet"
    AUDIO = "audio"
    IMAGE = "image"
    TEXT = "text"
    WEB = "web"

class ProcessingStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    PARTIALLY_READY = "partially_ready"
    FAILED = "failed"

class SourceDocument(Base, BaseMixin):
    __tablename__ = "source_documents"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), 
        ForeignKey("workspaces.id", ondelete="CASCADE"), 
        nullable=False,
        index=True
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    modality: Mapped[str] = mapped_column(String(50), nullable=False)
    processing_status: Mapped[str] = mapped_column(
        String(50), 
        default=ProcessingStatus.PENDING.value, 
        nullable=False
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    doc_metadata: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    __table_args__ = (
        UniqueConstraint("workspace_id", "sha256_hash", name="uq_workspace_source_hash"),
    )

    workspace: Mapped["Workspace"] = relationship("Workspace", back_populates="source_documents")
    chunks: Mapped[List["DocumentChunk"]] = relationship(
        "DocumentChunk", 
        back_populates="source",
        cascade="all, delete-orphan"
    )
    tabular_datasets: Mapped[List["TabularDataset"]] = relationship(
        "TabularDataset", 
        back_populates="source",
        cascade="all, delete-orphan"
    )
    evidence_items: Mapped[List["EvidenceItem"]] = relationship(
        "EvidenceItem", 
        back_populates="source",
        cascade="all, delete-orphan"
    )

class DocumentChunk(Base, BaseMixin):
    __tablename__ = "document_chunks"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), 
        ForeignKey("workspaces.id", ondelete="CASCADE"), 
        nullable=False,
        index=True
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), 
        ForeignKey("source_documents.id", ondelete="CASCADE"), 
        nullable=False,
        index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    modality: Mapped[str] = mapped_column(String(50), nullable=False)
    
    # Specific location coordinates
    page_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    cell_range: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    audio_start_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    audio_end_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    chunk_metadata: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    extraction_method: Mapped[str] = mapped_column(String(100), default="unknown", nullable=False)
    embedding: Mapped[Optional[List[float]]] = mapped_column(EmbeddingVector(), nullable=True)
    embedding_provider: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    embedding_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    embedding_dimension: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    embedding_generated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    semantic_search_status: Mapped[str] = mapped_column(String(50), default="PENDING", nullable=False)
    lexical_search_status: Mapped[str] = mapped_column(String(50), default="READY", nullable=False)
    search_vector: Mapped[Optional[str]] = mapped_column(SearchVector(), server_default=FetchedValue(), nullable=True)

    source: Mapped["SourceDocument"] = relationship("SourceDocument", back_populates="chunks")

class TabularDataset(Base, BaseMixin):
    __tablename__ = "tabular_datasets"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), 
        ForeignKey("workspaces.id", ondelete="CASCADE"), 
        nullable=False,
        index=True
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), 
        ForeignKey("source_documents.id", ondelete="CASCADE"), 
        nullable=False,
        index=True
    )
    table_name: Mapped[str] = mapped_column(String(255), nullable=False)
    row_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    column_count: Mapped[int] = mapped_column(Integer, nullable=False)
    schema_definition: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    parquet_storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)

    __table_args__ = (
        UniqueConstraint("workspace_id", "table_name", name="uq_workspace_table_name"),
    )

    workspace: Mapped["Workspace"] = relationship("Workspace", back_populates="tabular_datasets")
    source: Mapped["SourceDocument"] = relationship("SourceDocument", back_populates="tabular_datasets")
