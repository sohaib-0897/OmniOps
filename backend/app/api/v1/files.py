import uuid
import logging
from typing import List
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.core.rate_limit import enforce_rate_limit

from app.core.database import get_db
from app.core.config import settings
from app.models.user import WorkspaceMembership, WorkspaceRole
from app.models.document import SourceDocument, DocumentChunk, TabularDataset, ProcessingStatus
from app.schemas.document import DocumentResponse, DocumentChunkResponse
from app.schemas.common import ResponseEnvelope
from app.api.deps import get_workspace_membership, require_role
from app.ingestion.file_guard import process_and_save_upload
from app.ingestion.tabular import process_tabular_file
from app.ingestion.pdf_parser import extract_pdf_document
from app.ingestion.docx_parser import parse_docx_document
from app.ingestion.audio_parser import transcribe_audio_recording
from app.ingestion.vision_parser import analyze_image_file
from app.ingestion.contracts import ExtractionStatus, stable_extraction_id
from app.rag.embeddings import EmbeddingProvider, EmbeddingState

router = APIRouter(prefix="/workspaces/{workspace_id}/files", tags=["Files & Ingestion"])
logger = logging.getLogger(__name__)


def _managed_storage_path(raw_path: str) -> Path:
    """Resolve only application-owned upload/parquet paths for mutation."""
    candidate = Path(raw_path).resolve(strict=False)
    roots = [settings.UPLOAD_DIR.resolve(strict=False), settings.PARQUET_DIR.resolve(strict=False)]
    if not any(candidate.is_relative_to(root) for root in roots):
        raise ValueError("Storage path is outside managed application storage.")
    return candidate


async def _embedding_fields(content: str, db: AsyncSession) -> dict:
    development_fallback = db.get_bind().dialect.name == "sqlite" and settings.ENVIRONMENT.lower() in {"development", "test"}
    result = await EmbeddingProvider.generate(content, allow_development_fallback=development_fallback)
    searchable = result.state in {EmbeddingState.READY, EmbeddingState.DEVELOPMENT_FALLBACK}
    return {
        "embedding": result.vector if searchable else None,
        "embedding_provider": result.provider,
        "embedding_model": result.model,
        "embedding_dimension": result.dimension,
        "embedding_generated_at": result.generated_at,
        "semantic_search_status": result.state.value,
        "lexical_search_status": "READY",
    }


def _provenance_metadata(doc: SourceDocument, chunk: dict, index: int) -> dict:
    """Attach stable extraction identity and source coordinates to each chunk."""
    method = chunk.get("extraction_method", "unknown")
    locator = {
        "index": index,
        "page_number": chunk.get("page_number"),
        "audio_start_ms": chunk.get("audio_start_ms"),
        "audio_end_ms": chunk.get("audio_end_ms"),
    }
    metadata = dict(chunk.get("metadata") or chunk.get("chunk_metadata") or {})
    metadata.update({
        "source_document_id": str(doc.id),
        "extraction_method": method,
        "extraction_id": stable_extraction_id(
            source_hash=doc.sha256_hash,
            modality=doc.modality,
            method=method,
            locator=locator,
            content=chunk.get("content", ""),
        ),
    })
    return metadata

@router.post("", response_model=ResponseEnvelope[DocumentResponse])
async def upload_file(
    workspace_id: uuid.UUID,
    request: Request,
    file: UploadFile = File(...),
    membership: WorkspaceMembership = Depends(require_role(WorkspaceRole.EDITOR)),
    db: AsyncSession = Depends(get_db)
):
    """Upload and process multimodal document into the workspace."""
    await enforce_rate_limit(db, key=f"upload:workspace:{workspace_id}", limit=settings.RATE_LIMIT_UPLOAD_PER_HOUR, window_seconds=3600)
    if db.get_bind().dialect.name == "postgresql":
        await db.execute(
            select(func.pg_advisory_xact_lock(func.hashtext(f"workspace-storage:{workspace_id}")))
        )
    used = (await db.execute(select(func.coalesce(func.sum(SourceDocument.byte_size), 0)).where(SourceDocument.workspace_id == workspace_id))).scalar_one()
    if used >= settings.MAX_WORKSPACE_STORAGE_BYTES:
        raise HTTPException(status_code=413, detail="Workspace storage quota has been reached.")
    # 1. Guard and store
    clean_name, storage_path, byte_size, sha256_hash, modality = await process_and_save_upload(
        file=file,
        workspace_id=str(workspace_id)
    )
    if used + byte_size > settings.MAX_WORKSPACE_STORAGE_BYTES:
        Path(storage_path).unlink(missing_ok=True)
        raise HTTPException(status_code=413, detail="Upload would exceed the workspace storage quota.")

    # Check for duplicate document in workspace
    existing_doc = (await db.execute(
        select(SourceDocument).where(
            SourceDocument.workspace_id == workspace_id,
            SourceDocument.sha256_hash == sha256_hash
        )
    )).scalar_one_or_none()

    if existing_doc:
        if Path(storage_path).resolve(strict=False) != Path(existing_doc.storage_path).resolve(strict=False):
            _managed_storage_path(storage_path).unlink(missing_ok=True)
        return ResponseEnvelope.ok(DocumentResponse.model_validate(existing_doc))

    # Create SourceDocument record
    doc = SourceDocument(
        workspace_id=workspace_id,
        file_name=clean_name,
        storage_path=storage_path,
        mime_type=file.content_type or "application/octet-stream",
        byte_size=byte_size,
        sha256_hash=sha256_hash,
        modality=modality,
        processing_status=ProcessingStatus.PROCESSING.value
    )
    db.add(doc)
    created_paths = {_managed_storage_path(storage_path)}
    superseded_paths: set[Path] = set()
    try:
        await db.flush()
        # 2. Ingestion Dispatch
        if modality == "spreadsheet":
            datasets_meta = process_tabular_file(storage_path, workspace_id, clean_name)
            for d_meta in datasets_meta:
                created_paths.add(_managed_storage_path(d_meta["parquet_storage_path"]))
                existing_dataset = (await db.execute(
                    select(TabularDataset).where(
                        TabularDataset.workspace_id == workspace_id,
                        TabularDataset.table_name == d_meta["table_name"]
                    )
                )).scalar_one_or_none()

                if existing_dataset:
                    old_parquet_path = _managed_storage_path(existing_dataset.parquet_storage_path)
                    if old_parquet_path != _managed_storage_path(d_meta["parquet_storage_path"]):
                        superseded_paths.add(old_parquet_path)
                    existing_dataset.source_id = doc.id
                    existing_dataset.row_count = d_meta["row_count"]
                    existing_dataset.column_count = d_meta["column_count"]
                    existing_dataset.schema_definition = d_meta["schema_definition"]
                    existing_dataset.parquet_storage_path = d_meta["parquet_storage_path"]
                else:
                    dataset_obj = TabularDataset(
                        workspace_id=workspace_id,
                        source_id=doc.id,
                        table_name=d_meta["table_name"],
                        row_count=d_meta["row_count"],
                        column_count=d_meta["column_count"],
                        schema_definition=d_meta["schema_definition"],
                        parquet_storage_path=d_meta["parquet_storage_path"]
                    )
                    db.add(dataset_obj)

        elif modality == "pdf":
            parsed_pdf = extract_pdf_document(storage_path)
            doc.doc_metadata = {**(doc.doc_metadata or {}), **parsed_pdf.metadata, "extraction_status": parsed_pdf.status.value, "error_code": parsed_pdf.error_code}
            if parsed_pdf.status == ExtractionStatus.INVALID_MEDIA:
                raise ValueError(f"{parsed_pdf.error_code or 'INVALID_MEDIA'}: {parsed_pdf.error_message or 'PDF extraction failed.'}")
            for idx, record in enumerate(parsed_pdf.records):
                c = {"content": record.text or "", "page_number": record.page_number, "extraction_method": record.extraction_method.value, "metadata": record.metadata}
                embedding_fields = await _embedding_fields(c["content"], db)
                chunk_obj = DocumentChunk(
                    workspace_id=workspace_id,
                    source_id=doc.id,
                    chunk_index=idx,
                    content=c["content"],
                    modality="pdf",
                    page_number=c.get("page_number"),
                    chunk_metadata=_provenance_metadata(doc, c, idx),
                    extraction_method=c.get("extraction_method", "NATIVE_TEXT"),
                    **embedding_fields
                )
                db.add(chunk_obj)

        elif modality == "docx":
            chunks = parse_docx_document(storage_path)
            for idx, c in enumerate(chunks):
                embedding_fields = await _embedding_fields(c["content"], db)
                chunk_obj = DocumentChunk(
                    workspace_id=workspace_id,
                    source_id=doc.id,
                    chunk_index=idx,
                    content=c["content"],
                    modality="docx",
                    page_number=c.get("page_number"),
                    chunk_metadata=_provenance_metadata(doc, c, idx),
                    extraction_method=c.get("extraction_method", "DOCX_TEXT"),
                    **embedding_fields
                )
                db.add(chunk_obj)

        elif modality == "audio":
            parsed = await transcribe_audio_recording(storage_path)
            doc.doc_metadata = {**(doc.doc_metadata or {}), **parsed["metadata"], "semantic_status": parsed["status"], "extraction_status": parsed["status"]}
            if parsed["status"] == ExtractionStatus.INVALID_MEDIA.value:
                raise ValueError(f"{parsed['metadata'].get('error_code', 'INVALID_MEDIA')}: audio validation failed.")
            for idx, c in enumerate(parsed["chunks"]):
                embedding_fields = await _embedding_fields(c["content"], db)
                chunk_obj = DocumentChunk(
                    workspace_id=workspace_id,
                    source_id=doc.id,
                    chunk_index=idx,
                    content=c["content"],
                    modality="audio",
                    audio_start_ms=c.get("audio_start_ms"),
                    audio_end_ms=c.get("audio_end_ms"),
                    chunk_metadata=_provenance_metadata(doc, c, idx),
                    extraction_method=c.get("extraction_method", ExtractionStatus.TRANSCRIPTION_UNAVAILABLE.value),
                    **embedding_fields
                )
                db.add(chunk_obj)

        elif modality == "image":
            parsed = await analyze_image_file(storage_path)
            doc.doc_metadata = {**(doc.doc_metadata or {}), **parsed["metadata"], "semantic_status": parsed["status"], "extraction_status": parsed["status"]}
            if parsed["status"] == ExtractionStatus.INVALID_MEDIA.value:
                raise ValueError(f"{parsed['metadata'].get('error_code', 'INVALID_MEDIA')}: image validation failed.")
            for idx, c in enumerate(parsed["chunks"]):
                embedding_fields = await _embedding_fields(c["content"], db)
                chunk_obj = DocumentChunk(
                    workspace_id=workspace_id,
                    source_id=doc.id,
                    chunk_index=idx,
                    content=c["content"],
                    modality="image",
                    chunk_metadata=_provenance_metadata(doc, c, idx),
                    extraction_method=c.get("extraction_method", "VISION"),
                    **embedding_fields
                )
                db.add(chunk_obj)

        elif modality == "text":
            content = Path(storage_path).read_text(encoding="utf-8", errors="replace").strip()
            if content:
                embedding_fields = await _embedding_fields(content, db)
                db.add(DocumentChunk(
                    workspace_id=workspace_id, source_id=doc.id, chunk_index=0,
                    content=content, modality="text", extraction_method="UTF8_TEXT",
                    chunk_metadata=_provenance_metadata(doc, {"content": content, "extraction_method": "UTF8_TEXT"}, 0),
                    **embedding_fields,
                ))

        await db.flush()
        chunk_states = (await db.execute(select(DocumentChunk.semantic_search_status).where(DocumentChunk.source_id == doc.id))).scalars().all()
        if chunk_states:
            semantic_state = "READY" if all(state == "READY" for state in chunk_states) else (
                "DEVELOPMENT_FALLBACK" if all(state == "DEVELOPMENT_FALLBACK" for state in chunk_states) else "UNAVAILABLE"
            )
            doc.doc_metadata = {**(doc.doc_metadata or {}), "search_indexing": {"lexical": "READY", "semantic": semantic_state}}
        extraction_status = (doc.doc_metadata or {}).get("extraction_status")
        doc.processing_status = ProcessingStatus.PARTIALLY_READY.value if extraction_status in {
            ExtractionStatus.PARTIALLY_READY.value,
            ExtractionStatus.OCR_UNAVAILABLE.value,
            ExtractionStatus.OCR_FAILED.value,
            ExtractionStatus.VISION_UNAVAILABLE.value,
            ExtractionStatus.VISION_FAILED.value,
            ExtractionStatus.TRANSCRIPTION_UNAVAILABLE.value,
            ExtractionStatus.TRANSCRIPTION_FAILED.value,
            ExtractionStatus.NO_TEXT_DETECTED.value,
        } else ProcessingStatus.READY.value
        await db.commit()
        await db.refresh(doc)
        for path in superseded_paths:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                logger.exception("Committed dataset replacement left a superseded parquet file.")
        return ResponseEnvelope.ok(DocumentResponse.model_validate(doc))

    except Exception:
        await db.rollback()
        for path in created_paths:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                logger.exception("Failed to clean staged upload path after transaction rollback.")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to process {modality} document. No source was committed."
        )

@router.get("", response_model=ResponseEnvelope[List[DocumentResponse]])
async def list_workspace_files(
    workspace_id: uuid.UUID,
    membership: WorkspaceMembership = Depends(get_workspace_membership),
    db: AsyncSession = Depends(get_db)
):
    """List all ingested documents for workspace."""
    stmt = select(SourceDocument).where(SourceDocument.workspace_id == workspace_id).order_by(SourceDocument.created_at.desc())
    docs = (await db.execute(stmt)).scalars().all()
    return ResponseEnvelope.ok([DocumentResponse.model_validate(d) for d in docs])

@router.get("/{file_id}/preview", response_model=ResponseEnvelope[List[DocumentChunkResponse]])
async def get_file_preview(
    workspace_id: uuid.UUID,
    file_id: uuid.UUID,
    membership: WorkspaceMembership = Depends(get_workspace_membership),
    db: AsyncSession = Depends(get_db)
):
    """Get extracted text chunks and page metadata for a document."""
    # Verify file belongs to workspace
    doc = (await db.execute(
        select(SourceDocument).where(
            SourceDocument.id == file_id,
            SourceDocument.workspace_id == workspace_id
        )
    )).scalar_one_or_none()

    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found in workspace."
        )

    chunks = (await db.execute(
        select(DocumentChunk).where(DocumentChunk.source_id == file_id).order_by(DocumentChunk.chunk_index.asc())
    )).scalars().all()

    return ResponseEnvelope.ok([DocumentChunkResponse.model_validate(c) for c in chunks])

@router.delete("/{file_id}", response_model=ResponseEnvelope[dict])
async def delete_file(
    workspace_id: uuid.UUID,
    file_id: uuid.UUID,
    membership: WorkspaceMembership = Depends(require_role(WorkspaceRole.EDITOR)),
    db: AsyncSession = Depends(get_db)
):
    """Delete document, physical storage, parquet datasets, and chunks."""
    doc = (await db.execute(
        select(SourceDocument).where(
            SourceDocument.id == file_id,
            SourceDocument.workspace_id == workspace_id
        )
    )).scalar_one_or_none()

    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found in workspace."
        )

    # Query physical paths before deleting their database ownership records.
    tabular_datasets = (await db.execute(
        select(TabularDataset).where(
            TabularDataset.workspace_id == workspace_id,
            TabularDataset.source_id == file_id
        )
    )).scalars().all()

    paths = [*(ds.parquet_storage_path for ds in tabular_datasets if ds.parquet_storage_path)]
    if not doc.storage_path.startswith("web:"):
        paths.insert(0, doc.storage_path)
    staged: list[tuple[Path, Path]] = []
    try:
        for raw_path in paths:
            if not Path(raw_path).resolve(strict=False).exists():
                continue
            original = _managed_storage_path(raw_path)
            trash = original.parent / ".omniops-trash" / f"{uuid.uuid4().hex}_{original.name}"
            trash.parent.mkdir(parents=True, exist_ok=True)
            original.replace(trash)
            staged.append((original, trash))

        from app.agent.persistence import invalidate_source_dependents
        await invalidate_source_dependents(db, source_id=doc.id)
        await db.delete(doc)
        await db.commit()
    except Exception:
        await db.rollback()
        for original, trash in reversed(staged):
            if trash.exists() and not original.exists():
                original.parent.mkdir(parents=True, exist_ok=True)
                trash.replace(original)
        raise HTTPException(status_code=409, detail="Document deletion could not be committed; stored files were preserved.")

    for _, trash in staged:
        try:
            trash.unlink(missing_ok=True)
        except OSError:
            logger.exception("Committed document deletion left a quarantined file for reconciliation.")
    return ResponseEnvelope.ok({"deleted": True, "file_id": str(file_id)})
