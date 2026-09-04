import hashlib
import math
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

import httpx
from pydantic import BaseModel

from app.core.config import settings


class EmbeddingState(str, Enum):
    READY = "READY"
    EMBEDDING_PROVIDER_UNAVAILABLE = "EMBEDDING_PROVIDER_UNAVAILABLE"
    EMBEDDING_GENERATION_FAILED = "EMBEDDING_GENERATION_FAILED"
    DIMENSION_MISMATCH = "DIMENSION_MISMATCH"
    DEVELOPMENT_FALLBACK = "DEVELOPMENT_FALLBACK"


class EmbeddingResult(BaseModel):
    state: EmbeddingState
    vector: Optional[List[float]] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    dimension: Optional[int] = None
    generated_at: Optional[datetime] = None
    error: Optional[str] = None


class DevelopmentHashEmbeddingProvider:
    """Explicit SQLite/test-only ranking fallback. Never used for PostgreSQL retrieval."""

    @staticmethod
    def generate(text: str, dimension: int) -> List[float]:
        vector = [0.0] * dimension
        words = text.lower().split()
        for index, word in enumerate(words):
            digest = int(hashlib.sha256(f"{index}:{word}".encode()).hexdigest(), 16)
            vector[digest % dimension] += 1.0 if digest & 1 else -1.0
        norm = math.sqrt(sum(value * value for value in vector))
        return [value / norm for value in vector] if norm else vector


class EmbeddingProvider:
    """Genuine provider embeddings for PostgreSQL, explicit hash fallback for SQLite only."""

    @classmethod
    async def generate(cls, text: str, *, allow_development_fallback: bool = False) -> EmbeddingResult:
        text = text.strip()
        if not text:
            return EmbeddingResult(state=EmbeddingState.EMBEDDING_GENERATION_FAILED, error="Embedding input is empty.")
        settings.validate_embedding_configuration()

        if settings.EMBEDDING_PROVIDER != "openai" or not settings.OPENAI_API_KEY:
            if allow_development_fallback:
                vector = DevelopmentHashEmbeddingProvider.generate(text, settings.EMBEDDING_DIMENSION)
                return EmbeddingResult(
                    state=EmbeddingState.DEVELOPMENT_FALLBACK, vector=vector,
                    provider="development-hash", model="development-hash-v1",
                    dimension=len(vector), generated_at=datetime.now(timezone.utc),
                )
            return EmbeddingResult(
                state=EmbeddingState.EMBEDDING_PROVIDER_UNAVAILABLE,
                provider=settings.EMBEDDING_PROVIDER, model=settings.EMBEDDING_MODEL,
                dimension=settings.EMBEDDING_DIMENSION, error="A genuine embedding provider is not configured.",
            )

        payload = {
            "input": text[:8000], "model": settings.EMBEDDING_MODEL,
            "dimensions": settings.EMBEDDING_DIMENSION,
        }
        try:
            async with httpx.AsyncClient(timeout=20.0, trust_env=False) as client:
                response = await client.post(
                    "https://api.openai.com/v1/embeddings",
                    headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"}, json=payload,
                )
            if response.status_code != 200:
                return EmbeddingResult(
                    state=EmbeddingState.EMBEDDING_GENERATION_FAILED,
                    provider="openai", model=settings.EMBEDDING_MODEL,
                    dimension=settings.EMBEDDING_DIMENSION,
                    error=f"Embedding provider returned HTTP {response.status_code}.",
                )
            vector = response.json()["data"][0]["embedding"]
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            return EmbeddingResult(
                state=EmbeddingState.EMBEDDING_GENERATION_FAILED,
                provider="openai", model=settings.EMBEDDING_MODEL,
                dimension=settings.EMBEDDING_DIMENSION, error=str(exc),
            )
        if len(vector) != settings.EMBEDDING_DIMENSION:
            return EmbeddingResult(
                state=EmbeddingState.DIMENSION_MISMATCH, provider="openai",
                model=settings.EMBEDDING_MODEL, dimension=len(vector),
                error=f"Expected {settings.EMBEDDING_DIMENSION} values, received {len(vector)}.",
            )
        return EmbeddingResult(
            state=EmbeddingState.READY, vector=vector, provider="openai",
            model=settings.EMBEDDING_MODEL, dimension=len(vector), generated_at=datetime.now(timezone.utc),
        )
