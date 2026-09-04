"""Phase 3.5 recovery, idempotency, and contradiction persistence."""
from alembic import op
import sqlalchemy as sa

revision = "20260906_phase35_runtime"
down_revision = "20260905_phase3_inputs"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("investigation_sessions", sa.Column("idempotency_key", sa.String(128), nullable=True))
    op.add_column("investigation_sessions", sa.Column("worker_id", sa.String(128), nullable=True))
    op.add_column("investigation_sessions", sa.Column("lease_acquired_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("investigation_sessions", sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_investigation_sessions_idempotency_key", "investigation_sessions", ["idempotency_key"], unique=True)
    op.add_column("agent_tool_attempts", sa.Column("attempt_no", sa.Integer(), nullable=False, server_default="1"))
    op.create_table(
        "contradiction_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("investigation_id", sa.Uuid(), sa.ForeignKey("investigation_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("topic", sa.String(255), nullable=False),
        sa.Column("evidence_a_id", sa.Uuid(), sa.ForeignKey("evidence_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("evidence_b_id", sa.Uuid(), sa.ForeignKey("evidence_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("conflict_type", sa.String(80), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="UNRESOLVED"),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_contradiction_records_investigation_id", "contradiction_records", ["investigation_id"])


def downgrade():
    op.drop_index("ix_contradiction_records_investigation_id", table_name="contradiction_records")
    op.drop_table("contradiction_records")
    op.drop_column("agent_tool_attempts", "attempt_no")
    op.drop_index("ix_investigation_sessions_idempotency_key", table_name="investigation_sessions")
    for name in ["lease_expires_at", "lease_acquired_at", "worker_id", "idempotency_key"]:
        op.drop_column("investigation_sessions", name)
