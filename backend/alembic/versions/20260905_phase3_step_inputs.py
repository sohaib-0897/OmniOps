"""Persist validated plan-step inputs."""
from alembic import op
import sqlalchemy as sa

revision = "20260905_phase3_inputs"
down_revision = "20260904_phase3"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("agent_plan_steps", sa.Column("inputs", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))

def downgrade():
    op.drop_column("agent_plan_steps", "inputs")
