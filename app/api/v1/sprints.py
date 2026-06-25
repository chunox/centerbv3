"""
Sprints — operaciones específicas sobre ProjectRecords de tipo 'sprint'.

Modelo de datos:
- Sprint es un ProjectRecord con record_type="sprint"
- Las historias en sprint tienen parent_id = sprint.id
- Las historias en backlog tienen parent_id = epic.id
- Epic es un ProjectRecord con extra.scrum_role="epic"
- Story es un ProjectRecord con extra.scrum_role="story"
"""
from datetime import date, datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_actor_id
from app.api.v1.projects import get_project_or_404
from app.database import get_db
from app.models.entities import ProjectRecord
from app.schemas.records import RecordResponse
from app.services.access import require_capability, require_project_member
from app.services.audit import write_audit
from app.services.records.store import _load_query, _to_response
from app.services.workflow.engine import apply_transition
from app.services.workflow.side_effects import resolve_incomplete_sprint_stories, restore_story_to_backlog

router = APIRouter()

DONE_STATES = {"done", "cancelled"}


def _get_sprint_or_404(db: Session, project_id: str, sprint_id: str) -> ProjectRecord:
    sprint = db.query(ProjectRecord).filter(
        ProjectRecord.id == sprint_id,
        ProjectRecord.project_id == project_id,
        ProjectRecord.record_type == "sprint",
    ).first()
    if not sprint:
        raise HTTPException(status_code=404, detail="Sprint no encontrado")
    return sprint


class SprintResponse(BaseModel):
    id: str
    project_id: str
    title: str
    status: str
    orden: int
    fecha_inicio: str | None
    fecha_fin: str | None
    goal: str | None
    is_active: bool
    story_count: int
    stories_done: int
    created_at: str


def _sprint_to_response(sprint: ProjectRecord, db: Session) -> SprintResponse:
    stories = db.query(ProjectRecord).filter(
        ProjectRecord.parent_id == sprint.id,
        ProjectRecord.project_id == sprint.project_id,
    ).all()
    return SprintResponse(
        id=sprint.id,
        project_id=sprint.project_id,
        title=sprint.title,
        status=sprint.status,
        orden=sprint.orden,
        fecha_inicio=str(sprint.fecha_inicio) if sprint.fecha_inicio else None,
        fecha_fin=str(sprint.fecha_fin) if sprint.fecha_fin else None,
        goal=(sprint.extra or {}).get("goal"),
        is_active=sprint.status == "activo",
        story_count=len(stories),
        stories_done=sum(1 for s in stories if s.status in DONE_STATES),
        created_at=sprint.created_at.isoformat(),
    )


@router.get("/{project_id}/sprints", response_model=list[SprintResponse])
def list_sprints(
    project_id: str,
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_current_actor_id),
):
    get_project_or_404(db, project_id)
    require_project_member(db, actor_id, project_id)
    sprints = (
        db.query(ProjectRecord)
        .filter(
            ProjectRecord.project_id == project_id,
            ProjectRecord.record_type == "sprint",
        )
        .order_by(ProjectRecord.orden)
        .all()
    )
    return [_sprint_to_response(s, db) for s in sprints]


@router.get("/{project_id}/sprints/active", response_model=SprintResponse | None)
def get_active_sprint(
    project_id: str,
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_current_actor_id),
):
    get_project_or_404(db, project_id)
    require_project_member(db, actor_id, project_id)
    sprint = db.query(ProjectRecord).filter(
        ProjectRecord.project_id == project_id,
        ProjectRecord.record_type == "sprint",
        ProjectRecord.status == "activo",
    ).first()
    if not sprint:
        return None
    return _sprint_to_response(sprint, db)


@router.post("/{project_id}/sprints/{sprint_id}/activate", response_model=SprintResponse)
def activate_sprint(
    project_id: str,
    sprint_id: str,
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_current_actor_id),
):
    get_project_or_404(db, project_id)
    ctx = require_project_member(db, actor_id, project_id)
    require_capability(ctx, "sprint.transition.activar")
    project = get_project_or_404(db, project_id)
    sprint = _get_sprint_or_404(db, project_id, sprint_id)
    if sprint.status == "activo":
        raise HTTPException(status_code=409, detail="El sprint ya está activo")

    # Solo un sprint activo a la vez — cerrar otros vía workflow
    other_active = db.query(ProjectRecord).filter(
        ProjectRecord.project_id == project_id,
        ProjectRecord.record_type == "sprint",
        ProjectRecord.status == "activo",
        ProjectRecord.id != sprint_id,
    ).all()
    for other in other_active:
        apply_transition(db, project, other, "cerrar", actor_id, ctx)

    apply_transition(db, project, sprint, "activar", actor_id, ctx)
    sprint.extra = {**(sprint.extra or {}), "activated_at": datetime.now(timezone.utc).isoformat()}
    write_audit(
        db, project=project, actor_id=actor_id,
        entity_type="sprint", entity_id=sprint.id, action="activated",
        changes={"status": "activo"},
    )
    db.commit()
    db.refresh(sprint)
    return _sprint_to_response(sprint, db)


class CreateSprintBody(BaseModel):
    title: str
    fecha_inicio: date | None = None
    fecha_fin: date | None = None
    goal: str | None = None


class UpdateSprintBody(BaseModel):
    title: str | None = None
    goal: str | None = None
    fecha_fin: date | None = None


@router.post("/{project_id}/sprints", response_model=SprintResponse, status_code=status.HTTP_201_CREATED)
def create_sprint(
    project_id: str,
    body: CreateSprintBody,
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_current_actor_id),
):
    project = get_project_or_404(db, project_id)
    ctx = require_project_member(db, actor_id, project_id)
    require_capability(ctx, "sprint.create")
    count = db.query(ProjectRecord).filter(
        ProjectRecord.project_id == project_id,
        ProjectRecord.record_type == "sprint",
    ).count()
    sprint = ProjectRecord(
        project_id=project_id,
        record_type="sprint",
        title=body.title,
        status="pendiente",
        orden=count,
        fecha_inicio=body.fecha_inicio,
        fecha_fin=body.fecha_fin,
        extra={"goal": body.goal} if body.goal else {},
        created_by=actor_id,
    )
    db.add(sprint)
    db.flush()
    write_audit(
        db, project=project, actor_id=actor_id,
        entity_type="sprint", entity_id=sprint.id, action="created",
        changes={"title": sprint.title},
    )
    db.commit()
    db.refresh(sprint)
    return _sprint_to_response(sprint, db)


@router.patch("/{project_id}/sprints/{sprint_id}", response_model=SprintResponse)
def update_sprint(
    project_id: str,
    sprint_id: str,
    body: UpdateSprintBody,
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_current_actor_id),
):
    get_project_or_404(db, project_id)
    ctx = require_project_member(db, actor_id, project_id)
    require_capability(ctx, "sprint.create")
    sprint = _get_sprint_or_404(db, project_id, sprint_id)
    if body.title is not None:
        sprint.title = body.title
    if body.fecha_fin is not None:
        sprint.fecha_fin = body.fecha_fin
    if body.goal is not None:
        sprint.extra = {**(sprint.extra or {}), "goal": body.goal}
    db.commit()
    db.refresh(sprint)
    return _sprint_to_response(sprint, db)


class StoryResolution(BaseModel):
    story_id: str
    action: Literal["backlog", "next_sprint", "complete", "cancel", "keep"]


class CloseSprintBody(BaseModel):
    incomplete_action: Literal["backlog", "cancel", "keep"] = "backlog"
    resolutions: list[StoryResolution] = []  # per-story overrides


@router.post("/{project_id}/sprints/{sprint_id}/close", response_model=SprintResponse)
def close_sprint(
    project_id: str,
    sprint_id: str,
    body: CloseSprintBody,
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_current_actor_id),
):
    """
    Cierra el sprint activo. incomplete_action:
    - backlog: devolver historias incompletas al epic (parent_id = epic_id en extra)
    - cancel: marcar incompletas como canceladas
    - keep: dejarlas en el sprint (mover manualmente)
    """
    get_project_or_404(db, project_id)
    ctx = require_project_member(db, actor_id, project_id)
    require_capability(ctx, "sprint.transition.cerrar")
    project = get_project_or_404(db, project_id)
    sprint = _get_sprint_or_404(db, project_id, sprint_id)
    if sprint.status != "activo":
        raise HTTPException(status_code=409, detail="Solo se puede cerrar un sprint activo")

    resolution_map = {r.story_id: r.action for r in body.resolutions}

    resolve_incomplete_sprint_stories(
        db, sprint, project_id,
        default_action=body.incomplete_action,
        resolution_map=resolution_map,
    )

    apply_transition(db, project, sprint, "cerrar", actor_id, ctx)
    sprint.extra = {**(sprint.extra or {}), "closed_at": datetime.now(timezone.utc).isoformat()}
    write_audit(
        db, project=project, actor_id=actor_id,
        entity_type="sprint", entity_id=sprint.id, action="closed",
        changes={"status": "cerrado", "incomplete_action": body.incomplete_action},
    )
    db.commit()
    db.refresh(sprint)
    return _sprint_to_response(sprint, db)


@router.get("/{project_id}/sprints/{sprint_id}/stories", response_model=list[RecordResponse])
def list_sprint_stories(
    project_id: str,
    sprint_id: str,
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_current_actor_id),
):
    """Historias asignadas a este sprint (parent_id = sprint_id)."""
    get_project_or_404(db, project_id)
    require_project_member(db, actor_id, project_id)
    _get_sprint_or_404(db, project_id, sprint_id)
    stories = (
        _load_query(db, project_id)
        .filter(ProjectRecord.parent_id == sprint_id)
        .order_by(ProjectRecord.orden)
        .all()
    )
    return [_to_response(db, s) for s in stories]


class AssignSprintBody(BaseModel):
    story_ids: list[str]
    sprint_id: str | None  # None = quitar del sprint


@router.post("/{project_id}/sprints/assign-stories", status_code=status.HTTP_204_NO_CONTENT)
def assign_stories_to_sprint(
    project_id: str,
    body: AssignSprintBody,
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_current_actor_id),
):
    """
    Asigna historias al sprint: cambia parent_id y guarda el parent original en extra.
    Desasignar (sprint_id=None): restaura el parent original.
    """
    project = get_project_or_404(db, project_id)
    ctx = require_project_member(db, actor_id, project_id)
    if body.sprint_id:
        require_capability(ctx, "record.story.transition.comprometer")
    else:
        require_capability(ctx, "record.story.transition.devolver")
    if body.sprint_id:
        _get_sprint_or_404(db, project_id, body.sprint_id)

    stories = db.query(ProjectRecord).filter(
        ProjectRecord.id.in_(body.story_ids),
        ProjectRecord.project_id == project_id,
    ).all()

    for story in stories:
        if body.sprint_id:
            # Guardar parent original y mover al sprint
            if story.parent_id != body.sprint_id:
                extra = {**(story.extra or {}), "original_parent_id": story.parent_id}
                story.extra = extra
                story.parent_id = body.sprint_id
                story.status = "to_do"
        else:
            restore_story_to_backlog(story)

    write_audit(
        db, project=project, actor_id=actor_id,
        entity_type="sprint", entity_id=body.sprint_id or "",
        action="stories_assigned",
        changes={"story_ids": body.story_ids, "sprint_id": body.sprint_id},
    )
    db.commit()
