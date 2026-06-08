from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.entities import (
    Comment,
    Feature,
    FeatureQuery,
    FeatureReport,
    Task,
)
from app.schemas.comments import CommentCreate, CommentRead, EntidadTipo
from app.services.access import assert_member_of_project
from app.services.comments import create_comment as create_comment_service

router = APIRouter(prefix="/comments", tags=["comments"])

_ENTITY_GETTERS: dict[EntidadTipo, type] = {
    "feature": Feature,
    "tarea": Task,
    "feature_query": FeatureQuery,
    "feature_report": FeatureReport,
}


def _project_id_for_entidad(
    entidad_tipo: EntidadTipo, entidad_id: UUID, db: Session
) -> UUID:
    model = _ENTITY_GETTERS[entidad_tipo]
    row = db.get(model, entidad_id)
    if not row:
        raise HTTPException(
            status_code=404,
            detail=f"No existe {entidad_tipo} con id {entidad_id}",
        )
    if entidad_tipo == "feature":
        return row.project_id
    if entidad_tipo == "tarea":
        return row.project_id
    feature = db.get(Feature, row.feature_id)
    if not feature:
        raise HTTPException(status_code=404, detail="Feature no encontrada")
    return feature.project_id


def _ensure_entidad_exists(entidad_tipo: EntidadTipo, entidad_id: UUID, db: Session) -> UUID:
    return _project_id_for_entidad(entidad_tipo, entidad_id, db)


@router.get("", response_model=list[CommentRead])
def list_comments(
    entidad_tipo: EntidadTipo = Query(...),
    entidad_id: UUID = Query(...),
    viewer_user_id: UUID | None = Query(default=None),
    db: Session = Depends(get_db),
):
    project_id = _ensure_entidad_exists(entidad_tipo, entidad_id, db)
    if viewer_user_id is not None:
        assert_member_of_project(db, project_id, viewer_user_id)
    stmt = (
        select(Comment)
        .where(
            Comment.entidad_tipo == entidad_tipo,
            Comment.entidad_id == entidad_id,
        )
        .order_by(Comment.created_at.asc())
    )
    return list(db.scalars(stmt))


@router.post("", response_model=CommentRead, status_code=201)
def create_comment(payload: CommentCreate, db: Session = Depends(get_db)):
    _ensure_entidad_exists(payload.entidad_tipo, payload.entidad_id, db)
    comment = create_comment_service(db, payload)
    db.commit()
    db.refresh(comment)
    return comment
