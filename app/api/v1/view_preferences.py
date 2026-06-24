"""
View preferences — persistencia de columnas, filtros y agrupación por (usuario × vista × proyecto).
GET /projects/{id}/views/{view_key}/preferences
PUT /projects/{id}/views/{view_key}/preferences
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_actor_id
from app.api.v1.projects import get_project_or_404
from app.database import get_db
from app.models.entities import ProjectViewPreference
from app.services.access import require_project_member

router = APIRouter()


class SortSpec(BaseModel):
    field: str
    direction: str = "asc"  # asc | desc


class ViewPreferencesRequest(BaseModel):
    columns: list[str] | None = None
    filters: dict[str, str | list[str]] | None = None
    group_by: str | None = None
    sort: SortSpec | None = None


class ViewPreferencesResponse(BaseModel):
    view_key: str
    columns: list[str] | None = None
    filters: dict[str, str | list[str]] | None = None
    group_by: str | None = None
    sort: SortSpec | None = None


@router.get("/{project_id}/views/{view_key}/preferences", response_model=ViewPreferencesResponse)
def get_view_preferences(
    project_id: str,
    view_key: str,
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_current_actor_id),
):
    get_project_or_404(db, project_id)
    require_project_member(db, actor_id, project_id)
    pref = db.query(ProjectViewPreference).filter(
        and_(
            ProjectViewPreference.project_id == str(project_id),
            ProjectViewPreference.user_id == actor_id,
            ProjectViewPreference.view_key == view_key,
        )
    ).first()
    if not pref:
        return ViewPreferencesResponse(view_key=view_key)
    prefs = pref.preferences or {}
    return ViewPreferencesResponse(
        view_key=view_key,
        columns=prefs.get("columns"),
        filters=prefs.get("filters"),
        group_by=prefs.get("group_by"),
        sort=prefs.get("sort"),
    )


@router.put("/{project_id}/views/{view_key}/preferences", response_model=ViewPreferencesResponse)
def update_view_preferences(
    project_id: str,
    view_key: str,
    body: ViewPreferencesRequest,
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_current_actor_id),
):
    get_project_or_404(db, project_id)
    require_project_member(db, actor_id, project_id)
    pref = db.query(ProjectViewPreference).filter(
        and_(
            ProjectViewPreference.project_id == str(project_id),
            ProjectViewPreference.user_id == actor_id,
            ProjectViewPreference.view_key == view_key,
        )
    ).first()
    new_prefs: dict = {}
    if body.columns is not None:
        new_prefs["columns"] = body.columns
    if body.filters is not None:
        new_prefs["filters"] = body.filters
    if body.group_by is not None:
        new_prefs["group_by"] = body.group_by
    if body.sort is not None:
        new_prefs["sort"] = body.sort

    if pref:
        pref.preferences = {**(pref.preferences or {}), **new_prefs}
    else:
        pref = ProjectViewPreference(
            project_id=str(project_id),
            user_id=actor_id,
            view_key=view_key,
            preferences=new_prefs,
        )
        db.add(pref)
    db.commit()
    db.refresh(pref)
    prefs = pref.preferences or {}
    return ViewPreferencesResponse(
        view_key=view_key,
        columns=prefs.get("columns"),
        filters=prefs.get("filters"),
        group_by=prefs.get("group_by"),
        sort=prefs.get("sort"),
    )
