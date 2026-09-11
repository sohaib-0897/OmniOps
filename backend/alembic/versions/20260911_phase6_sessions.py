"""Phase 6 durable browser sessions and shared rate limits."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260911_phase6_sessions"
down_revision = "20260910_phase38_replan"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("user_sessions",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False), sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True), sa.Column("user_agent_hash", sa.String(64), nullable=True),
        sa.Column("rotation_counter", sa.Integer(), server_default="0", nullable=False), sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"), sa.PrimaryKeyConstraint("id"))
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"]); op.create_index("ix_user_sessions_expires_at", "user_sessions", ["expires_at"])
    op.create_table("refresh_tokens",
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False), sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True), sa.Column("replaced_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["user_sessions.id"], ondelete="CASCADE"), sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("token_hash"))
    op.create_index("ix_refresh_tokens_session_id", "refresh_tokens", ["session_id"]); op.create_index("ix_refresh_tokens_token_hash", "refresh_tokens", ["token_hash"], unique=True)
    op.create_table("rate_limit_buckets", sa.Column("key", sa.String(255), nullable=False), sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False), sa.Column("request_count", sa.Integer(), server_default="0", nullable=False), sa.PrimaryKeyConstraint("key"))

def downgrade():
    op.drop_table("rate_limit_buckets"); op.drop_index("ix_refresh_tokens_token_hash", table_name="refresh_tokens"); op.drop_index("ix_refresh_tokens_session_id", table_name="refresh_tokens"); op.drop_table("refresh_tokens"); op.drop_index("ix_user_sessions_expires_at", table_name="user_sessions"); op.drop_index("ix_user_sessions_user_id", table_name="user_sessions"); op.drop_table("user_sessions")
