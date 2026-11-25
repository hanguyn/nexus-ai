from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_session
from app.modules.rca.engine import RCAEngine
from app.webhooks.schemas import AlertmanagerWebhook
from app.webhooks.service import ingest

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/alertmanager")
def receive_alertmanager(body: AlertmanagerWebhook, db: Annotated[Session, Depends(get_session)]):
    with db.begin():
        affected = ingest(db, body.alerts)
        if affected:
            engine = RCAEngine(db)
            for incident_id in sorted(affected):
                engine.analyze_incident(incident_id)
    return {"processed": len(body.alerts)}
