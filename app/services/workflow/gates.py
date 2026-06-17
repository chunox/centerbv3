"""Plugins de gates para transiciones de workflow."""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.entities import Project, ProjectRecord
from app.services.project_profile import has_role_slug, pack_supports
from app.services.records.repository import (
    _data,
    list_children,
)
from app.services.workflow.categories import (
    is_task_cancel_state,
    resolve_workflow,
    task_test_state_keys,
)


def _entity_type(entity: Any, entity_type: str) -> str:
    if isinstance(entity, ProjectRecord):
        return entity.record_type
    if hasattr(entity, "record_type"):
        return entity.record_type
    return entity_type


def _is_feature_record(entity: Any) -> bool:
    if isinstance(entity, ProjectRecord):
        return entity.record_type == "feature"
    return _entity_type(entity, "") == "feature"


def _is_report_record(entity: Any) -> bool:
    if isinstance(entity, ProjectRecord):
        return entity.record_type == "report"
    return _entity_type(entity, "") == "report"


def evaluate_gates(
    db: Session,
    *,
    gate_specs: list[dict[str, Any]],
    project: Project,
    entity: Any,
    entity_type: str,
) -> None:
    for spec in gate_specs:
        gate_type = spec.get("type")
        if gate_type == "uat_tasks_complete":
            _gate_uat_tasks_complete(db, entity, entity_type)
        elif gate_type == "all_children_in_state":
            _gate_all_children_in_state(db, entity, spec.get("params") or {})
        elif gate_type == "blocked_by_active_query":
            _gate_blocked_by_active_query(entity)
        elif gate_type == "has_open_children_of_type":
            _gate_has_open_children(db, entity, spec.get("params") or {})
        elif gate_type == "field_equals":
            _gate_field_equals(entity, spec.get("params") or {})
        elif gate_type == "parent_in_state":
            _gate_parent_in_state(db, entity, spec.get("params") or {})
        elif gate_type == "project_active":
            if project.estado != "activo":
                raise HTTPException(
                    status_code=409,
                    detail="El proyecto no está activo",
                )
        elif gate_type == "report_source_feature_complete":
            _gate_report_source_feature_complete(db, entity, entity_type)


def _record_id(entity: Any) -> uuid.UUID:
    if isinstance(entity, ProjectRecord):
        return entity.id
    return entity.id


def _gate_uat_tasks_complete(db: Session, entity: Any, entity_type: str) -> None:
    from app.services.scrum_v2_structure import is_scrum_story, list_dev_tasks_for_story

    fid = _record_id(entity)
    if isinstance(entity, ProjectRecord) and is_scrum_story(entity):
        tasks = list_dev_tasks_for_story(db, entity.project_id, fid)
    elif _is_feature_record(entity):
        tasks = list_children(db, fid, "task")
    else:
        return
    project = db.get(Project, entity.project_id) if hasattr(entity, "project_id") else None
    task_wf = None
    if project is not None:
        task_wf = resolve_workflow(
            db,
            project.id,
            "task",
            "default",
        )
    test_keys = task_test_state_keys(task_wf) if task_wf else task_test_state_keys({})
    active = [t for t in tasks if not is_task_cancel_state(task_wf or {}, t.estado)]
    incomplete = [t for t in active if t.estado not in test_keys]
    if incomplete:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Gate UAT no cumplido",
                "can_pass_to_uat": False,
                "pending_tasks": len(incomplete),
                "total_active": len(active),
            },
        )


def _gate_all_children_in_state(
    db: Session, entity: Any, params: dict[str, Any]
) -> None:
    child_type = params.get("child_entity_type", "task")
    states = set(params.get("states") or ["completed", "cancel"])
    exclude = set(params.get("exclude_states") or [])
    parent_id = _record_id(entity)
    children = list_children(db, parent_id, child_type)
    for child in children:
        if child.estado in exclude:
            continue
        if child.estado not in states:
            raise HTTPException(
                status_code=409,
                detail=f"Hijos {child_type} no están en estados requeridos",
            )


def _gate_blocked_by_active_query(entity: Any) -> None:
    bloqueada = False
    if isinstance(entity, ProjectRecord):
        bloqueada = bool(_data(entity).get("bloqueada", False))
    elif hasattr(entity, "bloqueada"):
        bloqueada = bool(entity.bloqueada)
    if bloqueada:
        raise HTTPException(
            status_code=409,
            detail="La entidad está bloqueada por consultas activas",
        )


def _gate_has_open_children(
    db: Session, entity: Any, params: dict[str, Any]
) -> None:
    child_type = params.get("child_entity_type", "query")
    terminal = set(params.get("terminal_states") or ["cerrada", "rechazada"])
    parent_id = _record_id(entity)
    for child in list_children(db, parent_id, child_type):
        if child.estado not in terminal:
            raise HTTPException(
                status_code=409,
                detail=f"Hay {child_type} activos",
            )


def _gate_field_equals(entity: Any, params: dict[str, Any]) -> None:
    field = params.get("field", "bloqueada")
    expected = params.get("value", True)
    actual = None
    if isinstance(entity, ProjectRecord):
        actual = _data(entity).get(field)
    elif hasattr(entity, field):
        actual = getattr(entity, field)
    if actual != expected:
        raise HTTPException(status_code=409, detail=f"Gate field_equals falló: {field}")


def _gate_parent_in_state(db: Session, entity: Any, params: dict[str, Any]) -> None:
    states = set(params.get("states") or ["completado"])
    parent_id = None
    if isinstance(entity, ProjectRecord):
        parent_id = entity.parent_id
    elif hasattr(entity, "feature_id"):
        parent_id = entity.feature_id
    if parent_id is None:
        raise HTTPException(status_code=409, detail="Sin registro padre")
    parent = db.get(ProjectRecord, parent_id)
    if parent is None or parent.estado not in states:
        raise HTTPException(
            status_code=409,
            detail="El registro padre no está en el estado requerido",
        )


def _gate_report_source_feature_complete(
    db: Session, entity: Any, entity_type: str
) -> None:
    if not _is_report_record(entity):
        return
    feature_id = entity.parent_id if isinstance(entity, ProjectRecord) else entity.feature_id
    source = db.get(ProjectRecord, feature_id) if feature_id else None
    if source is None or source.estado != "completado":
        raise HTTPException(
            status_code=409,
            detail="La feature original debe estar en completado",
        )


def check_transition_conditions(
    db: Session | None,
    project: Project,
    conditions: list[dict[str, Any]] | None,
) -> bool:
    if not conditions:
        return True
    from app.services.project_profile import legacy_tipo_for_project

    for cond in conditions:
        ctype = cond.get("type")
        if ctype == "project_tipo":
            allowed = cond.get("in", [])
            legacy = legacy_tipo_for_project(project)
            if legacy not in allowed and getattr(project, "tipo", None) not in allowed:
                return False
        elif ctype == "has_role":
            if db is None:
                continue
            slug = cond.get("slug") or cond.get("role")
            if not slug:
                return False
            present = has_role_slug(db, project.id, str(slug))
            if cond.get("negate"):
                if present:
                    return False
            elif not present:
                return False
        elif ctype == "pack_trait":
            if db is None:
                continue
            trait = cond.get("trait") or cond.get("slug")
            if not trait or not pack_supports(db, project, str(trait)):
                return False
    return True
