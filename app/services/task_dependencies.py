"""Dependencias finish-to-start entre tareas del mismo proyecto."""

from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Project, Task, TaskDependency
from app.services.access import (
    assert_member_has_role,
    assert_not_pm_for_task_ops,
    assert_project_active,
)
from app.services.audit import record_audit_log

SATISFIED_PREDECESSOR_STATES = frozenset({"completed", "cancel"})
FORWARD_MOVE_STATES = frozenset(
    {"to_do", "in_progress", "ready_for_test", "completed"}
)


def list_project_dependencies(
    db: Session, project_id: uuid.UUID
) -> list[TaskDependency]:
    return list(
        db.scalars(
            select(TaskDependency)
            .where(TaskDependency.project_id == project_id)
            .order_by(TaskDependency.created_at.asc())
        )
    )


def _would_create_cycle(
    db: Session,
    project_id: uuid.UUID,
    successor_id: uuid.UUID,
    predecessor_id: uuid.UUID,
) -> bool:
    """True si predecessor ya depende transitivamente de successor."""
    visited: set[uuid.UUID] = set()
    stack = [successor_id]
    while stack:
        current = stack.pop()
        if current in visited:
            continue
        visited.add(current)
        dependents = db.scalars(
            select(TaskDependency.task_id).where(
                TaskDependency.project_id == project_id,
                TaskDependency.depends_on_task_id == current,
            )
        )
        for dependent_id in dependents:
            if dependent_id == predecessor_id:
                return True
            stack.append(dependent_id)
    return False


def unsatisfied_predecessors(db: Session, task_id: uuid.UUID) -> list[Task]:
    rows = db.execute(
        select(Task)
        .join(TaskDependency, TaskDependency.depends_on_task_id == Task.id)
        .where(
            TaskDependency.task_id == task_id,
            Task.estado.notin_(SATISFIED_PREDECESSOR_STATES),
        )
    )
    return list(rows.scalars())


def assert_move_allowed_by_dependencies(
    db: Session, task_id: uuid.UUID, nuevo_estado: str
) -> None:
    if nuevo_estado not in FORWARD_MOVE_STATES:
        return
    blocking = unsatisfied_predecessors(db, task_id)
    if blocking:
        titles = ", ".join(t.titulo for t in blocking[:3])
        suffix = f" (+{len(blocking) - 3} más)" if len(blocking) > 3 else ""
        raise HTTPException(
            status_code=409,
            detail=f"La tarea tiene dependencias sin cumplir: {titles}{suffix}",
        )


def create_dependency(
    db: Session,
    project: Project,
    successor: Task,
    predecessor: Task,
    *,
    actor_user_id: uuid.UUID,
) -> TaskDependency:
    assert_project_active(project)
    assert_not_pm_for_task_ops(db, project.id, actor_user_id)
    assert_member_has_role(db, project.id, actor_user_id, "dev")

    if successor.id == predecessor.id:
        raise HTTPException(
            status_code=400, detail="Una tarea no puede depender de sí misma"
        )
    if successor.project_id != project.id or predecessor.project_id != project.id:
        raise HTTPException(
            status_code=400,
            detail="Las tareas deben pertenecer al mismo proyecto",
        )

    existing = db.scalar(
        select(TaskDependency.id).where(
            TaskDependency.task_id == successor.id,
            TaskDependency.depends_on_task_id == predecessor.id,
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="La dependencia ya existe")

    if _would_create_cycle(db, project.id, successor.id, predecessor.id):
        raise HTTPException(
            status_code=409,
            detail="La dependencia crearía un ciclo entre tareas",
        )

    dep = TaskDependency(
        project_id=project.id,
        task_id=successor.id,
        depends_on_task_id=predecessor.id,
        created_by=actor_user_id,
    )
    db.add(dep)
    db.flush()

    record_audit_log(
        db,
        project_id=project.id,
        user_id=actor_user_id,
        entidad_tipo="tarea",
        entidad_id=successor.id,
        accion="dependency_added",
        campo="depends_on_task_id",
        valor_anterior=None,
        valor_nuevo=str(predecessor.id),
    )
    return dep


def delete_dependency(
    db: Session,
    project: Project,
    dep: TaskDependency,
    *,
    actor_user_id: uuid.UUID,
) -> None:
    assert_project_active(project)
    assert_not_pm_for_task_ops(db, project.id, actor_user_id)
    assert_member_has_role(db, project.id, actor_user_id, "dev")

    record_audit_log(
        db,
        project_id=project.id,
        user_id=actor_user_id,
        entidad_tipo="tarea",
        entidad_id=dep.task_id,
        accion="dependency_removed",
        campo="depends_on_task_id",
        valor_anterior=str(dep.depends_on_task_id),
        valor_nuevo=None,
    )
    db.delete(dep)
