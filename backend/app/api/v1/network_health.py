from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.integrations.prometheus.client import PrometheusClient, PrometheusError, get_prometheus_client
from app.models import Device
from app.modules.anomaly.models import AnomalyResult

router = APIRouter(tags=["network health"])
STEP_SECONDS = 30


@router.get("/network-health")
def network_health(
    db: Annotated[Session, Depends(get_session)],
    prometheus: Annotated[PrometheusClient, Depends(get_prometheus_client)],
):
    now = datetime.now(UTC)
    end = datetime.fromtimestamp(int(now.timestamp()) // STEP_SECONDS * STEP_SECONDS, UTC)
    start = end - timedelta(minutes=30)
    devices = db.execute(select(Device.id, Device.ip_address, Device.hostname, Device.monitoring_enabled)).all()
    latest = (
        select(AnomalyResult.is_anomaly)
        .where(
            AnomalyResult.window_end >= now - timedelta(hours=1),
            AnomalyResult.explanation_json["synthetic"].as_boolean().is_not(True),
            AnomalyResult.device_id.in_([device.id for device in devices if device.monitoring_enabled]),
        )
        .distinct(AnomalyResult.device_id, AnomalyResult.metric_name, AnomalyResult.algorithm)
        .order_by(
            AnomalyResult.device_id, AnomalyResult.metric_name, AnomalyResult.algorithm,
            AnomalyResult.window_end.desc(), AnomalyResult.id.desc(),
        )
        .subquery()
    )
    anomaly_count = db.scalar(select(func.count()).select_from(latest).where(latest.c.is_anomaly.is_(True)))
    db.rollback()

    try:
        metrics = prometheus.query_range(
            'up{job="snmp"} and (time() - timestamp(up{job="snmp"}) <= 90)', start, end, STEP_SECONDS,
        )
    except PrometheusError as exc:
        raise HTTPException(502, "Prometheus network health query failed") from exc

    samples = {
        device.id: (
            metrics.get(device.ip_address, metrics.get(device.hostname))
            if device.monitoring_enabled else None
        )
        for device in devices
    }
    history = []
    statuses = {}
    for offset in range(61):
        at = start + timedelta(seconds=offset * STEP_SECONDS)
        counts = {"online": 0, "offline": 0, "unknown": 0}
        for device_id, series in samples.items():
            value = series.get(at) if series is not None else None
            state = "online" if value == 1 else "offline" if value == 0 else "unknown"
            counts[state] += 1
            if at == end:
                statuses[device_id] = state
        history.append({"at": at, **counts})
    return {"history": history, "device_statuses": statuses, "active_anomalies": anomaly_count}
