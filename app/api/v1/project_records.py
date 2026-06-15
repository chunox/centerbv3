"""API genérica de registros de proyecto."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.v1.deps import get_milestone_or_404, get_project_or_404
from app.database import get_db
from app.domain.capabilities import (
    KANBAN_TASK_EDIT,
    KANBAN_VIEW,
    PROJECT_ROLES_MANAGE,
    WORKBENCH_INBOX_CLIENT,
    WORKBENCH_INBOX_DEV,
    WORKBENCH_INBOX_PM,
    WORKBENCH_INBOX_QA,
    is_record_capability,
)
from app.models.entities import ProjectRecord, ProjectRecordDependency
from app.schemas.records import (
    RecordCreate,
    RecordDependencyCreate,
    RecordDependencyRead,
    RecordMigrateRequest,
    RecordRead,
    RecordTransitionRead,
    RecordTransitionRequest,
    RecordUpdate,
)
from app.services.inbox_records import InboxQueue, list_inbox_records
from app.services.records import generic_store, registry
from app.services.workflow.authorize import assert_any_capability, assert_capability
from app.services.workflow.engine import get_available_transitions

router = APIRouter(prefix="/projects", tags=["project-records"])

_INBOX_QUEUE_CAPS: dict[InboxQueue, str] = {
    "pm": WORKBENCH_INBOX_PM,
    "client": WORKBENCH_INBOX_CLIENT,
    "dev": WORKBENCH_INBOX_DEV,
    "qa": WORKBENCH_INBOX_QA,
}


def _dto_to_read(dto) -> RecordRead:
    return RecordRead(
        id=dto.id,
        project_id=dto.project_id,
        record_type=dto.record_type,
        titulo=dto.titulo,
        descripcion=dto.descripcion,
        estado=dto.estado,
        parent_id=dto.parent_id,
        data=dto.data,
        fecha_inicio=dto.fecha_inicio,
        fecha_fin=dto.fecha_fin,
        orden=dto.orden,
        assignee_ids=dto.assignee_ids,
        created_by=dto.created_by,
        created_at=dto.created_at,
        updated_at=dto.updated_at,
    )


def _assert_record_cap(db: Session, project_id: UUID, user_id: UUID, cap: str) -> None:
    from app.services.workflow.capabilities import user_has_capability

    if user_has_capability(db, project_id, user_id, cap):
        return
    if user_has_capability(db, project_id, user_id, PROJECT_ROLES_MANAGE):
        return
    assert_capability(db, project_id, user_id, cap)


def _assert_dependency_read(db: Session, project_id: UUID, user_id: UUID) -> None:
    from app.services.workflow.capabilities import user_has_capability

    if user_has_capability(db, project_id, user_id, PROJECT_ROLES_MANAGE):
        return
    assert_any_capability(
        db,
        project_id,
        user_id,
        [KANBAN_VIEW, "record.task.read", "record.pieza.read"],
        detail="Sin permisos para ver dependencias",
    )


def _get_dependency_records(
    db: Session, project_id: UUID, predecessor_id: UUID, successor_id: UUID
) -> tuple[ProjectRecord, ProjectRecord]:
    pred = db.get(ProjectRecord, predecessor_id)
    succ = db.get(ProjectRecord, successor_id)
    if pred is None or succ is None:
        raise HTTPException(status_code=404, detail="Registro no encontrado")
    if pred.project_id != project_id or succ.project_id != project_id:
        raise HTTPException(status_code=404, detail="Registro no encontrado")
    return pred, succ


def _assert_dependency_write(
    db: Session,
    project_id: UUID,
    user_id: UUID,
    predecessor: ProjectRecord,
    successor: ProjectRecord,
) -> None:
    if predecessor.record_type == "task" and successor.record_type == "task":
        assert_capability(db, project_id, user_id, KANBAN_TASK_EDIT)
        return
    for record in (predecessor, successor):
        _assert_record_cap(db, project_id, user_id, f"record.{record.record_type}.edit")


@router.get("/{project_id}/records", response_model=list[RecordRead])
def list_project_records(
    project_id: UUID,
    record_type: str = Query(...),
    parent_id: UUID | None = None,
    actor_user_id: UUID = Query(...),
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    _assert_record_cap(
        db, project.id, actor_user_id, f"record.{record_type}.read"
    )
    rows = registry.list_records(
        db, project.id, record_type=record_type, parent_id=parent_id
    )
    return [_dto_to_read(r) for r in rows]


@router.get("/{project_id}/inbox-records", response_model=list[RecordRead])
def list_project_inbox_records(
    project_id: UUID,
    actor_user_id: UUID = Query(...),
    queue: InboxQueue | None = Query(default=None),
    workbench_key: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """Registros de bandeja filtrados server-side (queue legacy o workbench_key)."""
    project = get_project_or_404(project_id, db)
    if workbench_key:
        from app.services.inbox_queue_filter import list_inbox_records_for_workbench
        from app.services.workflow.store import get_workbenches
        from app.services.workflow.authorize import assert_any_capability

        workbenches = get_workbenches(db, project.id)
        wb = next((w for w in workbenches if w.get("key") == workbench_key), None)
        if wb is None:
            raise HTTPException(status_code=404, detail="Workbench no encontrado")
        caps = wb.get("required_capabilities") or []
        if caps:
            assert_any_capability(db, project.id, actor_user_id, caps)
        rows = list_inbox_records_for_workbench(
            db, project, workbench_key, actor_user_id=actor_user_id
        )
    elif queue is not None:
        assert_capability(db, project.id, actor_user_id, _INBOX_QUEUE_CAPS[queue])
        rows = list_inbox_records(
            db, project, queue, actor_user_id=actor_user_id
        )
    else:
        raise HTTPException(
            status_code=422, detail="Indicá queue o workbench_key"
        )
    return [_dto_to_read(generic_store._to_dto(r)) for r in rows]


@router.post("/{project_id}/records", response_model=RecordRead, status_code=201)
def create_project_record(
    project_id: UUID,
    payload: RecordCreate,
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    _assert_record_cap(
        db, project.id, payload.actor_user_id, f"record.{payload.record_type}.create"
    )
    if registry.is_legacy(payload.record_type):
        raise HTTPException(
            status_code=422,
            detail=f"Tipo '{payload.record_type}' usa API legacy",
        )

    if payload.record_type == "report":
        from app.domain.capabilities import REPORT_CREATE
        from app.services.feature_reports import notify_pms_report_received
        from app.services.project_profile import supports_reports
        from app.services.workflow.authorize import assert_capability

        if payload.parent_id is None:
            raise HTTPException(status_code=422, detail="parent_id requerido para reportes")
        feature = db.get(ProjectRecord, payload.parent_id)
        if feature is None or feature.record_type != "feature":
            raise HTTPException(status_code=404, detail="Feature no encontrada")
        assert_capability(db, project.id, payload.actor_user_id, REPORT_CREATE)
        if feature.estado != "completado":
            raise HTTPException(
                status_code=409,
                detail="Solo se puede reportar sobre una feature en estado completado",
            )
        if not supports_reports(db, project):
            raise HTTPException(
                status_code=400,
                detail="Los reportes solo aplican a proyectos con stakeholder externo",
            )
        data = dict(payload.data or {})
        data.setdefault("reported_by", str(payload.actor_user_id))
        dto = generic_store.create_record(
            db,
            project,
            record_type=payload.record_type,
            titulo=payload.titulo,
            created_by=payload.actor_user_id,
            descripcion=payload.descripcion,
            parent_id=payload.parent_id,
            data=data,
            fecha_inicio=payload.fecha_inicio,
            fecha_fin=payload.fecha_fin,
            assignee_ids=payload.assignee_ids,
            initial_state=payload.initial_state,
            orden=payload.orden,
        )
        from app.config import settings

        if not settings.communication_rules_only:
            notify_pms_report_received(db, project, db.get(ProjectRecord, dto.id))
    elif payload.record_type == "task":
        from app.domain.capabilities import KANBAN_TASK_CREATE
        from app.services.features import sync_feature_from_tasks
        from app.services.records.repository import _data
        from app.services.tasks import sync_task_assignees
        from app.services.workflow.authorize import assert_capability

        if payload.parent_id is None:
            raise HTTPException(status_code=422, detail="parent_id requerido para tareas")
        feature = db.get(ProjectRecord, payload.parent_id)
        if feature is None or feature.record_type != "feature":
            raise HTTPException(status_code=404, detail="Feature no encontrada")
        if _data(feature).get("bloqueada"):
            raise HTTPException(
                status_code=409,
                detail="La feature está bloqueada; no se pueden crear tareas",
            )
        assert_capability(db, project.id, payload.actor_user_id, KANBAN_TASK_CREATE)
        dto = generic_store.create_record(
            db,
            project,
            record_type=payload.record_type,
            titulo=payload.titulo,
            created_by=payload.actor_user_id,
            descripcion=payload.descripcion,
            parent_id=payload.parent_id,
            data=payload.data,
            fecha_inicio=payload.fecha_inicio,
            fecha_fin=payload.fecha_fin,
            initial_state=payload.initial_state,
            orden=payload.orden,
        )
        task = db.get(ProjectRecord, dto.id)
        if payload.assignee_ids:
            sync_task_assignees(
                db,
                task,
                project,
                actor_user_id=payload.actor_user_id,
                user_ids=payload.assignee_ids,
            )
        sync_feature_from_tasks(
            db, feature, project, actor_user_id=payload.actor_user_id
        )
        db.refresh(task)
        dto = generic_store.get_record(db, dto.id) or dto
    elif payload.record_type == "milestone":
        from app.services.milestones import next_milestone_orden

        dto = generic_store.create_record(
            db,
            project,
            record_type=payload.record_type,
            titulo=payload.titulo,
            created_by=payload.actor_user_id,
            descripcion=payload.descripcion,
            parent_id=payload.parent_id,
            data=payload.data or {"tipo": "entrega"},
            fecha_inicio=payload.fecha_inicio,
            fecha_fin=payload.fecha_fin,
            assignee_ids=payload.assignee_ids,
            initial_state=payload.initial_state,
            orden=payload.orden if payload.orden is not None else next_milestone_orden(db, project.id),
        )
    else:
        dto = generic_store.create_record(
            db,
            project,
            record_type=payload.record_type,
            titulo=payload.titulo,
            created_by=payload.actor_user_id,
            descripcion=payload.descripcion,
            parent_id=payload.parent_id,
            data=payload.data,
            fecha_inicio=payload.fecha_inicio,
            fecha_fin=payload.fecha_fin,
            assignee_ids=payload.assignee_ids,
            initial_state=payload.initial_state,
            orden=payload.orden,
        )
    db.commit()
    return _dto_to_read(dto)


@router.get("/{project_id}/records/{record_id}", response_model=RecordRead)
def get_project_record(
    project_id: UUID,
    record_id: UUID,
    actor_user_id: UUID = Query(...),
    record_type: str | None = None,
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    ref = registry.resolve_ref(db, record_type or "", record_id) if record_type else None
    if ref is None:
        row = db.get(ProjectRecord, record_id)
        if row and row.project_id == project.id:
            ref = registry.resolve_ref(db, row.record_type, record_id)
    if ref is None:
        for rt in registry.workflow_entity_types_for_project(db, project.id):
            ref = registry.resolve_ref(db, rt, record_id)
            if ref:
                break
    if ref is None or ref.project_id != project.id:
        raise HTTPException(status_code=404, detail="Registro no encontrado")
    _assert_record_cap(db, project.id, actor_user_id, f"record.{ref.record_type}.read")
    dto, _ = registry.get(db, ref)
    if dto is None:
        raise HTTPException(status_code=404, detail="Registro no encontrado")
    return _dto_to_read(dto)


@router.patch("/{project_id}/records/{record_id}", response_model=RecordRead)
def update_project_record(
    project_id: UUID,
    record_id: UUID,
    payload: RecordUpdate,
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    row = db.get(ProjectRecord, record_id)
    if row is None or row.project_id != project.id:
        raise HTTPException(status_code=404, detail="Registro no encontrado")
    _assert_record_cap(
        db, project.id, payload.actor_user_id, f"record.{row.record_type}.edit"
    )
    dto = generic_store.update_record(
        db,
        row,
        titulo=payload.titulo,
        descripcion=payload.descripcion,
        parent_id=payload.parent_id,
        data=payload.data,
        fecha_inicio=payload.fecha_inicio,
        fecha_fin=payload.fecha_fin,
        orden=payload.orden,
        reparent="parent_id" in payload.model_fields_set,
    )
    if payload.assignee_ids is not None:
        if row.record_type == "task":
            from app.services.tasks import sync_task_assignees

            sync_task_assignees(
                db,
                row,
                project,
                actor_user_id=payload.actor_user_id,
                user_ids=payload.assignee_ids,
            )
        else:
            generic_store.sync_assignees(db, row, payload.assignee_ids)
        db.refresh(row)
        dto = generic_store.get_record(db, row.id) or dto
    db.commit()
    return _dto_to_read(dto)


@router.delete("/{project_id}/records/{record_id}", status_code=204)
def delete_project_record(
    project_id: UUID,
    record_id: UUID,
    actor_user_id: UUID = Query(...),
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    row = db.get(ProjectRecord, record_id)
    if row is None or row.project_id != project.id:
        raise HTTPException(status_code=404, detail="Registro no encontrado")
    cap = f"record.{row.record_type}.delete"
    if not is_record_capability(cap):
        cap = f"record.{row.record_type}.edit"
    _assert_record_cap(db, project.id, actor_user_id, cap)
    generic_store.delete_record(db, row)
    db.commit()


@router.post("/{project_id}/records/{record_id}/transition", response_model=RecordRead)
def transition_project_record(
    project_id: UUID,
    record_id: UUID,
    payload: RecordTransitionRequest,
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    row = db.get(ProjectRecord, record_id)
    if row is None or row.project_id != project.id:
        raise HTTPException(status_code=404, detail="Registro no encontrado")

    if row.record_type == "task" and payload.action_id == "move":
        from app.services.tasks import move_task

        if payload.target_state is None:
            raise HTTPException(status_code=422, detail="Se requiere target_state")
        feature = db.get(ProjectRecord, row.parent_id)
        if feature is None or feature.record_type != "feature":
            raise HTTPException(status_code=404, detail="Feature no encontrada")
        move_task(
            db,
            row,
            feature,
            project,
            nuevo_estado=payload.target_state,
            actor_user_id=payload.actor_user_id,
        )
        db.commit()
        db.refresh(row)
        dto = generic_store.get_record(db, row.id)
        return _dto_to_read(dto)

    dto = generic_store.transition_record(
        db,
        project,
        row,
        action_id=payload.action_id,
        actor_user_id=payload.actor_user_id,
        target_state=payload.target_state,
        form_data=payload.form_data,
    )
    db.commit()
    return _dto_to_read(dto)


@router.post("/{project_id}/records/{record_id}/migrate", response_model=RecordRead)
def migrate_project_record(
    project_id: UUID,
    record_id: UUID,
    payload: RecordMigrateRequest,
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    feature = db.get(ProjectRecord, record_id)
    if feature is None or feature.project_id != project.id or feature.record_type != "feature":
        raise HTTPException(status_code=404, detail="Feature no encontrada")
    if feature.parent_id is None:
        raise HTTPException(status_code=409, detail="Feature sin hito padre")
    source_milestone = get_milestone_or_404(project_id, feature.parent_id, db)
    target_milestone = get_milestone_or_404(
        project_id, payload.target_milestone_id, db
    )
    from app.services.features import migrate_feature

    migrate_feature(
        db,
        feature,
        project,
        source_milestone,
        target_milestone,
        actor_user_id=payload.actor_user_id,
    )
    db.commit()
    db.refresh(feature)
    dto = generic_store.get_record(db, feature.id)
    if dto is None:
        raise HTTPException(status_code=404, detail="Feature no encontrada")
    return _dto_to_read(dto)


@router.get(
    "/{project_id}/records/{record_id}/transitions",
    response_model=list[RecordTransitionRead],
)
def list_record_transitions(
    project_id: UUID,
    record_id: UUID,
    actor_user_id: UUID = Query(...),
    record_type: str | None = None,
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    row = db.get(ProjectRecord, record_id)
    if row and row.project_id == project.id:
        entity = row
        etype = row.record_type
    else:
        raise HTTPException(status_code=404, detail="Registro no encontrado")
    available = get_available_transitions(
        db, project, entity, entity_type=etype, user_id=actor_user_id
    )
    return [RecordTransitionRead(**t) for t in available]


@router.get(
    "/{project_id}/record-dependencies",
    response_model=list[RecordDependencyRead],
)
def list_record_dependencies(
    project_id: UUID,
    actor_user_id: UUID = Query(...),
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    _assert_dependency_read(db, project.id, actor_user_id)
    deps = generic_store.list_dependencies(db, project.id)
    return [RecordDependencyRead.model_validate(d) for d in deps]


@router.post(
    "/{project_id}/record-dependencies",
    response_model=RecordDependencyRead,
    status_code=201,
)
def create_record_dependency(
    project_id: UUID,
    payload: RecordDependencyCreate,
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    pred, succ = _get_dependency_records(
        db, project.id, payload.predecessor_id, payload.successor_id
    )
    if pred.record_type == "task" and succ.record_type == "task":
        from app.services.task_dependencies import create_dependency

        dep = create_dependency(
            db,
            project,
            succ,
            pred,
            actor_user_id=payload.actor_user_id,
        )
    else:
        _assert_dependency_write(db, project.id, payload.actor_user_id, pred, succ)
        dep = generic_store.add_dependency(
            db,
            project,
            predecessor_id=payload.predecessor_id,
            successor_id=payload.successor_id,
            dependency_type=payload.dependency_type,
        )
    db.commit()
    return RecordDependencyRead.model_validate(dep)


@router.delete("/{project_id}/record-dependencies/{dep_id}", status_code=204)
def delete_record_dependency(
    project_id: UUID,
    dep_id: UUID,
    actor_user_id: UUID = Query(...),
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    dep = db.get(ProjectRecordDependency, dep_id)
    if dep is None or dep.project_id != project.id:
        raise HTTPException(status_code=404, detail="Dependencia no encontrada")
    pred = db.get(ProjectRecord, dep.predecessor_id)
    succ = db.get(ProjectRecord, dep.successor_id)
    if (
        pred is not None
        and succ is not None
        and pred.record_type == "task"
        and succ.record_type == "task"
    ):
        from app.services.task_dependencies import delete_dependency

        delete_dependency(db, project, dep, actor_user_id=actor_user_id)
    else:
        if pred is None or succ is None:
            raise HTTPException(status_code=404, detail="Registro no encontrado")
        _assert_dependency_write(db, project.id, actor_user_id, pred, succ)
        generic_store.remove_dependency(db, dep)
    db.commit()
