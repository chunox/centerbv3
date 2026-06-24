"""
Activity log — feed cronológico de eventos del proyecto.
GET /projects/{id}/activity?page=&per_page=&entity_type=&entity_id=

Lee de AuditLog. Si el proyecto no tiene actividad registrada aún,
devuelve lista vacía (no es un error).
"""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_actor_id
from app.api.v1.projects import get_project_or_404
from app.database import get_db
from app.models.entities import AuditLog
from app.services.access import require_project_member

router = APIRouter()


# ─── Schemas ──────────────────────────────────────────────────────────────────

class ActivityEntryResponse(BaseModel):
    id: str
    actor_id: str
    entity_type: str
    entity_id: str
    action: str
    changes: dict
    created_at: str


def _to_response(log: AuditLog) -> ActivityEntryResponse:
    return ActivityEntryResponse(
        id=log.id,
        actor_id=log.actor_id,
        entity_type=log.entity_type,
        entity_id=log.entity_id,
        action=log.action,
        changes=log.changes or {},
        created_at=log.created_at.isoformat(),
    )


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/{project_id}/activity", response_model=dict)
def list_project_activity(
    project_id: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(30, ge=1, le=100),
    entity_type: str | None = Query(None),
    entity_id: str | None = Query(None),
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_current_actor_id),
):
    get_project_or_404(db, project_id)
    require_project_member(db, actor_id, project_id)

    q = db.query(AuditLog).filter(AuditLog.project_id == str(project_id))
    if entity_type:
        q = q.filter(AuditLog.entity_type == entity_type)
    if entity_id:
        q = q.filter(AuditLog.entity_id == str(entity_id))

    total = q.count()
    logs = q.order_by(AuditLog.created_at.desc()).offset((page - 1) * per_page).limit(per_page).all()

    return {
        "items": [_to_response(log) for log in logs],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": max(1, (total + per_page - 1) // per_page),
    }
