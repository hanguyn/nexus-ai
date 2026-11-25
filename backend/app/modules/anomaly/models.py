from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Algorithm(StrEnum):
    zscore = "zscore"
    ewma = "ewma"
    isolation_forest = "isolation_forest"


class Severity(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"


class AnomalyResult(Base):
    __tablename__ = "anomaly_results"
    __table_args__ = (
        UniqueConstraint(
            "device_id", "metric_name", "algorithm", "window_end", name="uq_anomaly_result_window"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    simulation_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("demo_runs.id", name="fk_anomaly_simulation_run", ondelete="CASCADE"), index=True,
    )
    metric_name: Mapped[str] = mapped_column(String(64))
    algorithm: Mapped[Algorithm] = mapped_column(
        Enum(Algorithm, name="anomaly_algorithm", native_enum=False, create_constraint=True)
    )
    observed_value: Mapped[float] = mapped_column(Float)
    baseline_mean: Mapped[float] = mapped_column(Float)
    baseline_std: Mapped[float] = mapped_column(Float)
    anomaly_score: Mapped[float] = mapped_column(Float)
    is_anomaly: Mapped[bool] = mapped_column(Boolean)
    severity: Mapped[Severity] = mapped_column(
        Enum(Severity, name="anomaly_severity", native_enum=False, create_constraint=True)
    )
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    explanation_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
