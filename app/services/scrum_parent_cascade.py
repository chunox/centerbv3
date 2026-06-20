"""Cascade manual padre→hijos en Scrum (sin rollup hijo→padre)."""
from __future__ import annotations

import uuid
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.models.entities import Project, ProjectRecord
from app.services.audit import record_audit_log
from app.services.records.repository import update_record_fields
from app.services.scrum_tasks import resolve_story_for_dev_record
from app.services.scrum_v2_structure import (
    SCRUM_ROLE_DEV,
    get_scrum_role,
    is_scrum_dev_task,
    is_scrum_epic_task,
    is_scrum_story,
    list_all_dev_tasks_for_story,
    list_stories_for_epic,
)

ScrumCascadeMode = Literal[
    "all",
    "none",
    "cancel_backlog_then_sprint",
    "cascade_backlog",
]

STORY_TO_DEV_STATE: dict[str, str] = {
    "pendiente": "to_do",
    "en_progreso": "in_progress",
    "completado": "completed",
    "cancelado": "cancel",
}

EPIC_TO_STORY_STATE: dict[str, str] = {
    "abierta": "en_progreso",
    "cerrada": "completado",
}

STORY_KANBAN_STATES = frozenset({
    "pendiente",
    "en_progreso",
    "completado",
    "cancelado",
    "uat",
    "esperando_liberacion_pm",
    "esperando_validacion_cliente",
    "planificado",
})

STORY_BACKLOG_STATES = frozenset({"product_backlog", "planificado"})
STORY_CANCEL_STATE = "cancelado"
DEV_CANCEL_STATE = "cancel"

# Estados de historia que implican compromiso en un sprint (no PB).
STORY_SPRINT_BOARD_STATES = frozenset({
    "pendiente",
    "en_progreso",
    "completado",
    "cancelado",
    "uat",
    "esperando_liberacion_pm",
    "esperando_validacion_cliente",
})


def _dev_parent_key(record: ProjectRecord) -> str:
    data = record.data if isinstance(record.data, dict) else {}
    return str(data.get("parent_task_id") or "")


def list_scrum_direct_subtasks(
    db: Session,
    project_id: uuid.UUID,
    parent_dev_id: uuid.UUID,
) -> list[ProjectRecord]:
    parent_key = str(parent_dev_id)
    from sqlalchemy import select

    rows = list(
        db.scalars(
            select(ProjectRecord).where(
                ProjectRecord.project_id == project_id,
                ProjectRecord.record_type == "task",
            )
        )
    )
    return [
        r
        for r in rows
        if get_scrum_role(r) == SCRUM_ROLE_DEV and _dev_parent_key(r) == parent_key
    ]


def list_scrum_children_for_cascade(
    db: Session,
    project: Project,
    parent: ProjectRecord,
) -> list[ProjectRecord]:
    if is_scrum_epic_task(parent):
        return list_stories_for_epic(db, project.id, parent.id)
    if is_scrum_story(parent):
        return list_all_dev_tasks_for_story(db, project.id, parent.id)
    if is_scrum_dev_task(parent):
        return list_scrum_direct_subtasks(db, project.id, parent.id)
    return []


def map_parent_state_to_child_state(parent: ProjectRecord, parent_state: str) -> str | None:
    if is_scrum_epic_task(parent):
        if parent_state in STORY_KANBAN_STATES:
            return parent_state
        return EPIC_TO_STORY_STATE.get(parent_state)
    if is_scrum_story(parent):
        return STORY_TO_DEV_STATE.get(parent_state)
    if is_scrum_dev_task(parent):
        return parent_state if parent_state in {
            "backlog",
            "to_do",
            "in_progress",
            "ready_for_test",
            "completed",
            "cancel",
        } else STORY_TO_DEV_STATE.get(parent_state, parent_state)
    return None


def child_kind_label(parent: ProjectRecord) -> str:
    if is_scrum_epic_task(parent):
        return "historias"
    if is_scrum_story(parent):
        return "tareas"
    if is_scrum_dev_task(parent):
        return "subtareas"
    return "elementos"


def _cascade_child_label(db: Session, child: ProjectRecord) -> str:
    from app.services.workflow.engine import workflow_state_label

    titulo = child.titulo or str(child.id)
    estado = child.estado or ""
    estado_label = workflow_state_label(
        db, child.project_id, child.record_type, estado
    )
    return f"{titulo} · {estado_label}"


def _is_child_at_target(child: ProjectRecord, target_state: str) -> bool:
    return child.estado == target_state


def is_scrum_child_in_product_backlog(db: Session, child: ProjectRecord) -> bool:
    from app.services.scrum_effort import get_product_backlog_record

    if is_scrum_story(child):
        if child.estado in STORY_BACKLOG_STATES:
            return True
        backlog = get_product_backlog_record(db, child.project_id)
        return backlog is not None and child.parent_id == backlog.id
    if is_scrum_dev_task(child):
        project = db.get(Project, child.project_id)
        if project is None:
            return False
        story = resolve_story_for_dev_record(db, child, project)
        return is_scrum_child_in_product_backlog(db, story)
    return False


def _incomplete_children(
    db: Session,
    project: Project,
    parent: ProjectRecord,
    *,
    target_state: str,
) -> list[ProjectRecord]:
    child_target = map_parent_state_to_child_state(parent, target_state)
    if child_target is None:
        return []
    children = list_scrum_children_for_cascade(db, project, parent)
    return [c for c in children if not _is_child_at_target(c, child_target)]


def count_incomplete_scrum_children(
    db: Session,
    project: Project,
    parent: ProjectRecord,
    *,
    target_state: str,
) -> tuple[int, list[str]]:
    incomplete = _incomplete_children(db, project, parent, target_state=target_state)
    labels = [c.titulo or str(c.id) for c in incomplete[:5]]
    return len(incomplete), labels


def _cancel_state_for(child: ProjectRecord) -> str:
    if is_scrum_story(child) or is_scrum_epic_task(child):
        return STORY_CANCEL_STATE
    return DEV_CANCEL_STATE


def cancel_scrum_records(
    db: Session,
    project: Project,
    records: list[ProjectRecord],
    *,
    actor_user_id: uuid.UUID,
) -> int:
    changed = 0
    for record in records:
        if is_scrum_story(record):
            devs = list_all_dev_tasks_for_story(db, project.id, record.id)
            changed += cancel_scrum_records(
                db, project, devs, actor_user_id=actor_user_id
            )
        elif is_scrum_dev_task(record) and list_scrum_direct_subtasks(db, project.id, record.id):
            changed += cancel_scrum_records(
                db,
                project,
                list_scrum_direct_subtasks(db, project.id, record.id),
                actor_user_id=actor_user_id,
            )

        cancel_state = _cancel_state_for(record)
        if record.estado == cancel_state:
            continue
        anterior = record.estado
        update_record_fields(db, record, estado=cancel_state)
        record_audit_log(
            db,
            project_id=project.id,
            user_id=actor_user_id,
            entidad_tipo="tarea",
            entidad_id=record.id,
            accion="estado_changed",
            campo="estado",
            valor_anterior=anterior,
            valor_nuevo=f"{cancel_state} (cancel_backlog_cascade)",
        )
        changed += 1
    return changed


def cascade_scrum_children_to_state(
    db: Session,
    project: Project,
    parent: ProjectRecord,
    *,
    target_state: str,
    actor_user_id: uuid.UUID,
    backlog_filter: Literal["all", "backlog_only", "sprint_only"] = "all",
    sprint_id: uuid.UUID | None = None,
) -> int:
    """Mueve hijos al estado equivalente del padre. Devuelve cantidad actualizada."""
    child_target = map_parent_state_to_child_state(parent, target_state)
    if child_target is None:
        return 0

    children = list_scrum_children_for_cascade(db, project, parent)
    changed = 0

    for child in children:
        in_backlog = is_scrum_child_in_product_backlog(db, child)
        if backlog_filter == "backlog_only" and not in_backlog:
            continue
        if backlog_filter == "sprint_only" and in_backlog:
            continue

        if is_scrum_story(child):
            _maybe_commit_backlog_story_to_sprint(
                db,
                project,
                child,
                child_target=child_target,
                sprint_id=sprint_id,
            )
            changed += cascade_scrum_children_to_state(
                db,
                project,
                child,
                target_state=child_target,
                actor_user_id=actor_user_id,
                backlog_filter=backlog_filter,
                sprint_id=sprint_id,
            )
        elif is_scrum_dev_task(child) and list_scrum_direct_subtasks(db, project.id, child.id):
            changed += cascade_scrum_children_to_state(
                db,
                project,
                child,
                target_state=child_target,
                actor_user_id=actor_user_id,
                backlog_filter=backlog_filter,
                sprint_id=sprint_id,
            )

        if _is_child_at_target(child, child_target):
            continue

        anterior = child.estado
        update_record_fields(db, child, estado=child_target)
        record_audit_log(
            db,
            project_id=project.id,
            user_id=actor_user_id,
            entidad_tipo="tarea",
            entidad_id=child.id,
            accion="estado_changed",
            campo="estado",
            valor_anterior=anterior,
            valor_nuevo=f"{child_target} (cascade_padre)",
        )
        changed += 1

    return changed


def apply_scrum_parent_cascade(
    db: Session,
    project: Project,
    parent: ProjectRecord,
    *,
    target_state: str,
    actor_user_id: uuid.UUID,
    mode: ScrumCascadeMode = "all",
    side_effect_context: dict[str, Any] | None = None,
) -> int:
    if mode == "none":
        return 0

    sprint_id = resolve_cascade_sprint_id(db, project, parent, side_effect_context)

    if mode == "cancel_backlog_then_sprint":
        incomplete = _incomplete_children(
            db, project, parent, target_state=target_state
        )
        backlog = [c for c in incomplete if is_scrum_child_in_product_backlog(db, c)]
        changed = cancel_scrum_records(
            db, project, backlog, actor_user_id=actor_user_id
        )
        changed += cascade_scrum_children_to_state(
            db,
            project,
            parent,
            target_state=target_state,
            actor_user_id=actor_user_id,
            backlog_filter="sprint_only",
            sprint_id=sprint_id,
        )
        return changed

    if mode == "cascade_backlog":
        return cascade_scrum_children_to_state(
            db,
            project,
            parent,
            target_state=target_state,
            actor_user_id=actor_user_id,
            backlog_filter="backlog_only",
            sprint_id=sprint_id,
        )

    return cascade_scrum_children_to_state(
        db,
        project,
        parent,
        target_state=target_state,
        actor_user_id=actor_user_id,
        backlog_filter="all",
        sprint_id=sprint_id,
    )


def resolve_cascade_target_state(
    parent: ProjectRecord,
    *,
    target_state: str,
    cascade_target_state: str | None = None,
) -> str:
    """Estado usado para mapear cascade padre→hijos (puede ser estado de historia)."""
    if cascade_target_state and is_scrum_epic_task(parent):
        return cascade_target_state
    return target_state


def resolve_cascade_sprint_id(
    db: Session,
    project: Project,
    parent: ProjectRecord,
    side_effect_context: dict[str, Any] | None,
) -> uuid.UUID | None:
    """Sprint destino para comprometer historias del PB durante cascade de épica."""
    ctx = side_effect_context or {}
    raw = ctx.get("sprint_id")
    if raw is not None:
        try:
            sprint_id = uuid.UUID(str(raw))
        except (TypeError, ValueError):
            sprint_id = None
        else:
            sprint = db.get(ProjectRecord, sprint_id)
            if (
                sprint is not None
                and sprint.project_id == project.id
            ):
                from app.services.scrum_v2_structure import is_sprint_record

                if is_sprint_record(sprint):
                    return sprint_id

    if not is_scrum_epic_task(parent):
        return None

    from app.services.records.repository import list_records
    from app.services.scrum_effort import get_scrum_item_sprint_id
    from app.services.scrum_v2_structure import is_sprint_record, list_stories_for_epic

    for story in list_stories_for_epic(db, project.id, parent.id):
        sid = get_scrum_item_sprint_id(db, story)
        if sid is not None:
            return sid

    sprints = list_records(db, project.id, entity_type="sprint")
    legacy = [
        r
        for r in list_records(db, project.id, entity_type="milestone")
        if is_sprint_record(r)
    ]
    candidates = sprints + legacy
    active = next((s for s in candidates if s.estado == "en_progreso"), None)
    if active is not None:
        return active.id
    return candidates[0].id if candidates else None


def _story_cascade_needs_sprint_commit(child_target: str, in_backlog: bool) -> bool:
    if not in_backlog:
        return False
    if child_target in STORY_BACKLOG_STATES:
        return False
    if child_target in {"cancelado", "completado"}:
        return False
    return child_target in STORY_SPRINT_BOARD_STATES


def _maybe_commit_backlog_story_to_sprint(
    db: Session,
    project: Project,
    story: ProjectRecord,
    *,
    child_target: str,
    sprint_id: uuid.UUID | None,
) -> None:
    if sprint_id is None:
        return
    if not is_scrum_story(story):
        return
    if not _story_cascade_needs_sprint_commit(
        child_target, is_scrum_child_in_product_backlog(db, story)
    ):
        return
    from app.services.scrum_v2_structure import reparent_scrum_story_to_sprint

    reparent_scrum_story_to_sprint(db, project, story, sprint_id)


def scrum_parent_supports_cascade(parent: ProjectRecord) -> bool:
    return is_scrum_epic_task(parent) or is_scrum_story(parent) or (
        is_scrum_dev_task(parent)
    )


def build_cascade_preview(
    db: Session,
    project: Project,
    parent: ProjectRecord,
    *,
    target_state: str,
) -> dict[str, Any]:
    incomplete = _incomplete_children(
        db, project, parent, target_state=target_state
    )
    backlog_incomplete = [
        c for c in incomplete if is_scrum_child_in_product_backlog(db, c)
    ]
    sprint_incomplete = [
        c for c in incomplete if not is_scrum_child_in_product_backlog(db, c)
    ]
    child_target = map_parent_state_to_child_state(parent, target_state)
    labels = [_cascade_child_label(db, c) for c in incomplete[:5]]
    backlog_labels = [_cascade_child_label(db, c) for c in backlog_incomplete[:5]]
    sprint_labels = [_cascade_child_label(db, c) for c in sprint_incomplete[:5]]
    count = len(incomplete)
    backlog_count = len(backlog_incomplete)
    sprint_count = len(sprint_incomplete)
    return {
        "incomplete_count": count,
        "backlog_incomplete_count": backlog_count,
        "sprint_incomplete_count": sprint_count,
        "child_kind": child_kind_label(parent),
        "target_state": target_state,
        "child_target_state": child_target,
        "child_labels": labels,
        "backlog_child_labels": backlog_labels,
        "sprint_child_labels": sprint_labels,
        "has_backlog_children": backlog_count > 0,
        "has_sprint_children": sprint_count > 0,
        "requires_confirmation": count > 0,
    }
