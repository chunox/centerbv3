from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.auth_deps import get_current_actor_id
from app.api.v1.deps import get_project_or_404
from app.database import get_db
from app.schemas.timeline import ProjectTimelineRead
from app.services.timeline import build_project_timeline

router = APIRouter(tags=["timeline"])


@router.get("/{project_id}/timeline", response_model=ProjectTimelineRead)
def get_project_timeline(
    project_id: UUID,
    milestone_id: UUID | None = Query(default=None),
    feature_id: UUID | None = Query(default=None),
    incluir_eventos: bool = Query(default=True),
    incluir_plan: bool = Query(default=True),
    eventos_limit: int = Query(default=200, ge=1, le=500),
    eventos_offset: int = Query(default=0, ge=0),
    actor_user_id: UUID = Depends(get_current_actor_id),
    db: Session = Depends(get_db),
):
    """Timeline unificado: eventos (audit + comentarios) y plan (hitos + features)."""
    get_project_or_404(project_id, db)
    return build_project_timeline(
        db,
        project_id,
        milestone_id=milestone_id,
        feature_id=feature_id,
        incluir_eventos=incluir_eventos,
        incluir_plan=incluir_plan,
        eventos_limit=eventos_limit,
        eventos_offset=eventos_offset,
        viewer_user_id=actor_user_id,
    )
