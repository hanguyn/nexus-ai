from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    CheckConstraint, DateTime, Enum, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class VerificationStatus(StrEnum):
    verified = "verified"
    potential = "potential"


class EvidenceType(StrEnum):
    temporal = "temporal"
    topology = "topology"
    state = "state"
    metric = "metric"
    anomaly = "anomaly"


class RootCauseAnalysis(Base):
    __tablename__ = "root_cause_analyses"
    __table_args__ = (
        UniqueConstraint("incident_id", "rank", name="uq_rca_incident_rank"),
        CheckConstraint("confidence_score BETWEEN 0 AND 1", name="ck_rca_confidence"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"))
    candidate_device_id: Mapped[int | None] = mapped_column(
        ForeignKey("devices.id", ondelete="SET NULL"), index=True
    )
    candidate_component: Mapped[str] = mapped_column(String(512))
    rank: Mapped[int] = mapped_column(Integer)
    confidence_score: Mapped[float] = mapped_column(Float)
    verification_status: Mapped[VerificationStatus] = mapped_column(
        Enum(VerificationStatus, name="rca_verification_status", native_enum=False, create_constraint=True)
    )
    summary: Mapped[str] = mapped_column(Text)
    missing_data_json: Mapped[list[str]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    evidence: Mapped[list["AnalysisEvidence"]] = relationship(
        order_by="AnalysisEvidence.id", cascade="all, delete-orphan",
    )

    @property
    def recommended_checks(self) -> list[dict[str, str]]:
        checks = [
            {"type": "metric", "expression": "ifOperStatus == 2",
             "description": "Inspect interface state for the candidate during the incident."},
            {"type": "metric", "expression": "probe_success == 0",
             "description": "Review reachability probes for the candidate during the incident."},
        ]
        if any(item.evidence_type == EvidenceType.topology for item in self.evidence):
            checks.append({
                "type": "topology",
                "description": "Compare the recorded dependency paths with inventory and link telemetry.",
            })
        return checks


class AnalysisEvidence(Base):
    __tablename__ = "analysis_evidence"

    id: Mapped[int] = mapped_column(primary_key=True)
    rca_id: Mapped[int] = mapped_column(ForeignKey("root_cause_analyses.id", ondelete="CASCADE"), index=True)
    evidence_type: Mapped[EvidenceType] = mapped_column(
        Enum(EvidenceType, name="rca_evidence_type", native_enum=False, create_constraint=True)
    )
    description: Mapped[str] = mapped_column(Text)
    raw_reference_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    weight: Mapped[float] = mapped_column(Float)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
