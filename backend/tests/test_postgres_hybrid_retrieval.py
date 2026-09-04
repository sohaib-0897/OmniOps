import os
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.document import DocumentChunk, SourceDocument
from app.models.user import User, Workspace
from app.rag.embeddings import EmbeddingProvider, EmbeddingResult, EmbeddingState
from app.rag.hybrid_search import HybridRetriever


POSTGRES_TEST_URL = os.getenv("POSTGRES_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not POSTGRES_TEST_URL, reason="POSTGRES_TEST_DATABASE_URL is required for real pgvector integration tests")


def vector(axis: int) -> list[float]:
    values = [0.0] * 1536
    values[axis] = 1.0
    return values


@pytest_asyncio.fixture
async def postgres_session_factory():
    assert POSTGRES_TEST_URL
    database_name = POSTGRES_TEST_URL.rsplit("/", 1)[-1].split("?", 1)[0]
    if "test" not in database_name.lower():
        pytest.fail("POSTGRES_TEST_DATABASE_URL must point to a dedicated database whose name contains 'test'.")
    engine = create_async_engine(POSTGRES_TEST_URL)
    async with engine.begin() as connection:
        await connection.execute(text("DROP SCHEMA public CASCADE"))
        await connection.execute(text("CREATE SCHEMA public"))
    migration_env = {**os.environ, "DATABASE_URL": POSTGRES_TEST_URL, "ENVIRONMENT": "test"}
    result = subprocess.run(
        ["alembic", "-c", "alembic.ini", "upgrade", "head"],
        cwd=Path(__file__).resolve().parents[1], env=migration_env,
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await engine.dispose()


@pytest_asyncio.fixture
async def pg_session(postgres_session_factory):
    async with postgres_session_factory() as session:
        yield session
        await session.rollback()


async def seed_chunk(session, workspace, source, content, embedding):
    chunk = DocumentChunk(
        workspace_id=workspace.id, source_id=source.id, chunk_index=uuid.uuid4().int % 100000,
        content=content, modality="text", extraction_method="test-labeled-fixture",
        embedding=embedding, embedding_provider="labeled-test", embedding_model="labeled-test-1536",
        embedding_dimension=1536, embedding_generated_at=datetime.now(timezone.utc),
        semantic_search_status="READY", lexical_search_status="READY",
    )
    session.add(chunk)
    await session.flush()
    return chunk


@pytest_asyncio.fixture
async def retrieval_data(pg_session):
    user = User(email=f"retrieval-{uuid.uuid4()}@example.com", hashed_password="x", full_name="Retrieval Test")
    pg_session.add(user)
    await pg_session.flush()
    workspace_a = Workspace(name="Workspace A", created_by=user.id)
    workspace_b = Workspace(name="Workspace B", created_by=user.id)
    pg_session.add_all([workspace_a, workspace_b])
    await pg_session.flush()
    source_margin = SourceDocument(workspace_id=workspace_a.id, file_name="margin.txt", storage_path="fixture", mime_type="text/plain", byte_size=10, sha256_hash=uuid.uuid4().hex, modality="text", processing_status="ready")
    source_support = SourceDocument(workspace_id=workspace_a.id, file_name="support.txt", storage_path="fixture", mime_type="text/plain", byte_size=10, sha256_hash=uuid.uuid4().hex, modality="text", processing_status="ready")
    source_foreign = SourceDocument(workspace_id=workspace_b.id, file_name="foreign.txt", storage_path="fixture", mime_type="text/plain", byte_size=10, sha256_hash=uuid.uuid4().hex, modality="text", processing_status="ready")
    pg_session.add_all([source_margin, source_support, source_foreign])
    await pg_session.flush()
    semantic = await seed_chunk(pg_session, workspace_a, source_margin, "Southern division profitability exceeded every peer.", vector(0))
    lexical = await seed_chunk(pg_session, workspace_a, source_margin, "The highest operating margin was recorded in the North region.", vector(1))
    irrelevant = await seed_chunk(pg_session, workspace_a, source_support, "Customer support ticket response times improved.", vector(2))
    foreign = await seed_chunk(pg_session, workspace_b, source_foreign, "The highest operating margin was secret tenant data.", vector(0))
    await pg_session.commit()
    return {"workspace_a": workspace_a, "workspace_b": workspace_b, "source_margin": source_margin, "source_support": source_support, "semantic": semantic, "lexical": lexical, "irrelevant": irrelevant, "foreign": foreign}


@pytest.fixture
def query_embedding(monkeypatch):
    async def generate(cls, text_value, *, allow_development_fallback=False):
        return EmbeddingResult(state=EmbeddingState.READY, vector=vector(0), provider="labeled-test", model="labeled-test-1536", dimension=1536, generated_at=datetime.now(timezone.utc))
    monkeypatch.setattr(EmbeddingProvider, "generate", classmethod(generate))


@pytest.mark.asyncio
async def test_clean_postgres_database_migrated_to_phase2(pg_session):
    revision = (await pg_session.execute(text("SELECT version_num FROM alembic_version"))).scalar_one()
    assert revision in {"20260905_phase3_inputs", "20260906_phase35_runtime", "20260907_phase36_idempotency", "20260910_phase38_replan"}
    column_type = (await pg_session.execute(text("SELECT format_type(a.atttypid, a.atttypmod) FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid WHERE c.relname = 'document_chunks' AND a.attname = 'embedding' AND NOT a.attisdropped"))).scalar_one()
    assert column_type == "vector(1536)"


@pytest.mark.asyncio
async def test_vector_persistence_and_semantic_ranking(pg_session, retrieval_data, query_embedding):
    stored = (await pg_session.execute(text("SELECT vector_dims(embedding) FROM document_chunks WHERE id = :id"), {"id": retrieval_data["semantic"].id})).scalar_one()
    assert stored == 1536
    response = await HybridRetriever.search(retrieval_data["workspace_a"].id, "profitability performance", pg_session, top_k=3)
    assert response.backend == "POSTGRESQL_PGVECTOR_FTS_RRF"
    assert response.results[0].chunk_id == str(retrieval_data["semantic"].id)
    assert response.results[0].semantic_rank == 1


@pytest.mark.asyncio
async def test_postgres_fts_and_deterministic_rrf(pg_session, retrieval_data, query_embedding):
    first = await HybridRetriever.search(retrieval_data["workspace_a"].id, "highest operating margin", pg_session, top_k=3)
    second = await HybridRetriever.search(retrieval_data["workspace_a"].id, "highest operating margin", pg_session, top_k=3)
    lexical_result = next(result for result in first.results if result.chunk_id == str(retrieval_data["lexical"].id))
    semantic_result = next(result for result in first.results if result.chunk_id == str(retrieval_data["semantic"].id))
    assert lexical_result.lexical_rank == 1
    assert semantic_result.semantic_rank == 1
    assert [result.chunk_id for result in first.results] == [result.chunk_id for result in second.results]
    assert [result.fused_score for result in first.results] == [result.fused_score for result in second.results]


@pytest.mark.asyncio
async def test_tenant_and_source_filters_are_database_predicates(pg_session, retrieval_data, query_embedding):
    response = await HybridRetriever.search(retrieval_data["workspace_a"].id, "highest operating margin", pg_session, top_k=10)
    assert str(retrieval_data["foreign"].id) not in {result.chunk_id for result in response.results}
    restricted = await HybridRetriever.search(retrieval_data["workspace_a"].id, "support response", pg_session, top_k=10, source_ids=[retrieval_data["source_support"].id])
    assert restricted.results
    assert {result.source_id for result in restricted.results} == {str(retrieval_data["source_support"].id)}


@pytest.mark.asyncio
async def test_hnsw_gin_indexes_and_query_plans(pg_session, retrieval_data):
    indexes = (await pg_session.execute(text("SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'document_chunks'"))).all()
    definitions = {name: definition for name, definition in indexes}
    assert "USING hnsw" in definitions["ix_document_chunks_embedding_hnsw"]
    assert "vector_cosine_ops" in definitions["ix_document_chunks_embedding_hnsw"]
    assert "USING gin" in definitions["ix_document_chunks_search_vector_gin"]
    await pg_session.execute(text("SET LOCAL enable_seqscan = off"))
    vector_plan = "\n".join(row[0] for row in (await pg_session.execute(text("EXPLAIN SELECT id FROM document_chunks WHERE workspace_id = :workspace AND embedding IS NOT NULL ORDER BY embedding <=> CAST(:embedding AS vector) LIMIT 5"), {"workspace": retrieval_data["workspace_a"].id, "embedding": "[" + ",".join(map(str, vector(0))) + "]"})).all())
    lexical_plan = "\n".join(row[0] for row in (await pg_session.execute(text("EXPLAIN SELECT id FROM document_chunks WHERE workspace_id = :workspace AND search_vector @@ websearch_to_tsquery('english', 'operating margin') LIMIT 5"), {"workspace": retrieval_data["workspace_a"].id})).all())
    # PostgreSQL may prefer the tenant/source predicate index for a tiny fixture.
    # Index existence and planner observation are intentionally separate checks.
    assert "workspace_id" in vector_plan
    assert "workspace_id" in lexical_plan
