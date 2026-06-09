"""Movimiento Kanban y validación de transiciones (§5.2)."""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import HTTPException
from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.models.entities import Feature, Project, Task, TaskAssignee, TaskStateTransition, User
from app.services.audit import record_audit_log
from app.schemas.tasks import TaskSubtaskCreate, TaskUpdate
from app.services.access import (
    assert_member_has_role,
    assert_not_pm_for_task_ops,
    assert_project_active,
)
from app.services.features import CANCELLABLE_TASK_STATES, sync_feature_from_tasks
from app.services.notifications import create_notification
from app.services.task_dependencies import (
    assert_move_allowed_by_dependencies,
    create_dependency,
)

TaskEstado = Literal[
    "backlog",
    "to_do",
    "in_progress",
    "ready_for_test",
    "completed",
    "cancel",
]


def assert_task_transition_allowed(
    db: Session, estado_desde: str, estado_hasta: str
) -> None:
    allowed = db.scalar(
        select(
            exists().where(
                TaskStateTransition.estado_desde == estado_desde,
                TaskStateTransition.estado_hasta == estado_hasta,
                TaskStateTransition.rol_permitido == "dev",
            )
        )
    )
    if not allowed:
        raise HTTPException(
            status_code=409,
            detail=f"Transición no permitida: {estado_desde} → {estado_hasta}",
        )


def _validate_assignee_ids(db: Session, user_ids: list[uuid.UUID]) -> None:
    for user_id in user_ids:
        if not db.get(User, user_id):
            raise HTTPException(
                status_code=404,
                detail=f"Usuario asignado no encontrado: {user_id}",
            )


def sync_task_assignees(
    db: Session,
    task: Task,
    project: Project,
    *,
    actor_user_id: uuid.UUID,
    user_ids: list[uuid.UUID],
    notify: bool = True,
) -> None:
    unique_ids = list(dict.fromkeys(user_ids))
    _validate_assignee_ids(db, unique_ids)

    prev_ids = set(task.asignado_ids)
    new_ids = set(unique_ids)

    if prev_ids == new_ids:
        return

    for ta in list(task.task_assignees):
        if ta.user_id not in new_ids:
            db.delete(ta)
    existing = {ta.user_id for ta in task.task_assignees}
    for user_id in unique_ids:
        if user_id not in existing:
            db.add(TaskAssignee(task_id=task.id, user_id=user_id))

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
    task: Task,
    feature: Feature,
    project: Project,
    *,
    nuevo_estado: TaskEstado,
    actor_user_id: uuid.UUID,
) -> None:
    assert_project_active(project)
    assert_not_pm_for_task_ops(db, project.id, actor_user_id)
    assert_member_has_role(db, project.id, actor_user_id, "dev")

    if feature.bloqueada and nuevo_estado != "cancel":
        raise HTTPException(
            status_code=409,
            detail="La feature está bloqueada; no se pueden mover tareas",
        )
    if task.estado == nuevo_estado:
        return
    if task.estado == "cancel":
        raise HTTPException(status_code=409, detail="La tarea está cancelada")
    if nuevo_estado == "cancel" and task.estado not in CANCELLABLE_TASK_STATES:
        raise HTTPException(
            status_code=409,
            detail="No se puede cancelar una tarea en este estado",
        )

    assert_move_allowed_by_dependencies(db, task.id, nuevo_estado)
    assert_task_transition_allowed(db, task.estado, nuevo_estado)
    anterior = task.estado
    task.estado = nuevo_estado

    record_audit_log(
        db,
        project_id=project.id,
        user_id=actor_user_id,
        entidad_tipo="tarea",
        entidad_id=task.id,
        accion="estado_changed",
        campo="estado",
        valor_anterior=anterior,
        valor_nuevo=nuevo_estado,
    )
    sync_feature_from_tasks(
        db, feature, project, actor_user_id=actor_user_id
    )
    for assignee_id in task.asignado_ids:
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
    task: Task,
    feature: Feature,
    project: Project,
    payload: TaskUpdate,
) -> None:
    assert_project_active(project)
    assert_not_pm_for_task_ops(db, project.id, payload.actor_user_id)
    assert_member_has_role(db, project.id, payload.actor_user_id, "dev")

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

    for field, nuevo in changes.items():
        anterior = getattr(task, field)
        if anterior == nuevo:
            continue
        setattr(task, field, nuevo)
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
    parent: Task,
    feature: Feature,
    project: Project,
    payload: TaskSubtaskCreate,
) -> Task:
    assert_project_active(project)
    assert_not_pm_for_task_ops(db, project.id, payload.actor_user_id)
    assert_member_has_role(db, project.id, payload.actor_user_id, "dev")

    if parent.estado == "cancel":
        raise HTTPException(status_code=409, detail="La tarea padre está cancelada")
    if feature.bloqueada:
        raise HTTPException(
            status_code=409,
            detail="La feature está bloqueada; no se pueden crear sub-tareas",
        )

    child = Task(
        feature_id=parent.feature_id,
        project_id=parent.project_id,
        titulo=payload.titulo,
        descripcion=payload.descripcion,
        estado=payload.estado,
        created_by=payload.actor_user_id,
        parent_task_id=parent.id,
    )
    db.add(child)
    db.flush()

    create_dependency(
        db,
        project,
        parent,
        child,
        actor_user_id=payload.actor_user_id,
    )
    sync_feature_from_tasks(
        db, feature, project, actor_user_id=payload.actor_user_id
    )
    return child
