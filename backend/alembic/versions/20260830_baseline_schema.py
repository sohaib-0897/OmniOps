"""Baseline schema before Phase 1.

Revision ID: 20260830_baseline
"""
from alembic import op
import sqlalchemy as sa
from app.models.base import GUID

revision = "20260830_baseline"
down_revision = None
branch_labels = None
depends_on = None

def timestamps():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]

def upgrade():
    op.create_table("users", sa.Column("id", GUID(), primary_key=True), sa.Column("email", sa.String(255), nullable=False, unique=True), sa.Column("hashed_password", sa.String(255), nullable=False), sa.Column("full_name", sa.String(255), nullable=False), sa.Column("is_active", sa.Boolean(), nullable=False), *timestamps())
    op.create_table("workspaces", sa.Column("id", GUID(), primary_key=True), sa.Column("name", sa.String(255), nullable=False), sa.Column("description", sa.Text()), sa.Column("created_by", GUID(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False), *timestamps())
    op.create_table("workspace_memberships", sa.Column("id", GUID(), primary_key=True), sa.Column("workspace_id", GUID(), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False), sa.Column("user_id", GUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False), sa.Column("role", sa.String(50), nullable=False), *timestamps(), sa.UniqueConstraint("workspace_id", "user_id", name="uq_workspace_user_membership"))
    op.create_table("source_documents", sa.Column("id", GUID(), primary_key=True), sa.Column("workspace_id", GUID(), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False), sa.Column("file_name", sa.String(255), nullable=False), sa.Column("storage_path", sa.String(1024), nullable=False), sa.Column("mime_type", sa.String(100), nullable=False), sa.Column("byte_size", sa.BigInteger(), nullable=False), sa.Column("sha256_hash", sa.String(64), nullable=False), sa.Column("modality", sa.String(50), nullable=False), sa.Column("processing_status", sa.String(50), nullable=False), sa.Column("error_message", sa.Text()), sa.Column("doc_metadata", sa.JSON(), nullable=False), *timestamps(), sa.UniqueConstraint("workspace_id", "sha256_hash", name="uq_workspace_source_hash"))
    op.create_table("document_chunks", sa.Column("id", GUID(), primary_key=True), sa.Column("workspace_id", GUID(), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False), sa.Column("source_id", GUID(), sa.ForeignKey("source_documents.id", ondelete="CASCADE"), nullable=False), sa.Column("chunk_index", sa.Integer(), nullable=False), sa.Column("content", sa.Text(), nullable=False), sa.Column("modality", sa.String(50), nullable=False), sa.Column("page_number", sa.Integer()), sa.Column("cell_range", sa.String(50)), sa.Column("audio_start_ms", sa.Integer()), sa.Column("audio_end_ms", sa.Integer()), sa.Column("chunk_metadata", sa.JSON(), nullable=False), sa.Column("embedding", sa.JSON()), *timestamps())
    op.create_table("tabular_datasets", sa.Column("id", GUID(), primary_key=True), sa.Column("workspace_id", GUID(), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False), sa.Column("source_id", GUID(), sa.ForeignKey("source_documents.id", ondelete="CASCADE"), nullable=False), sa.Column("table_name", sa.String(255), nullable=False), sa.Column("row_count", sa.BigInteger(), nullable=False), sa.Column("column_count", sa.Integer(), nullable=False), sa.Column("schema_definition", sa.JSON(), nullable=False), sa.Column("parquet_storage_path", sa.String(1024), nullable=False), *timestamps(), sa.UniqueConstraint("workspace_id", "table_name", name="uq_workspace_table_name"))
    op.create_table("investigation_sessions", sa.Column("id", GUID(), primary_key=True), sa.Column("workspace_id", GUID(), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False), sa.Column("user_id", GUID(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False), sa.Column("objective", sa.Text(), nullable=False), sa.Column("status", sa.String(50), nullable=False), sa.Column("final_response", sa.JSON()), sa.Column("token_usage", sa.JSON(), nullable=False), sa.Column("error_message", sa.Text()), sa.Column("completed_at", sa.DateTime(timezone=True)), *timestamps())
    op.create_table("agent_steps", sa.Column("id", GUID(), primary_key=True), sa.Column("session_id", GUID(), sa.ForeignKey("investigation_sessions.id", ondelete="CASCADE"), nullable=False), sa.Column("step_number", sa.Integer(), nullable=False), sa.Column("step_type", sa.String(50), nullable=False), sa.Column("user_activity_summary", sa.String(500), nullable=False), sa.Column("tool_name", sa.String(100)), sa.Column("tool_input", sa.JSON()), sa.Column("tool_output", sa.JSON()), sa.Column("duration_ms", sa.Integer(), nullable=False), *timestamps())
    op.create_table("evidence_items", sa.Column("id", GUID(), primary_key=True), sa.Column("session_id", GUID(), sa.ForeignKey("investigation_sessions.id", ondelete="CASCADE"), nullable=False), sa.Column("source_id", GUID(), sa.ForeignKey("source_documents.id", ondelete="CASCADE"), nullable=False), sa.Column("chunk_id", GUID(), sa.ForeignKey("document_chunks.id", ondelete="SET NULL")), sa.Column("page_number", sa.Integer()), sa.Column("cell_range", sa.String(50)), sa.Column("audio_start_ms", sa.Integer()), sa.Column("audio_end_ms", sa.Integer()), sa.Column("exact_quote", sa.Text()), sa.Column("coordinates", sa.JSON()), sa.Column("confidence_score", sa.Float(), nullable=False), *timestamps())
    op.create_table("calculation_records", sa.Column("id", GUID(), primary_key=True), sa.Column("session_id", GUID(), sa.ForeignKey("investigation_sessions.id", ondelete="CASCADE"), nullable=False), sa.Column("calculation_type", sa.String(50), nullable=False), sa.Column("formula_or_code", sa.Text(), nullable=False), sa.Column("input_values", sa.JSON(), nullable=False), sa.Column("computed_output", sa.JSON(), nullable=False), sa.Column("reproducibility_hash", sa.String(64), nullable=False), *timestamps())
    op.create_table("verified_claims", sa.Column("id", GUID(), primary_key=True), sa.Column("session_id", GUID(), sa.ForeignKey("investigation_sessions.id", ondelete="CASCADE"), nullable=False), sa.Column("claim_id_code", sa.String(50), nullable=False), sa.Column("statement", sa.Text(), nullable=False), sa.Column("epistemic_type", sa.String(50), nullable=False), sa.Column("confidence_score", sa.Float(), nullable=False), sa.Column("calculation_id", GUID(), sa.ForeignKey("calculation_records.id", ondelete="SET NULL")), sa.Column("supporting_citations", sa.JSON(), nullable=False), sa.Column("supporting_claims", sa.JSON(), nullable=False), *timestamps())
    for table, columns in {"workspace_memberships": ["workspace_id", "user_id"], "source_documents": ["workspace_id"], "document_chunks": ["workspace_id", "source_id"], "tabular_datasets": ["workspace_id", "source_id"], "investigation_sessions": ["workspace_id", "user_id"], "agent_steps": ["session_id"], "evidence_items": ["session_id", "source_id"], "calculation_records": ["session_id"], "verified_claims": ["session_id"]}.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])

def downgrade():
    for table in ["verified_claims", "calculation_records", "evidence_items", "agent_steps", "investigation_sessions", "tabular_datasets", "document_chunks", "source_documents", "workspace_memberships", "workspaces", "users"]:
        op.drop_table(table)
