"""Creación y sync de tasks Scrum v2 (épica, historia, dev)."""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Project, ProjectRecord
from app.services.records import generic_store
from app.services.scrum_effort import is_scrum_project
from app.services.scrum_v2_structure import (
    SCRUM_ROLE_DEV,
    SCRUM_ROLE_EPIC,
    SCRUM_ROLE_STORY,
    ensure_product_backlog_milestone,
    get_epic_task_id,
    get_product_backlog_milestone,
    is_scrum_dev_task,
    is_scrum_story,
    list_dev_tasks_for_story,
)


def create_epic_task(
    db: Session,
    project: Project,
    *,
    titulo: str,
    created_by: uuid.UUID,
    descripcion: str | None = None,
) -> ProjectRecord:
    if not is_scrum_project(project):
        raise HTTPException(status_code=422, detail="Solo proyectos Scrum")
    backlog = ensure_product_backlog_milestone(db, project, created_by=created_by)
    dto = generic_store.create_record(
        db,
        project,
        record_type="task",
        titulo=titulo,
        created_by=created_by,
        descripcion=descripcion,
        parent_id=backlog.id,
        initial_state="abierta",
        data={"scrum_role": SCRUM_ROLE_EPIC},
    )
    return db.get(ProjectRecord, dto.id)  # type: ignore[return-value]


def create_story_task(
    db: Session,
    project: Project,
    *,
    titulo: str,
    created_by: uuid.UUID,
    epic_task_id: uuid.UUID,
    descripcion: str | None = None,
    prioridad: str = "media",
    initial_state: str = "product_backlog",
    data: dict[str, Any] | None = None,
) -> ProjectRecord:
    if not is_scrum_project(project):
        raise HTTPException(status_code=422, detail="Solo proyectos Scrum")
    epic = db.get(ProjectRecord, epic_task_id)
    if epic is None or epic.project_id != project.id:
        raise HTTPException(status_code=404, detail="Épica no encontrada")
    epic_data = epic.data if isinstance(epic.data, dict) else {}
    if epic_data.get("scrum_role") != SCRUM_ROLE_EPIC:
        raise HTTPException(status_code=422, detail="epic_task_id debe ser una task épica")

    backlog = ensure_product_backlog_milestone(db, project, created_by=created_by)
    payload = dict(data or {})
    payload["scrum_role"] = SCRUM_ROLE_STORY
    payload["epic_task_id"] = str(epic_task_id)
    payload["prioridad"] = prioridad
    payload.setdefault("bloqueada", False)

    dto = generic_store.create_record(
        db,
        project,
        record_type="task",
        titulo=titulo,
        created_by=created_by,
        descripcion=descripcion,
        parent_id=backlog.id,
        initial_state=initial_state,
        data=payload,
    )
    story = db.get(ProjectRecord, dto.id)
    assert story is not None
    generic_store.add_dependency(
        db,
        project,
        predecessor_id=story.id,
        successor_id=epic_task_id,
    )
    return story


def create_dev_task(
    db: Session,
    project: Project,
    *,
    titulo: str,
    created_by: uuid.UUID,
    story_id: uuid.UUID,
    descripcion: str | None = None,
    data: dict[str, Any] | None = None,
    initial_state: str | None = None,
    assignee_ids: list[uuid.UUID] | None = None,
) -> ProjectRecord:
    if not is_scrum_project(project):
        raise HTTPException(status_code=422, detail="Solo proyectos Scrum")
    story = db.get(ProjectRecord, story_id)
    if story is None or story.project_id != project.id or not is_scrum_story(story):
        raise HTTPException(status_code=404, detail="Historia no encontrada")
    story_data = story.data if isinstance(story.data, dict) else {}
    if story_data.get("bloqueada"):
        raise HTTPException(status_code=409, detail="La historia está bloqueada")

    payload = dict(data or {})
    payload["scrum_role"] = SCRUM_ROLE_DEV
    payload["parent_task_id"] = str(story_id)

    dto = generic_store.create_record(
        db,
        project,
        record_type="task",
        titulo=titulo,
        created_by=created_by,
        descripcion=descripcion,
        parent_id=story.parent_id,
        initial_state=initial_state or "to_do",
        data=payload,
        assignee_ids=assignee_ids,
    )
    dev = db.get(ProjectRecord, dto.id)
    assert dev is not None
    sync_story_from_dev_tasks(db, story, project, actor_user_id=created_by)
    return dev


def _resolve_story_for_dev(
    db: Session,
    dev: ProjectRecord,
    project: Project,
) -> ProjectRecord:
    data = dev.data if isinstance(dev.data, dict) else {}
    parent_key = str(data.get("parent_task_id") or "")
    if not parent_key:
        raise HTTPException(status_code=422, detail="parent_task_id inválido para subtarea dev")
    parent = db.get(ProjectRecord, uuid.UUID(parent_key))
    if parent is None or parent.project_id != project.id:
        raise HTTPException(status_code=404, detail="Tarea dev no encontrada")
    if is_scrum_story(parent):
        return parent
    if is_scrum_dev_task(parent):
        return _resolve_story_for_dev(db, parent, project)
    raise HTTPException(status_code=422, detail="parent_task_id inválido para subtarea dev")


def create_dev_subtask(
    db: Session,
    project: Project,
    *,
    titulo: str,
    created_by: uuid.UUID,
    parent_dev_id: uuid.UUID,
    descripcion: str | None = None,
    data: dict[str, Any] | None = None,
    initial_state: str | None = None,
    assignee_ids: list[uuid.UUID] | None = None,
) -> ProjectRecord:
    if not is_scrum_project(project):
        raise HTTPException(status_code=422, detail="Solo proyectos Scrum")
    parent = db.get(ProjectRecord, parent_dev_id)
    if parent is None or parent.project_id != project.id or not is_scrum_dev_task(parent):
        raise HTTPException(status_code=404, detail="Tarea dev no encontrada")
    story = _resolve_story_for_dev(db, parent, project)
    story_data = story.data if isinstance(story.data, dict) else {}
    if story_data.get("bloqueada"):
        raise HTTPException(status_code=409, detail="La historia está bloqueada")

    payload = dict(data or {})
    payload["scrum_role"] = SCRUM_ROLE_DEV
    payload["parent_task_id"] = str(parent_dev_id)

    dto = generic_store.create_record(
        db,
        project,
        record_type="task",
        titulo=titulo,
        created_by=created_by,
        descripcion=descripcion,
        parent_id=story.parent_id,
        initial_state=initial_state or "to_do",
        data=payload,
        assignee_ids=assignee_ids,
    )
    subtask = db.get(ProjectRecord, dto.id)
    assert subtask is not None
    generic_store.add_dependency(
        db,
        project,
        predecessor_id=subtask.id,
        successor_id=parent_dev_id,
    )
    sync_story_from_dev_tasks(db, story, project, actor_user_id=created_by)
    return subtask


def sync_story_from_dev_tasks(
    db: Session,
    story: ProjectRecord,
    project: Project,
    *,
    actor_user_id: uuid.UUID,
) -> bool:
    """Recalcula pendiente/en_progreso en historia-task según dev tasks."""
    if not is_scrum_story(story):
        return False
    story_data = story.data if isinstance(story.data, dict) else {}
    if story_data.get("bloqueada"):
        return False

    frozen = {
        "product_backlog",
        "uat",
        "esperando_liberacion_pm",
        "esperando_validacion_cliente",
        "completado",
        "cancelado",
    }
    if story.estado in frozen:
        return False

    dev_tasks = list_dev_tasks_for_story(db, project.id, story.id)
    active = [t for t in dev_tasks if t.estado != "cancel"]
    if not active:
        nuevo = "pendiente"
    elif all(t.estado in ("backlog", "to_do") for t in active):
        nuevo = "pendiente"
    elif story.estado == "uat":
        test_keys = {"ready_for_test", "completed"}
        if any(t.estado not in test_keys for t in active):
            nuevo = "en_progreso"
        else:
            return False
    else:
        nuevo = "en_progreso"

    if nuevo == story.estado:
        return False

    story.estado = nuevo
    db.flush()
    return True


def resolve_workflow_for_record(
    db: Session,
    project: Project,
    record: ProjectRecord,
) -> dict[str, Any] | None:
    from app.services.scrum_v2_structure import resolve_workflow_for_scrum_task
    from app.services.workflow.store import get_active_workflow

    if record.record_type == "task" and is_scrum_project(project) and (
        record.data or {}
    ).get("scrum_role") in (SCRUM_ROLE_EPIC, SCRUM_ROLE_STORY, SCRUM_ROLE_DEV):
        return resolve_workflow_for_scrum_task(db, project, record)
    return get_active_workflow(db, project.id, record.record_type)


def batch_story_effort_hours(
    db: Session,
    project_id: uuid.UUID,
    story_ids: list[uuid.UUID],
) -> dict[uuid.UUID, float]:
    if not story_ids:
        return {}
    totals: dict[uuid.UUID, float] = {sid: 0.0 for sid in story_ids}
    for sid in story_ids:
        for task in list_dev_tasks_for_story(db, project_id, sid):
            if task.estado == "cancel":
                continue
            data = task.data if isinstance(task.data, dict) else {}
            try:
                totals[sid] += max(0.0, float(data.get("estimacion_horas") or 0))
            except (TypeError, ValueError):
                pass
    return totals
