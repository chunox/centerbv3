from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.v1.deps import get_project_or_404
from app.database import get_db
from app.models.entities import User
from app.schemas.jobs import MilestoneSyncJobRequest, MilestoneSyncJobResponse
from app.domain.capabilities import SCOPE_MILESTONE_EDIT
from app.services.milestones import sync_all_milestone_states
from app.services.workflow.authorize import assert_capability

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("/milestones/sync-states", response_model=MilestoneSyncJobResponse)
def run_milestone_sync_job(
    payload: MilestoneSyncJobRequest,
    db: Session = Depends(get_db),
):
    """Recalcula estados de hitos (plazos bug §4.4). Invocable por cron o PM."""
    actor = db.get(User, payload.actor_user_id)
    if not actor:
        raise HTTPException(status_code=404, detail="Usuario actor no encontrado")

    if payload.project_id is not None:
        project = get_project_or_404(payload.project_id, db)
        assert_capability(
            db, project.id, payload.actor_user_id, SCOPE_MILESTONE_EDIT
        )

    updated = sync_all_milestone_states(
        db,
        actor_user_id=payload.actor_user_id,
        project_id=payload.project_id,
    )
    db.commit()
    return MilestoneSyncJobResponse(milestones_updated=updated)
