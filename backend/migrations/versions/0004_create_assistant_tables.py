"""Create incident assistant, troubleshooting, and verification tables."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ai_recommendations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("incident_id", sa.Integer(), sa.ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("model_provider", sa.String(20), nullable=False),
        sa.Column("model_name", sa.String(120), nullable=False),
        sa.Column("executive_summary", sa.Text(), nullable=False),
        sa.Column("technical_explanation", sa.Text(), nullable=False),
        sa.Column("impact_assessment", sa.Text(), nullable=False),
        sa.Column("checklist_json", JSONB(), nullable=False),
        sa.Column("evidence_citations_json", JSONB(), nullable=False),
        sa.Column("limitations_note", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_ai_recommendations_incident_id", "ai_recommendations", ["incident_id"])
    op.create_table(
        "troubleshooting_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("incident_id", sa.Integer(), sa.ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("step_title", sa.Text(), nullable=False),
        sa.Column("command_or_action", sa.Text(), nullable=False),
        sa.Column("execution_mode", sa.Enum(
            "read_only", "manual_check", name="troubleshooting_mode", native_enum=False, create_constraint=True,
        ), nullable=False),
        sa.Column("status", sa.Enum(
            "pending", "completed", "failed", name="troubleshooting_status", native_enum=False, create_constraint=True,
        ), nullable=False),
        sa.Column("operator_note", sa.Text()),
        sa.Column("executed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("incident_id", "command_or_action", name="uq_troubleshooting_incident_action"),
    )
    op.create_table(
        "verification_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("incident_id", sa.Integer(), sa.ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_metric_or_probe", sa.Text(), nullable=False),
        sa.Column("pre_fix_value", sa.Float()),
        sa.Column("post_fix_value", sa.Float()),
        sa.Column("is_recovered", sa.Boolean(), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_verification_results_incident_id", "verification_results", ["incident_id"])


def downgrade():
    op.drop_table("verification_results")
    op.drop_table("troubleshooting_runs")
    op.drop_table("ai_recommendations")
