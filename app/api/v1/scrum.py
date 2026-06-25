"""Endpoint de workspace Scrum — kanban y sprint board."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_actor_id
from app.api.v1.projects import get_project_or_404
from app.database import get_db
from app.schemas.records import RecordResponse
from app.services.access import require_project_member
from app.services.scrum.workspace import build_scrum_workspace

router = APIRouter()


class ActiveSprintSummary(BaseModel):
    id: str
    title: str
    status: str
    goal: str | None = None


class ScrumWorkspaceResponse(BaseModel):
    active_sprint: ActiveSprintSummary | None = None
    sprint_id: str | None = None
    epics: list[RecordResponse]
    stories: list[RecordResponse]
    dev_tasks: list[RecordResponse]
    subtasks: list[RecordResponse]


@router.get("/{project_id}/scrum/workspace", response_model=ScrumWorkspaceResponse)
def get_scrum_workspace(
    project_id: str,
    sprint_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_current_actor_id),
):
    get_project_or_404(db, project_id)
    require_project_member(db, actor_id, project_id)
    data: dict[str, Any] = build_scrum_workspace(db, project_id, sprint_id)
    return ScrumWorkspaceResponse(**data)
