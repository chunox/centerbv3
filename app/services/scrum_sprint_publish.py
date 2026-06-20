"""Publicación del plan de sprint: metadata + activación de historias planificadas."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.domain.records.types import RecordRef
from app.models.entities import Project, ProjectRecord
from app.services.records.repository import update_record_fields
from app.services.scrum_sprint_close import SPRINT_TERMINAL_STATES
from app.services.scrum_v2_structure import (
    SCRUM_STORY_STATE_PLANNED,
    is_scrum_story_planned,
    is_sprint_record,
    list_stories_for_sprint,
)
from app.services.workflow.engine import apply_record_transition


@dataclass(frozen=True)
class PublishSprintResult:
    sprint_id: uuid.UUID
    published_story_ids: list[uuid.UUID]


def publish_scrum_sprint(
    db: Session,
    project: Project,
    sprint: ProjectRecord,
    actor_user_id: uuid.UUID,
    *,
    sprint_goal: str | None = None,
    fecha_inicio: date | None = None,
    fecha_fin: date | None = None,
) -> PublishSprintResult:
    if not is_sprint_record(sprint) or sprint.project_id != project.id:
        raise HTTPException(status_code=404, detail="Sprint no encontrado")
    if sprint.estado in SPRINT_TERMINAL_STATES:
        raise HTTPException(status_code=409, detail="Sprint ya cerrado o cancelado")

    patch: dict[str, object] = {}
    if sprint_goal is not None:
        data = dict(sprint.data or {})
        data["sprint_goal"] = sprint_goal.strip() or None
        patch["data"] = data
    if fecha_inicio is not None:
        patch["fecha_inicio"] = fecha_inicio
    if fecha_fin is not None:
        patch["fecha_fin"] = fecha_fin
    if patch:
        update_record_fields(db, sprint, **patch)

    published: list[uuid.UUID] = []
    for story in list_stories_for_sprint(db, project.id, sprint.id):
        if not is_scrum_story_planned(story):
            continue
        apply_record_transition(
            db,
            project,
            story,
            record_ref=RecordRef(
                id=story.id,
                record_type=story.record_type,
                project_id=project.id,
            ),
            action_id="publicar_sprint",
            actor_user_id=actor_user_id,
        )
        published.append(story.id)

    return PublishSprintResult(
        sprint_id=sprint.id,
        published_story_ids=published,
    )
