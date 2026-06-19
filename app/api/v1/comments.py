from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.auth_deps import get_current_actor_id
from app.database import get_db
from app.models.entities import Comment, ProjectRecord
from app.schemas.comments import CommentCreate, CommentRead, EntidadTipo
from app.services.access import assert_member_of_project, get_project_id_for_comment_entity
from app.services.comments import create_comment as create_comment_service

router = APIRouter(prefix="/comments", tags=["comments"])


class _CommentCreateWithUser(CommentCreate):
    user_id: UUID


def _ensure_entidad_exists(entidad_tipo: EntidadTipo, entidad_id: UUID, db: Session) -> UUID:
    return get_project_id_for_comment_entity(db, entidad_tipo, entidad_id)


@router.get("", response_model=list[CommentRead])
def list_comments(
    entidad_tipo: EntidadTipo = Query(...),
    entidad_id: UUID = Query(...),
    actor_user_id: UUID = Depends(get_current_actor_id),
    db: Session = Depends(get_db),
):
    project_id = _ensure_entidad_exists(entidad_tipo, entidad_id, db)
    assert_member_of_project(db, project_id, actor_user_id)
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
def create_comment(
    payload: CommentCreate,
    actor_user_id: UUID = Depends(get_current_actor_id),
    db: Session = Depends(get_db),
):
    _ensure_entidad_exists(payload.entidad_tipo, payload.entidad_id, db)
    internal = _CommentCreateWithUser(**payload.model_dump(), user_id=actor_user_id)
    comment = create_comment_service(db, internal)
    db.commit()
    db.refresh(comment)
    return comment
