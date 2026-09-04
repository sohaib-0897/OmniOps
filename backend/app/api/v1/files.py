import uuid
from typing import List
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.config import settings
from app.models.user import WorkspaceMembership, WorkspaceRole
from app.models.document import SourceDocument, DocumentChunk, TabularDataset, ProcessingStatus
from app.schemas.document import DocumentResponse, DocumentChunkResponse
from app.schemas.common import ResponseEnvelope
from app.api.deps import get_workspace_membership, require_role
from app.ingestion.file_guard import process_and_save_upload
from app.ingestion.tabular import process_tabular_file
from app.ingestion.pdf_parser import parse_pdf_document
from app.ingestion.docx_parser import parse_docx_document
from app.ingestion.audio_parser import parse_audio_recording
from app.ingestion.vision_parser import parse_image_file
from app.rag.embeddings import EmbeddingProvider, EmbeddingState

router = APIRouter(prefix="/workspaces/{workspace_id}/files", tags=["Files & Ingestion"])


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

@router.post("", response_model=ResponseEnvelope[DocumentResponse])
async def upload_file(
    workspace_id: uuid.UUID,
    file: UploadFile = File(...),
    membership: WorkspaceMembership = Depends(require_role(WorkspaceRole.EDITOR)),
    db: AsyncSession = Depends(get_db)
):
    """Upload and process multimodal document into the workspace."""
    # 1. Guard and store
    clean_name, storage_path, byte_size, sha256_hash, modality = await process_and_save_upload(
        file=file,
        workspace_id=str(workspace_id)
    )

    # Check for duplicate document in workspace
    existing_doc = (await db.execute(
        select(SourceDocument).where(
            SourceDocument.workspace_id == workspace_id,
            SourceDocument.sha256_hash == sha256_hash
        )
    )).scalar_one_or_none()

    if existing_doc:
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
    await db.flush()

    try:
        # 2. Ingestion Dispatch
        if modality == "spreadsheet":
            datasets_meta = process_tabular_file(storage_path, workspace_id, clean_name)
            for d_meta in datasets_meta:
                existing_dataset = (await db.execute(
                    select(TabularDataset).where(
                        TabularDataset.workspace_id == workspace_id,
                        TabularDataset.table_name == d_meta["table_name"]
                    )
                )).scalar_one_or_none()

                if existing_dataset:
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
            chunks = parse_pdf_document(storage_path)
            for idx, c in enumerate(chunks):
                embedding_fields = await _embedding_fields(c["content"], db)
                chunk_obj = DocumentChunk(
                    workspace_id=workspace_id,
                    source_id=doc.id,
                    chunk_index=idx,
                    content=c["content"],
                    modality="pdf",
                    page_number=c.get("page_number"),
                    chunk_metadata=c.get("metadata", {}),
                    extraction_method="pymupdf",
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
                    chunk_metadata=c.get("metadata", {}),
                    extraction_method="python-docx",
                    **embedding_fields
                )
                db.add(chunk_obj)

        elif modality == "audio":
            parsed = parse_audio_recording(storage_path)
            doc.doc_metadata = {**(doc.doc_metadata or {}), **parsed["metadata"], "semantic_status": parsed["status"]}
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
                    chunk_metadata=c.get("metadata", {}),
                    extraction_method=c.get("metadata", {}).get("engine", "OpenAI-Whisper-1"),
                    **embedding_fields
                )
                db.add(chunk_obj)

        elif modality == "image":
            parsed = parse_image_file(storage_path)
            doc.doc_metadata = {**(doc.doc_metadata or {}), **parsed["metadata"], "semantic_status": parsed["status"]}
            for idx, c in enumerate(parsed["chunks"]):
                embedding_fields = await _embedding_fields(c["content"], db)
                chunk_obj = DocumentChunk(
                    workspace_id=workspace_id,
                    source_id=doc.id,
                    chunk_index=idx,
                    content=c["content"],
                    modality="image",
                    chunk_metadata=c.get("metadata", {}),
                    extraction_method="vision-provider",
                    **embedding_fields
                )
                db.add(chunk_obj)

        elif modality == "text":
            content = Path(storage_path).read_text(encoding="utf-8", errors="replace").strip()
            if content:
                embedding_fields = await _embedding_fields(content, db)
                db.add(DocumentChunk(
                    workspace_id=workspace_id, source_id=doc.id, chunk_index=0,
                    content=content, modality="text", extraction_method="utf-8-text",
                    **embedding_fields,
                ))

        await db.flush()
        chunk_states = (await db.execute(select(DocumentChunk.semantic_search_status).where(DocumentChunk.source_id == doc.id))).scalars().all()
        if chunk_states:
            semantic_state = "READY" if all(state == "READY" for state in chunk_states) else (
                "DEVELOPMENT_FALLBACK" if all(state == "DEVELOPMENT_FALLBACK" for state in chunk_states) else "UNAVAILABLE"
            )
            doc.doc_metadata = {**(doc.doc_metadata or {}), "search_indexing": {"lexical": "READY", "semantic": semantic_state}}
        doc.processing_status = ProcessingStatus.READY.value
        await db.commit()
        await db.refresh(doc)
        return ResponseEnvelope.ok(DocumentResponse.model_validate(doc))

    except Exception as e:
        doc.processing_status = ProcessingStatus.FAILED.value
        doc.error_message = str(e)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to process {modality} document: {str(e)}"
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

    # Query and delete physical parquet files associated with this document
    tabular_datasets = (await db.execute(
        select(TabularDataset).where(
            TabularDataset.workspace_id == workspace_id,
            TabularDataset.source_id == file_id
        )
    )).scalars().all()

    for ds in tabular_datasets:
        if ds.parquet_storage_path:
            try:
                Path(ds.parquet_storage_path).unlink(missing_ok=True)
            except Exception:
                pass

    # Delete primary physical file
    try:
        Path(doc.storage_path).unlink(missing_ok=True)
    except Exception:
        pass

    await db.delete(doc)
    await db.commit()
    return ResponseEnvelope.ok({"deleted": True, "file_id": str(file_id)})
