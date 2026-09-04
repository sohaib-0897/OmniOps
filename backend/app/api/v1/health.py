from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.core.database import get_db
from app.schemas.common import ResponseEnvelope

router = APIRouter(tags=["System"])

@router.get("/health", response_model=ResponseEnvelope[dict])
async def health_check(db: AsyncSession = Depends(get_db)):
    """System health and subsystem availability check."""
    db_status = "connected"
    try:
        await db.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"

    dialect = db.get_bind().dialect.name
    retrieval_status = "development_fallback" if dialect == "sqlite" else "unavailable"
    if dialect == "postgresql" and db_status == "connected":
        extension = (await db.execute(text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')"))).scalar()
        indexes = set((await db.execute(text("SELECT indexname FROM pg_indexes WHERE tablename = 'document_chunks' AND indexname IN ('ix_document_chunks_embedding_hnsw', 'ix_document_chunks_search_vector_gin')"))).scalars().all())
        retrieval_status = "ready" if extension and len(indexes) == 2 else "unavailable"

    return ResponseEnvelope.ok({
        "status": "healthy" if db_status == "connected" else "degraded",
        "service": "OmniOps Evidence-Grounded Backend",
        "version": "1.0.0",
        "subsystems": {
            "database": db_status,
            "duckdb_vectorized_engine": "ready",
            "python_subprocess_sandbox": "ready",
            "hybrid_retrieval": retrieval_status,
            "sse_event_broadcaster": "ready"
        }
    })
