"""Lectura de workflows y workbenches almacenados por proyecto."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.workbenches import DEFAULT_WORKBENCHES, DEPRECATED_WORKBENCH_KEYS
from app.domain.workflow_templates import workflow_for_project_tipo
from app.models.entities import (
    Project,
    ProjectWorkbenchDefinition,
    ProjectWorkflowDefinition,
)


def _parse_json(raw: dict | list | None) -> dict[str, Any] | list[Any]:
    return raw if raw is not None else {}


WORKFLOW_ENTITY_TYPES = ("feature", "task", "query", "report", "milestone")


def _active_workflow_row(
    db: Session, project_id: uuid.UUID, entity_type: str
) -> ProjectWorkflowDefinition | None:
    return db.scalar(
        select(ProjectWorkflowDefinition)
        .where(
            ProjectWorkflowDefinition.project_id == project_id,
            ProjectWorkflowDefinition.entity_type == entity_type,
            ProjectWorkflowDefinition.is_active.is_(True),
        )
        .order_by(ProjectWorkflowDefinition.version.desc())
        .limit(1)
    )


def get_active_workflow(
    db: Session, project_id: uuid.UUID, entity_type: str
) -> dict[str, Any] | None:
    row = _active_workflow_row(db, project_id, entity_type)
    if row is None:
        return None
    wf = _parse_json(row.definition)  # type: ignore[assignment]
    if entity_type == "task" and isinstance(wf, dict):
        from app.services.workflow.engine import normalize_task_workflow_moves

        return normalize_task_workflow_moves(wf)
    return wf  # type: ignore[return-value]


def get_active_workflow_version(
    db: Session, project_id: uuid.UUID, entity_type: str
) -> int | None:
    row = _active_workflow_row(db, project_id, entity_type)
    return row.version if row is not None else None


def workflow_entity_types(db: Session, project_id: uuid.UUID) -> list[str]:
    from app.services.records.registry import registry

    types = registry.workflow_entity_types_for_project(db, project_id)
    if types:
        return types
    rows = db.scalars(
        select(ProjectWorkflowDefinition.entity_type)
        .where(
            ProjectWorkflowDefinition.project_id == project_id,
            ProjectWorkflowDefinition.is_active.is_(True),
        )
        .distinct()
    ).all()
    if rows:
        return list(rows)
    return list(WORKFLOW_ENTITY_TYPES)


def get_all_active_workflows(db: Session, project_id: uuid.UUID) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for entity_type in workflow_entity_types(db, project_id):
        wf = get_active_workflow(db, project_id, entity_type)
        if wf:
            result[entity_type] = wf
    return result


def get_workbenches(db: Session, project_id: uuid.UUID) -> list[dict[str, Any]]:
    row = db.scalar(
        select(ProjectWorkbenchDefinition).where(
            ProjectWorkbenchDefinition.project_id == project_id
        )
    )
    if row is None:
        stored: list[dict[str, Any]] = []
    else:
        stored = list(_parse_json(row.definition))  # type: ignore[arg-type]
    return merge_default_workbenches(stored)


ADMIN_NAV_KEYS = frozenset({"studio", "settings"})


def merge_default_workbenches(stored: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Agrega workbenches sistema faltantes (p. ej. Studio) sin pisar personalizaciones."""
    stored = [wb for wb in stored if wb.get("key") not in DEPRECATED_WORKBENCH_KEYS]
    by_key = {wb["key"]: wb for wb in stored}
    merged = list(stored)
    for default in DEFAULT_WORKBENCHES:
        if default["key"] not in by_key:
            merged.append(dict(default))
    return sorted(merged, key=lambda w: w.get("orden", 0))


def admin_views_from_defaults(existing_keys: set[str]) -> list[dict[str, Any]]:
    """Vistas admin sintéticas para proyectos cuyo pack no las declaró."""
    extra: list[dict[str, Any]] = []
    for wb in DEFAULT_WORKBENCHES:
        key = wb["key"]
        if key not in ADMIN_NAV_KEYS or key in existing_keys:
            continue
        extra.append(
            {
                "key": key,
                "label": wb["label"],
                "route": wb["route"],
                "icon": wb.get("icon", "circle"),
                "section": wb.get("section", "admin"),
                "layout": {"blocks": [{"project_block_key": key, "width": "full"}]},
                "required_capabilities": wb.get("required_capabilities", []),
                "orden": wb.get("orden", 0),
            }
        )
    return extra


def ensure_project_defaults(db: Session, project: Project) -> None:
    """Crea roles sistema, workflows y workbenches si faltan (idempotente)."""
    from app.services.packs import seed_project_from_pack

    existing = db.scalar(
        select(ProjectWorkflowDefinition.id)
        .where(ProjectWorkflowDefinition.project_id == project.id)
        .limit(1)
    )
    if existing is not None:
        return
    seed_project_from_pack(
        db,
        project,
        project.pack_slug or "software",
        template_slug=project.template_slug,
    )
