"""Commit-safe event replay and persisted investigation budgets."""

from alembic import op
import sqlalchemy as sa


revision = "20260912_final_audit_closure"
down_revision = "20260911_phase6_sessions"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "investigation_sessions",
        sa.Column("max_steps", sa.Integer(), server_default="12", nullable=False),
    )
    op.add_column(
        "runtime_events",
        sa.Column("delivery_sequence", sa.BigInteger(), nullable=True),
    )
    op.create_unique_constraint(
        "uq_runtime_event_delivery_sequence",
        "runtime_events",
        ["investigation_id", "delivery_sequence"],
    )


def downgrade():
    op.drop_constraint(
        "uq_runtime_event_delivery_sequence",
        "runtime_events",
        type_="unique",
    )
    op.drop_column("runtime_events", "delivery_sequence")
    op.drop_column("investigation_sessions", "max_steps")
