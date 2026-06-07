from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1 import features as features_routes
from app.api.v1.deps import get_milestone_or_404, get_project_or_404
from app.database import get_db
from app.models.entities import Milestone, User
from app.schemas.milestones import (
    MilestoneActionRequest,
    MilestoneCreate,
    MilestoneRead,
    MilestoneUpdate,
)
from app.services.access import assert_member_has_role, assert_project_active
from app.services.deletions import delete_milestone
from app.services.milestones import cancel_milestone_cascade, update_milestone

router = APIRouter(tags=["milestones"])
router.include_router(features_routes.router)


@router.get("/{project_id}/milestones", response_model=list[MilestoneRead])
def list_milestones(project_id: UUID, db: Session = Depends(get_db)):
    get_project_or_404(project_id, db)
    stmt = (
        select(Milestone)
        .where(Milestone.project_id == project_id)
        .order_by(Milestone.orden.asc(), Milestone.created_at.asc())
    )
    return list(db.scalars(stmt))


@router.post("/{project_id}/milestones", response_model=MilestoneRead, status_code=201)
def create_milestone(
    project_id: UUID, payload: MilestoneCreate, db: Session = Depends(get_db)
):
    project = get_project_or_404(project_id, db)
    assert_project_active(project)
    creator = db.get(User, payload.created_by)
    if not creator:
        raise HTTPException(status_code=404, detail="Usuario creador no encontrado")
    assert_member_has_role(db, project_id, payload.created_by, "pm")

    milestone = Milestone(project_id=project_id, **payload.model_dump())
    db.add(milestone)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="No se pudo crear el milestone (conflicto de integridad)",
        )
    db.refresh(milestone)
    return milestone


@router.get("/{project_id}/milestones/{milestone_id}", response_model=MilestoneRead)
def get_milestone(
    project_id: UUID, milestone_id: UUID, db: Session = Depends(get_db)
):
    return get_milestone_or_404(project_id, milestone_id, db)


@router.patch(
    "/{project_id}/milestones/{milestone_id}",
    response_model=MilestoneRead,
)
def patch_milestone(
    project_id: UUID,
    milestone_id: UUID,
    payload: MilestoneUpdate,
    db: Session = Depends(get_db),
):
    milestone = get_milestone_or_404(project_id, milestone_id, db)
    project = get_project_or_404(project_id, db)
    actor = db.get(User, payload.actor_user_id)
    if not actor:
        raise HTTPException(status_code=404, detail="Usuario actor no encontrado")

    update_milestone(db, milestone, project, payload)
    db.commit()
    db.refresh(milestone)
    return milestone


@router.post(
    "/{project_id}/milestones/{milestone_id}/actions",
    response_model=MilestoneRead,
)
def perform_milestone_action(
    project_id: UUID,
    milestone_id: UUID,
    payload: MilestoneActionRequest,
    db: Session = Depends(get_db),
):
    milestone = get_milestone_or_404(project_id, milestone_id, db)
    project = get_project_or_404(project_id, db)

    actor = db.get(User, payload.actor_user_id)
    if not actor:
        raise HTTPException(status_code=404, detail="Usuario actor no encontrado")

    if payload.action == "cancelar":
        cancel_milestone_cascade(
            db,
            milestone,
            project,
            actor_user_id=payload.actor_user_id,
        )
    else:
        raise HTTPException(status_code=400, detail="Acción no reconocida")

    db.commit()
    db.refresh(milestone)
    return milestone


@router.delete(
    "/{project_id}/milestones/{milestone_id}",
    status_code=204,
)
def remove_milestone(
    project_id: UUID,
    milestone_id: UUID,
    actor_user_id: UUID,
    db: Session = Depends(get_db),
):
    milestone = get_milestone_or_404(project_id, milestone_id, db)
    project = get_project_or_404(project_id, db)
    actor = db.get(User, actor_user_id)
    if not actor:
        raise HTTPException(status_code=404, detail="Usuario actor no encontrado")

    delete_milestone(
        db, milestone, project, actor_user_id=actor_user_id
    )
    db.commit()
