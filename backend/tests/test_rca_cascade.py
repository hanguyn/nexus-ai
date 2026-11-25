from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db import engine, get_session
from app.main import app
from app.models import Device, DeviceDependency, Site
from app.modules.anomaly.models import AnomalyResult


def test_rca_cascade():
    start = datetime.now(UTC) - timedelta(seconds=30)
    suffix = uuid4().hex[:12]
    with engine.connect() as connection, connection.begin() as transaction:
        def session():
            with Session(bind=connection, join_transaction_mode="create_savepoint") as db:
                yield db

        app.dependency_overrides[get_session] = session
        try:
            with TestClient(app) as client:
                site = client.post("/api/v1/sites", json={"name": f"Cascade-{suffix}"}).json()
                names = ["WAN-Gateway", "Core-Router", "App-Server"]
                addresses = [f"cascade-{i}-{suffix}" for i in range(3)]
                with Session(bind=connection, join_transaction_mode="create_savepoint") as db:
                    devices = [
                        Device(site_id=site["id"], hostname=name, ip_address=address, device_type=kind)
                        for name, address, kind in zip(names, addresses, ["router", "router", "server"])
                    ]
                    db.add_all(devices)
                    db.flush()
                    device_ids = [device.id for device in devices]
                    for upstream, downstream in zip(device_ids, device_ids[1:]):
                        db.add(DeviceDependency(
                            upstream_device_id=upstream, downstream_device_id=downstream,
                            dependency_type="routing_next_hop",
                        ))
                    for metric, when, synthetic in [
                        ("traffic_in", start, False),
                        ("traffic_out", start - timedelta(minutes=5), False),
                        ("probe_success", start, True),
                    ]:
                        db.add(AnomalyResult(
                            device_id=device_ids[0], metric_name=metric, algorithm="zscore",
                            observed_value=0, baseline_mean=1, baseline_std=0.1, anomaly_score=10,
                            is_anomaly=True, severity="high", window_start=when - timedelta(minutes=10),
                            window_end=when, explanation_json={"synthetic": synthetic},
                        ))
                    db.commit()

                def alert(index, name="NetworkDeviceDown"):
                    when = start + timedelta(seconds=0 if index == 0 else 10)
                    return {
                        "status": "firing", "fingerprint": f"{suffix}-{index}-{name}",
                        "startsAt": when.isoformat(), "endsAt": "0001-01-01T00:00:00Z",
                        "labels": {"alertname": name, "instance": addresses[index], "severity": "critical"},
                        "annotations": {},
                    }

                def notify(*alerts):
                    response = client.post("/api/v1/webhooks/alertmanager", json={"alerts": alerts})
                    assert response.status_code == 200, response.text

                events = [alert(index) for index in range(3)]
                notify(*reversed(events))
                incident = next(item for item in client.get("/api/v1/incidents").json()
                                if item["site_id"] == site["id"])
                assert len(incident["alerts"]) == 3
                path = f"/api/v1/incidents/{incident['id']}"
                response = client.get(f"{path}/rca")
                assert response.status_code == 200, response.text
                ranking = response.json()
                assert [row["candidate_device_id"] for row in ranking] == device_ids
                assert [row["rank"] for row in ranking] == [1, 2, 3]
                for result in ranking:
                    kinds = sorted(item["evidence_type"] for item in result["evidence"])
                    print(f"RCA #{result['rank']} {result['candidate_component']} "
                          f"{result['confidence_score']:.4f} {result['verification_status']} "
                          f"{','.join(kinds)}")

                root = ranking[0]
                assert root["candidate_component"] == "WAN-Gateway"
                assert root["verification_status"] == "potential"
                assert root["missing_data_json"] and root["recommended_checks"]
                evidence = {item["evidence_type"]: item["raw_reference_json"] for item in root["evidence"]}
                assert {"topology", "temporal", "state", "anomaly"} <= evidence.keys()
                assert evidence["temporal"]["seconds_after_first"] == 0
                assert evidence["anomaly"]["metric"] == "traffic_in"
                paths = {item["downstream_device_id"]: item for item in evidence["topology"]["paths"]}
                assert paths[device_ids[-1]]["path_device_ids"] == device_ids
                assert all(item["secondary_symptom_alert_ids"] for item in paths.values())

                notify(*events)
                assert client.get(f"{path}/rca").json() == ranking

                probe = alert(0, "BlackboxProbeFailed")
                notify(probe)
                verified = client.get(f"{path}/rca").json()[0]
                assert verified["candidate_device_id"] == device_ids[0]
                assert verified["verification_status"] == "verified" and verified["missing_data_json"] == []
                assert any(item["evidence_type"] == "metric" and
                           item["raw_reference_json"]["metric"] == "probe_success"
                           for item in verified["evidence"])

                manual = client.post(f"{path}/analyze")
                assert manual.status_code == 200, manual.text
                assert [row["candidate_device_id"] for row in manual.json()] == device_ids
                assert client.get(f"{path}/rca").json() == manual.json()

                ends_at = (start + timedelta(seconds=25)).isoformat()
                notify(*(dict(item, status="resolved", endsAt=ends_at) for item in [*events, probe]))
                assert client.get(path).json()["status"] == "resolved"
                resolved_ranking = client.get(f"{path}/rca").json()
                assert resolved_ranking[0]["id"] != manual.json()[0]["id"]
                assert resolved_ranking[0]["verification_status"] == "verified"
        finally:
            app.dependency_overrides.pop(get_session)
            transaction.rollback()
