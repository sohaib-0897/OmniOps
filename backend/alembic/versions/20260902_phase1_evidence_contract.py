"""Phase 1 evidence contract.

Revision ID: 20260902_phase1
"""
from alembic import op
import sqlalchemy as sa
from app.models.base import GUID

revision = "20260902_phase1"
down_revision = "20260830_baseline"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("document_chunks", sa.Column("extraction_method", sa.String(100), nullable=False, server_default="unknown"))
    op.add_column("calculation_records", sa.Column("evidence_ids", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("calculation_records", sa.Column("source_ids", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("verified_claims", sa.Column("calculation_ids", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("verified_claims", sa.Column("verification_status", sa.String(30), nullable=False, server_default="PROPOSED"))
    op.add_column("verified_claims", sa.Column("verification_errors", sa.JSON(), nullable=False, server_default="[]"))
    op.alter_column("verified_claims", "confidence_score", nullable=True)
    op.alter_column("evidence_items", "confidence_score", nullable=True)
    op.create_table("inference_records", sa.Column("id", GUID(), primary_key=True), sa.Column("session_id", GUID(), sa.ForeignKey("investigation_sessions.id", ondelete="CASCADE"), nullable=False), sa.Column("inference_id_code", sa.String(50), nullable=False), sa.Column("statement", sa.Text(), nullable=False), sa.Column("supporting_claim_ids", sa.JSON(), nullable=False), sa.Column("verification_status", sa.String(30), nullable=False), sa.Column("verification_errors", sa.JSON(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("recommendation_records", sa.Column("id", GUID(), primary_key=True), sa.Column("session_id", GUID(), sa.ForeignKey("investigation_sessions.id", ondelete="CASCADE"), nullable=False), sa.Column("recommendation_id_code", sa.String(50), nullable=False), sa.Column("statement", sa.Text(), nullable=False), sa.Column("priority", sa.String(30), nullable=False), sa.Column("supporting_claim_ids", sa.JSON(), nullable=False), sa.Column("supporting_inference_ids", sa.JSON(), nullable=False), sa.Column("verification_status", sa.String(30), nullable=False), sa.Column("verification_errors", sa.JSON(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))

def downgrade():
    op.drop_table("recommendation_records")
    op.drop_table("inference_records")
    for table, column in [("verified_claims", "verification_errors"), ("verified_claims", "verification_status"), ("verified_claims", "calculation_ids"), ("calculation_records", "source_ids"), ("calculation_records", "evidence_ids"), ("document_chunks", "extraction_method")]:
        op.drop_column(table, column)
