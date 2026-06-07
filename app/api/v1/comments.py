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
from app.services.comments import create_comment as create_comment_service

router = APIRouter(prefix="/comments", tags=["comments"])

_ENTITY_GETTERS: dict[EntidadTipo, type] = {
    "feature": Feature,
    "tarea": Task,
    "feature_query": FeatureQuery,
    "feature_report": FeatureReport,
}


def _ensure_entidad_exists(entidad_tipo: EntidadTipo, entidad_id: UUID, db: Session) -> None:
    model = _ENTITY_GETTERS[entidad_tipo]
    if not db.get(model, entidad_id):
        raise HTTPException(
            status_code=404,
            detail=f"No existe {entidad_tipo} con id {entidad_id}",
        )


@router.get("", response_model=list[CommentRead])
def list_comments(
    entidad_tipo: EntidadTipo = Query(...),
    entidad_id: UUID = Query(...),
    db: Session = Depends(get_db),
):
    _ensure_entidad_exists(entidad_tipo, entidad_id, db)
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


@router.get("/{comment_id}", response_model=CommentRead)
def get_comment(comment_id: UUID, db: Session = Depends(get_db)):
    comment = db.get(Comment, comment_id)
    if not comment:
        raise HTTPException(status_code=404, detail="Comentario no encontrado")
    return comment
