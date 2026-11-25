"""Track simulator runs and their isolated anomaly results."""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "demo_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("scenario", sa.String(32), nullable=False),
        sa.Column("incident_id", sa.Integer(), sa.ForeignKey("incidents.id", ondelete="CASCADE"),
                  nullable=False, unique=True),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "uq_demo_runs_active_scenario", "demo_runs", ["scenario"], unique=True, postgresql_where=sa.text("active"),
    )
    op.add_column("anomaly_results", sa.Column("simulation_run_id", sa.Integer()))
    op.create_foreign_key(
        "fk_anomaly_simulation_run", "anomaly_results", "demo_runs", ["simulation_run_id"], ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_anomaly_results_simulation_run_id", "anomaly_results", ["simulation_run_id"])


def downgrade():
    op.drop_index("ix_anomaly_results_simulation_run_id", table_name="anomaly_results")
    op.drop_constraint("fk_anomaly_simulation_run", "anomaly_results", type_="foreignkey")
    op.drop_column("anomaly_results", "simulation_run_id")
    op.drop_table("demo_runs")
