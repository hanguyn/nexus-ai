from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import timedelta
from os import environ

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import AlertStatus
from app.models import AlertEvent, Device, DeviceDependency, Incident
from app.modules.anomaly.models import AnomalyResult
from app.modules.simulator.models import DemoRun

WINDOW = timedelta(seconds=int(environ.get("RCA_WINDOW_SECONDS", "180")))
OUTAGE_ALERTS = {"NetworkDeviceDown", "NetworkInterfaceDown", "BlackboxProbeFailed"}


@dataclass
class Correlation:
    alerts: list[AlertEvent]
    devices: dict[int, Device]
    paths: dict[int, dict[int, list[int]]]
    anomalies: dict[int, list[AnomalyResult]]


class CorrelationEngine:
    def __init__(self, db: Session, window: timedelta = WINDOW):
        if window <= timedelta():
            raise ValueError("Correlation window must be positive")
        self.db = db
        self.window = window

    def group(self, incident: Incident) -> Correlation:
        linked = incident.alerts
        if not linked:
            return Correlation([], {}, {}, {})
        active = [alert for alert in linked if alert.status == AlertStatus.firing]
        anchor = max(alert.starts_at for alert in active or linked)
        alerts = [alert for alert in linked if abs(alert.starts_at - anchor) <= self.window]
        alerted = {alert.device_id for alert in alerts if alert.device_id is not None}
        if not alerted:
            return Correlation(alerts, {}, {}, {})

        parents: dict[int, set[int]] = defaultdict(set)
        for upstream, downstream in self.db.execute(
            select(DeviceDependency.upstream_device_id, DeviceDependency.downstream_device_id)
        ):
            parents[downstream].add(upstream)

        paths: dict[int, dict[int, list[int]]] = defaultdict(dict)
        for downstream in sorted(alerted):
            seen = {downstream}
            queue = deque([(downstream, [downstream])])
            while queue:
                device, path = queue.popleft()
                for parent in sorted(parents[device] - seen):
                    seen.add(parent)
                    upstream_path = [parent, *path]
                    paths[parent][downstream] = upstream_path
                    queue.append((parent, upstream_path))

        # A circular dependency cannot establish which peer is upstream.
        for upstream, downstream_paths in paths.items():
            for downstream in list(downstream_paths):
                if self._reachable(upstream, downstream, parents):
                    del downstream_paths[downstream]
        candidates = alerted | {device_id for device_id, downstream in paths.items() if downstream}
        devices = {
            device.id: device for device in self.db.scalars(select(Device).where(Device.id.in_(candidates)))
        }
        simulation_run_id = self.db.scalar(select(DemoRun.id).where(DemoRun.incident_id == incident.id))
        anomaly_scope = (
            AnomalyResult.simulation_run_id == simulation_run_id if simulation_run_id is not None
            else AnomalyResult.simulation_run_id.is_(None)
            & AnomalyResult.explanation_json["synthetic"].as_boolean().is_not(True)
        )
        anomalies = defaultdict(list)
        for result in self.db.scalars(
            select(AnomalyResult).where(
                AnomalyResult.device_id.in_(candidates),
                AnomalyResult.is_anomaly.is_(True),
                AnomalyResult.window_end.between(anchor - self.window, anchor + self.window),
                anomaly_scope,
            ).order_by(AnomalyResult.window_end, AnomalyResult.id)
        ):
            anomalies[result.device_id].append(result)
        return Correlation(alerts, devices, dict(paths), dict(anomalies))

    @staticmethod
    def _reachable(start: int, target: int, parents: dict[int, set[int]]) -> bool:
        seen = {start}
        pending = [start]
        while pending:
            for parent in parents[pending.pop()] - seen:
                if parent == target:
                    return True
                seen.add(parent)
                pending.append(parent)
        return False
