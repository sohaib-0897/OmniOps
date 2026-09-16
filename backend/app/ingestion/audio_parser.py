"""Truthful audio validation and provider-backed transcription."""

from __future__ import annotations

import mimetypes
import os
import wave
import asyncio
from pathlib import Path
from typing import Any, Dict, List

from app.core.config import settings
from app.ingestion.contracts import ExtractionMethod, ExtractionStatus
from app.llm.base import ProviderError
from app.llm.multimodal import configured_gemini_multimodal, configured_openai_whisper


def _validate_audio(file_path: str) -> Dict[str, Any] | None:
    path = Path(file_path)
    file_size = os.path.getsize(file_path)
    if file_size > settings.MAX_FILE_SIZE_BYTES:
        return {"status": ExtractionStatus.INVALID_MEDIA.value, "chunks": [], "metadata": {"error_code": "MEDIA_TOO_LARGE", "file_size_bytes": file_size}}
    extension = path.suffix.lower()
    try:
        with open(file_path, "rb") as handle:
            header = handle.read(4096)
    except OSError:
        return {"status": ExtractionStatus.INVALID_MEDIA.value, "chunks": [], "metadata": {"error_code": "INVALID_MEDIA", "error_message": "Audio file could not be read."}}

    if extension == ".wav":
        try:
            with wave.open(file_path, "rb") as wav:
                duration = wav.getnframes() / max(1, wav.getframerate())
                if duration > settings.MAX_AUDIO_DURATION_SECONDS:
                    return {"status": ExtractionStatus.INVALID_MEDIA.value, "chunks": [], "metadata": {"error_code": "MEDIA_DURATION_EXCEEDED", "duration_seconds": duration}}
        except (wave.Error, EOFError, OSError):
            return {"status": ExtractionStatus.INVALID_MEDIA.value, "chunks": [], "metadata": {"error_code": "INVALID_MEDIA", "error_message": "WAV audio is malformed."}}
    elif extension == ".mp3":
        # Accept ID3-tagged files or a genuine MPEG audio frame header.  This
        # intentionally avoids attempting to decode user media in-process.
        has_id3 = header.startswith(b"ID3")
        has_frame = any(
            len(header) >= index + 2 and header[index] == 0xFF and (header[index + 1] & 0xE0) == 0xE0
            for index in range(max(0, len(header) - 1))
        )
        if not (has_id3 or has_frame):
            return {"status": ExtractionStatus.INVALID_MEDIA.value, "chunks": [], "metadata": {"error_code": "INVALID_MEDIA", "error_message": "MP3 audio header is malformed."}}
    elif extension == ".m4a":
        if len(header) < 12 or header[4:8] != b"ftyp":
            return {"status": ExtractionStatus.INVALID_MEDIA.value, "chunks": [], "metadata": {"error_code": "INVALID_MEDIA", "error_message": "M4A container header is malformed."}}
    elif extension == ".ogg":
        if not header.startswith(b"OggS"):
            return {"status": ExtractionStatus.INVALID_MEDIA.value, "chunks": [], "metadata": {"error_code": "INVALID_MEDIA", "error_message": "Ogg container header is malformed."}}
    if extension != ".wav":
        try:
            from mutagen import File as MutagenFile
            media = MutagenFile(file_path)
            duration = float(media.info.length) if media and media.info else 0.0
            if duration <= 0:
                raise ValueError("duration unavailable")
            if duration > settings.MAX_AUDIO_DURATION_SECONDS:
                return {"status": ExtractionStatus.INVALID_MEDIA.value, "chunks": [], "metadata": {"error_code": "MEDIA_DURATION_EXCEEDED", "duration_seconds": duration}}
        except Exception:
            return {"status": ExtractionStatus.INVALID_MEDIA.value, "chunks": [], "metadata": {"error_code": "INVALID_MEDIA", "error_message": "Audio duration could not be safely validated."}}
    return None


def _openai_transcription(file_path: str) -> Dict[str, Any]:
    provider = configured_openai_whisper()
    if provider is None:
        return {
            "status": ExtractionStatus.TRANSCRIPTION_UNAVAILABLE.value,
            "chunks": [],
            "metadata": {"error_code": "TRANSCRIPTION_UNAVAILABLE", "diarization": "NOT_SUPPORTED"},
        }
    chunks: List[Dict[str, Any]] = []
    try:
        analysis = provider.transcribe_audio_sync(file_path, mimetypes.guess_type(file_path)[0])
        for index, segment in enumerate(analysis.segments):
            chunks.append({
                "content": segment.text,
                "modality": "audio",
                "audio_start_ms": segment.start_ms,
                "audio_end_ms": segment.end_ms,
                "extraction_method": ExtractionMethod.TRANSCRIPTION.value,
                "metadata": {"segment_index": index, "provider": "openai", "model": provider.model, "speaker": None, "content_trusted": False, "content_label": "UNTRUSTED_AUDIO_DATA"},
            })
        if not chunks and analysis.transcript:
            chunks.append({"content": analysis.transcript, "modality": "audio", "extraction_method": ExtractionMethod.TRANSCRIPTION.value, "metadata": {"provider": "openai", "model": provider.model, "speaker": None, "timestamps": False, "content_trusted": False, "content_label": "UNTRUSTED_AUDIO_DATA"}})
        return {"status": ExtractionStatus.READY.value if chunks else ExtractionStatus.NO_TEXT_DETECTED.value, "chunks": chunks, "metadata": {"transcription_provider": "openai", "transcription_model": "whisper-1", "diarization": "NOT_SUPPORTED"}}
    except ProviderError as exc:
        return {"status": ExtractionStatus.TRANSCRIPTION_FAILED.value, "chunks": [], "metadata": {"error_code": exc.code, "provider": "openai", "model": provider.model}}
    except Exception as exc:
        return {"status": ExtractionStatus.TRANSCRIPTION_FAILED.value, "chunks": [], "metadata": {"error_code": "TRANSCRIPTION_FAILED", "provider": "openai", "model": provider.model, "exception_type": type(exc).__name__}}


def parse_audio_recording(file_path: str) -> Dict[str, Any]:
    """Synchronous compatibility API; provider calls are made by async ingestion."""
    invalid = _validate_audio(file_path)
    # Validation is independent of provider availability.  A malformed media
    # file must never be reported as merely "provider unavailable" because
    # that would make an invalid source appear recoverable/understood.
    if invalid:
        return invalid
    if settings.OPENAI_API_KEY:
        return _openai_transcription(file_path)
    return {
        "status": ExtractionStatus.TRANSCRIPTION_UNAVAILABLE.value,
        "chunks": [],
        "metadata": {"file_size_bytes": os.path.getsize(file_path), "transcription_status": ExtractionStatus.TRANSCRIPTION_UNAVAILABLE.value, "error_code": "TRANSCRIPTION_UNAVAILABLE", "diarization": "NOT_SUPPORTED"},
    }


async def transcribe_audio_recording(file_path: str) -> Dict[str, Any]:
    """Use the explicitly configured genuine provider, with no heuristic fallback."""
    invalid = _validate_audio(file_path)
    if invalid:
        return invalid
    # Gemini's dedicated transcription model is the preferred provider when
    # configured. OpenAI Whisper remains a genuine secondary provider, never a
    # fabricated fallback and never selected after a Gemini provider failure.
    provider = configured_gemini_multimodal()
    if provider is None and settings.OPENAI_API_KEY:
        return await asyncio.to_thread(_openai_transcription, file_path)
    if provider is None:
        return parse_audio_recording(file_path)
    provider_model = getattr(provider, "transcription_model", provider.model)
    try:
        analysis = await provider.transcribe_audio(file_path, mimetypes.guess_type(file_path)[0])
    except ProviderError as exc:
        return {"status": ExtractionStatus.TRANSCRIPTION_FAILED.value, "chunks": [], "metadata": {"error_code": exc.code, "provider": "gemini", "model": provider_model, "diarization": "REQUESTED"}}
    chunks: List[Dict[str, Any]] = []
    for index, segment in enumerate(analysis.segments):
        chunks.append({
            "content": segment.text.strip(), "modality": "audio", "audio_start_ms": segment.start_ms, "audio_end_ms": segment.end_ms,
            "extraction_method": ExtractionMethod.TRANSCRIPTION.value,
            "metadata": {"segment_index": index, "provider": "gemini", "model": provider_model, "provider_request_id": analysis.provider_request_id, "speaker": segment.speaker, "content_trusted": False, "content_label": "UNTRUSTED_AUDIO_DATA"},
        })
    if not chunks and analysis.transcript and analysis.transcript.strip():
        chunks.append({"content": analysis.transcript.strip(), "modality": "audio", "extraction_method": ExtractionMethod.TRANSCRIPTION.value, "metadata": {"provider": "gemini", "model": provider_model, "provider_request_id": analysis.provider_request_id, "speaker": None, "timestamps": False, "content_trusted": False, "content_label": "UNTRUSTED_AUDIO_DATA"}})
    diarization = "AVAILABLE" if any(segment.speaker for segment in analysis.segments) else "NOT_RETURNED"
    return {"status": ExtractionStatus.READY.value if chunks else ExtractionStatus.NO_TEXT_DETECTED.value, "chunks": chunks, "metadata": {"transcription_provider": "gemini", "transcription_model": provider_model, "diarization": diarization, "limitations": analysis.limitations}}
