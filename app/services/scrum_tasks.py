"""Creación y sync de tasks Scrum v2 (épica, historia, dev)."""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Project, ProjectRecord
from app.services.audit import record_audit_log
from app.services.records import generic_store
from app.services.records.repository import update_record_fields
from app.services.scrum_effort import is_scrum_project
from app.services.scrum_v2_structure import (
    SCRUM_ROLE_DEV,
    SCRUM_ROLE_EPIC,
    SCRUM_ROLE_STORY,
    ensure_product_backlog_milestone,
    get_epic_task_id,
    get_product_backlog_milestone,
    is_scrum_dev_task,
    is_scrum_epic_task,
    is_scrum_story,
    list_dev_tasks_for_story,
    list_all_dev_tasks_for_story,
    list_stories_for_epic,
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
    sync_epic_from_stories(db, epic, project, actor_user_id=created_by)
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
    return dev


def resolve_story_for_dev_record(
    db: Session,
    dev: ProjectRecord,
    project: Project,
) -> ProjectRecord:
    """Resuelve la historia Scrum desde una dev task o subtarea anidada."""
    return _resolve_story_for_dev(db, dev, project)


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
    return subtask


STORY_SYNC_FROZEN = frozenset(
    {
        "product_backlog",
        "planificado",
        "completado",
        "cancelado",
    }
)


def compute_scrum_story_estado_from_dev_tasks(
    story: ProjectRecord,
    dev_tasks: list[ProjectRecord],
    *,
    task_wf: dict[str, Any],
) -> str | None:
    """Estado destino de la historia según dev tasks, o None si no debe cambiar."""
    from app.services.workflow.categories import (
        is_task_cancel_state,
        task_backlog_state_keys,
        task_cancel_state_keys,
        task_done_state_keys,
    )

    story_data = story.data if isinstance(story.data, dict) else {}
    if story_data.get("bloqueada"):
        return None
    if story.estado in STORY_SYNC_FROZEN:
        return None

    cancel_keys = task_cancel_state_keys(task_wf)
    backlog_keys = task_backlog_state_keys(task_wf)
    done_keys = task_done_state_keys(task_wf)

    active = [t for t in dev_tasks if not is_task_cancel_state(task_wf, t.estado)]
    if not active:
        target = "pendiente"
    elif all(t.estado in backlog_keys for t in active):
        target = "pendiente"
    elif all(t.estado in done_keys for t in active):
        target = "completado"
    else:
        target = "en_progreso"

    if target == story.estado:
        return None
    return target


def close_scrum_dev_tasks_for_story(
    db: Session,
    project: Project,
    story: ProjectRecord,
    *,
    actor_user_id: uuid.UUID,
) -> None:
    """Cierra dev tasks abiertas al completar la historia (rollup o transición manual)."""
    from app.services.workflow.categories import (
        is_task_cancel_state,
        resolve_workflow,
        task_done_state_keys,
    )

    if not is_scrum_story(story):
        return
    task_wf = resolve_workflow(
        db, project.id, "task", project.template_slug or "default"
    )
    done_keys = task_done_state_keys(task_wf)
    for dev in list_all_dev_tasks_for_story(db, project.id, story.id):
        if is_task_cancel_state(task_wf, dev.estado) or dev.estado in done_keys:
            continue
        prev = dev.estado
        done_to = next(iter(done_keys), "completed")
        update_record_fields(db, dev, estado=done_to)
        record_audit_log(
            db,
            project_id=project.id,
            user_id=actor_user_id,
            entidad_tipo="tarea",
            entidad_id=dev.id,
            accion="estado_changed",
            campo="estado",
            valor_anterior=prev,
            valor_nuevo=f"{done_to} (story_completada)",
        )


def _set_story_estado_sync(
    db: Session,
    story: ProjectRecord,
    project: Project,
    *,
    nuevo: str,
    actor_user_id: uuid.UUID,
) -> None:
    anterior = story.estado
    if anterior == nuevo:
        return
    update_record_fields(db, story, estado=nuevo)
    if nuevo == "completado":
        close_scrum_dev_tasks_for_story(
            db, project, story, actor_user_id=actor_user_id
        )
    record_audit_log(
        db,
        project_id=project.id,
        user_id=actor_user_id,
        entidad_tipo="tarea",
        entidad_id=story.id,
        accion="estado_changed",
        campo="estado",
        valor_anterior=anterior,
        valor_nuevo=f"{nuevo} (sync_tareas)",
    )


def _try_apply_story_workflow_transition(
    db: Session,
    project: Project,
    story: ProjectRecord,
    *,
    action_id: str,
    actor_user_id: uuid.UUID,
) -> bool:
    from app.domain.records.types import RecordRef
    from app.services.workflow.engine import apply_record_transition

    try:
        apply_record_transition(
            db,
            project,
            story,
            record_ref=RecordRef(
                id=story.id,
                record_type=story.record_type,
                project_id=project.id,
            ),
            action_id=action_id,
            actor_user_id=actor_user_id,
        )
        return True
    except HTTPException:
        return False


def _advance_story_toward_target(
    db: Session,
    project: Project,
    story: ProjectRecord,
    target: str,
    *,
    actor_user_id: uuid.UUID,
) -> bool:
    current = story.estado
    if current == target:
        return False

    if target == "completado":
        if current == "pendiente":
            _set_story_estado_sync(
                db, story, project, nuevo="en_progreso", actor_user_id=actor_user_id
            )
            return True
        if current == "en_progreso":
            if _try_apply_story_workflow_transition(
                db, project, story, action_id="completar", actor_user_id=actor_user_id
            ):
                return True
            _set_story_estado_sync(
                db, story, project, nuevo="completado", actor_user_id=actor_user_id
            )
            return True

    if target in {"pendiente", "en_progreso"}:
        _set_story_estado_sync(
            db, story, project, nuevo=target, actor_user_id=actor_user_id
        )
        return True

    return False


def sync_story_from_dev_tasks(
    db: Session,
    story: ProjectRecord,
    project: Project,
    *,
    actor_user_id: uuid.UUID,
) -> bool:
    """Rollup hijo→padre desactivado: la historia solo cambia por movimiento manual."""
    return False


EPIC_STORY_TERMINAL = frozenset({"completado", "cancelado"})


def compute_scrum_epic_estado_from_stories(
    epic: ProjectRecord,
    stories: list[ProjectRecord],
) -> str | None:
    """Estado destino de la épica según historias hijas, o None si no debe cambiar."""
    if not stories:
        return None
    if all(s.estado in EPIC_STORY_TERMINAL for s in stories):
        target = "cerrada"
    else:
        target = "abierta"
    if target == epic.estado:
        return None
    return target


def _set_epic_estado_sync(
    db: Session,
    epic: ProjectRecord,
    project: Project,
    *,
    nuevo: str,
    actor_user_id: uuid.UUID,
) -> None:
    anterior = epic.estado
    if anterior == nuevo:
        return
    update_record_fields(db, epic, estado=nuevo)
    record_audit_log(
        db,
        project_id=project.id,
        user_id=actor_user_id,
        entidad_tipo="tarea",
        entidad_id=epic.id,
        accion="estado_changed",
        campo="estado",
        valor_anterior=anterior,
        valor_nuevo=f"{nuevo} (sync_historias)",
    )


def sync_epic_from_stories(
    db: Session,
    epic: ProjectRecord,
    project: Project,
    *,
    actor_user_id: uuid.UUID,
) -> bool:
    """Rollup hijo→padre desactivado: la épica solo cambia por movimiento manual."""
    return False


def migrate_story_sprint(
    db: Session,
    story: ProjectRecord,
    project: Project,
    source_sprint: ProjectRecord,
    target_sprint: ProjectRecord,
    *,
    actor_user_id: uuid.UUID,
) -> None:
    from app.domain.capabilities import SCOPE_FEATURE_MIGRATE
    from app.services.access import assert_project_active
    from app.services.records.repository import set_field
    from app.services.scrum_effort import get_feature_sprint_id, maybe_sync_scrum_on_sprint_assignment
    from app.services.workflow.authorize import assert_capability

    if not is_scrum_story(story):
        raise HTTPException(status_code=404, detail="Historia no encontrada")
    assert_project_active(project)
    assert_capability(db, project.id, actor_user_id, SCOPE_FEATURE_MIGRATE)
    if target_sprint.estado == "cancelado":
        raise HTTPException(
            status_code=409,
            detail="No se puede migrar a un sprint cancelado",
        )
    current_sprint = get_feature_sprint_id(story)
    if current_sprint == target_sprint.id:
        raise HTTPException(
            status_code=400,
            detail="La historia ya pertenece a ese sprint",
        )
    anterior = str(current_sprint) if current_sprint else None
    set_field(story, "sprint_id", str(target_sprint.id))
    db.flush()
    maybe_sync_scrum_on_sprint_assignment(db, project, story)
    record_audit_log(
        db,
        project_id=project.id,
        user_id=actor_user_id,
        entidad_tipo="task",
        entidad_id=story.id,
        accion="migrada",
        campo="sprint_id",
        valor_anterior=anterior,
        valor_nuevo=str(target_sprint.id),
    )


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
        for task in list_all_dev_tasks_for_story(db, project_id, sid):
            if task.estado == "cancel":
                continue
            data = task.data if isinstance(task.data, dict) else {}
            try:
                totals[sid] += max(0.0, float(data.get("estimacion_horas") or 0))
            except (TypeError, ValueError):
                pass
    return totals
