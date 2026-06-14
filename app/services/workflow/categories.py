"""Resolución de categorías y metadatos de estado desde workflows por proyecto."""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.workflow_templates import workflow_for_profile
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
    return workflow_for_profile(project_tipo, entity_type)


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
    cat = state_category(workflow, state_key)
    return cat in ("terminal", "done")


TASK_CATEGORIES = frozenset({"backlog", "todo", "active", "test", "done", "terminal"})

DEFAULT_TEST_KEYS = frozenset({"ready_for_test"})
DEFAULT_DONE_KEYS = frozenset({"completed"})
DEFAULT_CANCEL_KEYS = frozenset({"cancel"})
DEFAULT_BACKLOG_KEYS = frozenset({"backlog"})
DEFAULT_CANCELLABLE_KEYS = frozenset({"backlog", "to_do", "in_progress", "ready_for_test"})
DEFAULT_SATISFIED_PREDECESSOR_KEYS = frozenset({"completed", "cancel"})
DEFAULT_FORWARD_MOVE_KEYS = frozenset({"to_do", "in_progress", "ready_for_test", "completed"})


def _keys_or_fallback(
    workflow: dict[str, Any],
    categories: set[str] | frozenset[str],
    fallback: frozenset[str],
) -> frozenset[str]:
    keys = state_keys_in_categories(workflow, frozenset(categories))
    return keys if keys else fallback


def task_test_state_keys(workflow: dict[str, Any]) -> frozenset[str]:
    return _keys_or_fallback(workflow, {"test"}, DEFAULT_TEST_KEYS)


def task_done_state_keys(workflow: dict[str, Any]) -> frozenset[str]:
    return _keys_or_fallback(workflow, {"done"}, DEFAULT_DONE_KEYS)


def task_cancel_state_keys(workflow: dict[str, Any]) -> frozenset[str]:
    return _keys_or_fallback(workflow, {"terminal"}, DEFAULT_CANCEL_KEYS)


def task_backlog_state_keys(workflow: dict[str, Any]) -> frozenset[str]:
    return _keys_or_fallback(workflow, {"backlog"}, DEFAULT_BACKLOG_KEYS)


def is_task_cancel_state(workflow: dict[str, Any], state_key: str) -> bool:
    return state_key in task_cancel_state_keys(workflow)


def task_cancellable_state_keys(workflow: dict[str, Any]) -> frozenset[str]:
    keys: set[str] = set()
    for s in workflow.get("states", []):
        if not isinstance(s, dict):
            continue
        key = s.get("key")
        if not key or is_terminal_state(workflow, key):
            continue
        keys.add(key)
    return frozenset(keys) if keys else DEFAULT_CANCELLABLE_KEYS


def task_satisfied_predecessor_keys(workflow: dict[str, Any]) -> frozenset[str]:
    return task_done_state_keys(workflow) | task_cancel_state_keys(workflow)


def task_forward_move_keys(workflow: dict[str, Any]) -> frozenset[str]:
    keys: set[str] = set()
    for s in workflow.get("states", []):
        if not isinstance(s, dict):
            continue
        key = s.get("key")
        if not key:
            continue
        if is_terminal_state(workflow, key) and key not in task_done_state_keys(workflow):
            continue
        cat = s.get("category")
        if cat in ("backlog", "todo", "active", "test", "done") or not is_terminal_state(
            workflow, key
        ):
            keys.add(key)
    return frozenset(keys) if keys else DEFAULT_FORWARD_MOVE_KEYS


def validate_task_state_categories(workflow: dict[str, Any]) -> None:
    for s in workflow.get("states", []):
        if not isinstance(s, dict):
            continue
        cat = s.get("category")
        if cat and cat not in TASK_CATEGORIES:
            raise ValueError(f"Categoría de estado inválida: {cat}")


def batch_load_workflows(
    db: Session,
    projects: list[Project],
) -> dict[tuple[UUID, str], dict[str, Any]]:
    if not projects:
        return {}

    project_ids = [p.id for p in projects]
    profile_by_id = {
        p.id: getattr(p, "profile_slug", None) or "default" for p in projects
    }

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
            if key not in result and project.pack_slug == "software":
                result[key] = workflow_for_profile(
                    profile_by_id[project.id], entity_type
                )

    return result
