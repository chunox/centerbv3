"""Bloqueantes externos de entidades Scrum.

Un bloqueante es un impedimento externo (texto markdown) que bloquea el avance
de una épica, historia o tarea dev. No es una dependencia entre tareas.

Cuando existe al menos un bloqueante activo (resolved_at IS NULL), el campo
`data.bloqueada` del record se setea en True. Al resolver todos, vuelve a False.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Sequence
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Project, ProjectRecord, ProjectRecordBlocker


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ─── Helpers ───────────────────────────────────────────────────────────────────


def _sync_bloqueada(record: ProjectRecord, db: Session) -> bool:
    """Recalcula data.bloqueada según existan bloqueantes activos. Devuelve el nuevo valor."""
    has_active = db.scalar(
        select(ProjectRecordBlocker.id)
        .where(
            ProjectRecordBlocker.record_id == record.id,
            ProjectRecordBlocker.resolved_at.is_(None),
        )
        .limit(1)
    )
    new_value = has_active is not None
    data = dict(record.data or {})
    data["bloqueada"] = new_value
    record.data = data
    return new_value


def _get_blocker_or_404(
    db: Session, record_id: UUID, blocker_id: UUID
) -> ProjectRecordBlocker:
    blocker = db.get(ProjectRecordBlocker, blocker_id)
    if blocker is None or blocker.record_id != record_id:
        raise HTTPException(status_code=404, detail="Bloqueante no encontrado")
    return blocker


# ─── Queries ───────────────────────────────────────────────────────────────────


def list_blockers(
    db: Session, record_id: UUID, *, active_only: bool = False
) -> Sequence[ProjectRecordBlocker]:
    q = select(ProjectRecordBlocker).where(ProjectRecordBlocker.record_id == record_id)
    if active_only:
        q = q.where(ProjectRecordBlocker.resolved_at.is_(None))
    q = q.order_by(ProjectRecordBlocker.created_at.desc())
    return db.scalars(q).all()


# ─── Mutations ─────────────────────────────────────────────────────────────────


def add_blocker(
    db: Session,
    *,
    project: Project,
    record: ProjectRecord,
    description: str,
    actor_id: UUID,
) -> ProjectRecordBlocker:
    if record.project_id != project.id:
        raise HTTPException(status_code=404, detail="Record no pertenece al proyecto")
    if not description or not description.strip():
        raise HTTPException(status_code=422, detail="La descripción no puede estar vacía")

    blocker = ProjectRecordBlocker(
        id=uuid.uuid4(),
        project_id=project.id,
        record_id=record.id,
        description=description.strip(),
        created_by=actor_id,
        created_at=_utcnow(),
    )
    db.add(blocker)
    db.flush()
    _sync_bloqueada(record, db)
    db.commit()
    db.refresh(blocker)
    return blocker


def resolve_blocker(
    db: Session,
    *,
    project: Project,
    record: ProjectRecord,
    blocker_id: UUID,
    actor_id: UUID,
) -> ProjectRecordBlocker:
    blocker = _get_blocker_or_404(db, record.id, blocker_id)
    if blocker.resolved_at is not None:
        raise HTTPException(status_code=409, detail="El bloqueante ya fue resuelto")
    blocker.resolved_at = _utcnow()
    blocker.resolved_by = actor_id
    db.flush()
    _sync_bloqueada(record, db)
    db.commit()
    db.refresh(blocker)
    return blocker


def delete_blocker(
    db: Session,
    *,
    project: Project,
    record: ProjectRecord,
    blocker_id: UUID,
    actor_id: UUID,
) -> None:
    blocker = _get_blocker_or_404(db, record.id, blocker_id)
    db.delete(blocker)
    db.flush()
    _sync_bloqueada(record, db)
    db.commit()
