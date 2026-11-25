from datetime import UTC, datetime
from uuid import uuid4

import httpx
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db import engine, get_session
from app.integrations.prometheus.client import QUERIES, PrometheusClient, get_prometheus_client
from app.main import app
from app.models import Device, Site
from app.modules.anomaly.detectors import (
    FEATURES, EWMADetector, IsolationForestDetector, ZScoreDetector,
)


@pytest.mark.parametrize("detector", [ZScoreDetector(), EWMADetector()])
def test_statistical_detectors(detector):
    history = pd.Series(100 + np.sin(np.arange(80)))
    assert not detector.detect(history, 100).is_anomaly
    assert detector.detect(history, 130).is_anomaly
    assert detector.detect(history, 70).is_anomaly
    assert detector.detect(history.iloc[:3], 130) is None
    assert detector.detect(pd.Series([1.0] * 10), 0.0).is_anomaly


def test_isolation_forest():
    rng = np.random.default_rng(42)
    history = pd.DataFrame(
        rng.normal(loc=[100, 75, 0.02], scale=[5, 4, 0.002], size=(120, 3)), columns=FEATURES,
    )
    detector = IsolationForestDetector()
    normal = pd.Series([100, 75, 0.02], index=FEATURES)
    spike = pd.Series([800, 500, 0.8], index=FEATURES)
    assert not detector.detect(history, normal).is_anomaly
    assert detector.detect(history, spike).is_anomaly
    fallback = detector.detect(history.iloc[:20], spike)
    assert fallback.is_anomaly
    assert fallback.explanation["fallback"] == "zscore"


@pytest.fixture
def api():
    with engine.connect() as connection, connection.begin() as transaction:
        with Session(bind=connection, join_transaction_mode="create_savepoint") as db:
            suffix = uuid4().hex
            site = Site(name=f"Anomaly test {suffix}")
            db.add(site)
            db.flush()
            device = Device(
                site_id=site.id, hostname=f"test-{suffix}", ip_address=f"snmp-{suffix}",
                device_type="router",
            )
            db.add(device)
            db.flush()
            device_id, address = device.id, device.ip_address
            db.add(Device(
                site_id=site.id, hostname=f"inactive-{suffix}", ip_address=f"off-{suffix}",
                device_type="router", monitoring_enabled=False,
            ))
            db.commit()

        def session():
            with Session(bind=connection, join_transaction_mode="create_savepoint") as db:
                yield db

        calls = []
        settings = {"short": False, "fail": False}

        def prometheus_response(request):
            assert request.url.path == "/api/v1/query_range"
            query = request.url.params["query"]
            calls.append(query)
            if settings["fail"]:
                return httpx.Response(503)
            end = float(request.url.params["end"])
            step = float(request.url.params["step"])
            assert end - float(request.url.params["start"]) == 3600 and step == 15
            samples = 2 if settings["short"] else 80
            values = [
                [end - (samples - 1 - i) * step, str(100 + np.sin(i))]
                for i in range(samples)
            ]
            if not settings["short"] and query == QUERIES["traffic_in"]:
                values[-1][1] = "900"
            return httpx.Response(200, json={
                "status": "success",
                "data": {"resultType": "matrix", "result": [
                    {"metric": {"instance": address}, "values": values},
                ]},
            })

        with httpx.Client(
            base_url="http://prometheus:9090", transport=httpx.MockTransport(prometheus_response)
        ) as http:
            app.dependency_overrides[get_session] = session
            app.dependency_overrides[get_prometheus_client] = lambda: PrometheusClient(http)
            try:
                with TestClient(app) as client:
                    yield client, device_id, calls, settings
            finally:
                app.dependency_overrides.pop(get_session)
                app.dependency_overrides.pop(get_prometheus_client)
                transaction.rollback()


def test_scan_persists_results_and_filters(api):
    client, device_id, calls, _ = api
    response = client.post("/api/v1/anomalies/scan")
    assert response.status_code == 200, response.text
    assert response.json()["results_saved"] == 9
    assert set(calls) == set(QUERIES.values())

    endpoint = "/api/v1/anomalies"
    detected = client.get(endpoint, params={"device_id": device_id, "is_anomaly": True}).json()
    assert {"zscore", "ewma"} <= {item["algorithm"] for item in detected}
    assert all(item["device_id"] == device_id and item["is_anomaly"] for item in detected)
    assert not any(item["explanation_json"]["synthetic"] for item in detected)

    normal = client.get(endpoint, params={"device_id": device_id, "is_anomaly": False}).json()
    assert normal and not any(item["is_anomaly"] for item in normal)
    all_results = client.get(endpoint, params={"device_id": device_id}).json()
    assert len(all_results) == 9
    assert all(
        datetime.fromisoformat(entry["window_start"]) < datetime.fromisoformat(entry["window_end"])
        for entry in all_results
    )


def test_scan_synthetic_with_short_history(api):
    client, device_id, _, settings = api
    settings["short"] = True
    assert client.post("/api/v1/anomalies/scan").json()["results_saved"] == 0
    response = client.post("/api/v1/anomalies/scan", params={"synthetic_spike": True})
    assert response.status_code == 200, response.text
    assert response.json()["anomalies_detected"] > 0
    records = client.get("/api/v1/anomalies", params={"device_id": device_id, "is_anomaly": True}).json()
    assert records and all(item["explanation_json"]["synthetic"] for item in records)


def test_scan_prometheus_failure(api):
    client, device_id, _, settings = api
    settings["fail"] = True
    response = client.post("/api/v1/anomalies/scan")
    assert response.status_code == 502
    assert client.get("/api/v1/anomalies", params={"device_id": device_id}).json() == []
