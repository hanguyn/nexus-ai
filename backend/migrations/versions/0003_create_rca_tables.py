"""Create root cause analyses and supporting evidence."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "root_cause_analyses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("incident_id", sa.Integer(), sa.ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("candidate_device_id", sa.Integer(), sa.ForeignKey("devices.id", ondelete="SET NULL")),
        sa.Column("candidate_component", sa.String(512), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column("verification_status", sa.Enum(
            "verified", "potential", name="rca_verification_status", native_enum=False, create_constraint=True,
        ), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("missing_data_json", JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("incident_id", "rank", name="uq_rca_incident_rank"),
        sa.CheckConstraint("confidence_score BETWEEN 0 AND 1", name="ck_rca_confidence"),
    )
    op.create_index("ix_root_cause_analyses_candidate_device_id", "root_cause_analyses", ["candidate_device_id"])
    op.create_table(
        "analysis_evidence",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("rca_id", sa.Integer(), sa.ForeignKey("root_cause_analyses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("evidence_type", sa.Enum(
            "temporal", "topology", "state", "metric", "anomaly",
            name="rca_evidence_type", native_enum=False, create_constraint=True,
        ), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("raw_reference_json", JSONB(), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_analysis_evidence_rca_id", "analysis_evidence", ["rca_id"])


def downgrade():
    op.drop_table("analysis_evidence")
    op.drop_table("root_cause_analyses")
