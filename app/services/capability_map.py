"""
Mapeo de operaciones de dominio → capability strings del pack.
Usado por routers y workflow engine para enforcement server-side.
"""
from __future__ import annotations

from typing import Any

# Acciones kanban que comparten la capability "move"
_KANBAN_MOVE_ACTIONS = frozenset({"move_to_todo", "start", "review", "complete"})


def _scrum_entity(extra: dict[str, Any] | None) -> str | None:
    return (extra or {}).get("scrum_role")


def capability_for_record_create(record_type: str, extra: dict[str, Any] | None = None) -> str:
    role = _scrum_entity(extra)
    if role == "epic":
        return "record.epic.create"
    if role == "story":
        return "record.story.create"
    if role == "dev":
        return "record.dev_task.create"
    if role == "subtask":
        return "record.subtask.create"
    if record_type == "sprint":
        return "sprint.create"
    return f"record.{record_type}.create"


def capability_for_record_edit(record: Any) -> str:
    """record: ProjectRecord ORM or similar with record_type + extra."""
    role = _scrum_entity(getattr(record, "extra", None) or {})
    rt = record.record_type
    if role == "epic":
        return "record.epic.edit"
    if role == "story":
        return "record.story.edit"
    if role == "dev":
        return "record.dev_task.edit"
    if role == "subtask":
        return "record.subtask.edit"
    return f"record.{rt}.edit"


def capability_for_record_delete(record: Any) -> str | None:
    role = _scrum_entity(getattr(record, "extra", None) or {})
    rt = record.record_type
    if role == "story":
        return "record.story.delete"
    if role == "epic":
        return "record.epic.delete"
    if rt in ("milestone", "feature"):
        return f"record.{rt}.delete"
    return None


def capability_for_transition(entity_type: str, action_id: str) -> str | None:
    """Resuelve la capability requerida para una transición de workflow."""
    if entity_type == "task":
        if action_id == "cancel":
            return "record.task.transition.cancel"
        if action_id in _KANBAN_MOVE_ACTIONS:
            return "record.task.transition.move"
        return f"record.task.transition.{action_id}"

    if entity_type == "dev_task":
        if action_id == "cancel":
            return "record.dev_task.transition.cancel"
        if action_id == "reabrir":
            return "record.dev_task.transition.reabrir"
        if action_id in _KANBAN_MOVE_ACTIONS:
            return "record.dev_task.transition.move"
        return f"record.dev_task.transition.{action_id}"

    if entity_type == "subtask":
        if action_id == "cancel":
            return "record.subtask.transition.cancel"
        if action_id == "reabrir":
            return "record.subtask.transition.reabrir"
        if action_id in _KANBAN_MOVE_ACTIONS:
            return "record.subtask.transition.move"
        return None

    if entity_type == "epic":
        if action_id == "cancel":
            return "record.epic.transition.cancel"
        if action_id == "reabrir":
            return "record.epic.transition.reabrir"
        if action_id in _KANBAN_MOVE_ACTIONS:
            return "record.epic.transition.move"
        return None

    if entity_type == "story":
        if action_id == "cancelar":
            return "record.story.transition.cancelar"
        if action_id == "reabrir":
            return "record.story.transition.reabrir"
        if action_id in ("comprometer", "iniciar", "revisar", "completar"):
            return f"record.story.transition.{action_id}"
        if action_id == "devolver":
            return "record.story.transition.devolver"
        return f"record.story.transition.{action_id}"

    if entity_type == "sprint":
        return f"sprint.transition.{action_id}"

    return f"record.{entity_type}.transition.{action_id}"
