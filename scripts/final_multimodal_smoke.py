"""Two-request live Gemini smoke with persistence, retrieval, and lineage checks."""

import asyncio
import hashlib
import json
import sys
import uuid
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.api.v1.files import _provenance_metadata
from app.core.config import settings
from app.evidence.validator import validate_claim_proposal
from app.ingestion.audio_parser import transcribe_audio_recording
from app.ingestion.vision_parser import analyze_image_file
from app.models.document import DocumentChunk, SourceDocument
from app.models.evidence import EvidenceItem
from app.models.investigation import InvestigationSession
from app.models.user import User, Workspace
from app.rag.hybrid_search import HybridRetriever


async def main() -> None:
    if not settings.GEMINI_API_KEY:
        print(json.dumps({"status": "NOT_RUN", "reason": "GEMINI_CREDENTIAL_UNAVAILABLE"}))
        raise SystemExit(2)

    media = [
        ("image", ROOT / "phase7-evidence/test-media/vision.png", analyze_image_file),
        ("audio", ROOT / "phase7-evidence/test-media/speech-tts.wav", transcribe_audio_recording),
    ]
    engine = create_async_engine(settings.DATABASE_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    results = []
    try:
        async with factory() as db:
            user = User(
                email=f"final-multimodal-{uuid.uuid4()}@example.com",
                hashed_password="not-a-login-account",
                full_name="Final Multimodal Audit",
            )
            db.add(user)
            await db.flush()
            workspace = Workspace(
                name="Final Multimodal Audit", created_by=user.id,
                description="Authored two-request release smoke.",
            )
            db.add(workspace)
            await db.flush()

            for modality, path, parser in media:
                parsed = await parser(str(path))
                if parsed.get("status") != "READY" or not parsed.get("chunks"):
                    raise RuntimeError(
                        f"{modality.upper()}_PROVIDER_SMOKE_FAILED:{parsed.get('status')}:"
                        f"{parsed.get('metadata', {}).get('error_code')}"
                    )
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                document = SourceDocument(
                    workspace_id=workspace.id,
                    file_name=f"authored-{path.name}",
                    storage_path=str(path),
                    mime_type="image/png" if modality == "image" else "audio/wav",
                    byte_size=path.stat().st_size,
                    sha256_hash=digest,
                    modality=modality,
                    processing_status="ready",
                    doc_metadata={**parsed.get("metadata", {}), "authored_audit_fixture": True},
                )
                db.add(document)
                await db.flush()
                investigation = InvestigationSession(
                    workspace_id=workspace.id,
                    user_id=user.id,
                    objective=f"Authored {modality} provider persistence check",
                    current_state="failed",
                    status="failed",
                )
                db.add(investigation)
                await db.flush()

                evidence_ids = []
                provider_chunks = 0
                timestamped_chunks = 0
                speaker_chunks = 0
                request_id_present = False
                for index, payload in enumerate(parsed["chunks"]):
                    metadata = _provenance_metadata(document, payload, index)
                    provider_chunks += int(metadata.get("provider") == "gemini")
                    request_id_present = request_id_present or bool(metadata.get("provider_request_id"))
                    timestamped_chunks += int(
                        payload.get("audio_start_ms") is not None
                        and payload.get("audio_end_ms") is not None
                    )
                    speaker_chunks += int(bool(metadata.get("speaker")))
                    chunk = DocumentChunk(
                        workspace_id=workspace.id,
                        source_id=document.id,
                        chunk_index=index,
                        content=payload["content"],
                        modality=modality,
                        extraction_method=payload.get("extraction_method", "unknown"),
                        audio_start_ms=payload.get("audio_start_ms"),
                        audio_end_ms=payload.get("audio_end_ms"),
                        chunk_metadata=metadata,
                        semantic_search_status="UNAVAILABLE",
                        lexical_search_status="READY",
                    )
                    db.add(chunk)
                    await db.flush()
                    evidence = EvidenceItem(
                        session_id=investigation.id,
                        source_id=document.id,
                        chunk_id=chunk.id,
                        exact_quote=chunk.content,
                        audio_start_ms=chunk.audio_start_ms,
                        audio_end_ms=chunk.audio_end_ms,
                    )
                    db.add(evidence)
                    await db.flush()
                    evidence_ids.append(str(evidence.id))
                await db.commit()

                retrieval = await HybridRetriever.search(
                    workspace_id=workspace.id,
                    query="revenue",
                    db=db,
                    top_k=10,
                    source_ids=[document.id],
                )
                lineage = await validate_claim_proposal(
                    db, investigation.id, evidence_ids, [],
                )
                if provider_chunks == 0 or not request_id_present or not retrieval.results or not lineage.valid:
                    raise RuntimeError(f"{modality.upper()}_PERSISTENCE_CHAIN_FAILED")
                results.append({
                    "modality": modality,
                    "status": parsed["status"],
                    "provider": "gemini",
                    "chunks": len(parsed["chunks"]),
                    "provider_chunks": provider_chunks,
                    "request_id_present": request_id_present,
                    "timestamped_chunks": timestamped_chunks,
                    "speaker_chunks": speaker_chunks,
                    "retrieval_backend": retrieval.backend,
                    "retrieval_hits": len(retrieval.results),
                    "lineage_valid": lineage.valid,
                })
    finally:
        await engine.dispose()
    print(json.dumps({"status": "PASS", "requests": 2, "results": results}, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
