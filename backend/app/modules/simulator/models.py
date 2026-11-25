from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, func, text, true
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class DemoRun(Base):
    __tablename__ = "demo_runs"
    __table_args__ = (
        Index("uq_demo_runs_active_scenario", "scenario", unique=True, postgresql_where=text("active")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    scenario: Mapped[str] = mapped_column(String(32))
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, server_default=true())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
