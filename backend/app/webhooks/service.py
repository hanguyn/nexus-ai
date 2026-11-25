from collections import defaultdict
from datetime import UTC, datetime
from urllib.parse import urlsplit

from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from app.enums import AlertStatus, IncidentStatus
from app.models import AlertEvent, Device, DeviceDependency, Incident, IncidentAlert, IncidentHistory
from app.modules.correlation.engine import WINDOW
from app.modules.simulator.models import DemoRun
from app.webhooks.schemas import AlertmanagerAlert

ACTIVE = (IncidentStatus.new, IncidentStatus.acknowledged, IncidentStatus.investigating)
SEVERITY = {"info": 1, "warning": 2, "critical": 3}


def find_device(db: Session, instance: str) -> Device | None:
    address = instance.lower().rstrip(".")
    for candidate in (address, endpoint_host(address)):
        if candidate:
            device = db.scalar(
                select(Device)
                .where(or_(Device.ip_address == candidate, Device.hostname == candidate))
                .order_by((Device.ip_address == candidate).desc(), Device.id)
                .limit(1)
            )
            if device is not None:
                return device
    return None


def endpoint_host(address: str) -> str | None:
    try:
        endpoint = urlsplit(address if "://" in address else f"//{address}")
        return endpoint.hostname.rstrip(".") if endpoint.hostname else None
    except ValueError:
        return None


def ancestors(device_id: int, parents: dict[int, set[int]]) -> set[int]:
    seen = {device_id}
    pending = [device_id]
    while pending:
        for parent in parents.get(pending.pop(), ()):
            if parent not in seen:
                seen.add(parent)
                pending.append(parent)
    return seen


def correlate(db: Session, event: AlertEvent, device: Device | None, parents) -> Incident | None:
    candidates = db.execute(
        select(Incident, AlertEvent, Device.site_id)
        .join(IncidentAlert, IncidentAlert.incident_id == Incident.id)
        .join(AlertEvent, AlertEvent.id == IncidentAlert.alert_event_id)
        .outerjoin(Device, Device.id == AlertEvent.device_id)
        .where(
            Incident.status.in_(ACTIVE),
            ~Incident.id.in_(select(DemoRun.incident_id)),
            AlertEvent.starts_at.between(event.starts_at - WINDOW, event.starts_at + WINDOW),
        )
        .order_by(func.abs(func.extract("epoch", AlertEvent.starts_at - event.starts_at)), Incident.id)
    )
    path = ancestors(device.id, parents) if device else set()
    for incident, previous, previous_site_id in candidates:
        if device:
            if device.site_id in (incident.site_id, previous_site_id):
                return incident
            if previous.device_id is not None and path & ancestors(previous.device_id, parents):
                return incident
        elif previous.device_id is None and event.instance and previous.instance == event.instance:
            return incident
    return None


def record(incident: Incident, action: str, note: str) -> None:
    incident.updated_at = datetime.now(UTC)
    incident.history.append(IncidentHistory(action=action, note=note))


def attach_firing(
    db: Session, event: AlertEvent, device: Device | None, parents, incident: Incident | None = None,
) -> Incident:
    if incident is None:
        incident = correlate(db, event, device, parents)
    if incident is None:
        incident = Incident(
            site_id=device.site_id if device else None,
            title=f"{event.alertname} on {event.instance}" if event.instance else event.alertname,
            severity=event.severity,
            status=IncidentStatus.new,
        )
        db.add(incident)
        record(incident, "created", "Created from Alertmanager")
    elif SEVERITY.get(event.severity, 0) > SEVERITY.get(incident.severity, 0):
        incident.severity = event.severity
    incident.alerts.append(event)
    record(incident, "alert_firing", f"{event.alertname} ({event.fingerprint}) firing")
    return incident


def resolve_event(db: Session, event: AlertEvent, ends_at: datetime) -> int | None:
    event.status = AlertStatus.resolved
    event.ends_at = ends_at
    incident = db.scalar(
        select(Incident)
        .join(IncidentAlert, IncidentAlert.incident_id == Incident.id)
        .where(IncidentAlert.alert_event_id == event.id)
    )
    if incident is not None:
        record(incident, "alert_resolved", f"{event.alertname} ({event.fingerprint}) resolved")
        return incident.id
    return None


def lock_ingestion(db: Session) -> None:
    db.execute(text("SELECT pg_advisory_xact_lock(628314020)"))


def ingest(
    db: Session, alerts: list[AlertmanagerAlert], *, target_incident: Incident | None = None,
) -> set[int]:
    if not alerts:
        return set()

    # Serialize webhook and simulator writes so concurrent batches share one correlation decision.
    lock_ingestion(db)
    parents = defaultdict(set)
    for upstream, downstream in db.execute(
        select(DeviceDependency.upstream_device_id, DeviceDependency.downstream_device_id)
    ):
        parents[downstream].add(upstream)

    affected = set()
    firing_incidents = set()
    for alert in alerts:
        ends_at = alert.endsAt
        if alert.status == AlertStatus.resolved and (ends_at is None or ends_at < alert.startsAt):
            ends_at = max(alert.startsAt, datetime.now(UTC))
        event = db.scalar(select(AlertEvent).where(
            AlertEvent.fingerprint == alert.fingerprint, AlertEvent.starts_at == alert.startsAt
        ))
        if event is not None:
            if alert.status == AlertStatus.resolved and event.status == AlertStatus.firing:
                incident_id = resolve_event(db, event, ends_at)
                if incident_id is not None:
                    affected.add(incident_id)
            continue

        instance = alert.labels.get("instance", "")
        device = find_device(db, instance)
        event = AlertEvent(
            fingerprint=alert.fingerprint,
            alertname=alert.labels.get("alertname") or "Unknown alert",
            severity=(alert.labels.get("severity") or "unknown")[:32].lower(),
            device_id=device.id if device else None,
            instance=instance,
            interface_name=(alert.labels.get("ifName") or alert.labels.get("interface_name")
                            or alert.labels.get("interface") or alert.labels.get("ifDescr")
                            or alert.labels.get("ifIndex")),
            status=alert.status,
            labels_json=alert.labels,
            annotations_json=alert.annotations,
            starts_at=alert.startsAt,
            ends_at=ends_at if alert.status == AlertStatus.resolved else None,
        )
        db.add(event)
        if alert.status == AlertStatus.firing:
            firing_incidents.add(attach_firing(db, event, device, parents, target_incident))

    for incident_id in sorted(affected):
        incident = db.get(Incident, incident_id)
        if incident.status in ACTIVE and all(alert.status == AlertStatus.resolved for alert in incident.alerts):
            incident.status = IncidentStatus.resolved
            incident.resolved_at = max(alert.ends_at for alert in incident.alerts)
            record(incident, "resolved", "All linked alerts resolved")

    db.flush()
    return affected | {incident.id for incident in firing_incidents}
