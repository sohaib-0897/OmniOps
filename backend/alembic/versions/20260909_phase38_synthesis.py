"""Stable final synthesis identity."""
from alembic import op
import sqlalchemy as sa
revision = "20260909_phase38_synth"
down_revision = "20260908_phase38_contra_id"
branch_labels = None
depends_on = None
def upgrade():
    op.add_column("investigation_sessions", sa.Column("synthesis_identity", sa.String(128), nullable=True))
    op.create_index("ix_investigation_sessions_synthesis_identity", "investigation_sessions", ["synthesis_identity"], unique=True)
def downgrade():
    op.drop_index("ix_investigation_sessions_synthesis_identity", table_name="investigation_sessions")
    op.drop_column("investigation_sessions", "synthesis_identity")
