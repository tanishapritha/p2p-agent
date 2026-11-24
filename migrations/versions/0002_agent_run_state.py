"""Add persisted workflow state and human-review metadata, if not already present."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0002_agent_run_state"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

def upgrade():
    inspector=inspect(op.get_bind())
    columns={col["name"] for col in inspector.get_columns("agent_runs")}
    if "idempotency_key" not in columns:
        op.add_column("agent_runs", sa.Column("idempotency_key", sa.String(128), nullable=True))
    inspector=inspect(op.get_bind())
    uniques={constraint.get("name") for constraint in inspector.get_unique_constraints("agent_runs")}
    if "uq_agent_runs_idempotency_key" not in uniques:
        op.create_unique_constraint("uq_agent_runs_idempotency_key", "agent_runs", ["idempotency_key"])
    columns={col["name"] for col in inspect(op.get_bind()).get_columns("agent_runs")}
    if "state_json" not in columns:
        op.add_column("agent_runs", sa.Column("state_json", sa.JSON(), nullable=False, server_default="{}"))
    if "result_json" not in columns:
        op.add_column("agent_runs", sa.Column("result_json", sa.JSON(), nullable=False, server_default="{}"))
    if "reviewer" not in columns:
        op.add_column("agent_runs", sa.Column("reviewer", sa.String(255), nullable=True))
    if "review_note" not in columns:
        op.add_column("agent_runs", sa.Column("review_note", sa.Text(), nullable=True))
    if "updated_at" not in columns:
        op.add_column("agent_runs", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
    indexes={index["name"] for index in inspect(op.get_bind()).get_indexes("agent_runs")}
    if "ix_agent_runs_status" not in indexes:
        op.create_index("ix_agent_runs_status", "agent_runs", ["status"])

def downgrade():
    inspector=inspect(op.get_bind())
    indexes={index["name"] for index in inspector.get_indexes("agent_runs")}
    if "ix_agent_runs_status" in indexes:
        op.drop_index("ix_agent_runs_status", table_name="agent_runs")
    uniques={constraint.get("name") for constraint in inspect(op.get_bind()).get_unique_constraints("agent_runs")}
    if "uq_agent_runs_idempotency_key" in uniques:
        op.drop_constraint("uq_agent_runs_idempotency_key", "agent_runs", type_="unique")
    columns={col["name"] for col in inspect(op.get_bind()).get_columns("agent_runs")}
    for name in ("updated_at", "review_note", "reviewer", "result_json", "state_json", "idempotency_key"):
        if name in columns:
            op.drop_column("agent_runs", name)
