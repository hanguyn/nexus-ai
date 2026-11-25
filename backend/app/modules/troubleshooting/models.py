from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ExecutionMode(StrEnum):
    read_only = "read_only"
    manual_check = "manual_check"


class RunStatus(StrEnum):
    pending = "pending"
    completed = "completed"
    failed = "failed"


class TroubleshootingRun(Base):
    __tablename__ = "troubleshooting_runs"
    __table_args__ = (
        UniqueConstraint("incident_id", "command_or_action", name="uq_troubleshooting_incident_action"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"))
    step_title: Mapped[str] = mapped_column(Text)
    command_or_action: Mapped[str] = mapped_column(Text)
    execution_mode: Mapped[ExecutionMode] = mapped_column(
        Enum(ExecutionMode, name="troubleshooting_mode", native_enum=False, create_constraint=True)
    )
    status: Mapped[RunStatus] = mapped_column(
        Enum(RunStatus, name="troubleshooting_status", native_enum=False, create_constraint=True)
    )
    operator_note: Mapped[str | None] = mapped_column(Text)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class VerificationResult(Base):
    __tablename__ = "verification_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), index=True)
    target_metric_or_probe: Mapped[str] = mapped_column(Text)
    pre_fix_value: Mapped[float | None] = mapped_column(Float)
    post_fix_value: Mapped[float | None] = mapped_column(Float)
    is_recovered: Mapped[bool] = mapped_column(Boolean)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
