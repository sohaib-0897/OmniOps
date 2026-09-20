from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from app.core.config import settings
from app.core.database import engine, Base
from app.api.v1.router import api_v1_router
from app.schemas.common import ResponseEnvelope, ErrorDetail
from app.core.observability import request_observability

@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.validate_production_configuration()
    # SQLite development remains convenient; PostgreSQL schemas are migration-only.
    if settings.DATABASE_URL.startswith("sqlite"):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    else:
        settings.validate_embedding_configuration()
    yield
    # Shutdown: Dispose engine connection pool
    await engine.dispose()

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="OmniOps — Evidence-Grounded Business Intelligence Platform API",
    lifespan=lifespan
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.middleware("http")(request_observability)

# Exception Handlers: Standardize Error Envelopes
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    details = [
        ErrorDetail(
            code="VALIDATION_ERROR",
            message=err.get("msg", "Invalid parameter"),
            field=" -> ".join(str(loc) for loc in err.get("loc", []))
        )
        for err in exc.errors()
    ]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=ResponseEnvelope.fail(
            code="VALIDATION_ERROR",
            message="Request parameter validation failed.",
            details=details
        ).model_dump(mode="json")
    )

from fastapi import HTTPException
from starlette.exceptions import HTTPException as StarletteHTTPException

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    detail_msg = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    payload = ResponseEnvelope.fail(
        code=f"HTTP_{exc.status_code}",
        message=detail_msg
    ).model_dump(mode="json")
    payload["detail"] = detail_msg
    return JSONResponse(
        status_code=exc.status_code,
        content=payload,
        headers=exc.headers
    )

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ResponseEnvelope.fail(
            code="INTERNAL_SERVER_ERROR",
            message="An unexpected server error occurred."
        ).model_dump(mode="json")
    )

# Mount API Router
app.include_router(api_v1_router)
