"""
Generic record store — CRUD para project_records.

Todas las operaciones reciben project_id + org_id para
asegurar el scope correcto (multi-tenancy).
"""
from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import and_
from sqlalchemy.orm import Session, joinedload

from app.domain.packs.definitions import get_pack, TEMPLATE_TO_PACK
from app.models.entities import (
    Project,
    ProjectRecord,
    ProjectRecordAssignee,
    User,
)
from app.services.blockers import has_active_blocker_on_chain, has_unsatisfied_dependencies
from app.services.workflow.side_effects import restore_story_to_backlog
from app.schemas.records import (
    AssigneeResponse,
    BlockerResponse,
    CreateRecordRequest,
    RecordListResponse,
    RecordResponse,
    UpdateRecordRequest,
)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _initial_state_for(project: Project, record_type: str, extra: dict | None = None) -> str:
    pack_key = TEMPLATE_TO_PACK.get(str(project.template_slug), str(project.pack_slug))
    pack = get_pack(pack_key)
    if pack:
        scrum_role = (extra or {}).get("scrum_role")
        _SCRUM_ROLE_ENTITY = {
            "epic": "epic",
            "story": "story",
            "dev": "dev_task",
            "subtask": "subtask",
        }
        entity_key = _SCRUM_ROLE_ENTITY.get(scrum_role, scrum_role) if scrum_role else record_type
        if scrum_role and entity_key in pack.workflows:
            wf = pack.workflows.get(entity_key)
            if wf:
                return wf.initial_state
        wf = pack.workflows.get(record_type)
        if wf:
            return wf.initial_state
    return "backlog"


def _to_response(db: Session, record: ProjectRecord) -> RecordResponse:
    assignees = [
        AssigneeResponse(
            user_id=str(a.user_id),
            nombre=a.user.nombre if a.user else "",
            avatar_url=a.user.avatar_url if a.user else None,
        )
        for a in (record.assignees or [])
    ]
    blockers = [
        BlockerResponse(
            id=str(b.id),
            description=b.description,
            created_by=str(b.created_by),
            created_at=b.created_at,
        )
        for b in (record.active_blockers or [])
    ]
    return RecordResponse(
        id=str(record.id),
        project_id=str(record.project_id),
        record_type=record.record_type,
        parent_id=str(record.parent_id) if record.parent_id else None,
        orden=record.orden,
        title=record.title,
        descripcion=record.descripcion,
        status=record.status,
        fecha_inicio=record.fecha_inicio,
        fecha_fin=record.fecha_fin,
        estimacion=float(record.estimacion) if record.estimacion is not None else None,
        extra=record.extra or {},
        assignees=assignees,
        active_blockers=blockers,
        is_blocked=has_active_blocker_on_chain(db, record),
        has_unsatisfied_dependencies=has_unsatisfied_dependencies(db, record),
        created_by=str(record.created_by),
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _load_query(db: Session, project_id: str):
    return (
        db.query(ProjectRecord)
        .options(
            joinedload(ProjectRecord.assignees).joinedload(ProjectRecordAssignee.user),
            joinedload(ProjectRecord.active_blockers),
        )
        .filter(ProjectRecord.project_id == project_id)
    )


# ─── CRUD ────────────────────────────────────────────────────────────────────

def _filter_query(
    q,
    *,
    record_type: str | None = None,
    parent_id: str | None = None,
    status: str | None = None,
    sprint_id: str | None = None,
    search: str | None = None,
):
    if record_type:
        q = q.filter(ProjectRecord.record_type == record_type)
    if parent_id:
        q = q.filter(ProjectRecord.parent_id == parent_id)
    if status:
        q = q.filter(ProjectRecord.status == status)
    if sprint_id:
        q = q.filter(ProjectRecord.parent_id == sprint_id)
    if search:
        q = q.filter(ProjectRecord.title.ilike(f"%{search}%"))
    return q


def list_records(
    db: Session,
    project_id: str,
    record_type: str | None = None,
    parent_id: str | None = None,
    status: str | None = None,
    sprint_id: str | None = None,
    search: str | None = None,
    limit: int = 1000,
    offset: int = 0,
) -> RecordListResponse:
    base = _load_query(db, project_id)
    filtered = _filter_query(
        base,
        record_type=record_type,
        parent_id=parent_id,
        status=status,
        sprint_id=sprint_id,
        search=search,
    )
    total = filtered.count()
    records = (
        filtered.order_by(ProjectRecord.orden, ProjectRecord.created_at)
        .offset(offset)
        .limit(limit)
        .all()
    )
    items = [_to_response(db, r) for r in records]
    return RecordListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        has_more=(offset + len(items)) < total,
    )


def get_record(db: Session, project_id: str, record_id: str) -> RecordResponse:
    record = (
        _load_query(db, project_id)
        .filter(ProjectRecord.id == record_id)
        .first()
    )
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record no encontrado")
    return _to_response(db, record)


def create_record(
    db: Session,
    project: Project,
    body: CreateRecordRequest,
    actor_id: str,
) -> RecordResponse:
    initial_status = body.status or _initial_state_for(project, body.record_type, body.extra)
    record = ProjectRecord(
        project_id=str(project.id),
        record_type=body.record_type,
        parent_id=body.parent_id,
        orden=body.orden,
        title=body.title,
        descripcion=body.descripcion,
        status=initial_status,
        fecha_inicio=body.fecha_inicio,
        fecha_fin=body.fecha_fin,
        estimacion=body.estimacion,
        extra=body.extra or {},
        created_by=actor_id,
    )
    db.add(record)
    db.flush()  # para tener el id

    # Asignaciones
    for uid in body.assignee_ids:
        db.add(ProjectRecordAssignee(record_id=record.id, user_id=uid))

    db.commit()
    db.refresh(record)
    return _to_response(db, record)


def update_record(
    db: Session,
    project_id: str,
    record_id: str,
    body: UpdateRecordRequest,
) -> RecordResponse:
    record = (
        db.query(ProjectRecord)
        .filter(
            ProjectRecord.id == record_id,
            ProjectRecord.project_id == project_id,
        )
        .first()
    )
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record no encontrado")

    if body.title is not None:
        record.title = body.title
    if body.descripcion is not None:
        record.descripcion = body.descripcion
    if body.fecha_inicio is not None:
        record.fecha_inicio = body.fecha_inicio
    if body.fecha_fin is not None:
        record.fecha_fin = body.fecha_fin
    if body.estimacion is not None:
        record.estimacion = body.estimacion
    if body.extra is not None:
        record.extra = {**(record.extra or {}), **body.extra}
    if body.orden is not None:
        record.orden = body.orden

    # Actualizar asignaciones si se envían
    if body.assignee_ids is not None:
        db.query(ProjectRecordAssignee).filter(
            ProjectRecordAssignee.record_id == record_id
        ).delete()
        for uid in body.assignee_ids:
            db.add(ProjectRecordAssignee(record_id=record_id, user_id=uid))

    db.commit()
    db.refresh(record)

    # Reload con relaciones
    return get_record(db, project_id, record_id)


def delete_record(db: Session, project_id: str, record_id: str) -> None:
    record = (
        db.query(ProjectRecord)
        .filter(
            ProjectRecord.id == record_id,
            ProjectRecord.project_id == project_id,
        )
        .first()
    )
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record no encontrado")

    if record.record_type == "sprint":
        children = (
            db.query(ProjectRecord)
            .filter(
                ProjectRecord.parent_id == record_id,
                ProjectRecord.project_id == project_id,
            )
            .all()
        )
        for child in children:
            if (child.extra or {}).get("scrum_role") == "story":
                restore_story_to_backlog(child)

    db.delete(record)
    db.commit()


def reorder_records(db: Session, project_id: str, ordered_ids: list[str]) -> None:
    for i, rid in enumerate(ordered_ids):
        db.query(ProjectRecord).filter(
            ProjectRecord.id == rid,
            ProjectRecord.project_id == project_id,
        ).update({"orden": i * 10})
    db.commit()
