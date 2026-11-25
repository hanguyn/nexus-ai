from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.enums import AlertStatus, IncidentStatus


class Record(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class AlertRead(Record):
    id: int
    fingerprint: str
    alertname: str
    severity: str
    device_id: int | None
    instance: str
    interface_name: str | None
    status: AlertStatus
    labels_json: dict[str, str]
    annotations_json: dict[str, str]
    starts_at: datetime
    ends_at: datetime | None


class HistoryRead(Record):
    id: int
    action: str
    note: str
    created_at: datetime


class IncidentRead(Record):
    id: int
    site_id: int | None
    title: str
    severity: str
    status: IncidentStatus
    root_cause_summary: str | None
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None
    alerts: list[AlertRead]
    history: list[HistoryRead]
