import asyncio
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

backend_dir = Path(__file__).resolve().parents[1] / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.models.document import DocumentChunk, SourceDocument
from app.models.user import User, Workspace
from app.rag.embeddings import EmbeddingProvider, EmbeddingState
from app.rag.hybrid_search import HybridRetriever
from evals.retrieval_metrics import ndcg_at_k, precision_at_k, recall_at_k, reciprocal_rank


async def run():
    database_url = os.getenv("RETRIEVAL_EVAL_DATABASE_URL")
    if not database_url:
        print("Retrieval evaluation: NOT_RUN (RETRIEVAL_EVAL_DATABASE_URL is not configured)")
        return 2
    migration_env = {**os.environ, "DATABASE_URL": database_url, "ENVIRONMENT": "test"}
    migration = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        cwd=backend_dir, env=migration_env, capture_output=True, text=True, timeout=120,
    )
    if migration.returncode != 0:
        print("Retrieval evaluation: NOT_RUN (database migration failed)")
        print(migration.stdout + migration.stderr)
        return 2
    dataset = json.loads((Path(__file__).parent / "retrieval_dataset.json").read_text())
    engine = create_async_engine(database_url)
    async with AsyncSession(engine, expire_on_commit=False) as session:
        transaction = await session.begin()
        try:
            user = User(email=f"retrieval-eval-{uuid.uuid4()}@example.com", hashed_password="evaluation-only", full_name="Retrieval Evaluation")
            session.add(user)
            await session.flush()
            primary = Workspace(name="Retrieval Evaluation", created_by=user.id)
            foreign = Workspace(name="Retrieval Foreign Tenant", created_by=user.id)
            session.add_all([primary, foreign])
            await session.flush()
            for item in dataset["documents"]:
                workspace = foreign if item.get("tenant") == "foreign" else primary
                embedding = await EmbeddingProvider.generate(item["content"])
                if embedding.state != EmbeddingState.READY:
                    print(f"Retrieval evaluation: NOT_RUN ({embedding.state.value})")
                    return 2
                source = SourceDocument(workspace_id=workspace.id, file_name=f'{item["id"]}.txt', storage_path="evaluation", mime_type="text/plain", byte_size=len(item["content"]), sha256_hash=uuid.uuid4().hex, modality="text", processing_status="ready")
                session.add(source)
                await session.flush()
                session.add(DocumentChunk(
                    workspace_id=workspace.id, source_id=source.id, chunk_index=0,
                    content=item["content"], modality="text", extraction_method="labeled-evaluation-dataset",
                    embedding=embedding.vector, embedding_provider=embedding.provider,
                    embedding_model=embedding.model, embedding_dimension=embedding.dimension,
                    embedding_generated_at=embedding.generated_at, semantic_search_status="READY", lexical_search_status="READY",
                ))
            await session.flush()
            scores = []
            for case in dataset["queries"]:
                response = await HybridRetriever.search(primary.id, case["query"], session, top_k=3)
                retrieved = [result.source_name.removesuffix(".txt") for result in response.results]
                scores.append({
                    "id": case["id"], "precision_at_3": precision_at_k(retrieved, case["relevant"], 3),
                    "recall_at_3": recall_at_k(retrieved, case["relevant"], 3),
                    "mrr": reciprocal_rank(retrieved, case["relevant"]),
                    "ndcg_at_3": ndcg_at_k(retrieved, case["relevant"], 3),
                })
            print(json.dumps({"scenarios": scores, "means": {key: sum(row[key] for row in scores) / len(scores) for key in ("precision_at_3", "recall_at_3", "mrr", "ndcg_at_3")}}, indent=2))
            return 0
        finally:
            await transaction.rollback()
            await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
