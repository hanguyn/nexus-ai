from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db import engine, get_session
from app.main import app


def test_vps_demo_e2e(monkeypatch):
    monkeypatch.setenv("DEMO_READ_ONLY_MODE", "true")
    prefix = "/api/v1"
    sim = f"{prefix}/simulator"

    with engine.connect() as connection, connection.begin() as transaction:
        def session():
            with Session(bind=connection, join_transaction_mode="create_savepoint") as db:
                yield db

        app.dependency_overrides[get_session] = session
        try:
            with TestClient(app) as client:
                def call(method, path, payload=None, status=200, headers=None):
                    response = client.request(method, path, json=payload, headers=headers)
                    assert response.status_code == status, response.text
                    return response.json()

                call("POST", f"{sim}/reset")
                topology = call("POST", f"{sim}/seed-topology")
                assert call("POST", f"{sim}/seed-topology") == topology
                assert len(topology["device_ids"]) == 5
                saved = {item["id"]: item for item in call("GET", f"{prefix}/devices")}
                assert [saved[device_id]["ip_address"] for device_id in topology["device_ids"]] == [
                    "10.0.0.1", "192.168.10.1", "192.168.10.2", "192.168.10.20", "172.16.1.1",
                ]
                call("DELETE", f"{prefix}/sites/{topology['site_id']}", status=403)
                call("PATCH", f"{prefix}/devices/{topology['device_ids'][0]}",
                     {"monitoring_enabled": False}, status=403)
                call("POST", f"{prefix}/webhooks/alertmanager", {"alerts": []}, status=403,
                     headers={"X-Nexus-Public-Proxy": "1"})

                wan = call("POST", f"{sim}/trigger/wan_outage")
                assert call("POST", f"{sim}/trigger/wan_outage") == wan
                wan_path = f"{prefix}/incidents/{wan['incident_id']}"
                incident = call("GET", wan_path)
                assert incident["status"] == "new" and len(incident["alerts"]) == 4
                starts = [datetime.fromisoformat(alert["starts_at"]) for alert in incident["alerts"]]
                assert [(value - starts[0]).total_seconds() for value in starts] == [0, 10, 10, 10]

                root = call("GET", f"{wan_path}/rca")[0]
                assert root["rank"] == 1 and root["candidate_device_id"] == topology["device_ids"][0]
                assert root["candidate_component"] == "ISP-WAN-Gateway/Gi0/0"
                evidence = {row["evidence_type"]: row for row in root["evidence"]}
                assert {"topology", "temporal"} <= evidence.keys()
                assert len(evidence["topology"]["raw_reference_json"]["paths"]) == 3
                recommendation = call("GET", f"{wan_path}/assistant")["recommendation"]
                assert recommendation["model_provider"] == "mock"
                assert evidence["topology"]["id"] in {
                    row["evidence_id"] for row in recommendation["evidence_citations_json"]
                }
                print(f"WAN RCA rank 1: {root['candidate_component']} ({root['confidence_score']:.4f})")

                live_fingerprint = "demo-test-live-" + uuid4().hex
                call("POST", f"{prefix}/webhooks/alertmanager", {"alerts": [{
                    "status": "firing", "fingerprint": live_fingerprint,
                    "startsAt": datetime.now(UTC).isoformat(),
                    "labels": {"alertname": "LiveVerificationEvent", "instance": "10.0.0.1"},
                }]})
                live_incident = next(item for item in call("GET", f"{prefix}/incidents")
                                     if any(a["fingerprint"] == live_fingerprint for a in item["alerts"]))
                assert live_incident["id"] != wan["incident_id"]

                assert call("POST", f"{sim}/recover/wan_outage")["status"] == "resolved"
                recovered = call("GET", wan_path)
                verification = call("GET", f"{wan_path}/assistant")["verification"]
                assert recovered["status"] == "resolved"
                assert all(alert["status"] == "resolved" for alert in recovered["alerts"])
                assert verification["is_recovered"]
                assert all(row["target_metric_or_probe"].startswith("simulated:") for row in verification["results"])
                assert "Simulator telemetry" in recovered["history"][-1]["note"]

                vpn = call("POST", f"{sim}/trigger/vpn_tunnel_down")
                bandwidth = call("POST", f"{sim}/trigger/bandwidth_spike")
                anomalies = {}
                for device_index, scenario in [(4, "vpn_tunnel_down"), (1, "bandwidth_spike")]:
                    rows = call("GET", f"{prefix}/anomalies?device_id={topology['device_ids'][device_index]}")
                    anomalies[scenario] = [
                        row for row in rows if row["explanation_json"].get("scenario") == scenario
                    ]
                assert any(row["is_anomaly"] and row["metric_name"] == "packet_loss_pct"
                           for row in anomalies["vpn_tunnel_down"])
                assert {row["algorithm"] for row in anomalies["bandwidth_spike"] if row["is_anomaly"]} == {
                    "zscore", "isolation_forest",
                }
                bandwidth_rca = call("GET", f"{prefix}/incidents/{bandwidth['incident_id']}/rca")[0]
                assert bandwidth_rca["candidate_component"] == "Core-Router-R1/Gi0/1"
                assert sum(row["evidence_type"] == "anomaly" for row in bandwidth_rca["evidence"]) == 2

                assert call("POST", f"{sim}/reset")["deleted_incidents"] == 3
                for deleted in [wan, vpn, bandwidth]:
                    call("GET", f"{prefix}/incidents/{deleted['incident_id']}", status=404)
                call("GET", f"{prefix}/incidents/{live_incident['id']}")
                assert call("POST", f"{sim}/seed-topology") == topology
                assert not any(row["explanation_json"].get("scenario") == "bandwidth_spike" for row in call(
                    "GET", f"{prefix}/anomalies?device_id={topology['device_ids'][1]}"
                ))
        finally:
            app.dependency_overrides.pop(get_session)
            transaction.rollback()
