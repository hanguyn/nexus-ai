from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_serializer
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.integrations.prometheus.client import PrometheusClient, PrometheusError, get_prometheus_client
from app.models import Incident
from app.modules.assistant.llm_adapter import ProviderError
from app.modules.assistant.models import AIRecommendation
from app.modules.assistant.service import explain_incident
from app.modules.troubleshooting.models import ExecutionMode, RunStatus, TroubleshootingRun, VerificationResult
from app.modules.troubleshooting.service import verify_recovery

router = APIRouter(tags=["assistant", "troubleshooting"])
Database = Annotated[Session, Depends(get_session)]
Prometheus = Annotated[PrometheusClient, Depends(get_prometheus_client)]


class Record(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class RecommendationRead(Record):
    id: int
    incident_id: int
    model_provider: str
    model_name: str
    executive_summary: str
    technical_explanation: str
    impact_assessment: str
    checklist_json: list[dict[str, Any]]
    evidence_citations_json: list[dict[str, Any]]
    limitations_note: str
    created_at: datetime


class RunRead(Record):
    id: int
    incident_id: int
    step_title: str
    command_or_action: str
    execution_mode: ExecutionMode
    status: RunStatus
    operator_note: str | None
    executed_at: datetime | None


class VerificationRead(Record):
    id: int
    incident_id: int
    target_metric_or_probe: str
    pre_fix_value: float | None
    post_fix_value: float | None
    is_recovered: bool
    verified_at: datetime

    @field_serializer("verified_at")
    def serialize_verified_at(self, value: datetime) -> str:
        return value.astimezone(UTC).isoformat()


class VerificationResponse(BaseModel):
    is_recovered: bool
    results: list[VerificationRead]


class AssistantState(BaseModel):
    recommendation: RecommendationRead | None
    troubleshooting_runs: list[RunRead]
    verification: VerificationResponse | None


class RunUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal[RunStatus.pending, RunStatus.completed, RunStatus.failed] = RunStatus.completed
    operator_note: str | None = Field(default=None, max_length=4000)


@router.post("/incidents/{incident_id}/explain", response_model=RecommendationRead)
def explain(incident_id: int, db: Database):
    try:
        with db.begin():
            return RecommendationRead.model_validate(explain_incident(db, incident_id))
    except LookupError as exc:
        raise HTTPException(404, "Incident not found") from exc
    except ProviderError as exc:
        raise HTTPException(502, str(exc)) from exc


@router.get("/incidents/{incident_id}/assistant", response_model=AssistantState)
def assistant(incident_id: int, db: Database):
    if db.get(Incident, incident_id) is None:
        raise HTTPException(404, "Incident not found")
    recommendation = db.scalar(
        select(AIRecommendation).where(AIRecommendation.incident_id == incident_id)
        .order_by(AIRecommendation.id.desc()).limit(1)
    )
    runs = []
    if recommendation:
        actions = [step["command_or_action"] for step in recommendation.checklist_json]
        records = {
            run.command_or_action: run for run in db.scalars(select(TroubleshootingRun).where(
                TroubleshootingRun.incident_id == incident_id, TroubleshootingRun.command_or_action.in_(actions),
            ))
        }
        runs = [records[action] for action in dict.fromkeys(actions) if action in records]
    last_verified = select(func.max(VerificationResult.verified_at)).where(
        VerificationResult.incident_id == incident_id
    ).scalar_subquery()
    results = db.scalars(select(VerificationResult).where(
        VerificationResult.incident_id == incident_id, VerificationResult.verified_at == last_verified,
    ).order_by(VerificationResult.id)).all()
    return AssistantState(
        recommendation=recommendation, troubleshooting_runs=runs,
        verification=(VerificationResponse(
            is_recovered=all(result.is_recovered for result in results), results=results,
        ) if results else None),
    )


@router.patch("/troubleshooting/{run_id}", response_model=RunRead)
def update_run(run_id: int, body: RunUpdate, db: Database):
    with db.begin():
        run = db.get(TroubleshootingRun, run_id, with_for_update=True)
        if run is None:
            raise HTTPException(404, "Troubleshooting run not found")
        if run.status != body.status:
            run.status = body.status
            run.executed_at = None if body.status == RunStatus.pending else datetime.now(UTC)
        if "operator_note" in body.model_fields_set:
            run.operator_note = body.operator_note
        return RunRead.model_validate(run)


@router.post("/incidents/{incident_id}/verify-recovery", response_model=VerificationResponse)
def verify(incident_id: int, db: Database, prometheus: Prometheus):
    try:
        with db.begin():
            recovered, results = verify_recovery(db, incident_id, prometheus)
            return VerificationResponse(is_recovered=recovered, results=results)
    except LookupError as exc:
        raise HTTPException(404, "Incident not found") from exc
    except PrometheusError as exc:
        raise HTTPException(502, "Prometheus recovery query failed") from exc
