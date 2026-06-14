from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.entities import Comment, ProjectRecord
from app.schemas.comments import CommentCreate, CommentRead, EntidadTipo
from app.services.access import assert_member_of_project, get_project_id_for_comment_entity
from app.services.comments import create_comment as create_comment_service

router = APIRouter(prefix="/comments", tags=["comments"])


def _ensure_entidad_exists(entidad_tipo: EntidadTipo, entidad_id: UUID, db: Session) -> UUID:
    return get_project_id_for_comment_entity(db, entidad_tipo, entidad_id)


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
