from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class AIRecommendation(Base):
    __tablename__ = "ai_recommendations"

    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), index=True)
    model_provider: Mapped[str] = mapped_column(String(20))
    model_name: Mapped[str] = mapped_column(String(120))
    executive_summary: Mapped[str] = mapped_column(Text)
    technical_explanation: Mapped[str] = mapped_column(Text)
    impact_assessment: Mapped[str] = mapped_column(Text)
    checklist_json: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    evidence_citations_json: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    limitations_note: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
