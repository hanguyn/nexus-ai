from pydantic import AwareDatetime, BaseModel, Field

from app.enums import AlertStatus


class AlertmanagerAlert(BaseModel):
    status: AlertStatus
    labels: dict[str, str]
    annotations: dict[str, str] = Field(default_factory=dict)
    startsAt: AwareDatetime
    endsAt: AwareDatetime | None = None
    fingerprint: str = Field(min_length=1, max_length=128)


class AlertmanagerWebhook(BaseModel):
    alerts: list[AlertmanagerAlert]
