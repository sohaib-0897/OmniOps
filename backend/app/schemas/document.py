import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict

class DocumentResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    file_name: str
    mime_type: str
    byte_size: int
    sha256_hash: str
    modality: str
    processing_status: str
    error_message: Optional[str] = None
    doc_metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class DocumentChunkResponse(BaseModel):
    id: uuid.UUID
    source_id: uuid.UUID
    chunk_index: int
    content: str
    modality: str
    page_number: Optional[int] = None
    cell_range: Optional[str] = None
    audio_start_ms: Optional[int] = None
    audio_end_ms: Optional[int] = None
    chunk_metadata: Dict[str, Any] = Field(default_factory=dict)
    extraction_method: str
    embedding_provider: Optional[str] = None
    embedding_model: Optional[str] = None
    embedding_dimension: Optional[int] = None
    semantic_search_status: str
    lexical_search_status: str

    model_config = ConfigDict(from_attributes=True)

class PassageMapResponse(BaseModel):
    """Columnar passage outline for one source; never carries passage text.

    Index ``i`` of every list describes the same passage. Lists are ordered by
    ``chunk_index`` ascending.
    """
    source_id: uuid.UUID
    modality: str
    processing_status: str
    passage_count: int
    chunk_id: List[uuid.UUID]
    chunk_index: List[int]
    char_length: List[int]
    page_number: List[Optional[int]]
    audio_start_ms: List[Optional[int]]
    audio_end_ms: List[Optional[int]]
    heading: List[Optional[str]]

class TabularDatasetResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    source_id: uuid.UUID
    table_name: str
    row_count: int
    column_count: int
    schema_definition: List[Dict[str, Any]]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class TableQueryRequest(BaseModel):
    sql_query: str = Field(..., description="Read-only analytical SQL query against registered datasets")

class TablePreviewResponse(BaseModel):
    table_name: str
    row_count: int
    column_count: int
    columns: List[str]
    sample_rows: List[Dict[str, Any]]
    schema_definition: List[Dict[str, Any]]
