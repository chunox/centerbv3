"""
Bloqueantes — router dedicado para GET /projects/{id}/blockers (vista global).
Los endpoints por record siguen en records.py para mantener la jerarquía de URLs.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_actor_id
from app.api.v1.projects import get_project_or_404
from app.database import get_db
from app.models.entities import ProjectRecordBlocker
from app.schemas.blockers import BlockerResponse
from app.services.access import require_project_member

router = APIRouter()


def _blocker_to_response(b: ProjectRecordBlocker) -> BlockerResponse:
    return BlockerResponse(
        id=b.id,
        record_id=b.record_id,
        project_id=b.project_id,
        description=b.description,
        created_by=b.created_by,
        created_at=b.created_at,
        resolved_at=b.resolved_at,
        resolved_by=b.resolved_by,
        resolution_note=b.resolution_note,
        is_resolved=b.resolved_at is not None,
    )


@router.get("/{project_id}/blockers", response_model=list[BlockerResponse])
def list_project_blockers(
    project_id: str,
    resolved: bool | None = Query(None, description="None=todos, True=resueltos, False=activos"),
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_current_actor_id),
):
    """Lista todos los bloqueantes del proyecto con filtro opcional por estado resuelto."""
    get_project_or_404(db, project_id)
    require_project_member(db, actor_id, project_id)
    q = db.query(ProjectRecordBlocker).filter(
        ProjectRecordBlocker.project_id == str(project_id),
    )
    if resolved is False:
        q = q.filter(ProjectRecordBlocker.resolved_at.is_(None))
    elif resolved is True:
        q = q.filter(ProjectRecordBlocker.resolved_at.isnot(None))
    return [_blocker_to_response(b) for b in q.order_by(ProjectRecordBlocker.created_at).all()]
