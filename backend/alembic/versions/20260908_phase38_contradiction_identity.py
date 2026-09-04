"""Add deterministic contradiction identity."""
from alembic import op
import sqlalchemy as sa
import uuid

revision = "20260908_phase38_contra_id"
down_revision = "20260907_phase36_idempotency"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("contradiction_records", sa.Column("logical_identity", sa.String(128), nullable=True))
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, investigation_id, topic, evidence_a_id, evidence_b_id FROM contradiction_records")).fetchall()
    import hashlib
    for row in rows:
        a, b = sorted((str(row.evidence_a_id), str(row.evidence_b_id)))
        ident = hashlib.sha256(f"{row.investigation_id}:{row.topic.strip().lower()}:{a}:{b}".encode()).hexdigest()
        conn.execute(sa.text("UPDATE contradiction_records SET logical_identity=:i WHERE id=:id"), {"i": ident, "id": row.id})
    op.alter_column("contradiction_records", "logical_identity", nullable=False)
    op.create_unique_constraint("uq_contradiction_records_logical_identity", "contradiction_records", ["logical_identity"])

def downgrade():
    op.drop_constraint("uq_contradiction_records_logical_identity", "contradiction_records", type_="unique")
    op.drop_column("contradiction_records", "logical_identity")
