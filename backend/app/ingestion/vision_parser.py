"""Image validation and provider-backed semantic analysis."""

from __future__ import annotations

import hashlib
import mimetypes
import os
import shutil
from pathlib import Path
from typing import Any, Dict

from app.core.config import settings
from app.ingestion.contracts import ExtractionMethod, ExtractionStatus
from app.llm.base import ProviderError
from app.llm.multimodal import configured_gemini_multimodal


def parse_image_file(file_path: str) -> Dict[str, Any]:
    """Validate actual image bytes and return deterministic metadata only."""
    path = Path(file_path)
    file_size = os.path.getsize(file_path)
    try:
        from PIL import Image
        with Image.open(file_path) as image:
            image.verify()
        with Image.open(file_path) as image:
            image_format = (image.format or "").upper()
            width, height = image.size
    except Exception as exc:
        return {
            "status": ExtractionStatus.INVALID_MEDIA.value,
            "chunks": [],
            "metadata": {"file_name": path.name, "file_size_bytes": file_size, "error_code": "INVALID_MEDIA", "error_message": "Image bytes are malformed or unsupported."},
        }

    if image_format not in {"PNG", "JPEG"}:
        return {
            "status": ExtractionStatus.INVALID_MEDIA.value,
            "chunks": [],
            "metadata": {"file_name": path.name, "file_size_bytes": file_size, "format": image_format or None, "error_code": "UNSUPPORTED_FILE_TYPE", "error_message": "Only validated PNG and JPEG images are supported."},
        }
    if width * height > settings.MAX_IMAGE_PIXELS:
        return {
            "status": ExtractionStatus.INVALID_MEDIA.value,
            "chunks": [],
            "metadata": {"file_name": path.name, "file_size_bytes": file_size, "format": image_format, "width": width, "height": height, "error_code": "IMAGE_PIXEL_LIMIT_EXCEEDED"},
        }

    return {
        "status": ExtractionStatus.VISION_UNAVAILABLE.value,
        "chunks": [],
        "metadata": {
            "file_name": path.name,
            "file_type": image_format.lower(),
            "format": image_format,
            "width": width,
            "height": height,
            "file_size_bytes": file_size,
            "vision_status": ExtractionStatus.VISION_UNAVAILABLE.value,
            "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        },
    }


def _local_image_ocr(file_path: str) -> tuple[str | None, str | None]:
    """Run genuine local OCR when the pinned Tesseract runtime is present."""
    if not shutil.which("tesseract"):
        return None, "OCR_UNAVAILABLE"
    try:
        import pytesseract
        from PIL import Image
        with Image.open(file_path) as image:
            text = pytesseract.image_to_string(image, timeout=settings.PDF_OCR_TIMEOUT_SECONDS).strip()
        return (text or None), None
    except Exception:
        return None, "OCR_FAILED"


async def analyze_image_file(file_path: str) -> Dict[str, Any]:
    """Run genuine structured vision when configured; never invent semantics."""
    parsed = parse_image_file(file_path)
    if parsed["status"] == ExtractionStatus.INVALID_MEDIA.value:
        return parsed
    provider = configured_gemini_multimodal()
    chunks = []
    ocr_text, ocr_error = _local_image_ocr(file_path)
    if ocr_text:
        chunks.append({
            "content": ocr_text,
            "modality": "image",
            "extraction_method": ExtractionMethod.IMAGE_OCR.value,
            "metadata": {"content_type": "image_ocr", "provider": "Tesseract", "content_trusted": False, "content_label": "UNTRUSTED_IMAGE_DATA"},
        })
    if provider is None:
        if chunks:
            return {**parsed, "status": ExtractionStatus.PARTIALLY_READY.value, "chunks": chunks, "metadata": {**parsed["metadata"], "vision_status": ExtractionStatus.VISION_UNAVAILABLE.value, "ocr_status": ExtractionStatus.READY.value}}
        return {**parsed, "metadata": {**parsed["metadata"], "ocr_status": ocr_error or "OCR_UNAVAILABLE"}}

    try:
        analysis = await provider.analyze_image(file_path, mimetypes.guess_type(file_path)[0])
    except ProviderError as exc:
        return {**parsed, "status": ExtractionStatus.PARTIALLY_READY.value if chunks else ExtractionStatus.VISION_FAILED.value, "chunks": chunks, "metadata": {**parsed["metadata"], "vision_status": ExtractionStatus.VISION_FAILED.value, "error_code": exc.code, "provider": "gemini", "model": provider.model, "ocr_status": ExtractionStatus.READY.value if ocr_text else (ocr_error or "OCR_UNAVAILABLE")}}
    except Exception:
        return {**parsed, "status": ExtractionStatus.PARTIALLY_READY.value if chunks else ExtractionStatus.VISION_FAILED.value, "chunks": chunks, "metadata": {**parsed["metadata"], "vision_status": ExtractionStatus.VISION_FAILED.value, "error_code": "VISION_FAILED", "provider": "gemini", "model": provider.model, "ocr_status": ExtractionStatus.READY.value if ocr_text else (ocr_error or "OCR_UNAVAILABLE")}}

    metadata = {**parsed["metadata"], "vision_status": ExtractionStatus.READY.value, "provider": "gemini", "model": provider.model, "provider_request_id": analysis.provider_request_id, "content_trusted": False, "content_label": "UNTRUSTED_IMAGE_DATA"}
    if analysis.detected_text and analysis.detected_text.strip():
        chunks.append({
            "content": analysis.detected_text.strip(),
            "modality": "image",
            "extraction_method": ExtractionMethod.IMAGE_OCR.value,
            "metadata": {"content_type": "image_ocr", "provider": "gemini", "model": provider.model, "provider_request_id": analysis.provider_request_id, "content_trusted": False, "content_label": "UNTRUSTED_IMAGE_DATA"},
        })
    observations = [item.strip() for item in analysis.key_observations if isinstance(item, str) and item.strip()]
    if analysis.summary and analysis.summary.strip():
        observations.insert(0, analysis.summary.strip())
    if analysis.visual_entities:
        observations.append("Visual entities: " + ", ".join(str(item) for item in analysis.visual_entities))
    if analysis.chart_or_table:
        observations.append("Chart/table interpretation: " + (analysis.chart_or_table if isinstance(analysis.chart_or_table, str) else str(analysis.chart_or_table)))
    if observations:
        chunks.append({
            "content": "\n".join(observations),
            "modality": "image",
            "extraction_method": ExtractionMethod.VISION.value,
            "metadata": {
                "content_type": "vision_observation",
                "provider": "gemini",
                "model": provider.model,
                "provider_request_id": analysis.provider_request_id,
                "limitations": analysis.limitations,
                "confidence": analysis.confidence,
                "structured_payload": {
                    "visual_entities": analysis.visual_entities,
                    "chart_or_table": analysis.chart_or_table,
                },
                "content_trusted": False,
                "content_label": "UNTRUSTED_IMAGE_DATA",
            },
        })
    if not chunks:
        metadata.update({"vision_status": ExtractionStatus.NO_TEXT_DETECTED.value, "error_code": "NO_MEANINGFUL_VISION_OUTPUT"})
        return {"status": ExtractionStatus.NO_TEXT_DETECTED.value, "chunks": [], "metadata": metadata}
    return {"status": ExtractionStatus.READY.value, "chunks": chunks, "metadata": metadata}
