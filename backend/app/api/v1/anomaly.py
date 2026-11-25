from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.integrations.prometheus.client import PrometheusClient, PrometheusError, get_prometheus_client
from app.modules.anomaly.models import Algorithm, AnomalyResult, Severity
from app.modules.anomaly.service import scan

router = APIRouter(prefix="/anomalies", tags=["anomalies"])
Database = Annotated[Session, Depends(get_session)]
Prometheus = Annotated[PrometheusClient, Depends(get_prometheus_client)]


class ScanResult(BaseModel):
    devices_scanned: int
    results_saved: int
    anomalies_detected: int


class AnomalyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    device_id: int
    metric_name: str
    algorithm: Algorithm
    observed_value: float
    baseline_mean: float
    baseline_std: float
    anomaly_score: float
    is_anomaly: bool
    severity: Severity
    window_start: datetime
    window_end: datetime
    explanation_json: dict[str, Any]
    created_at: datetime


@router.post("/scan", response_model=ScanResult)
def scan_anomalies(db: Database, prometheus: Prometheus, synthetic_spike: bool = False):
    try:
        return scan(db, prometheus, synthetic_spike)
    except PrometheusError as exc:
        raise HTTPException(502, "Prometheus range query failed") from exc


@router.get("", response_model=list[AnomalyRead])
def list_anomalies(
    db: Database,
    device_id: Annotated[int | None, Query(gt=0)] = None,
    is_anomaly: bool | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    statement = select(AnomalyResult)
    if device_id is not None:
        statement = statement.where(AnomalyResult.device_id == device_id)
    if is_anomaly is not None:
        statement = statement.where(AnomalyResult.is_anomaly.is_(is_anomaly))
    return db.scalars(
        statement.order_by(AnomalyResult.window_end.desc(), AnomalyResult.id.desc())
        .offset(offset).limit(limit)
    ).all()
