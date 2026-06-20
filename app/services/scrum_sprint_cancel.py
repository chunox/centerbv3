"""Cancelación de sprint Scrum: elimina si está vacío; si tiene historias, las cancela o devuelve al backlog."""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.domain.records.types import RecordRef
from app.models.entities import Project, ProjectRecord
from app.services.records.generic_store import delete_record
from app.services.scrum_sprint_close import SPRINT_TERMINAL_STATES
from app.services.scrum_v2_structure import (
    is_sprint_record,
    list_stories_for_sprint,
    reparent_scrum_story_to_backlog,
)
from app.services.workflow.engine import apply_record_transition


@dataclass(frozen=True)
class CancelSprintResult:
    sprint_id: uuid.UUID
    deleted: bool
    estado: str | None
    returned_story_ids: list[uuid.UUID]
    cancelled_story_ids: list[uuid.UUID]


def cancel_scrum_sprint(
    db: Session,
    project: Project,
    sprint: ProjectRecord,
    actor_user_id: uuid.UUID,
    *,
    return_stories_to_backlog: bool = False,
) -> CancelSprintResult:
    if not is_sprint_record(sprint) or sprint.project_id != project.id:
        raise HTTPException(status_code=404, detail="Sprint no encontrado")
    if sprint.estado in SPRINT_TERMINAL_STATES:
        raise HTTPException(status_code=409, detail="Sprint ya cerrado o cancelado")

    stories = list_stories_for_sprint(db, project.id, sprint.id)
    sprint_id = sprint.id

    if not stories:
        delete_record(db, sprint)
        return CancelSprintResult(
            sprint_id=sprint_id,
            deleted=True,
            estado=None,
            returned_story_ids=[],
            cancelled_story_ids=[],
        )

    if return_stories_to_backlog:
        returned: list[uuid.UUID] = []
        for story in stories:
            reparent_scrum_story_to_backlog(db, project, story, actor_user_id)
            returned.append(story.id)
        delete_record(db, sprint)
        return CancelSprintResult(
            sprint_id=sprint_id,
            deleted=True,
            estado=None,
            returned_story_ids=returned,
            cancelled_story_ids=[],
        )

    apply_record_transition(
        db,
        project,
        sprint,
        record_ref=RecordRef(
            id=sprint.id,
            record_type=sprint.record_type,
            project_id=project.id,
        ),
        action_id="cancelar",
        actor_user_id=actor_user_id,
    )
    db.refresh(sprint)

    return CancelSprintResult(
        sprint_id=sprint_id,
        deleted=False,
        estado=sprint.estado,
        returned_story_ids=[],
        cancelled_story_ids=[story.id for story in stories],
    )
