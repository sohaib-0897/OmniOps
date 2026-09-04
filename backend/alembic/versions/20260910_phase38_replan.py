"""Stable logical replan identity."""
from alembic import op
import sqlalchemy as sa
revision = "20260910_phase38_replan"
down_revision = "20260909_phase38_synth"
branch_labels = None
depends_on = None
def upgrade():
    op.add_column("agent_plans", sa.Column("logical_identity", sa.String(128), nullable=True))
    op.create_index("ix_agent_plans_logical_identity", "agent_plans", ["logical_identity"], unique=True)
def downgrade():
    op.drop_index("ix_agent_plans_logical_identity", table_name="agent_plans")
    op.drop_column("agent_plans", "logical_identity")
