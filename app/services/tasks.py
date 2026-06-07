"""Movimiento Kanban y validación de transiciones (§5.2)."""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import HTTPException
from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.models.entities import Feature, Project, Task, TaskStateTransition, User
from app.services.audit import record_audit_log
from app.schemas.tasks import TaskUpdate
from app.services.access import (
    assert_member_has_role,
    assert_not_pm_for_task_ops,
    assert_project_active,
)
from app.services.features import sync_feature_from_tasks
from app.services.notifications import create_notification

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

    if feature.bloqueada:
        raise HTTPException(
            status_code=409,
            detail="La feature está bloqueada; no se pueden mover tareas",
        )
    if task.estado == nuevo_estado:
        return
    if task.estado == "cancel":
        raise HTTPException(status_code=409, detail="La tarea está cancelada")

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
    if task.asignado_a:
        create_notification(
            db,
            user_id=task.asignado_a,
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
    if not changes:
        return

    if "asignado_a" in changes and changes["asignado_a"] is not None:
        if not db.get(User, changes["asignado_a"]):
            raise HTTPException(status_code=404, detail="Usuario asignado no encontrado")

    prev_assignee = task.asignado_a
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

    if task.asignado_a and task.asignado_a != prev_assignee:
        create_notification(
            db,
            user_id=task.asignado_a,
            project_id=project.id,
            tipo="asignado",
            entidad_tipo="tarea",
            entidad_id=task.id,
        )
