import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.db import engine, get_session
from app.integrations.prometheus.client import PrometheusClient, get_prometheus_client
from app.main import app
from app.modules.assistant.llm_adapter import LLMAdapter, ProviderError
from app.modules.assistant.sanitizer import sanitize_context
from app.modules.assistant.schemas import ChecklistStep


def test_sanitize_context_credentials():
    payload = {
        "snmp_community_encrypted": "simulated-ciphertext",
        "nested": [{"rawPassword": "test-password", "apiKey": "simulated-api-key", "item": 7}],
        "notes": 'SNMP community string: "example-community" password=example-password '
        'snmpwalk -v2c -c embedded-community lab Authorization: Bearer example-bearer '
        'postgresql://name:embedded-password@postgres/db',
        "snmp_config": "snmp-server community ios-secret RO\nrocommunity netsnmp-secret",
        "blob": "-----BEGIN OPENSSH PRIVATE KEY-----\nexample-key\n-----END OPENSSH PRIVATE KEY-----",
    }
    cleaned = sanitize_context(payload)
    output = json.dumps(cleaned)
    for secret in (
        "simulated-ciphertext", "test-password", "simulated-api-key", "example-community",
        "example-password", "embedded-community", "example-bearer", "embedded-password", "example-key",
        "ios-secret", "netsnmp-secret",
    ):
        assert secret not in output
    assert cleaned["nested"] == [{"item": 7}]
    assert "[REDACTED]" in cleaned["notes"]


@pytest.mark.parametrize("command", ["reload", "show interfaces | redirect file", "ping <affected-device>; reboot"])
def test_rejects_non_allowlisted_commands(command):
    with pytest.raises(ValidationError):
        ChecklistStep(command_or_action=command, execution_mode="read_only")
    with pytest.raises(ValidationError):
        ChecklistStep(command_or_action=command, execution_mode="manual_check")


def test_rejects_wrong_evidence_id_or_timestamp(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    observed = datetime.now(UTC)
    context = {"affected_targets": 1, "incomplete": True, "candidates": [{
        "rank": 1, "device_id": 42, "confidence": 0.5, "status": "potential",
        "evidence": [{"evidence_id": 5, "observed_at": observed.isoformat(), "kind": "state"}],
    }]}
    output = LLMAdapter().explain(context).output
    output.evidence_citations[0].observed_at = observed + timedelta(seconds=1)
    with pytest.raises(ProviderError, match="outside"):
        LLMAdapter._validate_citations(output, context)
    output.evidence_citations[0].observed_at = observed
    output.evidence_citations[0].evidence_id = 6
    with pytest.raises(ProviderError, match="outside"):
        LLMAdapter._validate_citations(output, context)


def test_assistant_and_verification_workflow(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    address = "assistant-" + uuid4().hex[:12]
    hostname = f"{address}-router"
    values = {"up": 1, "probe_success": 0, "ifOperStatus": None}
    calls = []

    def prometheus_response(request):
        assert request.url.path == "/api/v1/query"
        query = request.url.params["query"]
        assert "timestamp(" in query and "<= 90" in query
        metric = next(name for name in values if query.startswith(name))
        calls.append(metric)
        samples = [{"metric": {"instance": "different-device", "ifIndex": "7"}, "value": [1, "1"]}]
        if values[metric] is not None:
            samples.append({"metric": {"instance": address, "ifIndex": "7"},
                            "value": [1, str(values[metric])]})
        return httpx.Response(200, json={
            "status": "success", "data": {"resultType": "vector", "result": samples},
        })

    with engine.connect() as connection, connection.begin() as transaction, httpx.Client(
        base_url="http://prometheus:9090", transport=httpx.MockTransport(prometheus_response)
    ) as http:
        def session():
            with Session(bind=connection, join_transaction_mode="create_savepoint") as db:
                yield db

        app.dependency_overrides[get_session] = session
        app.dependency_overrides[get_prometheus_client] = lambda: PrometheusClient(http)
        try:
            with TestClient(app) as client:
                def api(method, path, payload=None, expected=200):
                    response = client.request(method, path, json=payload)
                    assert response.status_code == expected, response.text
                    return response.json()

                prefix = "/api/v1"
                site = api("POST", f"{prefix}/sites", {"name": address}, 201)
                api("POST", f"{prefix}/devices", {
                    "site_id": site["id"], "hostname": hostname, "ip_address": address,
                    "device_type": "router", "snmp_community_encrypted": "private-test-credential",
                }, 201)
                start = (datetime.now(UTC) - timedelta(seconds=20)).isoformat()
                alerts = [{
                    "status": "firing", "fingerprint": f"{address}-{name}", "startsAt": start,
                    "endsAt": "0001-01-01T00:00:00Z", "labels": {
                        "alertname": name, "instance": address, "severity": "critical", **extra,
                    }, "annotations": {"description": "password=annotation-test-secret"},
                } for name, extra in [
                    ("NetworkDeviceDown", {}), ("BlackboxProbeFailed", {}),
                    ("NetworkInterfaceDown", {"ifIndex": "7"}),
                ]]
                api("POST", f"{prefix}/webhooks/alertmanager", {"alerts": alerts})
                incident = next(i for i in api("GET", f"{prefix}/incidents") if i["site_id"] == site["id"])
                path = f"{prefix}/incidents/{incident['id']}"
                rca = api("GET", path + "/rca")
                expected_citations = {item["id"]: item["observed_at"] for item in rca[0]["evidence"]}

                summary = api("POST", path + "/explain")
                assert summary["model_provider"] == "mock"
                assert "VI:" in summary["technical_explanation"] and "EN:" in summary["technical_explanation"]
                assert "private-test-credential" not in json.dumps(summary)
                assert "annotation-test-secret" not in json.dumps(summary)
                assert summary["limitations_note"]
                assert {
                    item["evidence_id"]: datetime.fromisoformat(item["observed_at"])
                    for item in summary["evidence_citations_json"]
                } == {key: datetime.fromisoformat(ts) for key, ts in expected_citations.items()}

                state = api("GET", path + "/assistant")
                assert state["recommendation"]["id"] == summary["id"]
                assert state["verification"] is None
                step = state["troubleshooting_runs"][0]
                assert step["status"] == "pending"
                updated = api("PATCH", f"{prefix}/troubleshooting/{step['id']}", {"operator_note": "Checked health."})
                assert updated["status"] == "completed" and updated["executed_at"]
                assert updated["operator_note"] == "Checked health."
                api("POST", path + "/explain")
                assert api("GET", path + "/assistant")["troubleshooting_runs"][0]["status"] == "completed"

                failed = api("POST", path + "/verify-recovery")
                assert not failed["is_recovered"]
                assert any(row["post_fix_value"] is None and not row["is_recovered"]
                           for row in failed["results"])
                assert api("GET", path)["status"] == "new"
                values.update(up=None, probe_success=None, ifOperStatus=None)
                assert not api("POST", path + "/verify-recovery")["is_recovered"]
                values.update(up=1, probe_success=1, ifOperStatus=1)
                verified = api("POST", path + "/verify-recovery")
                assert verified["is_recovered"] and len(verified["results"]) == 3
                assert {row["pre_fix_value"] for row in verified["results"]} == {0, 2}
                assert all(row["post_fix_value"] == 1 for row in verified["results"])
                assert all(hostname in row["target_metric_or_probe"] for row in verified["results"])
                assert set(calls) == set(values)
                assert api("GET", path + "/assistant")["verification"] == verified
                incident = api("GET", path)
                assert incident["status"] == "resolved" and incident["resolved_at"]
                assert incident["history"][-1]["action"] == "recovery_verified"

                ends_at = datetime.now(UTC).isoformat()
                api("POST", f"{prefix}/webhooks/alertmanager", {
                    "alerts": [dict(alert, status="resolved", endsAt=ends_at) for alert in alerts],
                })
                values.update(up=None, probe_success=0, ifOperStatus=None)
                assert not api("POST", path + "/verify-recovery")["is_recovered"]
                values.update(probe_success=None)
                fallback = api("POST", path + "/verify-recovery")
                assert fallback["is_recovered"]
                assert [row["target_metric_or_probe"] for row in fallback["results"]] == [
                    f"alert_resolution:{hostname}",
                ]
                assert "linked alert resolution" in api("GET", path)["history"][-1]["note"]
        finally:
            app.dependency_overrides.pop(get_session)
            app.dependency_overrides.pop(get_prometheus_client)
            transaction.rollback()
