"""API de bloqueantes externos de entidades Scrum.

Un bloqueante es un impedimento externo (texto markdown) — no una dependencia entre tareas.
Aplica a épicas, historias y tareas dev en proyectos Scrum sin cliente.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.v1.auth_deps import get_current_actor_id
from app.api.v1.deps import get_project_or_404
from app.database import get_db
from app.models.entities import ProjectRecord
from app.services import record_blockers
from fastapi import HTTPException

router = APIRouter(prefix="/projects", tags=["blockers"])


# ─── Schemas ───────────────────────────────────────────────────────────────────


class BlockerCreate(BaseModel):
    description: str = Field(min_length=1, max_length=5000)


class BlockerRead(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    record_id: UUID
    description: str
    created_by: UUID
    created_at: datetime
    resolved_at: datetime | None = None
    resolved_by: UUID | None = None


# ─── Helpers ───────────────────────────────────────────────────────────────────


def _get_record_or_404(
    project_id: UUID, record_id: UUID, db: Session
) -> ProjectRecord:
    record = db.get(ProjectRecord, record_id)
    if record is None or record.project_id != project_id:
        raise HTTPException(status_code=404, detail="Entidad no encontrada")
    return record


# ─── Endpoints ─────────────────────────────────────────────────────────────────


@router.get(
    "/{project_id}/records/{record_id}/blockers",
    response_model=list[BlockerRead],
)
def list_blockers(
    project_id: UUID,
    record_id: UUID,
    active_only: bool = False,
    db: Session = Depends(get_db),
    actor_id: UUID = Depends(get_current_actor_id),
) -> list[BlockerRead]:
    get_project_or_404(project_id, db)
    _get_record_or_404(project_id, record_id, db)
    items = record_blockers.list_blockers(db, record_id, active_only=active_only)
    return [BlockerRead.model_validate(b) for b in items]


@router.post(
    "/{project_id}/records/{record_id}/blockers",
    response_model=BlockerRead,
    status_code=201,
)
def create_blocker(
    project_id: UUID,
    record_id: UUID,
    body: BlockerCreate,
    db: Session = Depends(get_db),
    actor_id: UUID = Depends(get_current_actor_id),
) -> BlockerRead:
    project = get_project_or_404(project_id, db)
    record = _get_record_or_404(project_id, record_id, db)
    blocker = record_blockers.add_blocker(
        db,
        project=project,
        record=record,
        description=body.description,
        actor_id=actor_id,
    )
    return BlockerRead.model_validate(blocker)


@router.post(
    "/{project_id}/records/{record_id}/blockers/{blocker_id}/resolve",
    response_model=BlockerRead,
)
def resolve_blocker(
    project_id: UUID,
    record_id: UUID,
    blocker_id: UUID,
    db: Session = Depends(get_db),
    actor_id: UUID = Depends(get_current_actor_id),
) -> BlockerRead:
    project = get_project_or_404(project_id, db)
    record = _get_record_or_404(project_id, record_id, db)
    blocker = record_blockers.resolve_blocker(
        db,
        project=project,
        record=record,
        blocker_id=blocker_id,
        actor_id=actor_id,
    )
    return BlockerRead.model_validate(blocker)


@router.delete(
    "/{project_id}/records/{record_id}/blockers/{blocker_id}",
    status_code=204,
)
def delete_blocker(
    project_id: UUID,
    record_id: UUID,
    blocker_id: UUID,
    db: Session = Depends(get_db),
    actor_id: UUID = Depends(get_current_actor_id),
) -> None:
    project = get_project_or_404(project_id, db)
    record = _get_record_or_404(project_id, record_id, db)
    record_blockers.delete_blocker(
        db,
        project=project,
        record=record,
        blocker_id=blocker_id,
        actor_id=actor_id,
    )
