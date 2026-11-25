from collections import defaultdict
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, joinedload

from app.models import AlertEvent, Incident
from app.modules.correlation.engine import OUTAGE_ALERTS, CorrelationEngine
from app.modules.rca.models import AnalysisEvidence, EvidenceType, RootCauseAnalysis, VerificationStatus

FAILURE_METRICS = {
    "NetworkInterfaceDown": ("ifOperStatus", 2, EvidenceType.state),
    "BlackboxProbeFailed": ("probe_success", 0, EvidenceType.metric),
}


def ranked_causes(db: Session, incident_id: int) -> list[RootCauseAnalysis]:
    statement = (
        select(RootCauseAnalysis)
        .where(RootCauseAnalysis.incident_id == incident_id)
        .options(joinedload(RootCauseAnalysis.evidence))
        .order_by(RootCauseAnalysis.rank)
    )
    return list(db.scalars(statement).unique())


def evidence(kind: EvidenceType, description: str, raw: dict, weight: float, at: datetime):
    return AnalysisEvidence(
        evidence_type=kind, description=description, raw_reference_json=raw,
        weight=weight, observed_at=at,
    )


def alert_reference(alert: AlertEvent) -> dict:
    return {"alert_event_id": alert.id, "alertname": alert.alertname,
            "instance": alert.instance, "interface_name": alert.interface_name}


class RCAEngine:
    def __init__(self, db: Session):
        self.db = db
        self.correlation = CorrelationEngine(db)

    def analyze_incident(self, incident_id: int) -> list[RootCauseAnalysis]:
        incident = self.db.scalar(select(Incident).where(Incident.id == incident_id).with_for_update())
        if incident is None:
            raise LookupError("Incident not found")
        grouped = self.correlation.group(incident)
        by_device = defaultdict(list)
        unknown = defaultdict(list)
        for alert in grouped.alerts:
            if alert.device_id in grouped.devices:
                by_device[alert.device_id].append(alert)
            else:
                unknown[alert.instance].append(alert)

        candidates = []
        if grouped.alerts:
            first = min(alert.starts_at for alert in grouped.alerts)
            for device_id, device in grouped.devices.items():
                candidates.append(self._evaluate(
                    incident_id, device_id, device.hostname, by_device[device_id], first,
                    grouped.paths.get(device_id, {}), by_device, grouped.anomalies.get(device_id, []),
                ))
            for instance, alerts in sorted(unknown.items()):
                candidates.append(self._evaluate(
                    incident_id, None, instance or "unknown target", alerts, first, {}, by_device, [],
                ))

        candidates.sort(key=lambda item: (-item.confidence_score, item.candidate_component,
                                          item.candidate_device_id or 0))
        self.db.execute(delete(RootCauseAnalysis).where(RootCauseAnalysis.incident_id == incident_id))
        for rank, candidate in enumerate(candidates, 1):
            candidate.rank = rank
        self.db.add_all(candidates)
        self.db.flush()
        return candidates

    def _evaluate(self, incident_id, device_id, name, alerts, first, paths, by_device, anomalies):
        records = []
        confirmed = False
        first_alert = min(alerts, key=lambda alert: (alert.starts_at, alert.id), default=None)
        outage = min(
            (alert for alert in alerts if alert.alertname in OUTAGE_ALERTS),
            key=lambda alert: (alert.starts_at, alert.id), default=None,
        )
        if first_alert:
            elapsed = (first_alert.starts_at - first).total_seconds()
            precedence = 0.20 * (1 - elapsed / self.correlation.window.total_seconds())
            records.append(evidence(
                EvidenceType.temporal, f"First candidate alert fired {elapsed:g}s after the earliest alert.",
                {**alert_reference(first_alert), "seconds_after_first": elapsed},
                round(max(0, precedence), 4), first_alert.starts_at,
            ))

        affected = []
        for downstream_id, path in sorted(paths.items()):
            symptoms = [
                alert.id for alert in by_device[downstream_id]
                if outage and outage.starts_at <= alert.starts_at
            ]
            affected.append({
                "downstream_device_id": downstream_id, "path_device_ids": path,
                "secondary_symptom_alert_ids": symptoms,
            })
        if affected:
            cascades = sum(bool(path["secondary_symptom_alert_ids"]) for path in affected)
            weight = min(0.35, 0.12 + 0.08 * len(affected)) if outage else min(0.10, 0.04 * len(affected))
            records.append(evidence(
                EvidenceType.topology, f"Directed paths reach {len(affected)} alerted device(s). "
                f"{cascades} downstream device(s) have possible secondary symptoms.",
                {"paths": affected, "upstream_alert_id": outage.id if outage else None},
                weight, outage.starts_at if outage else first,
            ))

        counted = set()
        for alert in alerts:
            failure = FAILURE_METRICS.get(alert.alertname)
            if failure:
                metric, value, kind = failure
                weight = 0.27 if not confirmed else 0.0
                confirmed = True
            elif alert.alertname == "NetworkDeviceDown":
                metric, value, kind = "up", 0, EvidenceType.state
                weight = 0.12 if metric not in counted else 0.0
            else:
                continue
            counted.add(metric)
            reference = {**alert_reference(alert), "metric": metric, "value": value}
            if metric == "up":
                reference["job"] = "snmp"
            records.append(evidence(kind, f"Alert rule recorded {metric} == {value}.",
                                    reference, weight, alert.starts_at))

        counted_anomalies = set()
        for anomaly in anomalies:
            metric = anomaly.metric_name
            weight = 0.04 if metric not in counted_anomalies and len(counted_anomalies) < 3 else 0.0
            counted_anomalies.add(metric)
            reference = {
                "anomaly_result_id": anomaly.id, "metric": metric, "algorithm": anomaly.algorithm,
                "value": anomaly.observed_value, "score": anomaly.anomaly_score,
            }
            records.append(evidence(EvidenceType.anomaly, f"{metric} was anomalous in the correlation window.",
                                    reference, weight, anomaly.window_end))
            if metric == "probe_success" and anomaly.observed_value == 0 and not confirmed:
                confirmed = True
                records.append(evidence(EvidenceType.metric, "Probe telemetry recorded probe_success == 0.",
                                        reference, 0.27, anomaly.window_end))

        missing = []
        if not confirmed:
            missing.append("Interface-down or failed-probe evidence during the incident")
        if not first_alert:
            missing.append("Firing timestamp from a candidate-device alert")
        if device_id is None:
            missing.append("Inventory device matching the alert instance")
        component_alert = outage or first_alert
        component = (
            f"{name}/{component_alert.interface_name}" if component_alert and component_alert.interface_name else name
        )
        status = VerificationStatus.verified if confirmed else VerificationStatus.potential
        summary = (
            f"{component}: direct interface or reachability failure observed." if confirmed
            else f"{component}: candidate inferred from available alerts, topology, or anomalies."
        )
        return RootCauseAnalysis(
            incident_id=incident_id, candidate_device_id=device_id, candidate_component=component[:512],
            confidence_score=round(min(1.0, 0.10 + sum(record.weight for record in records)), 4),
            verification_status=status, summary=summary, missing_data_json=missing, evidence=records,
        )
