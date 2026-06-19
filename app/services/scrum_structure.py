"""Estructura Scrum — delegación v2 task-first + compat legacy."""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.domain.project_templates import SCRUM_TEMPLATE_SLUGS
from app.domain.project_mode import is_scrum_template  # re-export
from app.services.scrum_v2_structure import (
    apply_scrum_v2_structure,
    list_epic_tasks,
    list_stories_for_sprint,
    list_stories_in_backlog,
)

__all__ = [
    "SCRUM_TEMPLATE_SLUGS",
    "apply_scrum_v2_structure",
    "apply_scrum_structure",
    "is_scrum_template",
    "list_features_for_sprint",
    "list_stories_for_sprint",
    "list_stories_in_backlog",
    "list_epic_tasks",
]


def apply_scrum_structure(db, project) -> None:
    """Alias: aplica Scrum v2 task-first."""
    apply_scrum_v2_structure(db, project)


def list_features_for_sprint(
    db: Session,
    project_id: uuid.UUID,
    sprint_id: uuid.UUID,
) -> list[ProjectRecord]:
    """Compat API: historias del sprint (story tasks en v2)."""
    return list_stories_for_sprint(db, project_id, sprint_id)
