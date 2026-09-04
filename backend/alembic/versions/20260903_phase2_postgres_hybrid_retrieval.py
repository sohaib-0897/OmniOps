"""PostgreSQL-native pgvector and full-text hybrid retrieval.

Revision ID: 20260903_phase2
"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision = "20260903_phase2"
down_revision = "20260902_phase1"
branch_labels = None
depends_on = None

VECTOR_DIMENSION = 1536

def upgrade():
    if op.get_bind().dialect.name != "postgresql":
        raise RuntimeError("Phase 2 retrieval migration requires PostgreSQL with pgvector.")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.drop_column("document_chunks", "embedding")
    op.add_column("document_chunks", sa.Column("embedding", Vector(VECTOR_DIMENSION), nullable=True))
    op.add_column("document_chunks", sa.Column("embedding_provider", sa.String(50), nullable=True))
    op.add_column("document_chunks", sa.Column("embedding_model", sa.String(100), nullable=True))
    op.add_column("document_chunks", sa.Column("embedding_dimension", sa.Integer(), nullable=True))
    op.add_column("document_chunks", sa.Column("embedding_generated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("document_chunks", sa.Column("semantic_search_status", sa.String(50), nullable=False, server_default="PENDING"))
    op.add_column("document_chunks", sa.Column("lexical_search_status", sa.String(50), nullable=False, server_default="READY"))
    op.execute("ALTER TABLE document_chunks ADD COLUMN search_vector tsvector GENERATED ALWAYS AS (to_tsvector('english', coalesce(content, ''))) STORED")
    op.execute("CREATE INDEX ix_document_chunks_embedding_hnsw ON document_chunks USING hnsw (embedding vector_cosine_ops) WHERE embedding IS NOT NULL")
    op.execute("CREATE INDEX ix_document_chunks_search_vector_gin ON document_chunks USING gin (search_vector)")
    op.create_index("ix_document_chunks_workspace_source", "document_chunks", ["workspace_id", "source_id"])
    op.create_check_constraint("ck_document_chunks_embedding_dimension", "document_chunks", f"embedding IS NULL OR embedding_dimension = {VECTOR_DIMENSION}")

def downgrade():
    if op.get_bind().dialect.name != "postgresql":
        raise RuntimeError("Phase 2 retrieval migration requires PostgreSQL with pgvector.")
    op.drop_constraint("ck_document_chunks_embedding_dimension", "document_chunks", type_="check")
    op.drop_index("ix_document_chunks_workspace_source", table_name="document_chunks")
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_search_vector_gin")
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding_hnsw")
    op.drop_column("document_chunks", "search_vector")
    for column in ["lexical_search_status", "semantic_search_status", "embedding_generated_at", "embedding_dimension", "embedding_model", "embedding_provider"]:
        op.drop_column("document_chunks", column)
    op.drop_column("document_chunks", "embedding")
    op.add_column("document_chunks", sa.Column("embedding", sa.JSON(), nullable=True))
