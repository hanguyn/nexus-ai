from collections import defaultdict
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.enums import AlertStatus, IncidentStatus
from app.models import Device, Incident, IncidentHistory
from app.modules.assistant.schemas import ChecklistStep
from app.modules.troubleshooting.models import RunStatus, TroubleshootingRun, VerificationResult

METRICS = {"up": 'up{job="snmp"}', "probe_success": "probe_success", "ifOperStatus": "ifOperStatus"}
FAILURES = {
    "NetworkDeviceDown": ("up", 0.0),
    "BlackboxProbeFailed": ("probe_success", 0.0),
    "NetworkInterfaceDown": ("ifOperStatus", 2.0),
}
INTERFACE_LABELS = ("ifName", "ifIndex", "ifDescr", "interface", "interface_name")


def initialize_runs(db: Session, incident_id: int, steps: list[ChecklistStep]) -> None:
    statement = insert(TroubleshootingRun).on_conflict_do_nothing(
        constraint="uq_troubleshooting_incident_action"
    )
    db.execute(statement, [
        {"incident_id": incident_id, "step_title": step.title, "command_or_action": step.command_or_action,
         "execution_mode": step.execution_mode, "status": RunStatus.pending}
        for step in steps
    ])


class InstantTelemetry(Protocol):
    def query_instant(self, query: str, at: datetime) -> list[tuple[dict[str, str], float]]: ...


def verify_recovery(
    db: Session, incident_id: int, prometheus: InstantTelemetry, *, source: str = "Prometheus",
) -> tuple[bool, list[VerificationResult]]:
    incident = db.scalar(select(Incident).where(Incident.id == incident_id).with_for_update())
    if incident is None:
        raise LookupError("Incident not found")
    now = datetime.now(UTC)
    associated = defaultdict(list)
    for alert in incident.alerts:
        key = alert.device_id if alert.device_id is not None else alert.instance
        associated[key].append(alert)

    devices = {
        device.id: device for device in db.scalars(select(Device).where(
            Device.id.in_([key for key in associated if isinstance(key, int)])
        ))
    }
    samples = {
        metric: prometheus.query_instant(f"{expr} and (time() - timestamp({expr}) <= 90)", now)
        for metric, expr in METRICS.items()
    } if associated else {}

    results = []
    fallback_count = 0
    prefix = "simulated:" if source == "simulator" else ""
    for target, alerts in associated.items():
        aliases = {alert.instance for alert in alerts if alert.instance}
        device = devices.get(target)
        if device:
            aliases.update((device.hostname, device.ip_address))
        hostname = device.hostname if device else alerts[0].instance or "unknown target"
        matching_samples = {
            metric: [(labels, value) for labels, value in points if labels.get("instance") in aliases]
            for metric, points in samples.items()
        }
        if not any(matching_samples.values()) and all(alert.status == AlertStatus.resolved for alert in alerts):
            results.append(VerificationResult(
                incident_id=incident_id, target_metric_or_probe=f"{prefix}alert_resolution:{hostname}",
                post_fix_value=1.0, is_recovered=True, verified_at=now,
            ))
            fallback_count += 1
            continue

        required = defaultdict(dict)
        for alert in alerts:
            if failure := FAILURES.get(alert.alertname):
                metric, pre = failure
                selector = alert.interface_name if metric == "ifOperStatus" else None
                required[metric][selector] = pre

        checks = []
        for metric, matching in matching_samples.items():
            for interface, pre in (required.get(metric) or {None: None}).items():
                scoped = [
                    value for labels, value in matching
                    if interface is None or interface in {labels.get(key) for key in INTERFACE_LABELS}
                ]
                if scoped or metric in required:
                    healthy = bool(scoped) and all(value == 1 for value in scoped)
                    post = next((value for value in scoped if value != 1), scoped[0] if scoped else None)
                    label = f"{prefix}{metric}:{hostname}" + (f":{interface}" if interface else "")
                    checks.append(VerificationResult(
                        incident_id=incident_id, target_metric_or_probe=label,
                        pre_fix_value=pre, post_fix_value=post, is_recovered=healthy, verified_at=now,
                    ))
        if not checks:
            checks.append(VerificationResult(
                incident_id=incident_id, target_metric_or_probe=f"{prefix}telemetry:{hostname}",
                is_recovered=False, verified_at=now,
            ))
        results.extend(checks)

    recovered = bool(results) and all(result.is_recovered for result in results)
    db.add_all(results)
    if recovered and incident.status not in (IncidentStatus.resolved, IncidentStatus.closed):
        incident.status = IncidentStatus.resolved
        incident.resolved_at = now
    incident.updated_at = now
    if fallback_count:
        outcome = "confirmed" if recovered else "unconfirmed"
        note = (f"Recovery {outcome}. Used linked alert resolution for {fallback_count} "
                "target(s) without fresh telemetry.")
    elif recovered:
        note = f"{source.capitalize()} telemetry confirmed recovery across {len(results)} check(s)."
    else:
        note = f"{source.capitalize()} telemetry was missing or unhealthy for recovery verification."
    incident.history.append(IncidentHistory(
        action="recovery_verified" if recovered else "recovery_unconfirmed",
        note=note,
    ))
    db.flush()
    return recovered, results
