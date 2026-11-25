from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Device, Incident
from app.modules.assistant.llm_adapter import LLMAdapter
from app.modules.assistant.models import AIRecommendation
from app.modules.rca.engine import ranked_causes
from app.modules.troubleshooting.service import initialize_runs

KNOWN_METRICS = {
    "ifOperStatus", "up", "probe_success", "traffic_in", "traffic_out", "latency", "traffic_latency", "packet_loss_pct",
}


def build_context(db: Session, incident: Incident) -> dict:
    all_candidates = ranked_causes(db, incident.id)
    candidates = []
    for cause in all_candidates[:5]:
        evidence = []
        for item in cause.evidence[:20]:
            source = item.raw_reference_json
            entry = {
                "evidence_id": item.id, "observed_at": item.observed_at.isoformat(),
                "kind": item.evidence_type.value, "weight": item.weight,
            }
            metric = source.get("metric")
            value = source.get("value")
            if isinstance(metric, str) and metric in KNOWN_METRICS and isinstance(value, (int, float)):
                entry.update(metric=metric, value=value)
            evidence.append(entry)
        candidates.append({
            "rank": cause.rank, "device_id": cause.candidate_device_id,
            "status": cause.verification_status.value, "confidence": cause.confidence_score,
            "missing_evidence_count": len(cause.missing_data_json), "evidence": evidence,
        })

    # Only typed, allowlisted fields are projected. Raw payloads, notes, names and credentials stay local.
    return {
        "incident_id": incident.id,
        "incident_status": incident.status.value,
        "affected_targets": len({(alert.device_id or alert.instance) for alert in incident.alerts}),
        "incomplete": not candidates or any(
            cause.missing_data_json or not cause.evidence for cause in all_candidates
        ),
        "candidates": candidates,
    }


def explain_incident(
    db: Session, incident_id: int, *, adapter: LLMAdapter | None = None,
) -> AIRecommendation:
    incident = db.scalar(select(Incident).where(Incident.id == incident_id).with_for_update())
    if incident is None:
        raise LookupError("Incident not found")
    adapter = adapter or LLMAdapter()
    context = build_context(db, incident)
    hostname = None
    if adapter.provider == "mock" and context["candidates"]:
        device_id = context["candidates"][0]["device_id"]
        if device_id is not None:
            hostname = db.scalar(select(Device.hostname).where(Device.id == device_id))
    result = adapter.explain(context, hostname=hostname)
    output = result.output
    recommendation = AIRecommendation(
        incident_id=incident.id, model_provider=result.provider, model_name=result.model,
        executive_summary=output.executive_summary, technical_explanation=output.technical_explanation,
        impact_assessment=output.impact_assessment, limitations_note=output.limitations_note,
        checklist_json=[dict(step.model_dump(mode="json"), step_title=step.title) for step in output.checklist],
        evidence_citations_json=[item.model_dump(mode="json") for item in output.evidence_citations],
    )
    db.add(recommendation)
    initialize_runs(db, incident.id, output.checklist)
    db.flush()
    return recommendation
