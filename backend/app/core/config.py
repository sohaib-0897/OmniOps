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
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    
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
    ALLOWED_EXTENSIONS: List[str] = [
        ".pdf", ".docx", ".xlsx", ".xls", ".csv", ".tsv", 
        ".mp3", ".wav", ".m4a", ".ogg", ".png", ".jpg", ".jpeg", ".txt"
    ]
    
    # Python Sandbox Security
    SANDBOX_TIMEOUT_SECONDS: int = 5
    SANDBOX_MAX_MEMORY_MB: int = 256
    SANDBOX_MAX_CONCURRENT: int = 5
    
    # Agent Guardrails
    AGENT_DEFAULT_MAX_STEPS: int = 12
    AGENT_HARD_MAX_STEPS: int = 20
    AGENT_LOOP_DETECTION_THRESHOLD: int = 2
    
    # LLM & Embedding Settings
    LLM_PROVIDER: str = "auto"  # "auto", "openai", "gemini", "analytical"
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4o"
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-2.5-flash"
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

settings = Settings()

# Ensure critical storage directories exist
settings.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
settings.PARQUET_DIR.mkdir(parents=True, exist_ok=True)
settings.TEMP_DIR.mkdir(parents=True, exist_ok=True)
