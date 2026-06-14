"""Movimiento Kanban y validación de transiciones (§5.2)."""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.entities import Project, ProjectRecord, User
from app.services.audit import record_audit_log
from app.schemas.tasks import TaskSubtaskCreate, TaskUpdate
from app.services.access import assert_project_active
from app.services.features import sync_feature_from_tasks
from app.services.notifications import create_notification
from app.services.records.repository import (
    _data,
    create_record,
    list_assignee_ids,
    sync_assignees,
    update_record_fields,
)
from app.services.records import generic_store
from app.services.audit import record_audit_log
from app.services.task_dependencies import assert_move_allowed_by_dependencies

TaskEstado = str


def _task_state_keys(db: Session, project: Project) -> set[str]:
    from app.services.workflow.categories import resolve_workflow

    wf = resolve_workflow(db, project.id, "task", project.profile_slug)
    return {
        s["key"]
        for s in wf.get("states", [])
        if isinstance(s, dict) and s.get("key")
    }


def _assert_valid_task_state(db: Session, project: Project, state_key: str) -> None:
    keys = _task_state_keys(db, project)
    if keys and state_key not in keys:
        raise HTTPException(
            status_code=422,
            detail=f"Estado de tarea inválido: {state_key}",
        )


def _feature_bloqueada(feature: ProjectRecord) -> bool:
    return bool(_data(feature).get("bloqueada", False))


def _validate_assignee_ids(db: Session, user_ids: list[uuid.UUID]) -> None:
    for user_id in user_ids:
        if not db.get(User, user_id):
            raise HTTPException(
                status_code=404,
                detail=f"Usuario asignado no encontrado: {user_id}",
            )


def sync_task_assignees(
    db: Session,
    task: ProjectRecord,
    project: Project,
    *,
    actor_user_id: uuid.UUID,
    user_ids: list[uuid.UUID],
    notify: bool = True,
) -> None:
    unique_ids = list(dict.fromkeys(user_ids))
    _validate_assignee_ids(db, unique_ids)

    prev_ids = set(list_assignee_ids(db, task))
    new_ids = set(unique_ids)

    if prev_ids == new_ids:
        return

    sync_assignees(db, task, unique_ids)

    record_audit_log(
        db,
        project_id=project.id,
        user_id=actor_user_id,
        entidad_tipo="tarea",
        entidad_id=task.id,
        accion="updated",
        campo="asignado_ids",
        valor_anterior=",".join(str(x) for x in sorted(prev_ids)) or None,
        valor_nuevo=",".join(str(x) for x in sorted(new_ids)) or None,
    )

    if notify:
        for user_id in new_ids - prev_ids:
            create_notification(
                db,
                user_id=user_id,
                project_id=project.id,
                tipo="asignado",
                entidad_tipo="tarea",
                entidad_id=task.id,
            )


def move_task(
    db: Session,
    task: ProjectRecord,
    feature: ProjectRecord,
    project: Project,
    *,
    nuevo_estado: str,
    actor_user_id: uuid.UUID,
) -> None:
    from app.domain.capabilities import KANBAN_TASK_MOVE
    from app.services.workflow.authorize import assert_capability
    from app.services.workflow.categories import is_task_cancel_state, resolve_workflow
    from app.services.workflow.engine import apply_entity_transition

    assert_project_active(project)
    _assert_valid_task_state(db, project, nuevo_estado)

    task_wf = resolve_workflow(db, project.id, "task", project.profile_slug)

    if _feature_bloqueada(feature) and not is_task_cancel_state(task_wf, nuevo_estado):
        raise HTTPException(
            status_code=409,
            detail="La feature está bloqueada; no se pueden mover tareas",
        )
    if task.estado == nuevo_estado:
        return
    if is_task_cancel_state(task_wf, task.estado):
        raise HTTPException(status_code=409, detail="La tarea está cancelada")
    assert_move_allowed_by_dependencies(db, task.id, nuevo_estado)

    if is_task_cancel_state(task_wf, nuevo_estado):
        from app.domain.capabilities import KANBAN_TASK_CANCEL

        assert_capability(db, project.id, actor_user_id, KANBAN_TASK_CANCEL)
        apply_entity_transition(
            db,
            project,
            task,
            entity_type="task",
            action_id="cancel",
            actor_user_id=actor_user_id,
        )
    else:
        assert_capability(db, project.id, actor_user_id, KANBAN_TASK_MOVE)
        apply_entity_transition(
            db,
            project,
            task,
            entity_type="task",
            action_id="move",
            actor_user_id=actor_user_id,
            target_state=nuevo_estado,
        )

    sync_feature_from_tasks(
        db, feature, project, actor_user_id=actor_user_id
    )
    for assignee_id in list_assignee_ids(db, task):
        create_notification(
            db,
            user_id=assignee_id,
            project_id=project.id,
            tipo="estado_changed",
            entidad_tipo="tarea",
            entidad_id=task.id,
        )


def update_task(
    db: Session,
    task: ProjectRecord,
    feature: ProjectRecord,
    project: Project,
    payload: TaskUpdate,
) -> None:
    assert_project_active(project)
    from app.domain.capabilities import KANBAN_TASK_EDIT
    from app.services.workflow.authorize import assert_capability

    assert_capability(db, project.id, payload.actor_user_id, KANBAN_TASK_EDIT)

    if task.estado == "cancel":
        raise HTTPException(status_code=409, detail="La tarea está cancelada")

    changes = payload.model_dump(exclude_unset=True, exclude={"actor_user_id"})
    assignee_ids = changes.pop("asignado_ids", None)

    if assignee_ids is not None:
        sync_task_assignees(
            db,
            task,
            project,
            actor_user_id=payload.actor_user_id,
            user_ids=assignee_ids,
        )

    field_map = {"titulo": "titulo", "descripcion": "descripcion"}
    for field, nuevo in changes.items():
        attr = field_map.get(field, field)
        anterior = getattr(task, attr, None)
        if anterior == nuevo:
            continue
        update_record_fields(db, task, **{attr: nuevo})
        record_audit_log(
            db,
            project_id=project.id,
            user_id=payload.actor_user_id,
            entidad_tipo="tarea",
            entidad_id=task.id,
            accion="updated",
            campo=field,
            valor_anterior=str(anterior) if anterior is not None else None,
            valor_nuevo=str(nuevo) if nuevo is not None else None,
        )


def create_subtask(
    db: Session,
    parent: ProjectRecord,
    feature: ProjectRecord,
    project: Project,
    payload: TaskSubtaskCreate,
) -> ProjectRecord:
    assert_project_active(project)
    from app.domain.capabilities import KANBAN_TASK_CREATE
    from app.services.workflow.authorize import assert_capability

    assert_capability(db, project.id, payload.actor_user_id, KANBAN_TASK_CREATE)

    if parent.estado == "cancel":
        raise HTTPException(status_code=409, detail="La tarea padre está cancelada")
    if _feature_bloqueada(feature):
        raise HTTPException(
            status_code=409,
            detail="La feature está bloqueada; no se pueden crear sub-tareas",
        )

    child = create_record(
        db,
        project,
        entity_type="task",
        titulo=payload.titulo,
        created_by=payload.actor_user_id,
        parent_id=parent.parent_id,
        descripcion=payload.descripcion,
        estado=payload.estado,
        data={"parent_task_id": str(parent.id)},
    )

    generic_store.add_dependency(
        db,
        project,
        predecessor_id=child.id,
        successor_id=parent.id,
    )
    record_audit_log(
        db,
        project_id=project.id,
        user_id=payload.actor_user_id,
        entidad_tipo="tarea",
        entidad_id=parent.id,
        accion="dependency_added",
        campo="depends_on_task_id",
        valor_anterior=None,
        valor_nuevo=str(child.id),
    )
    sync_feature_from_tasks(
        db, feature, project, actor_user_id=payload.actor_user_id
    )
    return child
