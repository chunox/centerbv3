"""Dependencias finish-to-start entre tareas del mismo proyecto."""

from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Project, ProjectRecord, ProjectRecordDependency
from app.services.access import assert_project_active
from app.services.audit import record_audit_log

from app.services.workflow.categories import (
    is_task_cancel_state,
    resolve_workflow,
    task_forward_move_keys,
    task_satisfied_predecessor_keys,
)

SATISFIED_PREDECESSOR_STATES = frozenset({"completed", "cancel"})
FORWARD_MOVE_STATES = frozenset(
    {"to_do", "in_progress", "ready_for_test", "completed"}
)


def _task_workflow(db: Session, project_id: uuid.UUID) -> dict:
    project = db.get(Project, project_id)
    if project is None:
        return {}
    return resolve_workflow(db, project.id, "task", project.profile_slug)


def list_project_dependencies(
    db: Session, project_id: uuid.UUID
) -> list[ProjectRecordDependency]:
    return list(
        db.scalars(
            select(ProjectRecordDependency)
            .where(ProjectRecordDependency.project_id == project_id)
            .order_by(ProjectRecordDependency.created_at.asc())
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
            select(ProjectRecordDependency.successor_id).where(
                ProjectRecordDependency.project_id == project_id,
                ProjectRecordDependency.predecessor_id == current,
            )
        )
        for dependent_id in dependents:
            if dependent_id == predecessor_id:
                return True
            stack.append(dependent_id)
    return False


def unsatisfied_predecessors(
    db: Session, task_id: uuid.UUID
) -> list[ProjectRecord]:
    task = db.get(ProjectRecord, task_id)
    satisfied = (
        task_satisfied_predecessor_keys(_task_workflow(db, task.project_id))
        if task is not None
        else SATISFIED_PREDECESSOR_STATES
    )
    rows = db.scalars(
        select(ProjectRecord)
        .join(
            ProjectRecordDependency,
            ProjectRecordDependency.predecessor_id == ProjectRecord.id,
        )
        .where(
            ProjectRecordDependency.successor_id == task_id,
            ProjectRecord.estado.notin_(satisfied),
        )
    )
    return list(rows)


def assert_move_allowed_by_dependencies(
    db: Session, task_id: uuid.UUID, nuevo_estado: str
) -> None:
    task = db.get(ProjectRecord, task_id)
    forward = (
        task_forward_move_keys(_task_workflow(db, task.project_id))
        if task is not None
        else FORWARD_MOVE_STATES
    )
    if nuevo_estado not in forward:
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
    successor: ProjectRecord,
    predecessor: ProjectRecord,
    *,
    actor_user_id: uuid.UUID,
) -> ProjectRecordDependency:
    assert_project_active(project)
    from app.domain.capabilities import KANBAN_TASK_EDIT
    from app.services.workflow.authorize import assert_capability

    assert_capability(db, project.id, actor_user_id, KANBAN_TASK_EDIT)

    if successor.id == predecessor.id:
        raise HTTPException(
            status_code=400, detail="Una tarea no puede depender de sí misma"
        )
    if successor.project_id != project.id or predecessor.project_id != project.id:
        raise HTTPException(
            status_code=400,
            detail="Las tareas deben pertenecer al mismo proyecto",
        )
    if successor.record_type != "task" or predecessor.record_type != "task":
        raise HTTPException(status_code=400, detail="Las dependencias son entre tareas")

    existing = db.scalar(
        select(ProjectRecordDependency.id).where(
            ProjectRecordDependency.successor_id == successor.id,
            ProjectRecordDependency.predecessor_id == predecessor.id,
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="La dependencia ya existe")

    if _would_create_cycle(db, project.id, successor.id, predecessor.id):
        raise HTTPException(
            status_code=409,
            detail="La dependencia crearía un ciclo entre tareas",
        )

    dep = ProjectRecordDependency(
        project_id=project.id,
        successor_id=successor.id,
        predecessor_id=predecessor.id,
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
    dep: ProjectRecordDependency,
    *,
    actor_user_id: uuid.UUID,
) -> None:
    assert_project_active(project)
    from app.domain.capabilities import KANBAN_TASK_EDIT
    from app.services.workflow.authorize import assert_capability

    assert_capability(db, project.id, actor_user_id, KANBAN_TASK_EDIT)

    record_audit_log(
        db,
        project_id=project.id,
        user_id=actor_user_id,
        entidad_tipo="tarea",
        entidad_id=dep.successor_id,
        accion="dependency_removed",
        campo="depends_on_task_id",
        valor_anterior=str(dep.predecessor_id),
        valor_nuevo=None,
    )
    db.delete(dep)
