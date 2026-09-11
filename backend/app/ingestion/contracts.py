"""Shared, provenance-first contracts for multimodal extraction.

These records are normalized at the ingestion boundary and are persisted into
the existing source-document/chunk model.  Keeping the contract explicit
prevents provider output from being mistaken for native text or instructions.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ExtractionMethod(str, Enum):
    NATIVE_TEXT = "NATIVE_TEXT"
    OCR = "OCR"
    TABLE_EXTRACTION = "TABLE_EXTRACTION"
    DOCX_TEXT = "DOCX_TEXT"
    IMAGE_OCR = "IMAGE_OCR"
    VISION = "VISION"
    TRANSCRIPTION = "TRANSCRIPTION"
    DIARIZATION = "DIARIZATION"
    WEB_EXTRACTION = "WEB_EXTRACTION"


class ExtractionStatus(str, Enum):
    READY = "READY"
    PARTIALLY_READY = "PARTIALLY_READY"
    NO_TEXT_DETECTED = "NO_TEXT_DETECTED"
    OCR_UNAVAILABLE = "OCR_UNAVAILABLE"
    OCR_FAILED = "OCR_FAILED"
    VISION_UNAVAILABLE = "VISION_UNAVAILABLE"
    VISION_FAILED = "VISION_FAILED"
    TRANSCRIPTION_UNAVAILABLE = "TRANSCRIPTION_UNAVAILABLE"
    TRANSCRIPTION_FAILED = "TRANSCRIPTION_FAILED"
    INVALID_MEDIA = "INVALID_MEDIA"


class ExtractionRecord(BaseModel):
    """One bounded, source-locatable extraction unit."""

    id: Optional[str] = None
    source_document_id: Optional[UUID] = None
    modality: str
    content_type: Optional[str] = None
    text: Optional[str] = None
    structured_payload: Dict[str, Any] = Field(default_factory=dict)
    page_number: Optional[int] = None
    start_time_ms: Optional[int] = None
    end_time_ms: Optional[int] = None
    bounding_box: Optional[Dict[str, float]] = None
    speaker: Optional[str] = None
    extraction_method: ExtractionMethod
    provider: Optional[str] = None
    model: Optional[str] = None
    provider_request_id: Optional[str] = None
    confidence: Optional[float] = None
    status: ExtractionStatus = ExtractionStatus.READY
    error_code: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ExtractionBatch(BaseModel):
    """Parser result with explicit partial/failure semantics."""

    status: ExtractionStatus = ExtractionStatus.READY
    records: List[ExtractionRecord] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    error_code: Optional[str] = None
    error_message: Optional[str] = None


def stable_extraction_id(*, source_hash: str, modality: str, method: str, locator: Any = None, content: str = "") -> str:
    """Return a deterministic identity for replay-safe extraction units."""
    payload = json.dumps({
        "source_hash": source_hash,
        "modality": modality,
        "method": method,
        "locator": locator,
        "content": content,
    }, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
