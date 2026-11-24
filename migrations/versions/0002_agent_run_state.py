"""Add persisted workflow state and human-review metadata."""
from alembic import op
import sqlalchemy as sa

revision = "0002_agent_run_state"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("agent_runs", sa.Column("idempotency_key", sa.String(128), nullable=True))
    op.create_unique_constraint("uq_agent_runs_idempotency_key", "agent_runs", ["idempotency_key"])
    op.add_column("agent_runs", sa.Column("state_json", sa.JSON(), nullable=False, server_default="{}"))
    op.add_column("agent_runs", sa.Column("result_json", sa.JSON(), nullable=False, server_default="{}"))
    op.add_column("agent_runs", sa.Column("reviewer", sa.String(255), nullable=True))
    op.add_column("agent_runs", sa.Column("review_note", sa.Text(), nullable=True))
    op.add_column("agent_runs", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_agent_runs_status", "agent_runs", ["status"])

def downgrade():
    op.drop_index("ix_agent_runs_status", table_name="agent_runs")
    op.drop_constraint("uq_agent_runs_idempotency_key", "agent_runs", type_="unique")
    for name in ("updated_at", "review_note", "reviewer", "result_json", "state_json", "idempotency_key"):
        op.drop_column("agent_runs", name)
