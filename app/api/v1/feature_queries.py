from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.api.v1.deps import get_feature_or_404, get_project_or_404
from app.database import get_db
from app.models.entities import Feature, FeatureQuery, ProjectMember, User
from app.schemas.feature_queries import (
    FeatureQueryAction,
    FeatureQueryCreate,
    FeatureQueryInboxRead,
    FeatureQueryRead,
)
from app.services.feature_queries import (
    apply_query_action,
    assert_project_active,
    blocking_states_for_project,
)

router = APIRouter(tags=["feature-queries"])
inbox_router = APIRouter(tags=["feature-queries"])


def _get_query_or_404(
    feature_id: UUID, query_id: UUID, db: Session
) -> FeatureQuery:
    query = db.get(FeatureQuery, query_id)
    if not query or query.feature_id != feature_id:
        raise HTTPException(status_code=404, detail="Consulta no encontrada")
    return query


def _assert_query_creator_role(
    db: Session, project_id: UUID, user_id: UUID
) -> None:
    allowed = db.scalar(
        select(
            exists().where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == user_id,
                ProjectMember.rol.in_(("pm", "dev", "qa")),
            )
        )
    )
    if not allowed:
        raise HTTPException(
            status_code=403,
            detail="Solo PM, Dev o QA pueden crear consultas",
        )


@inbox_router.get("/{project_id}/feature-queries", response_model=list[FeatureQueryInboxRead])
def list_project_feature_queries(
    project_id: UUID,
    estado: str | None = Query(default=None),
    solo_bloqueantes: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    """Bandeja PM / Cliente: consultas del proyecto con contexto de feature."""
    project = get_project_or_404(project_id, db)
    stmt = (
        select(FeatureQuery, Feature)
        .join(Feature, Feature.id == FeatureQuery.feature_id)
        .where(Feature.project_id == project_id)
        .order_by(FeatureQuery.updated_at.desc())
    )
    if estado is not None:
        stmt = stmt.where(FeatureQuery.estado == estado)
    if solo_bloqueantes:
        blocking = blocking_states_for_project(project.tipo)
        stmt = stmt.where(FeatureQuery.estado.in_(blocking))

    rows = db.execute(stmt).all()
    return [
        FeatureQueryInboxRead(
            id=query.id,
            feature_id=query.feature_id,
            titulo=query.titulo,
            descripcion=query.descripcion,
            estado=query.estado,  # type: ignore[arg-type]
            created_by=query.created_by,
            created_at=query.created_at,
            updated_at=query.updated_at,
            project_id=feature.project_id,
            milestone_id=feature.milestone_id,
            feature_nombre=feature.nombre,
        )
        for query, feature in rows
    ]


@router.get(
    "/{project_id}/milestones/{milestone_id}/features/{feature_id}/queries",
    response_model=list[FeatureQueryRead],
)
def list_feature_queries(
    project_id: UUID,
    milestone_id: UUID,
    feature_id: UUID,
    db: Session = Depends(get_db),
):
    get_feature_or_404(project_id, milestone_id, feature_id, db)
    stmt = (
        select(FeatureQuery)
        .where(FeatureQuery.feature_id == feature_id)
        .order_by(FeatureQuery.created_at.desc())
    )
    return list(db.scalars(stmt))


@router.post(
    "/{project_id}/milestones/{milestone_id}/features/{feature_id}/queries",
    response_model=FeatureQueryRead,
    status_code=201,
)
def create_feature_query(
    project_id: UUID,
    milestone_id: UUID,
    feature_id: UUID,
    payload: FeatureQueryCreate,
    db: Session = Depends(get_db),
):
    feature = get_feature_or_404(project_id, milestone_id, feature_id, db)
    project = get_project_or_404(project_id, db)
    assert_project_active(project)

    creator = db.get(User, payload.created_by)
    if not creator:
        raise HTTPException(status_code=404, detail="Usuario creador no encontrado")
    _assert_query_creator_role(db, project_id, payload.created_by)

    query = FeatureQuery(
        feature_id=feature_id,
        titulo=payload.titulo,
        descripcion=payload.descripcion,
        estado="borrador",
        created_by=payload.created_by,
    )
    db.add(query)
    db.commit()
    db.refresh(query)
    return query


@router.get(
    "/{project_id}/milestones/{milestone_id}/features/{feature_id}/queries/{query_id}",
    response_model=FeatureQueryRead,
)
def get_feature_query(
    project_id: UUID,
    milestone_id: UUID,
    feature_id: UUID,
    query_id: UUID,
    db: Session = Depends(get_db),
):
    get_feature_or_404(project_id, milestone_id, feature_id, db)
    return _get_query_or_404(feature_id, query_id, db)


@router.post(
    "/{project_id}/milestones/{milestone_id}/features/{feature_id}/queries/{query_id}/actions",
    response_model=FeatureQueryRead,
)
def perform_query_action(
    project_id: UUID,
    milestone_id: UUID,
    feature_id: UUID,
    query_id: UUID,
    payload: FeatureQueryAction,
    db: Session = Depends(get_db),
):
    feature = get_feature_or_404(project_id, milestone_id, feature_id, db)
    project = get_project_or_404(project_id, db)
    query = _get_query_or_404(feature_id, query_id, db)

    actor = db.get(User, payload.actor_user_id)
    if not actor:
        raise HTTPException(status_code=404, detail="Usuario actor no encontrado")

    apply_query_action(
        db,
        query,
        feature,
        project,
        action=payload.action,
        actor_user_id=payload.actor_user_id,
        actor_rol=payload.actor_rol,
    )
    db.commit()
    db.refresh(query)
    db.refresh(feature)
    return query
