import math
import re
import uuid
from typing import Any, Dict, List, Optional, Sequence

from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.document import DocumentChunk, SourceDocument
from app.rag.embeddings import EmbeddingProvider, EmbeddingState


class RetrievalError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class RetrievedChunk(BaseModel):
    chunk_id: str
    source_id: str
    source_name: str
    modality: str
    content: str
    page_number: Optional[int] = None
    cell_range: Optional[str] = None
    audio_start_ms: Optional[int] = None
    audio_end_ms: Optional[int] = None
    semantic_rank: Optional[int] = None
    lexical_rank: Optional[int] = None
    semantic_similarity: Optional[float] = None
    lexical_score: Optional[float] = None
    fused_score: float
    embedding_provider: Optional[str] = None
    embedding_model: Optional[str] = None


class HybridSearchResponse(BaseModel):
    mode: str
    backend: str
    rrf_k: int
    results: List[RetrievedChunk] = Field(default_factory=list)
    semantic_state: str
    lexical_state: str


def _validate_request(query: str, top_k: int, source_ids: Optional[Sequence[uuid.UUID]]) -> str:
    query = query.strip()
    if not query:
        raise RetrievalError("EMPTY_RETRIEVAL_QUERY", "Retrieval query must not be empty.")
    if len(query) > settings.MAX_RETRIEVAL_QUERY_CHARS:
        raise RetrievalError("RETRIEVAL_QUERY_TOO_LARGE", f"Retrieval query exceeds {settings.MAX_RETRIEVAL_QUERY_CHARS} characters.")
    if not 1 <= top_k <= 100:
        raise RetrievalError("INVALID_TOP_K", "top_k must be between 1 and 100.")
    if source_ids and len(source_ids) > 100:
        raise RetrievalError("TOO_MANY_SOURCE_FILTERS", "At most 100 source IDs may be supplied.")
    for source_id in source_ids or []:
        try:
            uuid.UUID(str(source_id))
        except (ValueError, TypeError) as exc:
            raise RetrievalError("INVALID_SOURCE_FILTER", "Every source filter must be a valid UUID.") from exc
    return query


def _lexical_websearch_query(query: str) -> str:
    """Turn arbitrary natural language into a bounded, parameterized OR query."""
    tokens: list[str] = []
    seen: set[str] = set()
    for raw_token in re.findall(r"[^\W_]+", query.casefold(), flags=re.UNICODE):
        token = raw_token[:64]
        if token and token not in seen:
            seen.add(token)
            tokens.append(token)
        if len(tokens) == 32:
            break
    if not tokens:
        raise RetrievalError("EMPTY_RETRIEVAL_QUERY", "Retrieval query must contain searchable terms.")
    return " OR ".join(tokens)


class PostgresHybridRetriever:
    """PostgreSQL-native pgvector + full-text candidates fused by database-side RRF."""

    @classmethod
    async def search(
        cls, workspace_id: uuid.UUID, query: str, db: AsyncSession, top_k: int,
        source_ids: Optional[Sequence[uuid.UUID]], modality_filter: Optional[str],
    ) -> HybridSearchResponse:
        embedding = await EmbeddingProvider.generate(query, allow_development_fallback=False)
        semantic_ready = embedding.state == EmbeddingState.READY
        predicates = ["dc.workspace_id = :workspace_id"]
        params: Dict[str, Any] = {
            "workspace_id": workspace_id, "query": query,
            "lexical_query": _lexical_websearch_query(query), "top_k": top_k,
            "candidate_limit": min(settings.RETRIEVAL_CANDIDATE_LIMIT, 200), "rrf_k": settings.HYBRID_RRF_K,
        }
        if modality_filter:
            predicates.append("dc.modality = :modality")
            params["modality"] = modality_filter
        if source_ids:
            placeholders = []
            for index, source_id in enumerate(source_ids):
                key = f"source_id_{index}"
                params[key] = source_id
                placeholders.append(f":{key}")
            predicates.append(f"dc.source_id IN ({', '.join(placeholders)})")
        where_sql = " AND ".join(predicates)

        if semantic_ready:
            params["query_embedding"] = "[" + ",".join(format(value, ".12g") for value in embedding.vector or []) + "]"
            semantic_cte = f"""
            semantic AS (
                SELECT dc.id,
                       row_number() OVER (ORDER BY dc.embedding <=> CAST(:query_embedding AS vector), dc.id) AS semantic_rank,
                       1 - (dc.embedding <=> CAST(:query_embedding AS vector)) AS semantic_similarity
                FROM document_chunks dc
                WHERE {where_sql} AND dc.embedding IS NOT NULL AND dc.semantic_search_status = 'READY'
                ORDER BY dc.embedding <=> CAST(:query_embedding AS vector), dc.id
                LIMIT :candidate_limit
            )
            """
        else:
            semantic_cte = "semantic AS (SELECT NULL::uuid AS id, NULL::bigint AS semantic_rank, NULL::double precision AS semantic_similarity WHERE FALSE)"

        sql = text(f"""
            WITH {semantic_cte},
            lexical AS (
                SELECT dc.id,
                       row_number() OVER (ORDER BY ts_rank_cd(dc.search_vector, websearch_to_tsquery('english', :lexical_query)) DESC, dc.id) AS lexical_rank,
                       ts_rank_cd(dc.search_vector, websearch_to_tsquery('english', :lexical_query)) AS lexical_score
                FROM document_chunks dc
                WHERE {where_sql}
                  AND dc.search_vector @@ websearch_to_tsquery('english', :lexical_query)
                  AND dc.lexical_search_status = 'READY'
                ORDER BY lexical_score DESC, dc.id
                LIMIT :candidate_limit
            ),
            candidate_ids AS (
                SELECT id FROM semantic UNION SELECT id FROM lexical
            ),
            fused AS (
                SELECT ids.id, s.semantic_rank, l.lexical_rank, s.semantic_similarity, l.lexical_score,
                       COALESCE(1.0 / (:rrf_k + s.semantic_rank), 0.0) +
                       COALESCE(1.0 / (:rrf_k + l.lexical_rank), 0.0) AS fused_score
                FROM candidate_ids ids
                LEFT JOIN semantic s ON s.id = ids.id
                LEFT JOIN lexical l ON l.id = ids.id
            )
            SELECT dc.id AS chunk_id, dc.source_id, sd.file_name AS source_name, dc.modality, dc.content,
                   dc.page_number, dc.cell_range, dc.audio_start_ms, dc.audio_end_ms,
                   fused.semantic_rank, fused.lexical_rank, fused.semantic_similarity, fused.lexical_score,
                   fused.fused_score, dc.embedding_provider, dc.embedding_model
            FROM fused
            JOIN document_chunks dc ON dc.id = fused.id AND dc.workspace_id = :workspace_id
            JOIN source_documents sd ON sd.id = dc.source_id AND sd.workspace_id = :workspace_id
            ORDER BY fused.fused_score DESC, dc.id
            LIMIT :top_k
        """)
        rows = (await db.execute(sql, params)).mappings().all()
        results = [RetrievedChunk(**{**dict(row), "chunk_id": str(row["chunk_id"]), "source_id": str(row["source_id"])}) for row in rows]
        return HybridSearchResponse(
            mode="HYBRID" if semantic_ready else "LEXICAL_ONLY",
            backend="POSTGRESQL_PGVECTOR_FTS_RRF", rrf_k=settings.HYBRID_RRF_K,
            results=results, semantic_state=embedding.state.value, lexical_state="READY",
        )


class DevelopmentFallbackRetriever:
    """Labeled SQLite-only fallback. It makes no PostgreSQL/FTS/pgvector claims."""

    @classmethod
    async def search(
        cls, workspace_id: uuid.UUID, query: str, db: AsyncSession, top_k: int,
        source_ids: Optional[Sequence[uuid.UUID]], modality_filter: Optional[str],
    ) -> HybridSearchResponse:
        statement = select(DocumentChunk, SourceDocument.file_name).join(SourceDocument, DocumentChunk.source_id == SourceDocument.id).where(DocumentChunk.workspace_id == workspace_id)
        if source_ids:
            statement = statement.where(DocumentChunk.source_id.in_(source_ids))
        if modality_filter:
            statement = statement.where(DocumentChunk.modality == modality_filter)
        rows = (await db.execute(statement)).all()
        query_terms = set(re.findall(r"\w+", query.lower()))
        query_embedding = await EmbeddingProvider.generate(query, allow_development_fallback=True)
        ranked = []
        for chunk, source_name in rows:
            vector = chunk.embedding or []
            semantic = sum(a * b for a, b in zip(query_embedding.vector or [], vector)) if vector else 0.0
            lexical = len(query_terms.intersection(set(re.findall(r"\w+", chunk.content.lower()))))
            ranked.append((semantic, lexical, str(chunk.id), chunk, source_name))
        semantic_order = {item[2]: rank for rank, item in enumerate(sorted(ranked, key=lambda item: (-item[0], item[2])), 1)}
        lexical_order = {item[2]: rank for rank, item in enumerate(sorted(ranked, key=lambda item: (-item[1], item[2])), 1)}
        output = []
        for semantic, lexical, chunk_id, chunk, source_name in ranked:
            fused = 1 / (settings.HYBRID_RRF_K + semantic_order[chunk_id]) + 1 / (settings.HYBRID_RRF_K + lexical_order[chunk_id])
            output.append(RetrievedChunk(
                chunk_id=chunk_id, source_id=str(chunk.source_id), source_name=source_name,
                modality=chunk.modality, content=chunk.content, page_number=chunk.page_number,
                cell_range=chunk.cell_range, audio_start_ms=chunk.audio_start_ms, audio_end_ms=chunk.audio_end_ms,
                semantic_rank=semantic_order[chunk_id], lexical_rank=lexical_order[chunk_id],
                semantic_similarity=semantic, lexical_score=float(lexical), fused_score=fused,
                embedding_provider=chunk.embedding_provider, embedding_model=chunk.embedding_model,
            ))
        output.sort(key=lambda item: (-item.fused_score, item.chunk_id))
        return HybridSearchResponse(
            mode="DEVELOPMENT_FALLBACK", backend="SQLITE_DEVELOPMENT_FALLBACK",
            rrf_k=settings.HYBRID_RRF_K, results=output[:top_k],
            semantic_state=EmbeddingState.DEVELOPMENT_FALLBACK.value,
            lexical_state="DEVELOPMENT_TOKEN_MATCH",
        )


class HybridRetriever:
    @classmethod
    async def search(
        cls, workspace_id: uuid.UUID, query: str, db: AsyncSession, top_k: int = 5,
        source_ids: Optional[Sequence[uuid.UUID]] = None, modality_filter: Optional[str] = None,
    ) -> HybridSearchResponse:
        query = _validate_request(query, top_k, source_ids)
        dialect = db.get_bind().dialect.name
        if dialect == "postgresql":
            return await PostgresHybridRetriever.search(workspace_id, query, db, top_k, source_ids, modality_filter)
        if dialect == "sqlite" and settings.ENVIRONMENT.lower() in {"development", "test"}:
            return await DevelopmentFallbackRetriever.search(workspace_id, query, db, top_k, source_ids, modality_filter)
        raise RetrievalError("POSTGRESQL_RETRIEVAL_REQUIRED", "Full hybrid retrieval requires PostgreSQL with pgvector.")
