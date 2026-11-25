import re
from datetime import datetime
from ipaddress import ip_address
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

from app.enums import DeviceType, DependencyType

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
Host = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=253)]
Status = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=32)]
ID = Annotated[int, Field(gt=0)]


def normalize_address(value: str) -> str:
    try:
        return str(ip_address(value))
    except ValueError:
        labels = value.rstrip(".").split(".")
        if not all(re.fullmatch(r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?", part) for part in labels):
            raise ValueError("Expected an IP address or DNS hostname") from None
        if all(part.isdecimal() for part in labels):
            raise ValueError("Invalid IP address")
        return value.lower().rstrip(".")


Address = Annotated[Host, AfterValidator(normalize_address)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SiteCreate(Input):
    name: Name
    location: str | None = None
    description: str | None = None


class SiteUpdate(Input):
    name: Name | None = None
    location: str | None = None
    description: str | None = None


class SiteRead(SiteCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime


class DeviceCreate(Input):
    site_id: ID
    hostname: Address
    ip_address: Address
    device_type: DeviceType
    vendor: Name | None = None
    snmp_community_encrypted: str | None = Field(default=None, description="Pre-encrypted SNMP community ciphertext")
    monitoring_enabled: bool = True
    status: Status = "unknown"


class DeviceUpdate(Input):
    site_id: ID | None = None
    hostname: Address | None = None
    ip_address: Address | None = None
    device_type: DeviceType | None = None
    vendor: Name | None = None
    snmp_community_encrypted: str | None = None
    monitoring_enabled: bool | None = None
    status: Status | None = None


class DeviceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    site_id: int
    hostname: str
    ip_address: str
    device_type: DeviceType
    vendor: str | None
    monitoring_enabled: bool
    status: str
    created_at: datetime


class DependencyCreate(Input):
    upstream_device_id: ID
    downstream_device_id: ID
    dependency_type: DependencyType


class DependencyUpdate(Input):
    upstream_device_id: ID | None = None
    downstream_device_id: ID | None = None
    dependency_type: DependencyType | None = None


class DependencyRead(DependencyCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
