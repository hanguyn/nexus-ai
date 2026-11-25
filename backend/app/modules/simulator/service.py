from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.enums import IncidentStatus
from app.models import AlertEvent, Device, DeviceDependency, Incident, IncidentAlert, Site
from app.modules.anomaly.detectors import FEATURES, IsolationForestDetector, ZScoreDetector
from app.modules.anomaly.models import AnomalyResult
from app.modules.anomaly.service import row
from app.modules.assistant.llm_adapter import LLMAdapter
from app.modules.assistant.service import explain_incident
from app.modules.rca.engine import RCAEngine
from app.modules.simulator.models import DemoRun
from app.modules.simulator.scenarios import DEVICES, LINKS, SCENARIOS
from app.modules.troubleshooting.service import verify_recovery
from app.webhooks.schemas import AlertmanagerWebhook
from app.webhooks.service import ingest, lock_ingestion, record

SITE_NAME = "HCM-HQ-Lab"


class TopologyConflict(RuntimeError):
    pass


def seed_topology(db: Session) -> tuple[Site, dict[str, Device]]:
    lock_ingestion(db)
    site = db.scalar(select(Site).where(Site.name == SITE_NAME))
    if site is None:
        site = Site(name=SITE_NAME, location="Ho Chi Minh City", description="Simulated enterprise branch")
        db.add(site)
        db.flush()

    devices = {}
    for key, (hostname, address, device_type) in DEVICES.items():
        matches = db.scalars(select(Device).where(or_(
            func.lower(Device.hostname) == hostname.lower(), Device.ip_address == address,
        ))).all()
        if matches:
            if len(matches) != 1 or (
                matches[0].hostname.lower(), matches[0].ip_address, matches[0].site_id, matches[0].device_type
            ) != (hostname.lower(), address, site.id, device_type):
                raise TopologyConflict(f"Inventory conflicts with demo device {hostname}.")
            device = matches[0]
        else:
            device = Device(
                site_id=site.id, hostname=hostname, ip_address=address,
                device_type=device_type, vendor="Simulated", status="simulated",
            )
            db.add(device)
        devices[key] = device
    db.flush()

    for source, target, kind in LINKS:
        upstream, downstream = devices[source].id, devices[target].id
        if db.scalar(select(DeviceDependency.id).where(
            DeviceDependency.upstream_device_id == upstream,
            DeviceDependency.downstream_device_id == downstream,
            DeviceDependency.dependency_type == kind,
        )) is None:
            db.add(DeviceDependency(
                upstream_device_id=upstream, downstream_device_id=downstream, dependency_type=kind,
            ))
    return site, devices


def active_run(db: Session, scenario: str) -> DemoRun | None:
    return db.scalar(select(DemoRun).where(DemoRun.scenario == scenario, DemoRun.active.is_(True)))


def add_demo_anomalies(db: Session, run: DemoRun, devices: dict[str, Device], at: datetime) -> None:
    if run.scenario == "wan_outage":
        return
    index = pd.date_range(end=at - timedelta(seconds=15), periods=80, freq="15s")
    if run.scenario == "vpn_tunnel_down":
        history = pd.Series(np.zeros(len(index)), index=index)
        metric, observed, device = "packet_loss_pct", 82.0, devices["vpn"]
    else:
        rng = np.random.default_rng(42)
        frame = pd.DataFrame(rng.normal(
            loc=[900_000, 1_200_000, 0.02], scale=[30_000, 40_000, 0.002], size=(len(index), 3),
        ), columns=FEATURES, index=index)
        history = frame["traffic_out"]
        metric, observed, device = "traffic_out", 45_000_000.0, devices["core"]

    scores = [("zscore", ZScoreDetector().detect(history, observed))]
    if run.scenario == "bandwidth_spike":
        features = pd.Series([2_000_000, observed, 0.9], index=FEATURES)
        scores.append(("isolation_forest", IsolationForestDetector().detect(frame, features)))
    for algorithm, result in scores:
        values = row(device.id, metric, algorithm, result, history.index[0], pd.Timestamp(at), len(history), True)
        values["explanation_json"]["scenario"] = run.scenario
        if run.scenario == "bandwidth_spike":
            values["explanation_json"]["interface_name"] = "Gi0/1"
        db.add(AnomalyResult(simulation_run_id=run.id, **values))


def trigger(db: Session, scenario: str) -> DemoRun:
    lock_ingestion(db)
    previous = active_run(db, scenario)
    if previous is not None:
        return previous

    site, devices = seed_topology(db)
    definition = SCENARIOS[scenario]
    incident = Incident(site_id=site.id, title=definition.title, severity="critical", status=IncidentStatus.new)
    db.add(incident)
    record(incident, "created", f"Simulated incident for {scenario}.")
    db.flush()
    run = DemoRun(scenario=scenario, incident_id=incident.id, active=True)
    db.add(run)
    db.flush()

    # Backdate the first event so offsets are honest and the demo needs no wall-clock delay.
    at = datetime.now(UTC) - timedelta(seconds=max(alert.offset for alert in definition.alerts))
    add_demo_anomalies(db, run, devices, at)
    payload = AlertmanagerWebhook.model_validate({"alerts": [
        {
            "status": "firing", "fingerprint": f"demo-{run.id}-{index}",
            "startsAt": at + timedelta(seconds=alert.offset),
            "labels": {
                "alertname": alert.name, "instance": devices[alert.device].ip_address,
                "severity": "critical", "source": "simulator",
                **({"ifName": alert.interface} if alert.interface else {}),
            },
            "annotations": {"summary": definition.description},
        }
        for index, alert in enumerate(definition.alerts)
    ]})
    ingest(db, payload.alerts, target_incident=incident)
    RCAEngine(db).analyze_incident(incident.id)
    explain_incident(db, incident.id, adapter=LLMAdapter(mock=True))
    return run


class SimulatedRecoveryTelemetry:
    def __init__(self, alerts: list[AlertEvent]):
        self.alerts = alerts

    def query_instant(self, query: str, at: datetime):
        return [
            ({"instance": alert.instance, **({"ifName": alert.interface_name} if alert.interface_name else {})}, 1.0)
            for alert in self.alerts
        ]


def recover(db: Session, scenario: str) -> DemoRun | None:
    lock_ingestion(db)
    run = active_run(db, scenario)
    if run is None:
        return None
    incident = db.get(Incident, run.incident_id)
    now = datetime.now(UTC)
    alerts = incident.alerts
    payload = AlertmanagerWebhook.model_validate({"alerts": [
        {
            "status": "resolved", "fingerprint": alert.fingerprint,
            "startsAt": alert.starts_at, "endsAt": now,
            "labels": alert.labels_json, "annotations": alert.annotations_json,
        }
        for alert in alerts
    ]})
    ingest(db, payload.alerts)
    verify_recovery(db, incident.id, SimulatedRecoveryTelemetry(alerts), source="simulator")
    RCAEngine(db).analyze_incident(incident.id)
    explain_incident(db, incident.id, adapter=LLMAdapter(mock=True))
    run.active = False
    return run


def reset(db: Session) -> int:
    lock_ingestion(db)
    incidents = select(DemoRun.incident_id)
    owned_alerts = select(IncidentAlert.alert_event_id).where(IncidentAlert.incident_id.in_(incidents))
    db.execute(delete(AlertEvent).where(AlertEvent.id.in_(owned_alerts)))
    result = db.execute(delete(Incident).where(Incident.id.in_(incidents)))
    return result.rowcount
