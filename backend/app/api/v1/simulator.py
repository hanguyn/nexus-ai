from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.modules.simulator.models import DemoRun
from app.modules.simulator.scenarios import SCENARIOS
from app.modules.simulator.service import TopologyConflict, recover, reset, seed_topology, trigger

router = APIRouter(prefix="/simulator", tags=["simulator"])
Database = Annotated[Session, Depends(get_session)]


@router.get("/scenarios")
def list_scenarios(db: Database):
    runs = {run.scenario: run.incident_id for run in db.scalars(
        select(DemoRun).where(DemoRun.active.is_(True))
    )}
    return [
        {"id": key, "title": scenario.title, "description": scenario.description,
         "active_incident_id": runs.get(key)}
        for key, scenario in SCENARIOS.items()
    ]


@router.post("/seed-topology")
def seed(db: Database):
    try:
        with db.begin():
            site, devices = seed_topology(db)
            return {"site_id": site.id, "device_ids": [device.id for device in devices.values()]}
    except TopologyConflict as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/trigger/{scenario}")
def start_scenario(scenario: str, db: Database):
    if scenario not in SCENARIOS:
        raise HTTPException(404, "Unknown simulator scenario")
    try:
        with db.begin():
            run = trigger(db, scenario)
            return {"scenario": scenario, "incident_id": run.incident_id, "status": "active"}
    except TopologyConflict as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/recover/{scenario}")
def recover_scenario(scenario: str, db: Database):
    if scenario not in SCENARIOS:
        raise HTTPException(404, "Unknown simulator scenario")
    with db.begin():
        run = recover(db, scenario)
        return {"scenario": scenario, "incident_id": run.incident_id if run else None,
                "status": "resolved" if run else "inactive"}


@router.post("/reset")
def reset_simulator(db: Database):
    with db.begin():
        return {"deleted_incidents": reset(db)}
