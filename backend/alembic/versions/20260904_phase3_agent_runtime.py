"""Durable Phase 3 agent runtime persistence."""
from alembic import op
import sqlalchemy as sa

revision = "20260904_phase3"
down_revision = "20260903_phase2"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("investigation_sessions", sa.Column("current_state", sa.String(30), nullable=False, server_default="created"))
    op.add_column("investigation_sessions", sa.Column("plan_version", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("investigation_sessions", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("investigation_sessions", sa.Column("failure_code", sa.String(80), nullable=True))
    op.add_column("investigation_sessions", sa.Column("failure_message", sa.Text(), nullable=True))
    op.add_column("investigation_sessions", sa.Column("cancellation_requested", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index("ix_investigation_sessions_current_state", "investigation_sessions", ["current_state"])
    common = [sa.Column("id", sa.Uuid(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False)]
    op.create_table("agent_plans", *common, sa.Column("investigation_id", sa.Uuid(), sa.ForeignKey("investigation_sessions.id", ondelete="CASCADE"), nullable=False), sa.Column("version", sa.Integer(), nullable=False), sa.Column("generated_by", sa.String(50), nullable=False), sa.Column("reason", sa.Text(), nullable=True), sa.PrimaryKeyConstraint("id"))
    op.create_index("ix_agent_plans_investigation_id", "agent_plans", ["investigation_id"])
    op.create_table("agent_plan_steps", *common, sa.Column("plan_id", sa.Uuid(), sa.ForeignKey("agent_plans.id", ondelete="CASCADE"), nullable=False), sa.Column("sequence", sa.Integer(), nullable=False), sa.Column("step_key", sa.String(100), nullable=False), sa.Column("objective", sa.Text(), nullable=False), sa.Column("tool_name", sa.String(100), nullable=False), sa.Column("dependencies", sa.JSON(), nullable=False), sa.Column("expected_evidence_type", sa.String(50), nullable=True), sa.Column("completion_criteria", sa.JSON(), nullable=False), sa.Column("status", sa.String(30), nullable=False), sa.Column("attempts", sa.Integer(), nullable=False), sa.Column("result_reference", sa.String(255), nullable=True), sa.Column("failure_reference", sa.String(255), nullable=True), sa.PrimaryKeyConstraint("id"))
    op.create_index("ix_agent_plan_steps_plan_id", "agent_plan_steps", ["plan_id"])
    op.create_table("agent_tool_attempts", *common, sa.Column("step_id", sa.Uuid(), sa.ForeignKey("agent_plan_steps.id", ondelete="CASCADE"), nullable=False), sa.Column("tool_name", sa.String(100), nullable=False), sa.Column("tool_version", sa.String(50), nullable=True), sa.Column("validated_input", sa.JSON(), nullable=False), sa.Column("started_at", sa.DateTime(timezone=True), nullable=False), sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True), sa.Column("status", sa.String(30), nullable=False), sa.Column("output_reference", sa.String(255), nullable=True), sa.Column("error_classification", sa.String(80), nullable=True), sa.Column("retryable", sa.Boolean(), nullable=False), sa.Column("duration_ms", sa.Integer(), nullable=True), sa.PrimaryKeyConstraint("id"))
    op.create_index("ix_agent_tool_attempts_step_id", "agent_tool_attempts", ["step_id"])
    op.create_table("agent_observations", *common, sa.Column("investigation_id", sa.Uuid(), sa.ForeignKey("investigation_sessions.id", ondelete="CASCADE"), nullable=False), sa.Column("step_id", sa.Uuid(), sa.ForeignKey("agent_plan_steps.id", ondelete="SET NULL"), nullable=True), sa.Column("attempt_id", sa.Uuid(), sa.ForeignKey("agent_tool_attempts.id", ondelete="SET NULL"), nullable=True), sa.Column("classification", sa.String(50), nullable=False), sa.Column("success", sa.Boolean(), nullable=False), sa.Column("summary", sa.Text(), nullable=False), sa.Column("payload", sa.JSON(), nullable=False), sa.PrimaryKeyConstraint("id"))
    op.create_index("ix_agent_observations_investigation_id", "agent_observations", ["investigation_id"]); op.create_index("ix_agent_observations_step_id", "agent_observations", ["step_id"])
    op.create_table("agent_transitions", *common, sa.Column("investigation_id", sa.Uuid(), sa.ForeignKey("investigation_sessions.id", ondelete="CASCADE"), nullable=False), sa.Column("from_state", sa.String(30), nullable=True), sa.Column("to_state", sa.String(30), nullable=False), sa.Column("reason", sa.Text(), nullable=True), sa.Column("metadata_json", sa.JSON(), nullable=False), sa.PrimaryKeyConstraint("id"))
    op.create_index("ix_agent_transitions_investigation_id", "agent_transitions", ["investigation_id"])

def downgrade():
    op.drop_index("ix_agent_transitions_investigation_id", table_name="agent_transitions"); op.drop_table("agent_transitions")
    op.drop_index("ix_agent_observations_step_id", table_name="agent_observations"); op.drop_index("ix_agent_observations_investigation_id", table_name="agent_observations"); op.drop_table("agent_observations")
    op.drop_index("ix_agent_tool_attempts_step_id", table_name="agent_tool_attempts"); op.drop_table("agent_tool_attempts")
    op.drop_index("ix_agent_plan_steps_plan_id", table_name="agent_plan_steps"); op.drop_table("agent_plan_steps")
    op.drop_index("ix_agent_plans_investigation_id", table_name="agent_plans"); op.drop_table("agent_plans")
    op.drop_index("ix_investigation_sessions_current_state", table_name="investigation_sessions")
    for name in ["cancellation_requested", "failure_message", "failure_code", "started_at", "plan_version", "current_state"]: op.drop_column("investigation_sessions", name)
