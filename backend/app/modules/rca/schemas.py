from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.modules.rca.models import EvidenceType, VerificationStatus


class EvidenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    evidence_type: EvidenceType
    description: str
    raw_reference_json: dict[str, Any]
    weight: float
    observed_at: datetime


class RCARead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    incident_id: int
    candidate_device_id: int | None
    candidate_component: str
    rank: int
    confidence_score: float
    verification_status: VerificationStatus
    summary: str
    missing_data_json: list[str]
    recommended_checks: list[dict[str, str]]
    evidence: list[EvidenceRead]
    created_at: datetime
