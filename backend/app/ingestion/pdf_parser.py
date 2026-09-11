"""Page-aware PDF extraction with genuine OCR fallback when available."""

from __future__ import annotations

import shutil
from typing import Any, Dict, List, Tuple

import fitz  # PyMuPDF

from app.core.config import settings
from app.ingestion.contracts import ExtractionBatch, ExtractionMethod, ExtractionRecord, ExtractionStatus


def _chunk_text(text: str, page_number: int, method: ExtractionMethod, metadata: Dict[str, Any]) -> List[ExtractionRecord]:
    paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
    if not paragraphs:
        paragraphs = [text.strip()] if text.strip() else []
    records: List[ExtractionRecord] = []
    current: List[str] = []
    current_len = 0
    for paragraph in paragraphs:
        current.append(paragraph)
        current_len += len(paragraph)
        if current_len > 1200:
            chunk = "\n\n".join(current)
            records.append(ExtractionRecord(
                modality="pdf", text=chunk, page_number=page_number,
                extraction_method=method, metadata={**metadata, "page": page_number, "char_count": len(chunk)},
            ))
            current, current_len = [], 0
    if current:
        chunk = "\n\n".join(current)
        records.append(ExtractionRecord(
            modality="pdf", text=chunk, page_number=page_number,
            extraction_method=method, metadata={**metadata, "page": page_number, "char_count": len(chunk)},
        ))
    return records


def _ocr_page_text(page: fitz.Page) -> Tuple[str, Dict[str, Any]]:
    """Run real local OCR, or return a typed unavailable result."""
    if not shutil.which("tesseract"):
        raise RuntimeError("OCR_UNAVAILABLE: Tesseract executable is not installed.")
    try:
        import pytesseract
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("OCR_UNAVAILABLE: pytesseract and Pillow are required.") from exc

    pixmap = page.get_pixmap(matrix=fitz.Matrix(settings.PDF_OCR_DPI / 72, settings.PDF_OCR_DPI / 72), alpha=False)
    image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
    text = pytesseract.image_to_string(image, timeout=settings.PDF_OCR_TIMEOUT_SECONDS).strip()
    version = None
    try:
        version = str(pytesseract.get_tesseract_version())
    except Exception:
        pass
    return text, {"ocr_engine": "Tesseract", "ocr_engine_version": version}


def extract_pdf_document(file_path: str) -> ExtractionBatch:
    """Extract native text page-by-page and OCR only pages without usable text."""
    records: List[ExtractionRecord] = []
    ocr_pages: List[int] = []
    failed_pages: List[Dict[str, Any]] = []
    pages_processed = 0
    extracted_chars = 0
    try:
        doc = fitz.open(file_path)
    except Exception as exc:
        return ExtractionBatch(status=ExtractionStatus.INVALID_MEDIA, error_code="INVALID_MEDIA", error_message="PDF could not be opened.", metadata={"exception_type": type(exc).__name__})

    try:
        if len(doc) > settings.MAX_PDF_PAGES:
            return ExtractionBatch(status=ExtractionStatus.INVALID_MEDIA, error_code="MEDIA_TOO_LARGE", error_message=f"PDF exceeds the {settings.MAX_PDF_PAGES}-page limit.")
        for page_idx in range(len(doc)):
            page = doc[page_idx]
            page_number = page_idx + 1
            pages_processed += 1
            native_text = page.get_text("text").strip()

            table_markdowns: List[str] = []
            try:
                tables = page.find_tables()
                for table in tables:
                    try:
                        dataframe = table.to_pandas()
                        if not dataframe.empty:
                            table_markdowns.append(dataframe.to_markdown(index=False))
                    except Exception:
                        continue
            except Exception:
                pass

            if len(native_text) >= settings.PDF_MIN_NATIVE_TEXT_CHARS:
                extracted_chars += len(native_text) + sum(len(value) for value in table_markdowns)
                if extracted_chars > settings.MAX_EXTRACTED_TEXT_CHARS:
                    return ExtractionBatch(status=ExtractionStatus.INVALID_MEDIA, error_code="EXTRACTED_TEXT_LIMIT_EXCEEDED", error_message="PDF extracted text exceeds the configured limit.")
                records.extend(_chunk_text(native_text, page_number, ExtractionMethod.NATIVE_TEXT, {"extraction_method": ExtractionMethod.NATIVE_TEXT.value, "has_tables": bool(table_markdowns)}))
                if table_markdowns:
                    records.extend(_chunk_text("\n\n".join(table_markdowns), page_number, ExtractionMethod.TABLE_EXTRACTION, {"extraction_method": ExtractionMethod.TABLE_EXTRACTION.value, "has_tables": True}))
                continue

            try:
                ocr_text, ocr_meta = _ocr_page_text(page)
                ocr_pages.append(page_number)
                if ocr_text:
                    extracted_chars += len(ocr_text)
                    if extracted_chars > settings.MAX_EXTRACTED_TEXT_CHARS:
                        return ExtractionBatch(status=ExtractionStatus.INVALID_MEDIA, error_code="EXTRACTED_TEXT_LIMIT_EXCEEDED", error_message="PDF extracted text exceeds the configured limit.")
                    records.extend(_chunk_text(ocr_text, page_number, ExtractionMethod.OCR, {"extraction_method": ExtractionMethod.OCR.value, **ocr_meta}))
                else:
                    failed_pages.append({"page": page_number, "status": ExtractionStatus.NO_TEXT_DETECTED.value, "error_code": "NO_TEXT_DETECTED"})
            except RuntimeError as exc:
                message = str(exc)
                code = "OCR_UNAVAILABLE" if message.startswith("OCR_UNAVAILABLE") else "OCR_FAILED"
                failed_pages.append({"page": page_number, "status": code, "error_code": code, "message": message})
            except Exception as exc:
                failed_pages.append({"page": page_number, "status": ExtractionStatus.OCR_FAILED.value, "error_code": "OCR_FAILED", "message": str(exc)})
    finally:
        doc.close()

    status = ExtractionStatus.READY if not failed_pages else ExtractionStatus.PARTIALLY_READY
    if not records and failed_pages and all(page.get("status") == ExtractionStatus.NO_TEXT_DETECTED.value for page in failed_pages):
        status = ExtractionStatus.NO_TEXT_DETECTED
    return ExtractionBatch(
        status=status,
        records=records,
        metadata={"pages_processed": pages_processed, "ocr_pages": ocr_pages, "failed_pages": failed_pages},
        error_code=failed_pages[0].get("error_code") if failed_pages and not records else None,
    )


def parse_pdf_document(file_path: str) -> List[Dict[str, Any]]:
    """Backward-compatible list API used by callers/tests."""
    batch = extract_pdf_document(file_path)
    return [
        {
            "content": record.text or "",
            "page_number": record.page_number,
            "modality": record.modality,
            "extraction_method": record.extraction_method.value,
            "metadata": {**record.metadata, "status": record.status.value, "provider": record.provider, "model": record.model},
        }
        for record in batch.records
    ]
