"""API genérica de registros de proyecto."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.v1.auth_deps import get_current_actor_id
from app.api.v1.deps import get_project_or_404
from app.database import get_db
from app.domain.project_mode import is_record_type_allowed
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
from app.services.delivery.caps import assert_record_cap
from app.services.delivery.resolve import get_delivery_service
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


def _dto_to_read(dto, *, esfuerzo_horas: float | None = None) -> RecordRead:
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
        esfuerzo_horas=esfuerzo_horas,
    )


def _effort_hours_for_dto(db: Session, project, dto) -> float | None:
    if dto.record_type not in ("feature", "task"):
        return None
    effort_map = get_delivery_service(project).list_effort_map(
        db, project, dto.record_type, [dto]
    )
    return effort_map.get(dto.id)


def _assert_record_cap(db: Session, project_id: UUID, user_id: UUID, cap: str) -> None:
    assert_record_cap(db, project_id, user_id, cap)


def _assert_task_create_capability(
    db: Session,
    project,
    payload: RecordCreate,
    actor_user_id: UUID,
) -> None:
    get_delivery_service(project).assert_task_create(db, project, payload, actor_user_id)


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
    sprint_id: UUID | None = None,
    in_product_backlog: bool | None = Query(default=None),
    estado: str | None = Query(default=None),
    actor_user_id: UUID = Depends(get_current_actor_id),
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    _assert_record_cap(
        db, project.id, actor_user_id, f"record.{record_type}.read"
    )
    if in_product_backlog:
        get_delivery_service(project).validate_in_product_backlog_filter(
            project, record_type
        )
    rows = registry.list_records(
        db,
        project.id,
        record_type=record_type,
        parent_id=parent_id,
        sprint_id=sprint_id,
        in_product_backlog=in_product_backlog,
        estado=estado,
    )
    effort_map = get_delivery_service(project).list_effort_map(
        db, project, record_type, rows
    )
    return [
        _dto_to_read(
            r,
            esfuerzo_horas=effort_map.get(r.id) if effort_map else None,
        )
        for r in rows
    ]


@router.get("/{project_id}/inbox-records", response_model=list[RecordRead])
def list_project_inbox_records(
    project_id: UUID,
    actor_user_id: UUID = Depends(get_current_actor_id),
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
    actor_user_id: UUID = Depends(get_current_actor_id),
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    allowed, mode_msg = is_record_type_allowed(project, payload.record_type, data=payload.data)
    if not allowed and mode_msg:
        raise HTTPException(status_code=422, detail=mode_msg)
    if payload.record_type == "task":
        _assert_task_create_capability(db, project, payload, actor_user_id)
    else:
        _assert_record_cap(
            db, project.id, actor_user_id, f"record.{payload.record_type}.create"
        )
    if registry.is_legacy(payload.record_type, project):
        raise HTTPException(
            status_code=422,
            detail=f"Tipo '{payload.record_type}' usa API legacy",
        )

    delivery = get_delivery_service(project)
    if payload.record_type in ("report", "task", "milestone", "sprint"):
        dto = delivery.create_record(db, project, payload, actor_user_id)
    else:
        dto = generic_store.create_record(
            db,
            project,
            record_type=payload.record_type,
            titulo=payload.titulo,
            created_by=actor_user_id,
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
    actor_user_id: UUID = Depends(get_current_actor_id),
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
    return _dto_to_read(dto, esfuerzo_horas=_effort_hours_for_dto(db, project, dto))


@router.patch("/{project_id}/records/{record_id}", response_model=RecordRead)
def update_project_record(
    project_id: UUID,
    record_id: UUID,
    payload: RecordUpdate,
    actor_user_id: UUID = Depends(get_current_actor_id),
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    row = db.get(ProjectRecord, record_id)
    if row is None or row.project_id != project.id:
        raise HTTPException(status_code=404, detail="Registro no encontrado")
    _assert_record_cap(
        db, project.id, actor_user_id, f"record.{row.record_type}.edit"
    )
    if row.record_type == "milestone":
        from app.schemas.milestones import MilestoneUpdate
        from app.services.milestones import update_milestone

        if "parent_id" in payload.model_fields_set:
            raise HTTPException(
                status_code=422,
                detail="Los hitos no admiten parent_id",
            )

        mu_fields: dict = {"actor_user_id": actor_user_id}
        if "titulo" in payload.model_fields_set:
            mu_fields["nombre"] = payload.titulo
        if "descripcion" in payload.model_fields_set:
            mu_fields["descripcion"] = payload.descripcion
        if "fecha_inicio" in payload.model_fields_set:
            mu_fields["fecha_inicio"] = payload.fecha_inicio
        if "fecha_fin" in payload.model_fields_set:
            mu_fields["fecha_fin"] = payload.fecha_fin
        if "orden" in payload.model_fields_set:
            mu_fields["orden"] = payload.orden

        if len(mu_fields) > 1:
            update_milestone(db, row, project, MilestoneUpdate(**mu_fields))

        dto = None
        if payload.data is not None:
            dto = generic_store.update_record(db, row, data=payload.data)
        if dto is None:
            dto = generic_store.get_record(db, row.id)
        if dto is None:
            raise HTTPException(status_code=404, detail="Registro no encontrado")
    else:
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
                actor_user_id=actor_user_id,
                user_ids=payload.assignee_ids,
            )
        else:
            generic_store.sync_assignees(db, row, payload.assignee_ids)
        db.refresh(row)
        dto = generic_store.get_record(db, row.id) or dto
    db.commit()
    return _dto_to_read(dto, esfuerzo_horas=_effort_hours_for_dto(db, project, dto))


def _task_delete_capabilities(row: ProjectRecord) -> list[str]:
    caps = ["record.task.delete", "record.task.edit"]
    role = (row.data or {}).get("scrum_role")
    if role == "epic":
        caps.extend(["scope.epic.delete", "record.epic.delete"])
    elif role == "story":
        caps.extend(
            [
                "scope.story.edit",
                "scope.feature.edit",
                "scope.feature.cancel",
            ]
        )
    else:
        caps.extend(["scope.story.edit", "kanban.task.cancel"])
    return list(dict.fromkeys(caps))


@router.delete("/{project_id}/records/{record_id}", status_code=204)
def delete_project_record(
    project_id: UUID,
    record_id: UUID,
    actor_user_id: UUID = Depends(get_current_actor_id),
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    row = db.get(ProjectRecord, record_id)
    if row is None or row.project_id != project.id:
        raise HTTPException(status_code=404, detail="Registro no encontrado")
    if row.record_type == "task":
        assert_any_capability(db, project.id, actor_user_id, _task_delete_capabilities(row))
    else:
        cap = f"record.{row.record_type}.delete"
        if not is_record_capability(cap):
            cap = f"record.{row.record_type}.edit"
        _assert_record_cap(db, project.id, actor_user_id, cap)
    if row.record_type == "milestone":
        from app.services.deletions import delete_milestone

        delete_milestone(db, row, project, actor_user_id=actor_user_id)
    else:
        generic_store.delete_record(db, row)
    db.commit()


@router.post("/{project_id}/records/{record_id}/transition", response_model=RecordRead)
def transition_project_record(
    project_id: UUID,
    record_id: UUID,
    payload: RecordTransitionRequest,
    actor_user_id: UUID = Depends(get_current_actor_id),
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    row = db.get(ProjectRecord, record_id)
    if row is None or row.project_id != project.id:
        raise HTTPException(status_code=404, detail="Registro no encontrado")

    from app.services.delivery.resolve import get_delivery_service

    if row.record_type == "task":
        get_delivery_service(project).assert_task_transition(
            db,
            project,
            row,
            action_id=payload.action_id,
            target_state=payload.target_state,
            actor_user_id=actor_user_id,
        )

    dto = generic_store.transition_record(
        db,
        project,
        row,
        action_id=payload.action_id,
        actor_user_id=actor_user_id,
        target_state=payload.target_state,
        form_data=payload.form_data,
        side_effect_context=payload.side_effect_context,
    )
    db.commit()
    return _dto_to_read(dto)


@router.post("/{project_id}/records/{record_id}/migrate", response_model=RecordRead)
def migrate_project_record(
    project_id: UUID,
    record_id: UUID,
    payload: RecordMigrateRequest,
    actor_user_id: UUID = Depends(get_current_actor_id),
    db: Session = Depends(get_db),
):
    project = get_project_or_404(project_id, db)
    work_item = db.get(ProjectRecord, record_id)
    if work_item is None or work_item.project_id != project.id:
        raise HTTPException(status_code=404, detail="Registro no encontrado")
    dto = get_delivery_service(project).migrate_record(
        db, project, work_item, payload, actor_user_id
    )
    db.commit()
    return _dto_to_read(dto)


@router.get(
    "/{project_id}/records/{record_id}/transitions",
    response_model=list[RecordTransitionRead],
)
def list_record_transitions(
    project_id: UUID,
    record_id: UUID,
    actor_user_id: UUID = Depends(get_current_actor_id),
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
    actor_user_id: UUID = Depends(get_current_actor_id),
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
    actor_user_id: UUID = Depends(get_current_actor_id),
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
            actor_user_id=actor_user_id,
        )
    else:
        _assert_dependency_write(db, project.id, actor_user_id, pred, succ)
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
    actor_user_id: UUID = Depends(get_current_actor_id),
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
