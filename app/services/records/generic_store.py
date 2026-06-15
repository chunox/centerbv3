"""CRUD de project_records."""
from __future__ import annotations

import json
import uuid
from datetime import date
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.records.types import RecordDTO, RecordRef
from app.models.entities import (
    Project,
    ProjectRecord,
    ProjectRecordAssignee,
    ProjectRecordDependency,
    ProjectRecordType,
    User,
)
from app.services.records.field_validation import apply_validated_data, validate_record_data
from app.services.workflow.engine import apply_record_transition


def _parse_data(raw: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw) if raw else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _to_dto(row: ProjectRecord) -> RecordDTO:
    return RecordDTO(
        id=row.id,
        project_id=row.project_id,
        record_type=row.record_type,
        titulo=row.titulo,
        descripcion=row.descripcion,
        estado=row.estado,
        parent_id=row.parent_id,
        data=_parse_data(row.data),
        fecha_inicio=row.fecha_inicio,
        fecha_fin=row.fecha_fin,
        orden=row.orden,
        assignee_ids=sorted(a.user_id for a in row.assignees),
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _get_record_type(db: Session, project_id: uuid.UUID, key: str) -> ProjectRecordType:
    rt = db.scalar(
        select(ProjectRecordType).where(
            ProjectRecordType.project_id == project_id,
            ProjectRecordType.key == key,
        )
    )
    if rt is None:
        raise HTTPException(status_code=422, detail=f"Tipo de registro '{key}' no configurado")
    return rt


def list_records(
    db: Session,
    project_id: uuid.UUID,
    *,
    record_type: str | None = None,
    parent_id: uuid.UUID | None = None,
) -> list[RecordDTO]:
    stmt = select(ProjectRecord).where(ProjectRecord.project_id == project_id)
    if record_type:
        stmt = stmt.where(ProjectRecord.record_type == record_type)
    if parent_id is not None:
        stmt = stmt.where(ProjectRecord.parent_id == parent_id)
    stmt = stmt.order_by(ProjectRecord.orden.asc(), ProjectRecord.created_at.asc())
    return [_to_dto(r) for r in db.scalars(stmt)]


def get_record(db: Session, record_id: uuid.UUID) -> RecordDTO | None:
    row = db.get(ProjectRecord, record_id)
    return _to_dto(row) if row else None


def get_record_entity(db: Session, record_id: uuid.UUID) -> ProjectRecord | None:
    return db.get(ProjectRecord, record_id)


def create_record(
    db: Session,
    project: Project,
    *,
    record_type: str,
    titulo: str,
    created_by: uuid.UUID,
    descripcion: str | None = None,
    parent_id: uuid.UUID | None = None,
    data: dict[str, Any] | None = None,
    fecha_inicio: date | None = None,
    fecha_fin: date | None = None,
    assignee_ids: list[uuid.UUID] | None = None,
    initial_state: str | None = None,
    orden: int | None = None,
) -> RecordDTO:
    from app.services.access import assert_project_active

    assert_project_active(project)
    rt = _get_record_type(db, project.id, record_type)
    if parent_id and rt.parent_types:
        parents = rt.parent_types
        parent_row = db.get(ProjectRecord, parent_id)
        if parent_row is None or parent_row.project_id != project.id:
            raise HTTPException(status_code=404, detail="Registro padre no encontrado")
        if parents and parent_row.record_type not in parents:
            raise HTTPException(status_code=422, detail="Tipo de padre inválido")

    from app.services.workflow.store import get_active_workflow

    wf = get_active_workflow(db, project.id, record_type)
    estado = initial_state or (wf or {}).get("initial_state") or "pendiente"

    if not db.get(User, created_by):
        raise HTTPException(status_code=404, detail="Usuario creador no encontrado")

    validated_data = validate_record_data(
        db, project.id, record_type, data or {}, partial=bool(data)
    )
    row = ProjectRecord(
        project_id=project.id,
        record_type=record_type,
        parent_id=parent_id,
        titulo=titulo.strip(),
        descripcion=descripcion,
        estado=estado,
        data=validated_data,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        created_by=created_by,
        orden=orden or 0,
    )
    db.add(row)
    db.flush()

    if assignee_ids:
        sync_assignees(db, row, assignee_ids)

    from app.config import settings
    from app.services.communication.engine import dispatch_record_created_rules

    if settings.communication_rules_only:
        dispatch_record_created_rules(
            db,
            project=project,
            actor_user_id=created_by,
            record=row,
        )

    return _to_dto(row)


def update_record(
    db: Session,
    record: ProjectRecord,
    *,
    titulo: str | None = None,
    descripcion: str | None = None,
    parent_id: uuid.UUID | None = None,
    data: dict[str, Any] | None = None,
    fecha_inicio: date | None = None,
    fecha_fin: date | None = None,
    orden: int | None = None,
    reparent: bool = False,
) -> RecordDTO:
    if titulo is not None:
        record.titulo = titulo.strip()
    if descripcion is not None:
        record.descripcion = descripcion
    if reparent:
        rt = _get_record_type(db, record.project_id, record.record_type)
        if parent_id is None:
            if rt.parent_types:
                parents = rt.parent_types
                if parents:
                    raise HTTPException(status_code=422, detail="Tipo de padre requerido")
            record.parent_id = None
        else:
            parents = rt.parent_types or []
            parent_row = db.get(ProjectRecord, parent_id)
            if parent_row is None or parent_row.project_id != record.project_id:
                raise HTTPException(status_code=404, detail="Registro padre no encontrado")
            if parents and parent_row.record_type not in parents:
                raise HTTPException(status_code=422, detail="Tipo de padre inválido")
            record.parent_id = parent_id
    if data is not None:
        apply_validated_data(db, record, data, partial=True)
    if fecha_inicio is not None:
        record.fecha_inicio = fecha_inicio
    if fecha_fin is not None:
        record.fecha_fin = fecha_fin
    if orden is not None:
        record.orden = orden
    return _to_dto(record)


def delete_record(db: Session, record: ProjectRecord) -> None:
    db.delete(record)


def sync_assignees(
    db: Session, record: ProjectRecord, user_ids: list[uuid.UUID]
) -> None:
    unique = list(dict.fromkeys(user_ids))
    for uid in unique:
        if not db.get(User, uid):
            raise HTTPException(status_code=404, detail=f"Usuario no encontrado: {uid}")
    current = {a.user_id for a in record.assignees}
    target = set(unique)
    for a in list(record.assignees):
        if a.user_id not in target:
            db.delete(a)
    existing = {a.user_id for a in record.assignees}
    for uid in unique:
        if uid not in existing:
            db.add(ProjectRecordAssignee(record_id=record.id, user_id=uid))


def _task_transition_target_state(
    db: Session,
    project: Project,
    record: ProjectRecord,
    *,
    action_id: str,
    actor_user_id: uuid.UUID,
    target_state: str | None,
) -> str | None:
    from app.services.workflow.engine import _find_transition
    from app.services.workflow.store import get_active_workflow

    workflow = get_active_workflow(db, project.id, record.record_type)
    if workflow is None:
        return None
    transition = _find_transition(
        workflow,
        action_id,
        record.estado,
        db=db,
        project=project,
        target_state=target_state,
        actor_user_id=actor_user_id,
    )
    if transition is None:
        return None
    if transition.get("dynamic_to") and target_state:
        return target_state
    nuevo = transition.get("to")
    if nuevo == "*":
        return target_state
    return nuevo if isinstance(nuevo, str) else None


def transition_record(
    db: Session,
    project: Project,
    record: ProjectRecord,
    *,
    action_id: str,
    actor_user_id: uuid.UUID,
    target_state: str | None = None,
    form_data: dict[str, Any] | None = None,
) -> RecordDTO:
    if record.record_type == "task":
        from app.services.task_dependencies import assert_move_allowed_by_dependencies

        nuevo = _task_transition_target_state(
            db,
            project,
            record,
            action_id=action_id,
            actor_user_id=actor_user_id,
            target_state=target_state,
        )
        if nuevo:
            assert_move_allowed_by_dependencies(db, record.id, nuevo)

    apply_record_transition(
        db,
        project,
        record,
        record_ref=RecordRef(
            id=record.id,
            record_type=record.record_type,
            project_id=project.id,
        ),
        action_id=action_id,
        actor_user_id=actor_user_id,
        target_state=target_state,
        form_data=form_data,
    )
    db.flush()
    db.refresh(record)
    return _to_dto(record)


def add_dependency(
    db: Session,
    project: Project,
    *,
    predecessor_id: uuid.UUID,
    successor_id: uuid.UUID,
    dependency_type: str = "finish_to_start",
) -> ProjectRecordDependency:
    if predecessor_id == successor_id:
        raise HTTPException(status_code=422, detail="Un registro no puede depender de sí mismo")
    for rid in (predecessor_id, successor_id):
        row = db.get(ProjectRecord, rid)
        if row is None or row.project_id != project.id:
            raise HTTPException(status_code=404, detail="Registro no encontrado")
    dep = ProjectRecordDependency(
        project_id=project.id,
        predecessor_id=predecessor_id,
        successor_id=successor_id,
        dependency_type=dependency_type,
    )
    db.add(dep)
    db.flush()
    return dep


def remove_dependency(db: Session, dep: ProjectRecordDependency) -> None:
    db.delete(dep)


def list_dependencies(
    db: Session, project_id: uuid.UUID
) -> list[ProjectRecordDependency]:
    return list(
        db.scalars(
            select(ProjectRecordDependency).where(
                ProjectRecordDependency.project_id == project_id
            )
        )
    )
