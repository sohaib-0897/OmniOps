"""Phase 3.6 logical output/event idempotency and worker claiming support."""
from alembic import op
import sqlalchemy as sa

revision = "20260907_phase36_idempotency"
down_revision = "20260906_phase35_runtime"
branch_labels = None
depends_on = None

def upgrade():
    for table in ["evidence_items", "calculation_records", "verified_claims"]:
        op.add_column(table, sa.Column("logical_identity", sa.String(128), nullable=True))
        op.create_index(f"ix_{table}_logical_identity", table, ["session_id", "logical_identity"], unique=True)
    op.create_table(
        "runtime_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("investigation_id", sa.Uuid(), sa.ForeignKey("investigation_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=True),
        sa.Column("logical_identity", sa.String(128), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("logical_identity"),
    )
    op.create_index("ix_runtime_events_investigation_id", "runtime_events", ["investigation_id"])

def downgrade():
    op.drop_index("ix_runtime_events_investigation_id", table_name="runtime_events")
    op.drop_table("runtime_events")
    for table in ["verified_claims", "calculation_records", "evidence_items"]:
        op.drop_index(f"ix_{table}_logical_identity", table_name=table)
        op.drop_column(table, "logical_identity")
