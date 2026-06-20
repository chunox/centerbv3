"""Gates de workflow exclusivos de Scrum."""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.entities import ProjectRecord
from app.services.scrum_v2_structure import is_sprint_record


def gate_parent_is_sprint(db: Session, entity: ProjectRecord) -> None:
    if entity.parent_id is None:
        raise HTTPException(
            status_code=409, detail="La historia no está asignada a un sprint"
        )
    parent = db.get(ProjectRecord, entity.parent_id)
    if parent is None or not is_sprint_record(parent):
        raise HTTPException(
            status_code=409,
            detail="La historia no está planificada en un sprint",
        )
