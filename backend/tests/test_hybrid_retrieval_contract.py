import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.document import DocumentChunk, SourceDocument
from app.models.user import User, Workspace
from app.rag.embeddings import EmbeddingProvider, EmbeddingState
from app.rag.hybrid_search import HybridRetriever, RetrievalError


@pytest.mark.asyncio
async def test_embedding_provider_unavailable_is_explicit(monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", None)
    result = await EmbeddingProvider.generate("actual content", allow_development_fallback=False)
    assert result.state == EmbeddingState.EMBEDDING_PROVIDER_UNAVAILABLE
    assert result.vector is None
    development = await EmbeddingProvider.generate("actual content", allow_development_fallback=True)
    assert development.state == EmbeddingState.DEVELOPMENT_FALLBACK
    assert development.provider == "development-hash"


def test_embedding_dimension_configuration_rejects_mismatch(monkeypatch):
    monkeypatch.setattr(settings, "EMBEDDING_DIMENSION", 768)
    with pytest.raises(ValueError, match="dimension mismatch"):
        settings.validate_embedding_configuration()


@pytest.mark.asyncio
@pytest.mark.parametrize("query,top_k,code", [("", 5, "EMPTY_RETRIEVAL_QUERY"), ("x", 0, "INVALID_TOP_K"), ("x", 101, "INVALID_TOP_K")])
async def test_retrieval_rejects_invalid_requests(db_session, test_workspace, query, top_k, code):
    with pytest.raises(RetrievalError) as exc:
        await HybridRetriever.search(test_workspace.id, query, db_session, top_k=top_k)
    assert exc.value.code == code


@pytest.mark.asyncio
async def test_retrieval_rejects_huge_query(db_session, test_workspace):
    with pytest.raises(RetrievalError) as exc:
        await HybridRetriever.search(test_workspace.id, "x" * (settings.MAX_RETRIEVAL_QUERY_CHARS + 1), db_session)
    assert exc.value.code == "RETRIEVAL_QUERY_TOO_LARGE"


@pytest.mark.asyncio
async def test_retrieval_rejects_malformed_source_id(db_session, test_workspace):
    with pytest.raises(RetrievalError) as exc:
        await HybridRetriever.search(test_workspace.id, "margin", db_session, source_ids=["not-a-uuid"])
    assert exc.value.code == "INVALID_SOURCE_FILTER"


@pytest.mark.asyncio
async def test_sqlite_fallback_is_labeled_and_tenant_filtered(db_session: AsyncSession, test_user: User, test_workspace: Workspace):
    foreign_workspace = Workspace(name="Foreign retrieval workspace", created_by=test_user.id)
    db_session.add(foreign_workspace)
    await db_session.flush()
    own_source = SourceDocument(workspace_id=test_workspace.id, file_name="own.txt", storage_path="fixture", mime_type="text/plain", byte_size=1, sha256_hash=uuid.uuid4().hex, modality="text", processing_status="ready")
    foreign_source = SourceDocument(workspace_id=foreign_workspace.id, file_name="foreign.txt", storage_path="fixture", mime_type="text/plain", byte_size=1, sha256_hash=uuid.uuid4().hex, modality="text", processing_status="ready")
    db_session.add_all([own_source, foreign_source])
    await db_session.flush()
    own_embedding = await EmbeddingProvider.generate("operating margin", allow_development_fallback=True)
    foreign_embedding = await EmbeddingProvider.generate("operating margin", allow_development_fallback=True)
    db_session.add_all([
        DocumentChunk(workspace_id=test_workspace.id, source_id=own_source.id, chunk_index=0, content="operating margin", modality="text", embedding=own_embedding.vector, embedding_provider="development-hash", embedding_model="development-hash-v1", embedding_dimension=1536, semantic_search_status="DEVELOPMENT_FALLBACK", lexical_search_status="READY"),
        DocumentChunk(workspace_id=foreign_workspace.id, source_id=foreign_source.id, chunk_index=0, content="operating margin secret", modality="text", embedding=foreign_embedding.vector, embedding_provider="development-hash", embedding_model="development-hash-v1", embedding_dimension=1536, semantic_search_status="DEVELOPMENT_FALLBACK", lexical_search_status="READY"),
    ])
    await db_session.flush()
    response = await HybridRetriever.search(test_workspace.id, "operating margin", db_session)
    assert response.mode == "DEVELOPMENT_FALLBACK"
    assert response.backend == "SQLITE_DEVELOPMENT_FALLBACK"
    assert {result.source_id for result in response.results} == {str(own_source.id)}
    restricted = await HybridRetriever.search(test_workspace.id, "operating margin", db_session, source_ids=[foreign_source.id])
    assert restricted.results == []
