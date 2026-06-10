"""Resolución de categorías y metadatos de estado desde workflows por proyecto."""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.workflow_templates import workflow_for_project_tipo
from app.models.entities import Project, ProjectWorkflowDefinition
from app.services.workflow.store import WORKFLOW_ENTITY_TYPES, get_active_workflow


def resolve_workflow(
    db: Session,
    project_id: UUID,
    entity_type: str,
    project_tipo: str,
) -> dict[str, Any]:
    wf = get_active_workflow(db, project_id, entity_type)
    if wf is not None:
        return wf
    return workflow_for_project_tipo(project_tipo, entity_type)


def state_keys_in_categories(
    workflow: dict[str, Any],
    categories: frozenset[str] | set[str],
) -> frozenset[str]:
    states = workflow.get("states", [])
    return frozenset(
        s["key"]
        for s in states
        if isinstance(s, dict) and s.get("category") in categories
    )


def state_category(workflow: dict[str, Any], state_key: str) -> str | None:
    for s in workflow.get("states", []):
        if isinstance(s, dict) and s.get("key") == state_key:
            return s.get("category")
    return None


def state_meta(workflow: dict[str, Any], state_key: str) -> dict[str, str]:
    for s in workflow.get("states", []):
        if isinstance(s, dict) and s.get("key") == state_key:
            return {
                "label": str(s.get("label", state_key)),
                "badge": str(s.get("badge", "info")),
            }
    return {"label": state_key, "badge": "info"}


def is_terminal_state(workflow: dict[str, Any], state_key: str) -> bool:
    terminal = workflow.get("terminal_states") or []
    if state_key in terminal:
        return True
    return state_category(workflow, state_key) == "terminal"


def batch_load_workflows(
    db: Session,
    projects: list[Project],
) -> dict[tuple[UUID, str], dict[str, Any]]:
    if not projects:
        return {}

    project_ids = [p.id for p in projects]
    tipo_by_id = {p.id: p.tipo for p in projects}

    rows = list(
        db.scalars(
            select(ProjectWorkflowDefinition)
            .where(
                ProjectWorkflowDefinition.project_id.in_(project_ids),
                ProjectWorkflowDefinition.entity_type.in_(WORKFLOW_ENTITY_TYPES),
                ProjectWorkflowDefinition.is_active.is_(True),
            )
            .order_by(
                ProjectWorkflowDefinition.project_id,
                ProjectWorkflowDefinition.entity_type,
                ProjectWorkflowDefinition.version.desc(),
            )
        )
    )

    seen: set[tuple[UUID, str]] = set()
    result: dict[tuple[UUID, str], dict[str, Any]] = {}

    for row in rows:
        key = (row.project_id, row.entity_type)
        if key in seen:
            continue
        seen.add(key)
        result[key] = json.loads(row.definition)

    for project in projects:
        for entity_type in WORKFLOW_ENTITY_TYPES:
            key = (project.id, entity_type)
            if key not in result:
                result[key] = workflow_for_project_tipo(project.tipo, entity_type)

    return result
