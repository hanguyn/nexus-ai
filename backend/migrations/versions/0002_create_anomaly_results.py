"""Create anomaly results."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "anomaly_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("device_id", sa.Integer(), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("metric_name", sa.String(64), nullable=False),
        sa.Column("algorithm", sa.Enum(
            "zscore", "ewma", "isolation_forest", name="anomaly_algorithm",
            native_enum=False, create_constraint=True,
        ), nullable=False),
        sa.Column("observed_value", sa.Float(), nullable=False),
        sa.Column("baseline_mean", sa.Float(), nullable=False),
        sa.Column("baseline_std", sa.Float(), nullable=False),
        sa.Column("anomaly_score", sa.Float(), nullable=False),
        sa.Column("is_anomaly", sa.Boolean(), nullable=False),
        sa.Column("severity", sa.Enum(
            "low", "medium", "high", name="anomaly_severity",
            native_enum=False, create_constraint=True,
        ), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("explanation_json", JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "device_id", "metric_name", "algorithm", "window_end", name="uq_anomaly_result_window"
        ),
    )
    op.create_index("ix_anomaly_results_device_id", "anomaly_results", ["device_id"])
    op.create_index("ix_anomaly_results_window_end", "anomaly_results", ["window_end"])


def downgrade():
    op.drop_table("anomaly_results")
