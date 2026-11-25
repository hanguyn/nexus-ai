from dataclasses import dataclass


@dataclass(frozen=True)
class SimulatedAlert:
    device: str
    name: str
    offset: int = 0
    interface: str | None = None


@dataclass(frozen=True)
class Scenario:
    title: str
    description: str
    alerts: tuple[SimulatedAlert, ...]


SCENARIOS = {
    "wan_outage": Scenario(
        "Simulate WAN Cascade Outage",
        "The WAN interface fails 10 seconds before downstream router, VPN, and server probes.",
        (
            SimulatedAlert("wan", "NetworkInterfaceDown", interface="Gi0/0"),
            SimulatedAlert("core", "BlackboxProbeFailed", 10),
            SimulatedAlert("vpn", "BlackboxProbeFailed", 10),
            SimulatedAlert("app", "BlackboxProbeFailed", 10),
        ),
    ),
    "vpn_tunnel_down": Scenario(
        "Simulate VPN Tunnel Down",
        "The branch tunnel goes down and probe packet loss spikes.",
        (SimulatedAlert("vpn", "NetworkInterfaceDown", interface="Tunnel0"),),
    ),
    "bandwidth_spike": Scenario(
        "Simulate Traffic Anomaly Spike",
        "Outbound traffic on Gi0/1 spikes and is evaluated by Z-Score and Isolation Forest.",
        (SimulatedAlert("core", "NetworkBandwidthSpike", interface="Gi0/1"),),
    ),
}

DEVICES = {
    "wan": ("ISP-WAN-Gateway", "10.0.0.1", "router"),
    "core": ("Core-Router-R1", "192.168.10.1", "router"),
    "distribution": ("Dist-Switch-SW1", "192.168.10.2", "switch"),
    "app": ("Ubuntu-App-Server", "192.168.10.20", "server"),
    "vpn": ("VPN-Branch-Tunnel", "172.16.1.1", "firewall"),
}

LINKS = (
    ("wan", "core", "routing_next_hop"),
    ("core", "distribution", "physical_link"),
    ("distribution", "app", "physical_link"),
    ("distribution", "vpn", "vpn_tunnel"),
)
