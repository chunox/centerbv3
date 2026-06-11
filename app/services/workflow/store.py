"""Lectura de workflows y workbenches almacenados por proyecto."""
from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.workbenches import DEFAULT_WORKBENCHES
from app.domain.workflow_templates import workflow_for_project_tipo
from app.models.entities import (
    Project,
    ProjectWorkbenchDefinition,
    ProjectWorkflowDefinition,
)


def _parse_json(raw: str) -> dict[str, Any] | list[Any]:
    return json.loads(raw)


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
    return _parse_json(row.definition)  # type: ignore[return-value]


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
        return list(DEFAULT_WORKBENCHES)
    return list(_parse_json(row.definition))  # type: ignore[arg-type]


def ensure_project_defaults(db: Session, project: Project) -> None:
    """Crea roles sistema, workflows y workbenches si faltan (idempotente)."""
    from app.services.project_roles import seed_default_project_access

    existing = db.scalar(
        select(ProjectWorkflowDefinition.id)
        .where(ProjectWorkflowDefinition.project_id == project.id)
        .limit(1)
    )
    if existing is not None:
        return
    seed_default_project_access(db, project)
