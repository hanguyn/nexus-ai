from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_session
from app.inventory.schemas import (
    DependencyCreate, DependencyRead, DependencyUpdate, DeviceCreate, DeviceRead,
    DeviceUpdate, SiteCreate, SiteRead, SiteUpdate,
)
from app.models import Device, DeviceDependency, Site

router = APIRouter(tags=["inventory"])
Database = Annotated[Session, Depends(get_session)]


def get_entity(db, model, entity_id):
    entity = db.get(model, entity_id)
    if entity is None:
        raise HTTPException(404, "Resource not found")
    return entity


def save(db):
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        detail = {
            "23503": "Referenced resource does not exist or is still in use",
            "23505": "Resource conflicts with an existing record",
            "23514": "Resource violates a topology constraint",
        }.get(error.orig.sqlstate)
        if detail is None:
            raise
        raise HTTPException(409, detail) from error


def update_entity(db, entity, body: BaseModel):
    for field, value in body.model_dump(exclude_unset=True).items():
        if value is None and not entity.__table__.columns[field].nullable:
            raise HTTPException(422, f"{field} cannot be null")
        setattr(entity, field, value)
    save(db)
    return entity


@router.get("/sites", response_model=list[SiteRead])
def list_sites(db: Database):
    return db.scalars(select(Site).order_by(Site.id)).all()


@router.post("/sites", response_model=SiteRead, status_code=201)
def create_sites(body: SiteCreate, db: Database):
    entity = Site(**body.model_dump())
    db.add(entity)
    save(db)
    return entity


@router.get("/sites/{entity_id}", response_model=SiteRead)
def get_site(entity_id: int, db: Database):
    return get_entity(db, Site, entity_id)


@router.patch("/sites/{entity_id}", response_model=SiteRead)
def update_site(entity_id: int, body: SiteUpdate, db: Database):
    return update_entity(db, get_entity(db, Site, entity_id), body)


@router.delete("/sites/{entity_id}", status_code=204)
def delete_site(entity_id: int, db: Database):
    db.delete(get_entity(db, Site, entity_id))
    save(db)


@router.get("/devices", response_model=list[DeviceRead])
def list_devices(db: Database):
    return db.scalars(select(Device).order_by(Device.id)).all()


@router.post("/devices", response_model=DeviceRead, status_code=201)
def create_devices(body: DeviceCreate, db: Database):
    entity = Device(**body.model_dump())
    db.add(entity)
    save(db)
    return entity


@router.get("/devices/{entity_id}", response_model=DeviceRead)
def get_device(entity_id: int, db: Database):
    return get_entity(db, Device, entity_id)


@router.patch("/devices/{entity_id}", response_model=DeviceRead)
def update_device(entity_id: int, body: DeviceUpdate, db: Database):
    return update_entity(db, get_entity(db, Device, entity_id), body)


@router.delete("/devices/{entity_id}", status_code=204)
def delete_device(entity_id: int, db: Database):
    db.delete(get_entity(db, Device, entity_id))
    save(db)


@router.get("/dependencies", response_model=list[DependencyRead])
def list_dependencies(db: Database):
    return db.scalars(select(DeviceDependency).order_by(DeviceDependency.id)).all()


@router.post("/dependencies", response_model=DependencyRead, status_code=201)
def create_dependencies(body: DependencyCreate, db: Database):
    entity = DeviceDependency(**body.model_dump())
    db.add(entity)
    save(db)
    return entity


@router.get("/dependencies/{entity_id}", response_model=DependencyRead)
def get_dependency(entity_id: int, db: Database):
    return get_entity(db, DeviceDependency, entity_id)


@router.patch("/dependencies/{entity_id}", response_model=DependencyRead)
def update_dependency(entity_id: int, body: DependencyUpdate, db: Database):
    return update_entity(db, get_entity(db, DeviceDependency, entity_id), body)


@router.delete("/dependencies/{entity_id}", status_code=204)
def delete_dependency(entity_id: int, db: Database):
    db.delete(get_entity(db, DeviceDependency, entity_id))
    save(db)
