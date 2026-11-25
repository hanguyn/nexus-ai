from enum import StrEnum


class DeviceType(StrEnum):
    router = "router"
    switch = "switch"
    firewall = "firewall"
    server = "server"


class DependencyType(StrEnum):
    physical_link = "physical_link"
    routing_next_hop = "routing_next_hop"
    vpn_tunnel = "vpn_tunnel"
    hosted_service = "hosted_service"


class AlertStatus(StrEnum):
    firing = "firing"
    resolved = "resolved"


class IncidentStatus(StrEnum):
    new = "new"
    acknowledged = "acknowledged"
    investigating = "investigating"
    resolved = "resolved"
    closed = "closed"
