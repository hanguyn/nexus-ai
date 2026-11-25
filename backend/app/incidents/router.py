from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import get_session
from app.incidents.schemas import IncidentRead
from app.models import Incident
from app.modules.rca.engine import RCAEngine, ranked_causes
from app.modules.rca.schemas import RCARead

router = APIRouter(prefix="/incidents", tags=["incidents"])
Database = Annotated[Session, Depends(get_session)]


def incident_query():
    return select(Incident).options(selectinload(Incident.alerts), selectinload(Incident.history))


@router.get("", response_model=list[IncidentRead])
def list_incidents(db: Database):
    return db.scalars(incident_query().order_by(Incident.id.desc())).all()


@router.get("/{incident_id}", response_model=IncidentRead)
def get_incident(incident_id: int, db: Database):
    incident = db.scalar(incident_query().where(Incident.id == incident_id))
    if incident is None:
        raise HTTPException(404, "Incident not found")
    return incident


@router.post("/{incident_id}/analyze", response_model=list[RCARead])
def analyze_incident(incident_id: int, db: Database):
    try:
        with db.begin():
            candidates = RCAEngine(db).analyze_incident(incident_id)
            return [RCARead.model_validate(candidate) for candidate in candidates]
    except LookupError as exc:
        raise HTTPException(404, "Incident not found") from exc


@router.get("/{incident_id}/rca", response_model=list[RCARead])
def get_rca(incident_id: int, db: Database):
    if db.get(Incident, incident_id) is None:
        raise HTTPException(404, "Incident not found")
    return ranked_causes(db, incident_id)
