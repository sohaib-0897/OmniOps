"""Truthful multimodal capability discovery.

Capability values are derived from installed engines and configured provider
credentials/model metadata.  This module never performs a provider request
and never reports semantic support merely because a file type is accepted.
"""

from __future__ import annotations

import importlib.util
import shutil
from enum import Enum
from typing import Dict

from pydantic import BaseModel

from app.core.config import settings


class CapabilityStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_SUPPORTED = "NOT_SUPPORTED"


class Capability(BaseModel):
    status: CapabilityStatus
    provider: str | None = None
    model: str | None = None
    reason: str | None = None


# Keep model capability knowledge in one place. Unknown models are not
# assumed to support binary modalities, even if their names look similar.
# The dedicated transcription model is intentionally separate from the
# general/vision model: a model which can understand an audio attachment is
# not automatically a timestamped transcription or diarization provider.
GEMINI_MODEL_CAPABILITIES: Dict[str, Dict[str, bool]] = {
    "gemini-3.8-flash": {
        "text": True,
        "image": True,
        "audio_understanding": True,
        "structured_output": True,
    },
    "gemini-3.5-transcribe": {
        "audio_transcription": True,
        "word_timestamps": True,
        "speaker_diarization": True,
    },
    # Retain known historical models for installations that have not yet
    # moved their configuration. They do not inherit transcription-specific
    # capabilities merely from accepting audio input.
    "gemini-2.5-flash": {"text": True, "image": True, "audio_understanding": True, "structured_output": True},
    "gemini-2.5-pro": {"text": True, "image": True, "audio_understanding": True, "structured_output": True},
}

# Backwards-compatible view used by existing callers/tests. New code should
# use GEMINI_MODEL_CAPABILITIES so that capability names remain explicit.
GEMINI_MODALITY_CAPABILITIES: Dict[str, Dict[str, bool]] = {
    model: {
        "image": values.get("image", False),
        "audio": values.get("audio_understanding", False),
        "structured": values.get("structured_output", False),
    }
    for model, values in GEMINI_MODEL_CAPABILITIES.items()
}


def _gemini_capability(modality: str, *, model: str | None = None) -> Capability:
    model = model or settings.GEMINI_MODEL
    capability_name = {
        "image": "image",
        "audio": "audio_understanding",
        "audio_transcription": "audio_transcription",
        "word_timestamps": "word_timestamps",
        "speaker_diarization": "speaker_diarization",
    }.get(modality, modality)
    supported = GEMINI_MODEL_CAPABILITIES.get(model, {}).get(capability_name, False)
    if not settings.GEMINI_API_KEY:
        return Capability(status=CapabilityStatus.UNAVAILABLE, provider="gemini", model=model, reason="GEMINI_API_KEY is unavailable.")
    if not supported:
        return Capability(status=CapabilityStatus.UNAVAILABLE, provider="gemini", model=model, reason=f"Configured model does not advertise {modality} input support.")
    return Capability(status=CapabilityStatus.AVAILABLE, provider="gemini", model=model)


def capability_matrix() -> Dict[str, Capability]:
    fitz_available = importlib.util.find_spec("fitz") is not None
    pillow_available = importlib.util.find_spec("PIL") is not None
    tesseract_available = bool(shutil.which("tesseract")) and importlib.util.find_spec("pytesseract") is not None

    return {
        "pdf_native_text": Capability(
            status=CapabilityStatus.AVAILABLE if fitz_available else CapabilityStatus.UNAVAILABLE,
            provider="PyMuPDF" if fitz_available else None,
            reason=None if fitz_available else "PyMuPDF is not installed.",
        ),
        "pdf_ocr": Capability(
            status=CapabilityStatus.AVAILABLE if tesseract_available else CapabilityStatus.UNAVAILABLE,
            provider="Tesseract" if tesseract_available else None,
            reason=None if tesseract_available else "Tesseract and pytesseract are unavailable.",
        ),
        "image_ocr": Capability(
            status=CapabilityStatus.AVAILABLE if tesseract_available else (CapabilityStatus.PARTIAL if _gemini_capability("image", model=settings.GEMINI_VISION_MODEL).status == CapabilityStatus.AVAILABLE else CapabilityStatus.UNAVAILABLE),
            provider="Tesseract" if tesseract_available else ("Gemini vision detected_text" if settings.GEMINI_API_KEY else None),
            model=settings.GEMINI_VISION_MODEL if not tesseract_available and settings.GEMINI_API_KEY else None,
            reason=None if tesseract_available else ("Image OCR is provider-derived and is returned only when the vision response contains detected_text." if settings.GEMINI_API_KEY else "No configured OCR or vision provider."),
        ),
        "image_semantic_vision": _gemini_capability("image", model=settings.GEMINI_VISION_MODEL),
        "audio_transcription": Capability(
            status=CapabilityStatus.AVAILABLE if settings.GEMINI_API_KEY and _gemini_capability("audio_transcription", model=settings.GEMINI_TRANSCRIPTION_MODEL).status == CapabilityStatus.AVAILABLE else (
                CapabilityStatus.AVAILABLE if settings.OPENAI_API_KEY else CapabilityStatus.UNAVAILABLE
            ),
            provider="Gemini" if settings.GEMINI_API_KEY and _gemini_capability("audio_transcription", model=settings.GEMINI_TRANSCRIPTION_MODEL).status == CapabilityStatus.AVAILABLE else ("OpenAI Whisper" if settings.OPENAI_API_KEY else None),
            model=settings.GEMINI_TRANSCRIPTION_MODEL if settings.GEMINI_API_KEY and _gemini_capability("audio_transcription", model=settings.GEMINI_TRANSCRIPTION_MODEL).status == CapabilityStatus.AVAILABLE else ("whisper-1" if settings.OPENAI_API_KEY else None),
            reason=None if settings.GEMINI_API_KEY or settings.OPENAI_API_KEY else "No configured genuine transcription provider.",
        ),
        "audio_timestamps": Capability(
            status=CapabilityStatus.AVAILABLE if settings.GEMINI_API_KEY and _gemini_capability("word_timestamps", model=settings.GEMINI_TRANSCRIPTION_MODEL).status == CapabilityStatus.AVAILABLE else (
                CapabilityStatus.AVAILABLE if settings.OPENAI_API_KEY else CapabilityStatus.UNAVAILABLE
            ),
            provider="Gemini" if settings.GEMINI_API_KEY and _gemini_capability("word_timestamps", model=settings.GEMINI_TRANSCRIPTION_MODEL).status == CapabilityStatus.AVAILABLE else ("OpenAI Whisper" if settings.OPENAI_API_KEY else None),
            model=settings.GEMINI_TRANSCRIPTION_MODEL if settings.GEMINI_API_KEY and _gemini_capability("word_timestamps", model=settings.GEMINI_TRANSCRIPTION_MODEL).status == CapabilityStatus.AVAILABLE else ("whisper-1" if settings.OPENAI_API_KEY else None),
            reason=None if settings.GEMINI_API_KEY or settings.OPENAI_API_KEY else "No configured genuine timestamped transcription provider.",
        ),
        "audio_diarization": Capability(
            status=CapabilityStatus.AVAILABLE if settings.GEMINI_API_KEY and _gemini_capability("speaker_diarization", model=settings.GEMINI_TRANSCRIPTION_MODEL).status == CapabilityStatus.AVAILABLE else CapabilityStatus.NOT_SUPPORTED,
            provider="Gemini" if settings.GEMINI_API_KEY and _gemini_capability("speaker_diarization", model=settings.GEMINI_TRANSCRIPTION_MODEL).status == CapabilityStatus.AVAILABLE else None,
            model=settings.GEMINI_TRANSCRIPTION_MODEL if settings.GEMINI_API_KEY and _gemini_capability("speaker_diarization", model=settings.GEMINI_TRANSCRIPTION_MODEL).status == CapabilityStatus.AVAILABLE else None,
            reason=None if settings.GEMINI_API_KEY else "No diarization provider is configured; speaker remains null.",
        ),
    }
