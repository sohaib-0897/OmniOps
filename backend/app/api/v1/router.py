from fastapi import APIRouter
from app.api.v1.auth import router as auth_router
from app.api.v1.workspaces import router as workspaces_router
from app.api.v1.files import router as files_router
from app.api.v1.tables import router as tables_router
from app.api.v1.investigations import router as investigations_router
from app.api.v1.evidence import router as evidence_router
from app.api.v1.health import router as health_router

api_v1_router = APIRouter(prefix="/api/v1")

api_v1_router.include_router(auth_router)
api_v1_router.include_router(workspaces_router)
api_v1_router.include_router(files_router)
api_v1_router.include_router(tables_router)
api_v1_router.include_router(investigations_router)
api_v1_router.include_router(evidence_router)
api_v1_router.include_router(health_router)
