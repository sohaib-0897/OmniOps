from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

POSTGRES_VECTOR_DIMENSION = 1536

class Settings(BaseSettings):
    PROJECT_NAME: str = "OmniOps"
    VERSION: str = "1.0.0"
    API_V1_PREFIX: str = "/api/v1"
    
    # Environment
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    
    # Security / Auth
    # Must be set in production via environment variable
    SECRET_KEY: Optional[str] = None
    ALGORITHM: str = "HS256"
    # Short enough to bound stolen bearer-token use while avoiding disruptive
    # refresh churn during an investigation. Browser refresh sessions rotate.
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    REFRESH_COOKIE_NAME: str = "omniops_refresh"
    COOKIE_SECURE: bool = False
    COOKIE_SAMESITE: str = "lax"
    # Explicit exception for an initial single-VM deployment by public IPv4.
    ALLOW_INSECURE_HTTP: bool = False
    
    # Storage Paths
    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent
    STORAGE_DIR: Path = BASE_DIR / "storage"
    UPLOAD_DIR: Path = STORAGE_DIR / "uploads"
    PARQUET_DIR: Path = STORAGE_DIR / "parquet"
    TEMP_DIR: Path = STORAGE_DIR / "temp"

    # Database
    # Production retrieval requires PostgreSQL with the migrated pgvector schema.
    DATABASE_URL: str = f"sqlite+aiosqlite:///{(Path(__file__).resolve().parent.parent.parent / 'omniops_dev.db').as_posix()}"
    DATABASE_URL_TEST: str = f"sqlite+aiosqlite:///{(Path(__file__).resolve().parent.parent.parent / 'omniops_test.db').as_posix()}"
    
    # File Ingestion Limits
    MAX_FILE_SIZE_BYTES: int = 50 * 1024 * 1024  # 50 MB
    MAX_UNCOMPRESSED_BYTES: int = 200 * 1024 * 1024  # 200 MB
    MAX_EXTRACTED_TEXT_CHARS: int = 5_000_000
    MAX_DOCX_PARAGRAPHS: int = 20_000
    MAX_WORKSPACE_STORAGE_BYTES: int = 2 * 1024 * 1024 * 1024
    MAX_INGESTION_CONCURRENT: int = 4
    ALLOWED_EXTENSIONS: List[str] = [
        ".pdf", ".docx", ".xlsx", ".xls", ".csv", ".tsv", 
        ".mp3", ".wav", ".m4a", ".ogg", ".png", ".jpg", ".jpeg", ".txt"
    ]
    
    # Python Sandbox Security
    SANDBOX_TIMEOUT_SECONDS: int = 5
    SANDBOX_MAX_MEMORY_MB: int = 256
    SANDBOX_CPU_LIMIT: float = 1.0
    SANDBOX_MAX_PIDS: int = 32
    SANDBOX_MAX_STDOUT_BYTES: int = 64 * 1024
    SANDBOX_MAX_STDERR_BYTES: int = 64 * 1024
    SANDBOX_MAX_OUTPUT_BYTES: int = 256 * 1024
    SANDBOX_MAX_ARTIFACTS: int = 10
    SANDBOX_IMAGE: str = "omniops-python-sandbox:2026.09.05"
    # `container` is the only execution mode.  In production a dedicated
    # runner service URL is required; local Docker execution is only a
    # development/test convenience and fails closed in production.
    SANDBOX_EXECUTION_MODE: str = "container"
    SANDBOX_RUNNER_URL: Optional[str] = None
    SANDBOX_RUNNER_TOKEN: Optional[str] = None
    SANDBOX_MAX_CONCURRENT: int = 5

    # Outbound web retrieval security policy
    WEB_ALLOWED_SCHEMES: List[str] = ["http", "https"]
    WEB_ALLOWED_PORTS: List[int] = [80, 443]
    WEB_CONNECT_TIMEOUT_SECONDS: float = 5.0
    WEB_READ_TIMEOUT_SECONDS: float = 10.0
    WEB_TOTAL_TIMEOUT_SECONDS: float = 20.0
    WEB_MAX_REDIRECTS: int = 3
    WEB_MAX_RESPONSE_BYTES: int = 2 * 1024 * 1024
    WEB_MAX_DECODED_BYTES: int = 2 * 1024 * 1024
    WEB_ALLOWED_CONTENT_TYPES: List[str] = ["text/html", "application/xhtml+xml", "text/plain"]

    # Multimodal ingestion bounds and capability configuration
    MAX_PDF_PAGES: int = 500
    # A page with only a token or two is usually an image-only page with a
    # stray parser artifact; route it through OCR instead of declaring it
    # natively extractable.
    PDF_MIN_NATIVE_TEXT_CHARS: int = 20
    PDF_OCR_DPI: int = 200
    PDF_OCR_TIMEOUT_SECONDS: int = 20
    MAX_IMAGE_PIXELS: int = 20_000_000
    MAX_AUDIO_DURATION_SECONDS: int = 4 * 60 * 60

    # Shared, database-backed fixed-window abuse controls.
    RATE_LIMIT_LOGIN_PER_5_MINUTES: int = 10
    RATE_LIMIT_REGISTER_PER_HOUR: int = 5
    RATE_LIMIT_REFRESH_PER_5_MINUTES: int = 30
    RATE_LIMIT_UPLOAD_PER_HOUR: int = 30
    RATE_LIMIT_INVESTIGATION_PER_HOUR: int = 20

    # Database pool bounds are deliberately conservative per application process.
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 5
    DB_POOL_TIMEOUT_SECONDS: int = 30
    DB_POOL_RECYCLE_SECONDS: int = 1800
    
    # Agent Guardrails
    AGENT_DEFAULT_MAX_STEPS: int = 12
    AGENT_HARD_MAX_STEPS: int = 20
    AGENT_LOOP_DETECTION_THRESHOLD: int = 2
    
    # LLM & Embedding Settings
    LLM_PROVIDER: str = ""  # Explicit: "ollama", "openai", or "gemini" ("analytical" is test/dev only)
    OLLAMA_BASE_URL: str = "http://host.docker.internal:11434"
    OLLAMA_MODEL: str = "qwen3:4b"
    OLLAMA_TIMEOUT_SECONDS: float = 90.0
    # Sent explicitly as options.num_ctx; the server default (4096) is smaller
    # than a multi-chunk synthesis prompt plus the embedded output schema.
    OLLAMA_NUM_CTX: int = 8192
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4o"
    GEMINI_API_KEY: Optional[str] = None
    # General text/agent model.  Binary modalities use the dedicated model
    # settings below so capability and provider selection stay centralized.
    GEMINI_MODEL: str = "gemini-3.8-flash"
    GEMINI_VISION_MODEL: str = "gemini-3.8-flash"
    GEMINI_TRANSCRIPTION_MODEL: str = "gemini-3.5-transcribe"
    ANTHROPIC_API_KEY: Optional[str] = None
    EMBEDDING_PROVIDER: str = "openai"
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIMENSION: int = 1536
    EMBEDDING_SCHEMA_DIMENSION: int = 1536
    HYBRID_RRF_K: int = 60
    RETRIEVAL_CANDIDATE_LIMIT: int = 50
    MAX_RETRIEVAL_QUERY_CHARS: int = 2000

    def validate_embedding_configuration(self) -> None:
        known_dimensions = {"text-embedding-3-small": 1536, "text-embedding-3-large": 3072}
        expected = known_dimensions.get(self.EMBEDDING_MODEL)
        if expected is None:
            raise ValueError(f"Unsupported embedding model '{self.EMBEDDING_MODEL}'; configure an explicit supported schema/model pair.")
        if self.EMBEDDING_SCHEMA_DIMENSION != POSTGRES_VECTOR_DIMENSION or self.EMBEDDING_DIMENSION != expected or self.EMBEDDING_DIMENSION != self.EMBEDDING_SCHEMA_DIMENSION:
            raise ValueError(
                f"Embedding dimension mismatch: model={expected}, configured={self.EMBEDDING_DIMENSION}, schema={self.EMBEDDING_SCHEMA_DIMENSION}."
            )
    
    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="allow"
    )

    def get_secret_key(self) -> str:
        if self.SECRET_KEY and self.SECRET_KEY != "omniops-production-secret-key-change-in-production-2026":
            return self.SECRET_KEY
        if self.ENVIRONMENT.lower() in ("production", "prod", "staging"):
            raise ValueError(
                "CRITICAL SECURITY CONFIGURATION ERROR: A strong, unique SECRET_KEY environment "
                "variable must be configured for production/staging environments."
            )
        # In development/test environments, use a stable fallback if not provided
        return self.SECRET_KEY or "omniops-dev-insecure-fallback-secret-key-local-only"

    def validate_production_configuration(self) -> None:
        if self.ENVIRONMENT.lower() not in {"production", "prod", "staging"}:
            return
        self.get_secret_key()
        if len(self.SECRET_KEY or "") < 32:
            raise ValueError("Production SECRET_KEY must contain at least 32 characters.")
        if self.ALGORITHM != "HS256":
            raise ValueError("This deployment profile supports only HS256 signing.")
        if not self.DATABASE_URL.startswith("postgresql"):
            raise ValueError("Production requires a PostgreSQL DATABASE_URL.")
        if not self.CORS_ORIGINS or "*" in self.CORS_ORIGINS:
            raise ValueError("Production CORS_ORIGINS must be explicit and non-empty.")
        if self.ALLOW_INSECURE_HTTP:
            if any(not origin.startswith("http://") for origin in self.CORS_ORIGINS):
                raise ValueError("HTTP deployment CORS_ORIGINS must use explicit HTTP origins.")
            if self.COOKIE_SECURE:
                raise ValueError("HTTP deployment requires COOKIE_SECURE=false.")
        else:
            if any(not origin.startswith("https://") for origin in self.CORS_ORIGINS):
                raise ValueError("Production CORS_ORIGINS must use HTTPS.")
            if not self.COOKIE_SECURE:
                raise ValueError("Production refresh cookies require COOKIE_SECURE=true.")
        if self.COOKIE_SAMESITE.lower() not in {"strict", "lax"}:
            raise ValueError("Production COOKIE_SAMESITE must be strict or lax.")
        if self.SANDBOX_EXECUTION_MODE != "remote" or not self.SANDBOX_RUNNER_URL or not self.SANDBOX_RUNNER_TOKEN:
            raise ValueError("Production requires the authenticated remote sandbox runner.")

settings = Settings()

# Ensure critical storage directories exist
settings.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
settings.PARQUET_DIR.mkdir(parents=True, exist_ok=True)
settings.TEMP_DIR.mkdir(parents=True, exist_ok=True)
