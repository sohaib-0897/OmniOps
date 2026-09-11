from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import httpx
from app.core.config import settings
from app.core.database import get_db
from app.ingestion.capabilities import capability_matrix
from app.schemas.common import ResponseEnvelope
from app.core.observability import prometheus_metrics

router = APIRouter(tags=["System"])

@router.get("/health", response_model=ResponseEnvelope[dict])
async def health_check():
    """Liveness only: reaching this handler proves the process event loop is alive."""
    return ResponseEnvelope.ok({"status": "healthy", "service": "OmniOps Backend", "version": settings.VERSION})

@router.get("/readiness", response_model=ResponseEnvelope[dict])
async def readiness_check(response: Response, db: AsyncSession = Depends(get_db)):
    checks = {}
    try:
        await db.execute(text("SELECT 1")); checks["database"] = "ready"
        if db.get_bind().dialect.name == "postgresql":
            vector = (await db.execute(text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname='vector')"))).scalar()
            checks["pgvector"] = "ready" if vector else "unavailable"
            revision = (await db.execute(text("SELECT version_num FROM alembic_version"))).scalar_one_or_none()
            checks["migrations"] = "ready" if revision == "20260911_phase6_sessions" else "out_of_date"
    except Exception:
        checks["database"] = "unavailable"
    if settings.ENVIRONMENT.lower() in {"production", "prod", "staging"}:
        checks["sandbox_runner"] = "unavailable"
        if settings.SANDBOX_RUNNER_URL and settings.SANDBOX_RUNNER_TOKEN:
            try:
                async with httpx.AsyncClient(timeout=3.0) as client:
                    result = await client.get(f"{settings.SANDBOX_RUNNER_URL.rstrip('/')}/health", headers={"Authorization": f"Bearer {settings.SANDBOX_RUNNER_TOKEN}"})
                    checks["sandbox_runner"] = "ready" if result.status_code == 200 else "unavailable"
            except httpx.HTTPError: pass
    else: checks["sandbox_runner"] = "development_local" if not settings.SANDBOX_RUNNER_URL else "configured"
    checks["multimodal_capabilities"] = {k: v.status.value for k, v in capability_matrix().items()}
    required = [checks.get("database") == "ready", checks.get("pgvector", "ready") == "ready", checks.get("migrations", "ready") == "ready", checks.get("sandbox_runner") not in {"unavailable"}]
    ready = all(required); response.status_code = status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE
    return ResponseEnvelope.ok({"status": "ready" if ready else "not_ready", "checks": checks})

@router.get("/metrics", include_in_schema=False)
async def metrics():
    return PlainTextResponse(prometheus_metrics(), media_type="text/plain; version=0.0.4")
