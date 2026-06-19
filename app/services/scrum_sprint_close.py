"""Cierre de sprint Scrum con carry-over opcional al siguiente sprint."""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.records.types import RecordRef
from app.models.entities import Project, ProjectRecord
from app.services.scrum_metrics import sync_sprint_horas_completadas
from app.services.scrum_v2_structure import (
    is_scrum_story,
    is_sprint_record,
    list_stories_for_sprint,
    reparent_scrum_story_to_sprint,
)
from app.services.workflow.engine import apply_record_transition

STORY_TERMINAL_STATES = frozenset({"completado", "cancelado"})
SPRINT_TERMINAL_STATES = frozenset({"completado", "cancelado"})


def is_incomplete_scrum_story(story: ProjectRecord) -> bool:
    return is_scrum_story(story) and story.estado not in STORY_TERMINAL_STATES


def list_project_sprints_ordered(
    db: Session, project_id: uuid.UUID
) -> list[ProjectRecord]:
    rows = list(
        db.scalars(
            select(ProjectRecord)
            .where(
                ProjectRecord.project_id == project_id,
                ProjectRecord.record_type.in_(("sprint", "milestone")),
            )
            .order_by(ProjectRecord.orden.asc(), ProjectRecord.created_at.asc())
        )
    )
    return [row for row in rows if is_sprint_record(row)]


def resolve_next_open_sprint(
    db: Session,
    project_id: uuid.UUID,
    current_sprint_id: uuid.UUID,
) -> ProjectRecord | None:
    sprints = list_project_sprints_ordered(db, project_id)
    current_idx = next(
        (idx for idx, sprint in enumerate(sprints) if sprint.id == current_sprint_id),
        -1,
    )
    if current_idx < 0:
        return None
    for sprint in sprints[current_idx + 1 :]:
        if sprint.estado not in SPRINT_TERMINAL_STATES:
            return sprint
    return None


@dataclass(frozen=True)
class CloseSprintResult:
    sprint_id: uuid.UUID
    target_sprint_id: uuid.UUID | None
    carried_over_story_ids: list[uuid.UUID]
    horas_completadas: float


def close_scrum_sprint(
    db: Session,
    project: Project,
    sprint: ProjectRecord,
    actor_user_id: uuid.UUID,
    *,
    carry_over_to_next_sprint: bool = False,
) -> CloseSprintResult:
    if not is_sprint_record(sprint) or sprint.project_id != project.id:
        raise HTTPException(status_code=404, detail="Sprint no encontrado")
    if sprint.estado in SPRINT_TERMINAL_STATES:
        raise HTTPException(status_code=409, detail="Sprint ya cerrado o cancelado")

    target_sprint: ProjectRecord | None = None
    carried_over: list[uuid.UUID] = []

    if carry_over_to_next_sprint:
        target_sprint = resolve_next_open_sprint(db, project.id, sprint.id)
        if target_sprint is None:
            raise HTTPException(
                status_code=400,
                detail="No hay un sprint siguiente disponible para mover historias incompletas",
            )
        for story in list_stories_for_sprint(db, project.id, sprint.id):
            if not is_incomplete_scrum_story(story):
                continue
            reparent_scrum_story_to_sprint(db, project, story, target_sprint.id)
            carried_over.append(story.id)

    apply_record_transition(
        db,
        project,
        sprint,
        record_ref=RecordRef(
            id=sprint.id,
            record_type=sprint.record_type,
            project_id=project.id,
        ),
        action_id="sync",
        actor_user_id=actor_user_id,
        target_state="completado",
    )

    horas = sync_sprint_horas_completadas(db, sprint, commit=False)

    return CloseSprintResult(
        sprint_id=sprint.id,
        target_sprint_id=target_sprint.id if target_sprint is not None else None,
        carried_over_story_ids=carried_over,
        horas_completadas=horas,
    )
