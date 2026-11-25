from datetime import datetime

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, Enum, ForeignKey, Index, String, Text,
    UniqueConstraint, func, true,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.enums import AlertStatus, DependencyType, DeviceType, IncidentStatus


class Site(Base):
    __tablename__ = "sites"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    location: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="RESTRICT"), index=True)
    hostname: Mapped[str] = mapped_column(String(253), unique=True)
    ip_address: Mapped[str] = mapped_column(String(253), unique=True)
    device_type: Mapped[DeviceType] = mapped_column(
        Enum(DeviceType, name="device_type", native_enum=False, create_constraint=True)
    )
    vendor: Mapped[str | None] = mapped_column(String(255))
    snmp_community_encrypted: Mapped[str | None] = mapped_column(Text)
    monitoring_enabled: Mapped[bool] = mapped_column(Boolean, server_default=true())
    status: Mapped[str] = mapped_column(String(32), server_default="unknown")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DeviceDependency(Base):
    __tablename__ = "device_dependencies"
    __table_args__ = (
        CheckConstraint("upstream_device_id <> downstream_device_id", name="different_devices"),
        UniqueConstraint("upstream_device_id", "downstream_device_id", "dependency_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    upstream_device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"))
    downstream_device_id: Mapped[int] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"), index=True
    )
    dependency_type: Mapped[DependencyType] = mapped_column(
        Enum(DependencyType, name="dependency_type", native_enum=False, create_constraint=True)
    )


class AlertEvent(Base):
    __tablename__ = "alert_events"
    __table_args__ = (UniqueConstraint("fingerprint", "starts_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(128))
    alertname: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(32))
    device_id: Mapped[int | None] = mapped_column(
        ForeignKey("devices.id", ondelete="SET NULL"), index=True
    )
    instance: Mapped[str] = mapped_column(Text)
    interface_name: Mapped[str | None] = mapped_column(Text)
    status: Mapped[AlertStatus] = mapped_column(
        Enum(AlertStatus, name="alert_status", native_enum=False, create_constraint=True)
    )
    labels_json: Mapped[dict[str, str]] = mapped_column(JSONB)
    annotations_json: Mapped[dict[str, str]] = mapped_column(JSONB)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Incident(Base):
    __tablename__ = "incidents"
    __table_args__ = (Index("ix_incidents_site_status", "site_id", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int | None] = mapped_column(ForeignKey("sites.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(32))
    status: Mapped[IncidentStatus] = mapped_column(
        Enum(IncidentStatus, name="incident_status", native_enum=False, create_constraint=True)
    )
    root_cause_summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    alerts: Mapped[list[AlertEvent]] = relationship(
        secondary="incident_alerts", order_by=(AlertEvent.starts_at, AlertEvent.id)
    )
    history: Mapped[list["IncidentHistory"]] = relationship(
        order_by="IncidentHistory.id", cascade="all, delete-orphan"
    )


class IncidentAlert(Base):
    __tablename__ = "incident_alerts"

    incident_id: Mapped[int] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), primary_key=True
    )
    alert_event_id: Mapped[int] = mapped_column(
        ForeignKey("alert_events.id", ondelete="CASCADE"), primary_key=True, unique=True
    )


class IncidentHistory(Base):
    __tablename__ = "incident_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), index=True)
    action: Mapped[str] = mapped_column(String(50))
    note: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
