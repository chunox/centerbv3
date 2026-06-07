from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1 import feature_queries as feature_queries_routes
from app.api.v1 import feature_reports as feature_reports_routes
from app.api.v1 import tasks as tasks_routes
from app.api.v1.deps import get_feature_or_404, get_milestone_or_404, get_project_or_404
from app.database import get_db
from app.models.entities import Feature, User
from app.schemas.features import (
    FeatureActionRequest,
    FeatureCreate,
    FeatureMigrateRequest,
    FeatureRead,
    FeatureUpdate,
    UatGateRead,
)
from app.services.access import assert_member_has_role, assert_project_active
from app.services.feature_create import (
    after_feature_created,
    validate_and_prepare_feature_create,
)
from app.services.features import (
    apply_feature_action,
    ensure_default_task,
    load_active_tasks,
    migrate_feature,
    uat_gate_status,
    update_feature,
)

router = APIRouter(tags=["features"])
router.include_router(tasks_routes.router)
router.include_router(feature_reports_routes.router)
router.include_router(feature_queries_routes.router)


@router.get(
    "/{project_id}/milestones/{milestone_id}/features",
    response_model=list[FeatureRead],
)
def list_features(
    project_id: UUID, milestone_id: UUID, db: Session = Depends(get_db)
):
    get_milestone_or_404(project_id, milestone_id, db)
    stmt = (
        select(Feature)
        .where(Feature.milestone_id == milestone_id)
        .order_by(Feature.created_at.asc())
    )
    return list(db.scalars(stmt))


@router.post(
    "/{project_id}/milestones/{milestone_id}/features",
    response_model=FeatureRead,
    status_code=201,
)
def create_feature(
    project_id: UUID,
    milestone_id: UUID,
    payload: FeatureCreate,
    db: Session = Depends(get_db),
):
    milestone = get_milestone_or_404(project_id, milestone_id, db)
    project = get_project_or_404(project_id, db)
    creator = db.get(User, payload.created_by)
    if not creator:
        raise HTTPException(status_code=404, detail="Usuario creador no encontrado")
    assert_project_active(project)
    assert_member_has_role(db, project.id, payload.created_by, "pm")

    validate_and_prepare_feature_create(db, project, milestone, payload)

    feature = Feature(
        milestone_id=milestone_id,
        project_id=milestone.project_id,
        **payload.model_dump(),
    )
    db.add(feature)
    try:
        db.flush()
        ensure_default_task(db, feature, created_by=payload.created_by)
        after_feature_created(
            db,
            project,
            milestone,
            feature,
            payload,
            actor_user_id=payload.created_by,
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=422,
            detail="Datos inválidos (revisa fechas o duracion_estimada para tipo mejora)",
        )
    db.refresh(feature)
    return feature


@router.get(
    "/{project_id}/milestones/{milestone_id}/features/{feature_id}",
    response_model=FeatureRead,
)
def get_feature(
    project_id: UUID,
    milestone_id: UUID,
    feature_id: UUID,
    db: Session = Depends(get_db),
):
    return get_feature_or_404(project_id, milestone_id, feature_id, db)


@router.patch(
    "/{project_id}/milestones/{milestone_id}/features/{feature_id}",
    response_model=FeatureRead,
)
def patch_feature(
    project_id: UUID,
    milestone_id: UUID,
    feature_id: UUID,
    payload: FeatureUpdate,
    db: Session = Depends(get_db),
):
    feature = get_feature_or_404(project_id, milestone_id, feature_id, db)
    project = get_project_or_404(project_id, db)
    actor = db.get(User, payload.actor_user_id)
    if not actor:
        raise HTTPException(status_code=404, detail="Usuario actor no encontrado")

    update_feature(db, feature, project, payload)
    db.commit()
    db.refresh(feature)
    return feature


@router.post(
    "/{project_id}/milestones/{milestone_id}/features/{feature_id}/migrate",
    response_model=FeatureRead,
)
def migrate_feature_to_milestone(
    project_id: UUID,
    milestone_id: UUID,
    feature_id: UUID,
    payload: FeatureMigrateRequest,
    db: Session = Depends(get_db),
):
    feature = get_feature_or_404(project_id, milestone_id, feature_id, db)
    project = get_project_or_404(project_id, db)
    source_milestone = get_milestone_or_404(project_id, milestone_id, db)
    target_milestone = get_milestone_or_404(
        project_id, payload.target_milestone_id, db
    )

    actor = db.get(User, payload.actor_user_id)
    if not actor:
        raise HTTPException(status_code=404, detail="Usuario actor no encontrado")

    migrate_feature(
        db,
        feature,
        project,
        source_milestone,
        target_milestone,
        actor_user_id=payload.actor_user_id,
    )
    db.commit()
    db.refresh(feature)
    return feature


@router.get(
    "/{project_id}/milestones/{milestone_id}/features/{feature_id}/uat-gate",
    response_model=UatGateRead,
)
def get_uat_gate(
    project_id: UUID,
    milestone_id: UUID,
    feature_id: UUID,
    db: Session = Depends(get_db),
):
    feature = get_feature_or_404(project_id, milestone_id, feature_id, db)
    tasks = load_active_tasks(db, feature.id)
    return UatGateRead(**uat_gate_status(feature, tasks))


@router.post(
    "/{project_id}/milestones/{milestone_id}/features/{feature_id}/actions",
    response_model=FeatureRead,
)
def perform_feature_action(
    project_id: UUID,
    milestone_id: UUID,
    feature_id: UUID,
    payload: FeatureActionRequest,
    db: Session = Depends(get_db),
):
    feature = get_feature_or_404(project_id, milestone_id, feature_id, db)
    project = get_project_or_404(project_id, db)

    actor = db.get(User, payload.actor_user_id)
    if not actor:
        raise HTTPException(status_code=404, detail="Usuario actor no encontrado")

    apply_feature_action(
        db,
        feature,
        project,
        action=payload.action,
        actor_user_id=payload.actor_user_id,
        actor_rol=payload.actor_rol,
    )
    db.commit()
    db.refresh(feature)
    return feature
